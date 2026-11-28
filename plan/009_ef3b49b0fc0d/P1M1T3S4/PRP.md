# PRP — P1.M1.T3.S4: Reserve one native owner and fence its startup

## Goal

**Feature Goal**: Give the daemon ONE internal, connection-bound **native owner reservation** — created
atomically with its busy check, bound to the recorder-host's lifetime, capped at 30 s total — and a
**startup fence** so that (a) no generic/context/other-native start, toggle or cancel can supersede,
join, or queue behind it, (b) the mic opens only when the reservation is still the current, un-expired,
un-tombstoned owner, and (c) every termination tombstones the owner token *before* a late load/prime
result could ever arm. Pure stdlib; no socket route is exposed (P1.M1.T4.S7 activates it).

**Deliverable** (1 module created, 1 module edited, 1 test file created):
1. `voice_typing/editor_session.py` — **NEW**: `Stage`, `Owner`, `EndRecord`, `NativeReserveResult`,
   `NativeReservation` (pure, lock-free state transitions run under the daemon's `_lock`, injected
   clock, `END_REASONS` re-exported from S2).
2. `voice_typing/daemon.py` — **EDIT** (append-only in spirit; no existing line deleted except the
   three return statements that now return their outcome): native fields in `__init__`; the hooks
   `reserve_native`, `begin_native_start`, `begin_native_drain`, `terminate_native`; the busy predicate
   `_native_blockers_locked` / `_native_owner_live_locked`; the fence `_native_can_commit_locked`
   called from `_start_fenced` (new kwarg `native_tok`) at BOTH its reserve block and its atomic commit
   block; `_native_start_worker` (the session's lifecycle thread); busy arbitration in `start`,
   `toggle`, `cancel`, `_dispatch`; termination hooks in `stop`, `_request_stop`, `_maybe_auto_stop`,
   `_disarm`, `_handle_dead_host`, `request_shutdown`, `shutdown`. Mode A docstrings on each.
3. `tests/test_editor_session.py` — **NEW**, hermetic: fake clock + manual timers + Event-barrier
   hosts; 18 tests / ~40 assertions; no sleeps, no socket listener, no CUDA, no `run()`.

**Success Definition**:
- (a) **Atomic check-and-reserve**: `reserve_native` under one `_lock` hold evaluates shutdown → id →
  owner → generic-arm busy in that order and, on rejection, reserves NOTHING (no token, no timer,
  `_arm_seq` untouched, `_native` unchanged). Codes: `busy` | `duplicate_id` | `invalid_request`.
- (b) **Symmetric busy, no queue**: while a native owner is live (STARTING/LISTENING/DRAINING),
  `start()`, `toggle()` (arm side), `start_with_seed()`, `start_context()` return
  `ArmOutcome(reason="busy")`; `_dispatch("toggle"/"start…")` replies `{"ok":false,"busy":true,…}`;
  `cancel()` replies busy and performs no backspace/host cancel; a second `reserve_native` is `busy`.
- (c) **Fenced commit**: `_start_fenced(..., native_tok=T)` commits (opens the mic) only if
  `_native_can_commit_locked(T)`; the STARTING→LISTENING transition happens in the SAME `_lock` hold
  as `_arm()` (asserted from inside the fake recorder's `set_microphone(True)`); the Start-cap timer
  is retired at commit.
- (d) **30 s total cap, enforced twice**: the watchdog timer at `owner.deadline` ends the reservation
  (`timeout`, cause `start-cap`); a worker reaching the commit block after the deadline ends it THERE
  and aborts — the mic never opens, the host is left idle-resident, an installed seed is cleaned up by
  the existing `_abort_start`. Exactly one `EndRecord` is delivered.
- (e) **Stop/status/quit usable**: `status_snapshot()` and `stop()` return within 1 s while the worker
  is blocked inside `spawn`; `stop()` during STARTING ends the reservation (`stopped`, cause
  `stop-during-start`) without opening capture; during LISTENING it is the emergency graceful stop.
- (f) **Off-lock, exactly-once end delivery**: the `on_end` callback is invoked once per owner, never
  under `_lock` (a callback that calls `status_snapshot()` does not deadlock), even under a 3-way race
  of stop + timer + transport loss; a raising callback is swallowed (type name only).
- (g) Scope: `git diff --name-only` ⊆ {`voice_typing/editor_session.py`, `voice_typing/daemon.py`,
  `tests/test_editor_session.py`}; new suite green; `tests/test_daemon.py` FAILED-name set-diff vs
  `tests/G1_BASELINE.md` shows no NEW failures; `tests/test_control_socket.py` + `tests/test_voicectl.py`
  green.

## User Persona

**Target User**: implementers of P1.M1.T4.S4 (route native finals before generic output), T4.S5
(stop/cancel/drain — consumes `begin_native_drain` and the parked lifecycle thread), T4.S6 (`ended`
frame + private failure hints — consumes `EndRecord` via `on_end`), T4.S7 (socket activation — calls
`reserve_native` → emits `starting` → `begin_native_start`; maps `on_loss` to `terminate_native`).
**Use Case**: an editor sends `editor-start`; the daemon may spend up to 30 s cold-loading models.
During that window the user presses the global hotkey (`toggle`), another editor tries to start, the
first editor vanishes (EOF), or the user runs `voicectl stop`. Today a plain `toggle` would SUPERSEDE
the in-flight arm (`_arm_seq` bump) and steal the mic; a late load would re-arm after a stop.
**Pain Points Addressed**: stolen mic mid-start; a stopped session that arms seconds later; a
cancelled start whose seed leaks into the next session; `status`/`stop` wedged behind a cold load.

## Why

- **PRD §4.8.1 B is normative** (prd_snapshot.md ~448-472): "Every successful native Start reserves an
  exclusive connection-owned session; status/stop/quit remain available, but all other start/toggle/
  cancel attempts (including legacy ones) return busy while the native reservation exists. Native Start
  likewise returns busy if **any** other arm is loading, listening, or draining. … A start rejected as
  busy never queues for later." "Reject an id already active or retained." "Cap Start (including model
  load/priming) at 30 s … The daemon must be able to service EOF/stop/lost/heartbeat during cold load;
  a cancelled reservation cannot resume/arm when the worker returns. Check reservation before opening
  capture."
- **architecture/system_context.md** "Confirmed seed before capture": "`_load_host` shares the resident
  recorder, releases `_lock` before `RecorderHost.spawn` … Make the reservation/arm decision under
  `_lock` but wait for load and prompt confirmation outside it. Treat the 30-second native cap as a
  total start deadline; a late worker may leave a safely idle resident host, never re-arm it."
  "Control/recorder boundaries": "`editor_session.py` owns reservation/ordered delivery state … Keep
  status/stop/quit responsive while the owner starts … Recheck reservation on commit/end/mic commands
  and retain ownership through cleanup/drain. … Reader/lease/ACK/worker can race; make revocation
  sticky before any subsequent offer or arm commit."
- **Inputs (landed)**: T2.S3's `_start_fenced` reserve→load→prime→atomic-commit seam
  (daemon.py:2631) — the native commit hook slots into its existing revalidate expression; T2.S5's
  `reject_busy` convention (`_arming | _loading | _listening | _drain`) is the busy predicate reused
  here; S2's `is_uuid_v4`, `END_REASONS`, `native_error_reply`; S3's `START_CAP_S`, `ThreadTimers`,
  `LossCause`, `remaining` (on disk at editor_protocol.py:397/464/413).
- **Scope discipline.** No `editor-start` socket routing (T4.S7), no offer FIFO/ACK (T4.S2), no drain
  budget policy (T4.S5), no `ended` frame construction or status hints (T4.S6), no recorder-identity
  work (T4.S3), no recovery store (T4.S1). `status_snapshot()` is unchanged.

## What

A native reservation is a daemon-side object installed under `_lock` by `reserve_native(conn,
session_id, on_end=…)`. It mints a monotonic owner **token** (the fence), records the client's UUIDv4,
arms a 30 s watchdog, and stays STARTING until the worker — spawned by `begin_native_start(token,
seed, streaming)` — carries the token through `_start_fenced`, whose commit block revalidates the
token and transitions STARTING→LISTENING atomically with `_arm()`. Every generic arm entry is made
busy while the owner is live. Termination (`stop` during start, cap expiry, transport loss via
T4.S7, host death, shutdown, disarm) tombstones the token under `_lock` and delivers one
`EndRecord` off-lock; a worker that returns late finds a tombstoned token and aborts.

### Success Criteria

- [ ] `editor_session.py` exports `Stage`, `Owner`, `EndRecord`, `NativeReserveResult`,
      `NativeReservation`, `END_REASONS`; imports only `enum`, `dataclasses`, `threading` (one
      `Event` per reservation) and `editor_protocol`; no daemon import, no I/O.
- [ ] `reserve_native` is atomic and ordered (shutdown → duplicate_id → owner busy → generic busy);
      rejections reserve nothing; acceptance arms exactly one timer at `created_at + 30`.
- [ ] `_start_fenced(native_tok=T)` commits only into its own live, un-expired STARTING reservation;
      generic arms return `busy` (nothing reserved) while a native owner is live.
- [ ] `start()`/`toggle()` return their `ArmOutcome`; `_dispatch` maps `busy` to a busy reply;
      `cancel()` returns busy without side effects.
- [ ] 30 s cap: timer fire → `timeout`; late commit → `timeout` + abort, mic never opens, host idle.
- [ ] `stop()` during STARTING → `stopped`/`stop-during-start`, no capture; during LISTENING →
      `stopped` after `_disarm`; `_maybe_auto_stop` → `idle`; host death → `load_failed`/`disconnected`
      + `host-died`; `request_shutdown` → `shutdown`.
- [ ] `on_end` exactly once, off-lock, per owner; raising callbacks swallowed.
- [ ] No seed/request text in any `EndRecord`, log line or reply (caplog assertion).
- [ ] Validation gates (below) all pass; diff ⊆ the three files.

## All Needed Context

### Context Completeness Check

_Pass._ The new module is given verbatim; every daemon edit has an exact anchor (method + line at HEAD
`6fd5309`) and code; the upstream contracts (T2.S3 seam, T2.S5 busy convention, S2/S3 symbols on disk)
are quoted with line numbers; the test harness (fake clock, manual timers, gated host factory, control
server construction) is given verbatim; the two-timeout discipline is spelled out. Pure stdlib.

### Documentation & References

```yaml
# THIS ITEM'S RESEARCH — read first
- docfile: plan/009_ef3b49b0fc0d/P1M1T3S4/research/native_reservation_design.md
  why: "§1 seam table with HEAD line numbers; §3 decisions D1–D10 (two modules, atomic reserve, token
        fence, two-phase start, cap enforced twice, off-lock exactly-once delivery, symmetric busy,
        host lifetime, duplicate ids, reason mapping); §5 cross-item notes."
  critical: "D6 — daemon `_lock` is a NON-reentrant threading.Lock (daemon.py:836) and `_disarm` is
            always called under it: end records made there are STASHED and delivered by the parked
            worker; every other terminator delivers on its own thread after releasing the lock."

# THE SPEC — PRD §4.8.1 B
- file: PRD.md
  why: "prd_snapshot.md ~448-472 (native wire v1): exclusive connection-owned reservation; busy for all
        other start/toggle/cancel incl. legacy; native Start busy if any arm loading/listening/draining;
        no queue; reject an id already active or retained; 30 s Start cap; service stop/lost/heartbeat
        during cold load; 'a cancelled reservation cannot resume/arm when the worker returns'; 'Check
        reservation before opening capture'; ended reasons list (stopped, idle, cancelled, target_lost,
        disconnected, timeout, delivery_failed, load_failed, shutdown); 'Shutdown/host failure clean up
        without promising a recoverable drain'."
  critical: "`voicectl stop` is an emergency GRACEFUL stop of the active session (allowed); toggle-off
            is the same action. Only ARM attempts and cancel are busy."

# THE ARCHITECTURE MANDATE
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: "'Confirmed seed before capture' + 'Control/recorder boundaries' + 'Buffer ownership and
        recovery' (quoted in Why). Names editor_session.py as the reservation/ordered-delivery module."
- docfile: plan/009_ef3b49b0fc0d/architecture/verification.md
  why: "T10b: 'Production ControlServer on temporary private socket, fake host/feedback/backend,
        deterministic events/barriers plus injected monotonic clock … busy races through all ownership
        phases, responsive status/stop/quit, phase order, deadlines'. This task's test discipline."

# THE UPSTREAM CONTRACTS (landed / parallel — treat as given)
- file: voice_typing/daemon.py
  why: ":247 _START_DEADLINE_S=30.0; :252 ArmOutcome(.ok,.reason,…); :836 `self._lock =
        threading.Lock()`; :847 _shutdown; :921 `_drain: bool`; :975-976 `_arm_seq`/`_arming`; :981
        `_stop_seq`; :1098 `_load_host` (sets `_loading` under _lock, `host.spawn()` OUTSIDE, may
        block); :1327 `_handle_dead_host`; :1759 `_arm`; :1839 `_disarm` (under _lock; clears
        _listening, set_microphone(False), _duck_release); :1958 `_request_stop`; :2263 `cancel`;
        :2367 `_maybe_auto_stop` (`with self._lock: self._disarm()` ~:2388); :2631 `_start_fenced`;
        :2752 `_abort_start`; :2799 `start_with_seed`; ~:2808 `start_context` (reject_busy=True);
        :2866/:2881/:2886 start/stop/toggle; :2907 request_shutdown; :3069 status_snapshot;
        :3196 shutdown; :3360 ControlServer(daemon, socket_path=None, on_quit=None); :3507 `_handle`;
        :3591 `_dispatch`; :137 `from voice_typing.editor_protocol import (` — the import list to extend."
  pattern: "T2.S5's reject_busy block in _start_fenced is the busy convention to reuse verbatim:
            `self._arming is not None or self._loading or self._listening.is_set() or self._drain`."
  gotcha: "`_start_fenced` RETURNS from inside its `with self._lock:` commit block. The only thing the
            commit hook may do there besides the transition is `Timer.cancel()` (a flag set — no wait,
            I/O or callback). Anything else must be deferred to the worker after the call returns."
- file: voice_typing/editor_protocol.py
  why: "S2 (landed): `is_uuid_v4` :170, `END_REASONS`, `NATIVE_ERROR_CODES` :143, `native_error_reply`.
        S3 (parallel, on disk): `START_CAP_S = 30.0` :397, `LossCause` :413, `ThreadTimers(clock)` with
        `.arm(deadline, fire) -> handle` / `.cancel(handle)` :464, `remaining(deadline, now=None)`."
  gotcha: "`ThreadTimers.arm` starts a daemon `threading.Timer`; `cancel` is `handle.cancel()`. A timer
            fire can be LATE — every timer callback re-checks the clock under _lock (mirrors S3's
            generation discipline)."
- docfile: plan/009_ef3b49b0fc0d/P1M1T3S3/PRP.md
  why: "The pump T4.S7 will construct: `OwnerPump(conn, session_id, *, on_command, on_loss, reader,
        clock, timers, …)`; `on_loss(cause: LossCause, detail)` exactly once off-lock after
        `SHUT_RDWR`; `send_event` non-blocking; `write_reject(conn, code)`. It does NOT decide
        busy/duplicate_id — 'reservation busy/duplicate_id stay in T3.S4/T4.S7'. That is this task."
  gotcha: "Do not construct an OwnerPump here. T4.S7's sequence is: `res = d.reserve_native(conn, id,
        on_end=…)`; rejected → `write_reject(conn, res.error)`; else `pump.send_event({'event':
        'starting','id':id})` (PumpClosed → `d.terminate_native('disconnected', cause=exc.cause.value,
        token=res.owner.token)`), then `d.begin_native_start(res.owner.token, seed=ctx or None)`."

# THE TEST CONVENTIONS TO MIRROR
- file: tests/test_daemon.py
  why: ":904 `_make_daemon(*, recorder=None, recorder_host=None, host_factory=None, backend=None,
        cfg=None) -> (d, fb, rec, be)` (hermetic cfg, fake feedback, `_ok_probe`); :887
        `_fake_host_factory(spawn_result=True, device=None)`; :783 `_FakeHost` (wraps a `_StubRecorder`;
        `set_microphone(on)` proxies to `self.recorder.set_microphone`; `spawn(timeout=180.0)`);
        `_wait_for(pred)`; :5955-5978 a host fake whose `prime_prompt(text, *, timeout)` records calls
        and can gate; barrier style `started/release = threading.Event()` (:1286-1287)."
  gotcha: "Importing across test files: pytest's default `prepend` import mode puts `tests/` on sys.path
          — `import test_daemon as td` works; add `sys.path.insert(0, str(Path(__file__).parent))`
          first as a belt. `tests/` has no `__init__.py`."
- file: tests/test_control_socket.py
  why: ":124 `srv = daemon.ControlServer(_StubDaemon(), socket_path=path)`; :133
        `daemon.ControlServer(_ModeDaemon())._dispatch(…)` — construct the server around a REAL daemon
        (`daemon.ControlServer(d, socket_path=str(tmp_path/'s.sock'))`) WITHOUT `start()` to test
        `_dispatch` replies directly."
- file: tests/test_editor_protocol.py
  why: "Header style: 'NO live socket listener, NO CUDA'. Mirror it: 'NO live socket listener, NO CUDA,
        NO daemon run()'."

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py             # 3949 lines @ 6fd5309; T2.S3 seam at :2631; ControlServer :3360
voice_typing/editor_protocol.py    # S1 + S2 landed; S3's pump symbols present (:397 START_CAP_S, :413 LossCause, :464 ThreadTimers)
voice_typing/editor_session.py     # DOES NOT EXIST — created here (reservation state only)
tests/test_daemon.py               # fakes + helpers reused (imported, never edited)
tests/test_editor_session.py       # DOES NOT EXIST — created here
```

### Desired Codebase tree with files to be added

```bash
voice_typing/editor_session.py     # CREATE — Stage, Owner, EndRecord, NativeReserveResult, NativeReservation, END_REASONS (re-export)
voice_typing/daemon.py             # EDIT — imports; _NATIVE_ID_MEMORY; __init__ fields; hooks; fence in _start_fenced;
                                  #         busy in start/toggle/cancel/_dispatch; termination in stop/_request_stop/
                                  #         _maybe_auto_stop/_disarm/_handle_dead_host/request_shutdown/shutdown
tests/test_editor_session.py       # CREATE — FakeClock, ManualTimers, gated host factory, 18 tests
# Nothing else. editor_protocol.py, ctl.py, config.py, recorder_host.py, existing tests: untouched.
```

### Known Gotchas of our Codebase & Library Quirks

```python
# CRITICAL #1 — `self._lock` IS A NON-REENTRANT threading.Lock (daemon.py:836). Never call a method
# that takes `_lock` while holding it; never invoke a callback under it. Transitions under the lock,
# delivery after. `_disarm` is ALWAYS called under `_lock` → it may only STASH (see CRITICAL #6).

# CRITICAL #2 — THE TOKEN IS THE FENCE. `_native_seq` only increments. A worker's `native_tok` that is
# not the CURRENT reservation's token, or whose reservation is not STARTING, can never commit. A new
# reserve after an end replaces `self._native` with a new token → stale workers fail the check.

# CRITICAL #3 — TWO LOCK HOLDS IN `_start_fenced` CHECK THE FENCE: the reserve block (before `_arm_seq`
# bumps) and the atomic commit block (the `abort_reason` expression). The second is the one that
# matters: load/prime happened outside the lock for up to 30 s.

# CRITICAL #4 — ENFORCE THE 30 s CAP TWICE, BOTH UNDER _lock, EXACTLY ONCE: the timer callback AND
# `_native_can_commit_locked` re-read the injected clock; whichever sees `now >= deadline` first calls
# `_end_native_locked("timeout", "start-cap")` (idempotent) — a late timer or a late worker cannot
# produce a second EndRecord nor a late arm.

# CRITICAL #5 — DELIVERY IS EXACTLY-ONCE VIA A CLAIM: `_claim_native_end_locked` flips
# `_native_end_delivered` under the lock; `_flush_native_end()` (any thread, never under the lock)
# invokes the callback. Reset both flags at every reserve.

# CRITICAL #6 — `_disarm` STASHES; THE PARKED WORKER DELIVERS. After a successful commit the worker
# thread parks on ITS reservation's `end_evt`; `_end_native_locked` sets it. Termination during
# STARTING is delivered immediately by the terminating thread (never behind a blocked load). Use a
# PER-RESERVATION Event (`NativeReservation.end_evt`), not a daemon-wide one — a daemon-wide Event
# would be `clear()`ed by the next reserve and could strand the previous worker.

# CRITICAL #7 — `Timer.cancel()` UNDER _lock IS ACCEPTABLE (flag set only) — nothing else is.

# CRITICAL #8 — NO ECHO. EndRecord/log/reply content is fixed codes + the owner token/id. Never the
# seed, request text, frame bytes or exception messages (`type(exc).__name__` only).

# CRITICAL #9 — `start()`/`toggle()` currently DISCARD their ArmOutcome; change them to return it
# (`-> ArmOutcome | None`); duck-typed test daemons return None → `getattr(out, "reason", None)`.

# CRITICAL #10 — `_handle_dead_host` resets `_host = None` INSIDE its lock block; add the termination
# AFTER that block (it must not run under the lock).

# CRITICAL #11 — Full paths + two timeouts: `timeout 300 .venv/bin/python -m pytest <files> -q`
# (bash-tool timeout ≥ 360); test_daemon.py: `timeout 500 … tests/test_daemon.py -q --tb=no` (bash
# tool ≥ 560) then set-diff FAILED names against tests/G1_BASELINE.md's CPU addendum. Never bare
# python/pytest/uv; never `.venv/bin/voicectl` without `timeout 30`; never start the daemon.

# GOTCHA #12 — S3's pump and this task append to different files; do not touch editor_protocol.py.
# If `grep -c 'START_CAP_S\|class ThreadTimers' voice_typing/editor_protocol.py` < 2 → STOP (S3 not landed).

# CROSS-ITEM NOTE (report, do not fix): PRD's first daemon→editor frame is {"ok":true,"event":"starting"}
# but S2's validate_event closes `starting` to {event,id}. T4.S2/T4.S7 own that. Here `reserve_native`
# does NOT emit anything; T4.S7 emits `starting` between reserve and begin (that ordering is why the
# API is two-phase).
```

## Implementation Blueprint

### Data models and structure

Stdlib only. `voice_typing/editor_session.py` (verbatim):

```python
"""Native v1 session ownership — reservation + startup fence (P1.M1.T3.S4; PRD §4.8.1 B).

RESERVATION STATE ONLY. This module answers three questions for the daemon: who owns the mic (one
connection-bound native owner), what stage its startup/session is in, and when its Start budget
expires. Ordered offer delivery (P1.M1.T4.S2), stop/cancel/drain policy (T4.S5), the `ended` frame and
failure hints (T4.S6) and socket activation (T4.S7) all build on these hooks.

Discipline (Mode A):
  * No I/O, no sockets, no threads started, no daemon import. The only import is editor_protocol
    (END_REASONS, START_CAP_S) — the single reference for every native timer/reason code.
  * Every method is a PURE transition that MUST run under the CALLER's lock (the daemon's `_lock`);
    nothing here takes a lock. The daemon's critical sections make check-and-reserve atomic.
  * Time is an injected monotonic clock; the Start deadline is ABSOLUTE (created_at + START_CAP_S).
  * EndRecords carry fixed codes only — never request text, seed text or frame bytes.
"""

from __future__ import annotations

import enum
import threading
from dataclasses import dataclass

from voice_typing.editor_protocol import END_REASONS, START_CAP_S

__all__ = ["Stage", "Owner", "EndRecord", "NativeReserveResult", "NativeReservation", "END_REASONS"]


class Stage(str, enum.Enum):
    STARTING = "starting"    # reservation acquired; load/priming may be running; capture NOT open
    LISTENING = "listening"  # arm committed under the daemon lock: capture open
    DRAINING = "draining"    # stop/idle/lost wind-down ("finishing"); T4.S5 owns the policy
    ENDED = "ended"          # terminal; the owner token is tombstoned from here on


ACTIVE_STAGES = frozenset({Stage.STARTING, Stage.LISTENING, Stage.DRAINING})


@dataclass(frozen=True)
class Owner:
    id: str          # the client's UUIDv4 (S2 is_uuid_v4) — opaque, safe to log
    token: int       # daemon-side monotonic owner token — THE fence every hook checks
    created_at: float
    deadline: float  # created_at + START_CAP_S — the TOTAL Start cap incl. model load + priming


@dataclass(frozen=True)
class EndRecord:
    """What T4.S6 turns into the `ended` frame. Fixed codes only."""
    owner: Owner
    stage: Stage          # the stage just before ENDED
    reason: str           # §4.8.1 B ended.reason (an END_REASONS member)
    cause: str | None     # "start-cap" | "stop-during-start" | "host-died" | "shutdown" | a LossCause value | None
    ended_at: float


@dataclass(frozen=True)
class NativeReserveResult:
    accepted: bool
    owner: Owner | None
    error: str | None     # native error code for native_error_reply/write_reject: busy | duplicate_id | invalid_request


class NativeReservation:
    """The one live reservation. Guarded by the daemon's `_lock`; pure transitions; terminal is idempotent.
    `end_evt` is per-reservation so the session's parked worker can be woken by an under-lock terminator
    (daemon._disarm) without a daemon-wide Event being cleared by the next reserve."""

    def __init__(self, owner: Owner, conn: object, *, now: float) -> None:
        self.owner = owner
        self.conn = conn                 # kept for T4.S6/T4.S7; never used here
        self.stage = Stage.STARTING
        self.drain_reason: str | None = None
        self.end: EndRecord | None = None
        self.end_evt = threading.Event()

    @property
    def live(self) -> bool:
        return self.stage in ACTIVE_STAGES

    @property
    def end_reason(self) -> str:
        """The reason an end from DRAINING will carry (recorded by begin_drain; 'stopped' otherwise)."""
        return self.drain_reason or "stopped"

    def can_commit(self, token: int, now: float) -> bool:
        """True iff `token` is this reservation, it is still STARTING, and the Start cap has not passed."""
        return token == self.owner.token and self.stage is Stage.STARTING and now < self.owner.deadline

    def commit(self, token: int) -> bool:
        """STARTING -> LISTENING. Must run in the SAME lock hold that opens capture (daemon._start_fenced)."""
        if token != self.owner.token or self.stage is not Stage.STARTING:
            return False
        self.stage = Stage.LISTENING
        return True

    def begin_drain(self, reason: str) -> bool:
        """LISTENING -> DRAINING, recording the reason the end will carry ('stopped' | 'idle' | ...)."""
        if self.stage is not Stage.LISTENING or reason not in END_REASONS:
            return False
        self.stage = Stage.DRAINING
        self.drain_reason = reason
        return True

    def terminate(self, reason: str, cause: str | None, *, now: float) -> EndRecord | None:
        """Any live stage -> ENDED (tombstones the token). Idempotent: None once ended."""
        if reason not in END_REASONS:
            raise ValueError("unknown end reason")
        if not self.live:
            return None
        prev, self.stage = self.stage, Stage.ENDED
        self.end = EndRecord(self.owner, prev, reason, cause, now)
        return self.end

    def tombstoned(self, token: int) -> bool:
        return self.owner.token == token and self.stage is Stage.ENDED
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREREQUISITE GATE
  - RUN: grep -c 'START_CAP_S\|class ThreadTimers\|class LossCause' voice_typing/editor_protocol.py;
          grep -c 'def is_uuid_v4\|^END_REASONS' voice_typing/editor_protocol.py;
          grep -n 'def _start_fenced' voice_typing/daemon.py
  - EXPECT: ≥ 3 lines / 2 / one hit at :2631. Missing S3 symbols → STOP "P1.M1.T3.S3 not landed".
            Missing S2 → STOP "P1.M1.T3.S2 not landed".

Task 1: CREATE voice_typing/editor_session.py — the module above, verbatim.
  - NAMING: exactly as written (T4.S5/S6/S7 import these names).

Task 2: EDIT voice_typing/daemon.py — imports + constant
  - EXTEND the `from voice_typing.editor_protocol import (` list (:137) with: START_CAP_S, ThreadTimers,
    remaining, is_uuid_v4  (keep S1/S2 names; one per line, alphabetical within the existing style).
  - ADD after it: `from voice_typing.editor_session import (EndRecord, NativeReservation,
    NativeReserveResult, Owner, Stage,)`; `from collections import deque` (skip if already imported).
  - ADD next to `_START_DEADLINE_S` (:247): `_NATIVE_ID_MEMORY: int = 8  # P1.M1.T3.S4: active + recently
    ended native ids → duplicate_id ("reject an id already active or retained")` and
    `_NATIVE_START_FAILURE = {"load-failed": "load_failed", "seed-unconfirmed": "load_failed",
    "prompt-unconfirmed": "load_failed"}  # ArmOutcome.reason → ended.reason for a native start`.

Task 3: EDIT daemon.py __init__ — native fields (inside the T2.S3 block, right after `self._stop_seq = 0`
        at ~:981; copy the comment block — it IS the Mode A documentation of the reservation fields):
    # P1.M1.T3.S4 — native owner reservation (§4.8.1 B). _native is the ONE connection-bound owner
    # (kept, ENDED, until the next reserve replaces it — a tombstoned token still fails the fence);
    # _native_seq mints owner tokens (the startup fence); _native_ids remembers active + recently
    # ended ids (duplicate_id). Clock + timer source are instance attributes so tests inject fakes;
    # production uses editor_protocol's START_CAP_S + ThreadTimers (the client-facing 30 s reference).
    self._native: NativeReservation | None = None
    self._native_seq = 0
    self._native_ids: deque[str] = deque(maxlen=_NATIVE_ID_MEMORY)
    self._native_timer = None                   # Start-cap watchdog handle (armed at reserve)
    self._native_worker: threading.Thread | None = None
    self._native_clock = time.monotonic
    self._native_timers = ThreadTimers(time.monotonic)
    self._native_end_cb = None                  # T4.S6/T4.S7: receives the EndRecord once, off-lock
    self._native_end_delivered = False

Task 4: EDIT daemon.py — the reservation API (NEW methods; place them directly AFTER `_abort_start`
        / `_isolate_host` and BEFORE `start_with_seed`, ~:2798, under a banner comment
        `# --- P1.M1.T3.S4: native owner reservation + startup fence (§4.8.1 B) ---`). Each with a Mode A
        docstring (one sentence on ownership/locking/time). Code:
    def _native_owner_live_locked(self) -> bool:
        return self._native is not None and self._native.live

    def _native_blockers_locked(self) -> bool:
        """§4.8.1 B 'any other arm is loading, listening, or draining' — T2.S5's four flags, verbatim."""
        return (self._arming is not None or self._loading or self._listening.is_set() or self._drain)

    def native_id_known(self, session_id: str) -> bool:
        """duplicate_id predicate ('active or retained'); T4.S1 may extend it with its recovery store."""
        return session_id in self._native_ids

    def reserve_native(self, conn, session_id: str, *, on_end=None) -> NativeReserveResult:
        """INTERNAL (T4.S7 wires `editor-start` to it). ATOMIC check-and-reserve under _lock, in this
        order: shutdown → busy; id active/retained → duplicate_id; native owner live → busy; any
        generic arm loading/listening/draining → busy. On acceptance mints the owner token, installs the
        STARTING reservation, registers the id, and (outside the lock) arms the 30 s Start-cap watchdog.
        Spawns nothing — call begin_native_start(token) after emitting `starting`. Never writes."""
        if not is_uuid_v4(session_id):
            return NativeReserveResult(False, None, "invalid_request")
        with self._lock:
            if self._shutdown.is_set():
                return NativeReserveResult(False, None, "busy")
            if session_id in self._native_ids:
                return NativeReserveResult(False, None, "duplicate_id")
            if self._native_owner_live_locked() or self._native_blockers_locked():
                return NativeReserveResult(False, None, "busy")
            self._native_seq += 1
            now = self._native_clock()
            owner = Owner(session_id, self._native_seq, now, now + START_CAP_S)
            self._native = NativeReservation(owner, conn, now=now)
            self._native_ids.append(session_id)
            self._native_end_cb = on_end
            self._native_end_delivered = False
            self._native_worker = None
        # outside the lock: arm the watchdog; a fire is re-checked against the clock under the lock
        self._native_timer = self._native_timers.arm(
            owner.deadline, lambda tok=owner.token: self._native_start_expired(tok))
        logger.info("voice-typing native: reserved owner token=%d stage=starting cap=%.0fs",
                    owner.token, START_CAP_S)
        return NativeReserveResult(True, owner, None)

    def _native_start_expired(self, token: int) -> None:
        """Watchdog (timer thread). Ends the reservation as 'timeout' only if it is still the current
        STARTING owner AND the injected clock says the cap has passed (a late/early fire is ignored)."""
        with self._lock:
            r = self._native
            if (r is None or r.owner.token != token or r.stage is not Stage.STARTING
                    or self._native_clock() < r.owner.deadline):
                return
            self._end_native_locked("timeout", "start-cap")
        self._flush_native_end()

    def begin_native_start(self, token: int, *, seed: str | None = None,
                           streaming: bool | None = None) -> bool:
        """INTERNAL (T4.S7): spawn the session's lifecycle thread for a reserved token. False if the
        token is no longer the current STARTING owner inside its cap (tombstoned/replaced/expired — an
        expired one is ended here as 'timeout') or a worker already exists. Idempotent per token."""
        with self._lock:
            if not self._native_can_commit_locked(token) or self._native_worker is not None:
                spawn = False
            else:
                self._native_worker = threading.Thread(
                    target=self._native_start_worker, args=(token,),
                    kwargs={"seed": seed, "streaming": streaming},
                    name=f"native-start-{token}", daemon=True)
                spawn = True
        self._flush_native_end()
        if not spawn:
            return False
        self._native_worker.start()
        return True

    def _native_can_commit_locked(self, token: int) -> bool:
        """THE STARTUP FENCE (caller holds _lock). True iff `token` is the CURRENT reservation, still
        STARTING, inside its Start cap. An expired reservation is terminated HERE ('timeout',
        'start-cap'; stashed for off-lock delivery) so the cap holds even when the watchdog fires late.
        False for a tombstoned or replaced token."""
        r = self._native
        if r is None or r.owner.token != token or r.stage is not Stage.STARTING:
            return False
        now = self._native_clock()
        if now >= r.owner.deadline:
            self._end_native_locked("timeout", "start-cap", now=now)
            return False
        return True

    def _end_native_locked(self, reason: str, cause: str | None, *, now: float | None = None) -> EndRecord | None:
        """Transition the live reservation to ENDED under _lock; retire the watchdog (Timer.cancel is a
        flag set — the ONE thing allowed under the lock); wake a parked worker. Idempotent."""
        r = self._native
        if r is None or not r.live:
            return None
        rec = r.terminate(reason, cause, now=self._native_clock() if now is None else now)
        handle, self._native_timer = self._native_timer, None
        if handle is not None:
            self._native_timers.cancel(handle)
        r.end_evt.set()
        logger.info("voice-typing native: ended owner token=%d from=%s reason=%s cause=%s",
                    r.owner.token, rec.stage.value, rec.reason, rec.cause)
        return rec

    def _claim_native_end_locked(self) -> EndRecord | None:
        """Exactly-once delivery claim: the first caller gets the record, everyone after gets None."""
        r = self._native
        if r is None or r.end is None or self._native_end_delivered:
            return None
        self._native_end_delivered = True
        return r.end

    def _flush_native_end(self) -> None:
        """Deliver the pending EndRecord to on_end — NEVER under _lock; swallows a raising callback
        (type name only). Safe from any thread; a no-op when nothing is pending."""
        with self._lock:
            rec = self._claim_native_end_locked()
        if rec is None:
            return
        cb = self._native_end_cb
        if cb is None:
            return
        try:
            cb(rec)
        except Exception as exc:  # defensive: a misbehaving listener — TYPE name only
            logger.warning("native end callback raised (%s)", type(exc).__name__)

    def terminate_native(self, reason: str, *, cause: str | None = None, token: int | None = None) -> EndRecord | None:
        """INTERNAL hook (T4.S5/S6/S7): end the live reservation with an §4.8.1 B reason; `token`
        restricts the call to that owner (None = any). Must be called WITHOUT _lock held. Delivers
        on_end on the calling thread after releasing the lock. Idempotent (None if already ended)."""
        with self._lock:
            r = self._native
            if r is None or (token is not None and r.owner.token != token):
                return None
            rec = self._end_native_locked(reason, cause)
        self._flush_native_end()
        return rec

    def begin_native_drain(self, reason: str) -> bool:
        """INTERNAL hook (T4.S5; also _request_stop/_maybe_auto_stop): LISTENING -> DRAINING and record
        the reason the end will carry. No-op (False) without a LISTENING native owner."""
        with self._lock:
            r = self._native
            return r is not None and r.begin_drain(reason)

    def _native_start_worker(self, token: int, *, seed: str | None, streaming: bool | None) -> None:
        """The native session's lifecycle thread. (1) runs the fenced start carrying its owner token
        (heavy waits inside _start_fenced run OUTSIDE _lock; stop/status stay responsive); (2) on
        failure ends the reservation with the mapped reason; (3) on success parks on its reservation's
        end_evt and delivers the EndRecord an under-lock terminator (_disarm) stashed. Never holds the
        lock across a wait; never logs text."""
        with self._lock:
            r = self._native
            if r is None or r.owner.token != token:
                return
        out = self._start_fenced(seed, streaming=streaming,
                                 timeout=max(0.0, remaining(r.owner.deadline, self._native_clock())),
                                 reject_busy=True, native_tok=token)
        with self._lock:
            mine = self._native is r and r.live
            if not out.ok and mine:
                reason = _NATIVE_START_FAILURE.get(out.reason)
                if reason is not None:          # superseded/aborted/busy/start-timeout → someone ended us already
                    self._end_native_locked(reason, None)
            committed = out.ok and self._native is r and r.stage is Stage.LISTENING
        self._flush_native_end()
        if not committed:
            return
        r.end_evt.wait()                         # woken by _end_native_locked (per-reservation Event)
        self._flush_native_end()

Task 5: EDIT daemon.py _start_fenced — the fence at BOTH lock holds
  - SIGNATURE: add `native_tok: int | None = None` as the last kwarg.
  - DOCSTRING: add one paragraph: "P1.M1.T3.S4: native_tok carries a native owner's token — the arm
    commits only into ITS OWN live STARTING reservation inside the 30 s Start cap (checked here at
    reserve AND in the atomic commit block; an expired one is ended as 'timeout'). Without native_tok,
    a live native owner makes this call return reason 'busy' with NOTHING reserved — no generic or
    context arm supersedes or joins a native session (§4.8.1 B)."
  - IN THE RESERVE BLOCK (the first `with self._lock:`), insert BEFORE `if reject_busy and (`:
        if native_tok is not None:
            if not self._native_can_commit_locked(native_tok):
                return ArmOutcome(False, False, "superseded", None, None, self._arm_seq)
        elif self._native_owner_live_locked():   # P1.M1.T3.S4: never supersede/join a native owner
            return ArmOutcome(False, False, "busy", None, None, self._arm_seq)
  - IN THE ATOMIC COMMIT BLOCK (`with self._lock:` → `stale = …`), EXTEND the abort condition with
        or (native_tok is not None and not self._native_can_commit_locked(native_tok))
    (keep it inside the same parenthesized `if (`. Because `_native_can_commit_locked` may END an
    expired reservation, the existing fallthrough `return self._abort_start(tok, host, abort_reason, …)`
    then runs — `_abort_start` already performs the confirmed seed cleanup / host isolation.)
  - IN THE COMMIT BRANCH, immediately BEFORE `self._arm(streaming=streaming)`:
        if native_tok is not None:
            # P1.M1.T3.S4 COMMIT HOOK — same lock hold as capture: STARTING→LISTENING is atomic with
            # the mic opening; the Start-cap watchdog is retired (Timer.cancel = flag set, allowed here).
            self._native.commit(native_tok)
            handle, self._native_timer = self._native_timer, None
            if handle is not None:
                self._native_timers.cancel(handle)

Task 6: EDIT daemon.py — busy arbitration on every arm entry + cancel
  - `start()` (:2866): `return self._start_fenced(None, streaming=streaming)`; annotation
    `-> ArmOutcome | None`; docstring += "P1.M1.T3.S4: returns the outcome — reason 'busy' while a
    native editor session owns the mic (nothing reserved)."
  - `toggle()` (:2886): the arm branch `return self._start_fenced(None, streaming=streaming)`; same
    annotation/docstring sentence. The listening branch (toggle-off = a stop) is unchanged.
  - `start_with_seed`/`start_context`: NO edit — they already return the outcome / map 'busy'.
  - `cancel()` (:2263): FIRST statement of the body:
        with self._lock:
            if self._native_owner_live_locked():   # P1.M1.T3.S4: cancel is not an owner command
                return {"ok": False, "listening": self._listening.is_set(), "busy": True,
                        "error": "busy: a native editor session owns the mic"}
  - `ControlServer._dispatch` (:3591): in the toggle branch AND the start branch, assign the daemon
    call to `out` (`out = self._daemon.toggle()` / `toggle(streaming=mode)` / `start()` /
    `start(streaming=mode)`) and immediately after each branch's calls add:
        if getattr(out, "reason", None) == "busy":   # P1.M1.T3.S4: duck-typed daemons return None
            return {"ok": False, "listening": False, "busy": True,
                    "error": "busy: a native editor session owns the mic"}
    Leave the existing fallthrough reply untouched.

Task 7: EDIT daemon.py — termination hooks
  - `stop()` (:2881): body becomes
        if self._stop_native_start():   # P1.M1.T3.S4: Stop during startup aborts the reservation; capture never opens
            return
        self._request_stop()
    and ADD:
        def _stop_native_start(self) -> bool:
            """P1.M1.T3.S4: a STARTING native owner ends here ('stopped', 'stop-during-start'), delivered
            off-lock; the worker's late commit finds a tombstoned token. False when nothing to stop."""
            with self._lock:
                if not (self._native_owner_live_locked() and self._native.stage is Stage.STARTING):
                    return False
                self._end_native_locked("stopped", "stop-during-start")
            self._flush_native_end()
            return True
  - `_request_stop()` (:1958): FIRST statement (before any lock): `self._native_drain_or_stop("stopped")`
    where `def _native_drain_or_stop(self, reason): self.begin_native_drain(reason)` (one-line helper;
    no-op without a LISTENING native owner). Docstring += "P1.M1.T3.S4: a native LISTENING owner is
    tagged 'stopped' so _disarm ends it with that reason."
  - `_maybe_auto_stop()` (:2367): FIRST statement, before its `with self._lock:` block:
    `self._native_drain_or_stop("idle")`.
  - `_disarm()` (:1839): LAST statements of the body (still under the caller's `_lock`):
        # P1.M1.T3.S4: the native owner's mic just closed — end its reservation HERE (under _lock) with
        # the drain reason recorded by _request_stop/_maybe_auto_stop (else 'stopped'); the record is
        # delivered off-lock by the session's parked worker, never under this lock.
        if self._native_owner_live_locked():
            self._end_native_locked(self._native.end_reason, None)
  - `_handle_dead_host()` (:1327): AFTER its `with self._lock:` block:
        # P1.M1.T3.S4: the reservation is bound to the recorder host's lifetime
        with self._lock:
            starting = self._native_owner_live_locked() and self._native.stage is Stage.STARTING
        self.terminate_native("load_failed" if starting else "disconnected", cause="host-died")
  - `request_shutdown()` (:2907): immediately AFTER the lock block that sets `_shutdown`:
    `self.terminate_native("shutdown", cause="shutdown")  # P1.M1.T3.S4`. Docstring += one sentence.
  - `shutdown()` (:3196): FIRST statement: the same call (idempotent; covers the SIGTERM/finally path).

Task 8: CREATE tests/test_editor_session.py (harness + 18 tests below).

Task 9: RUN the validation loop; fix; confirm scope with `git diff --name-only`.
```

### Implementation Patterns & Key Details

```python
# PATTERN — every terminator is "transition under the lock, deliver after it":
with self._lock:
    rec = self._end_native_locked(reason, cause)   # pure; idempotent; retires the timer; sets end_evt
self._flush_native_end()                           # claim-once + callback, NEVER under the lock

# PATTERN — the ONE under-lock terminator (_disarm): stash only; the parked worker delivers:
if self._native_owner_live_locked():
    self._end_native_locked(self._native.end_reason, None)   # sets r.end_evt → worker wakes, flushes

# PATTERN — timer callbacks re-check the clock under the lock (a Timer can fire late or early):
if r is None or r.owner.token != token or r.stage is not Stage.STARTING or self._native_clock() < r.owner.deadline:
    return

# GOTCHA — `_start_fenced` returns INSIDE its commit `with self._lock:` block: the commit hook may
# only flip the stage and Timer.cancel(); everything else (logging, callback) waits for the worker.
```

### Integration Points

```yaml
DAEMON (voice_typing/daemon.py):
  - imports: extend the editor_protocol from-list (:137) with START_CAP_S, ThreadTimers, remaining, is_uuid_v4;
             add `from voice_typing.editor_session import EndRecord, NativeReservation, NativeReserveResult, Owner, Stage`
             and `from collections import deque` (if absent)
  - constants: _NATIVE_ID_MEMORY = 8; _NATIVE_START_FAILURE = {...}   (next to _START_DEADLINE_S :247)
  - __init__: nine _native_* fields (Task 3)                        (after `self._stop_seq = 0` ~:981)
  - methods: the Task 4 block + _stop_native_start + _native_drain_or_stop   (before start_with_seed ~:2798)
  - _start_fenced: kwarg native_tok; reserve-block guard; commit-block guard; commit hook (Task 5)
  - busy: start/toggle return outcome; cancel early-return; _dispatch mapping   (Task 6)
  - termination: stop/_request_stop/_maybe_auto_stop/_disarm/_handle_dead_host/request_shutdown/shutdown (Task 7)

SOCKET: NONE in this task (T4.S7: `_handle` branches on request_kind → validate_request → reserve_native
        → `starting` → begin_native_start; on_loss → terminate_native('disconnected', cause=…)).
CONFIG: none. RECORDER_HOST: none. EDITOR_PROTOCOL: none (read-only import).
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m py_compile voice_typing/editor_session.py voice_typing/daemon.py   # bash-tool timeout 90
timeout 60 .venv/bin/python -c "import voice_typing.editor_session as es, voice_typing.daemon as d; \
  print(sorted(es.__all__), d._NATIVE_ID_MEMORY)"   # expect the 6 names and 8; bash-tool timeout 90
# Expected: no output errors. pytest only (no ruff/mypy configured in this repo).
```

### Level 2: Unit Tests (Component Validation)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_editor_session.py -q                 # bash-tool timeout ≥ 360
timeout 300 .venv/bin/python -m pytest tests/test_editor_protocol.py tests/test_editor_protocol_vectors.py -q
timeout 300 .venv/bin/python -m pytest tests/test_editor_pump.py -q 2>/dev/null || echo "S3 suite absent — skip"   # if present
# Expected: 0 failures. Debug root cause; never loosen an assertion to pass.
```

### Level 3: Integration Regression (daemon.py and _dispatch are touched)

```bash
timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no > /tmp/s4_daemon.txt 2>&1; echo "exit=$?"   # bash-tool timeout ≥ 560
grep -E '^FAILED' /tmp/s4_daemon.txt | sed 's/ - .*//' | sort > /tmp/s4_failed.txt; wc -l < /tmp/s4_failed.txt
# Set-diff the names against the G1 CPU addendum in tests/G1_BASELINE.md: NO NEW FAILED names allowed.
timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_voicectl.py -q   # bash-tool timeout ≥ 360
rm -f /tmp/s4_daemon.txt /tmp/s4_failed.txt   # /tmp is RAM — remove scratch when done
# Expected: G1 parity; control-socket/voicectl green.
```

### Level 4: Domain-Specific Validation (fence properties, all inside the new suite)

```bash
# The suite IS the domain validation (verification.md T10b): busy races through all ownership phases,
# responsive status/stop/quit during a blocked load, the 30 s cap enforced from both sides, late-commit
# refusal with the host left idle, exactly-once off-lock end delivery under a 3-way race.
timeout 300 .venv/bin/python -m pytest tests/test_editor_session.py -q -k "fence or cap or race or busy or stop_during" -v
git diff --name-only   # Expected: exactly the three files
```

## Final Validation Checklist

### Technical Validation
- [ ] `py_compile` clean; new suite 18/18; S1/S2 (and S3 if present) suites unchanged and green.
- [ ] `tests/test_daemon.py` FAILED-name set ⊆ G1 CPU addendum (no new failures); `test_control_socket.py`
      + `test_voicectl.py` green.
- [ ] `git diff --name-only` ⊆ {`voice_typing/editor_session.py`, `voice_typing/daemon.py`, `tests/test_editor_session.py`}.

### Feature Validation
- [ ] Rejections reserve nothing (token, timer, `_arm_seq`, `_native` all unchanged) — tests 7a–h.
- [ ] Mic opens only from a fenced commit; stage is LISTENING inside `set_microphone(True)` — test 12.
- [ ] Late commit after the cap never opens the mic; host idle-resident; seed cleaned — tests 10–11.
- [ ] `status_snapshot()`/`stop()` ≤ 1 s while the worker is blocked in `spawn` — test 9.
- [ ] `on_end` once, off-lock (no deadlock), raising callback swallowed — tests 16–17.
- [ ] No seed/request text in logs/records/replies — test 18.

### Code Quality Validation
- [ ] No callback, wait, join or socket I/O under `_lock`; `Timer.cancel()` is the only thing done under it.
- [ ] Every new public/internal method has a Mode A docstring naming the §4.8.1 clause it encodes.
- [ ] Existing T2.S3/T2.S5 behavior byte-identical when no native owner exists (G1 parity proves it).

### Documentation & Deployment
- [ ] `__init__` comment block + `_start_fenced` docstring document busy arbitration and the fence (Mode A).
- [ ] No new config keys, env vars, deps, or socket commands.

---

## Anti-Patterns to Avoid

- ❌ Don't check busy in one place and reserve in another — one `_lock` hold (CRITICAL #1/#3).
- ❌ Don't let a plain `start()`/`toggle()` supersede a native owner via the existing `_arm_seq` bump.
- ❌ Don't deliver `on_end` under `_lock` or from `_disarm` — stash; the parked worker delivers.
- ❌ Don't defer a STARTING termination's `ended` behind the blocked load — deliver on the terminating thread.
- ❌ Don't rely on the timer alone for the 30 s cap — the commit block re-reads the clock.
- ❌ Don't use a daemon-wide Event for the worker wakeup (the next reserve would clear it).
- ❌ Don't emit `starting`, construct an `OwnerPump`, route `editor-start`, or build `ended` here.
- ❌ Don't log/return seed or request text; codes, counts, ids and tokens only.
- ❌ Don't run `voicectl`, the daemon, or the E2E scripts; two timeouts on every pytest command.

---

## Appendix A — tests/test_editor_session.py (harness verbatim + 18 tests)

```python
"""P1.M1.T3.S4 — native owner reservation + startup fence (PRD §4.8.1 B).
NO live socket listener, NO CUDA, NO daemon run(). Fake clock + manual timers + Event barriers; no sleeps."""
import sys, threading, dataclasses
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parent))          # tests/ has no __init__.py; pytest prepend mode
import test_daemon as td                                # _make_daemon, _fake_host_factory, _wait_for
from voice_typing import daemon
from voice_typing.editor_session import (Stage, Owner, EndRecord, NativeReservation, NativeReserveResult)
from voice_typing.editor_protocol import START_CAP_S, ThreadTimers


class FakeClock:
    def __init__(self, t=1000.0): self.t = t
    def now(self): return self.t
    def advance(self, s): self.t += s


class ManualTimers:                                      # S3's test convention: arm records, fire is explicit
    def __init__(self): self.armed, self.fired, self.cancelled = [], [], []
    def arm(self, deadline, fire):
        h = object(); self.armed.append((h, deadline, fire)); return h
    def cancel(self, h): self.cancelled.append(h)
    def fire(self, h):
        for hh, d, f in self.armed:
            if hh is h: self.fired.append(h); f()


def _gated_host_factory(entered, gate, mic_log):
    """Wraps td._fake_host_factory(): spawn blocks on `gate`; set_microphone calls are logged with the
    daemon's native stage at call time (proves the commit is atomic with capture)."""
    inner = td._fake_host_factory()
    def factory(*a, **k):
        host = inner(*a, **k)
        orig_spawn, orig_mic = host.spawn, host.set_microphone
        def spawn(timeout=180.0):
            entered.set(); gate.wait(5.0); return orig_spawn(timeout)
        def set_microphone(on):
            mic_log.append((bool(on), factory.daemon._native.stage if factory.daemon._native else None))
            orig_mic(on)
        host.spawn, host.set_microphone = spawn, set_microphone
        return host
    factory.daemon = None
    return factory


def _native_daemon(*, gate=None, entered=None, mic_log=None, prime=None):
    """A hermetic daemon with injected clock/timers and (optionally) a gated spawn."""
    mic_log = mic_log if mic_log is not None else []
    if gate is None:
        d, _fb, _rec, _be = td._make_daemon(host_factory=td._fake_host_factory())
        rec = _rec
    else:
        f = _gated_host_factory(entered, gate, mic_log)
        d, _fb, _rec, _be = td._make_daemon(host_factory=f); f.daemon = d; rec = _rec
    fc, mt = FakeClock(), ManualTimers()
    d._native_clock, d._native_timers = fc.now, mt
    return d, fc, mt, mic_log, rec


class _Ends:                                             # on_end collector with an optional hook
    def __init__(self, hook=None): self.records, self.hook, self.lock = [], hook, threading.Lock()
    def __call__(self, rec):
        with self.lock: self.records.append(rec)
        if self.hook: self.hook(rec)


ID = "123e4567-e89b-42d3-a456-426614174000"     # a valid UUIDv4 (S2 vectors use this one)
ID2 = "123e4567-e89b-42d3-a456-426614174001"


# ---- A. pure state machine (editor_session.NativeReservation) ----
def test_reservation_stage_machine_fake_clock():
    fc = FakeClock(); r = NativeReservation(Owner(ID, 1, fc.now(), fc.now() + START_CAP_S), object(), now=fc.now())
    assert r.stage is Stage.STARTING and r.live and r.can_commit(1, fc.now()) and not r.can_commit(2, fc.now())
    assert not r.begin_drain("stopped")                       # not listening yet
    assert r.commit(1) and r.stage is Stage.LISTENING and not r.commit(1)
    assert r.begin_drain("idle") and r.stage is Stage.DRAINING and r.end_reason == "idle"
    rec = r.terminate("idle", None, now=fc.now())
    assert isinstance(rec, EndRecord) and rec.stage is Stage.DRAINING and r.stage is Stage.ENDED
    assert not r.live and r.tombstoned(1) and r.terminate("stopped", None, now=fc.now()) is None


def test_reservation_cap_boundary_is_exclusive():
    fc = FakeClock(); dl = fc.now() + START_CAP_S
    r = NativeReservation(Owner(ID, 1, fc.now(), dl), object(), now=fc.now())
    assert r.can_commit(1, dl - 0.001) and not r.can_commit(1, dl)   # at the deadline the cap has passed


def test_end_record_fields_are_codes_only():
    names = {f.name for f in dataclasses.fields(EndRecord)}
    assert names == {"owner", "stage", "reason", "cause", "ended_at"}
    r = NativeReservation(Owner(ID, 1, 0.0, 1.0), object(), now=0.0)
    with pytest.raises(ValueError): r.terminate("not-a-code", None, now=0.0)
    assert r.live                                           # an unknown reason did not end it


# ---- B. atomic check-and-reserve ----
def test_reserve_native_accepts_and_arms_one_timer():
    d, fc, mt, _, _ = _native_daemon()
    res = d.reserve_native(object(), ID, on_end=_Ends())
    assert res.accepted and res.error is None and res.owner.token == 1 and res.owner.id == ID
    assert res.owner.deadline == fc.now() + START_CAP_S and d._native.stage is Stage.STARTING
    assert d.native_id_known(ID) and len(mt.armed) == 1 and mt.armed[0][1] == res.owner.deadline
    assert d._arming is None and d._arm_seq == 0 and not d._listening.is_set()   # nothing armed


def test_reserve_native_rejections_reserve_nothing():
    d, fc, mt, _, _ = _native_daemon()
    assert d.reserve_native(object(), "nope") == NativeReserveResult(False, None, "invalid_request")
    assert d._native is None and not mt.armed
    d._shutdown.set(); assert d.reserve_native(object(), ID).error == "busy"; d._shutdown.clear()
    for flag in ("_arming", "_loading", "_drain"):
        setattr(d, flag, 2 if flag == "_arming" else True)
        assert d.reserve_native(object(), ID).error == "busy" and d._native is None and d._arm_seq == 0
        setattr(d, flag, None if flag == "_arming" else False)
    d._listening.set(); assert d.reserve_native(object(), ID).error == "busy"; d._listening.clear()
    assert not mt.armed


def test_second_native_owner_and_duplicate_id_are_busy():
    d, fc, mt, _, _ = _native_daemon(); ends = _Ends()
    assert d.reserve_native(object(), ID, on_end=ends).accepted
    assert d.reserve_native(object(), ID2).error == "busy"             # one owner at a time
    d.terminate_native("stopped", cause="test", token=1)
    assert len(ends.records) == 1
    assert d.reserve_native(object(), ID).error == "duplicate_id"      # ended ids stay retained
    res = d.reserve_native(object(), ID2); assert res.accepted and res.owner.token == 2


# ---- C. symmetric busy: generic/context arms never supersede or join ----
def test_generic_arms_are_busy_under_native_owner_and_reserve_nothing():
    d, fc, mt, _, _ = _native_daemon(); d.reserve_native(object(), ID)
    seq0 = d._arm_seq
    assert d.start().reason == "busy" and d.toggle().reason == "busy"
    assert d.start_with_seed("seed text").reason == "busy"
    reply = d.start_context("seed text")
    assert reply["ok"] is False and "busy" in reply["error"] and reply["context_seeded"] is False
    assert d._arm_seq == seq0 and d._arming is None and d._native.stage is Stage.STARTING


def test_dispatch_maps_native_busy_for_toggle_and_start():
    d, fc, mt, _, _ = _native_daemon(); d.reserve_native(object(), ID)
    srv = daemon.ControlServer(d, socket_path="/nonexistent/s4.sock")   # never started: _dispatch only
    for cmd in ('{"cmd":"toggle"}', '{"cmd":"start"}', '{"cmd":"start-block"}', '{"cmd":"start-stream"}',
                '{"cmd":"toggle-stream"}', '{"cmd":"toggle-block"}'):
        r = srv._dispatch(cmd)
        assert r["ok"] is False and r["busy"] is True and "native" in r["error"], cmd
    assert srv._dispatch('{"cmd":"status"}')["ok"] is True                 # status stays usable


def test_cancel_is_busy_without_side_effects_under_native_owner():
    d, fc, mt, _, rec = _native_daemon(); d.reserve_native(object(), ID)
    r = d.cancel()
    assert r["ok"] is False and r["busy"] is True and "native" in r["error"]


# ---- D. the startup fence (worker blocked in spawn = the cold-load barrier) ----
def _start_blocked(d, **kw):
    gate, entered = threading.Event(), threading.Event()
    f = _gated_host_factory(entered, gate, []); f.daemon = d
    d._host_factory = f                                       # the lazy loader picks the gated factory
    res = d.reserve_native(object(), ID, on_end=_Ends()); assert res.accepted
    assert d.begin_native_start(res.owner.token, **kw) is True
    assert td._wait_for(entered.is_set)                       # worker is inside spawn, no lock held
    return gate, res


def test_status_and_stop_stay_responsive_during_blocked_load():
    d, fc, mt, mic, _ = _native_daemon(); gate, res = _start_blocked(d)
    out = {}
    t = threading.Thread(target=lambda: out.update(snap=d.status_snapshot(), stopped=d.stop()))
    t.start(); t.join(timeout=1.0)
    assert not t.is_alive() and "listening" in out["snap"]     # both returned while spawn was blocked
    assert d._native.stage is Stage.ENDED and d._native.end.reason == "stopped"
    assert d._native.end.cause == "stop-during-start"
    gate.set(); d._native_worker.join(timeout=5.0)
    assert not d._native_worker.is_alive() and d._arming is None and not d._listening.is_set()
    assert all(not on for on, _ in mic)                       # capture never opened


def test_stop_during_startup_delivers_end_once_before_worker_returns():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); gate = threading.Event(); entered = threading.Event()
    f = _gated_host_factory(entered, gate, mic); f.daemon = d; d._host_factory = f
    res = d.reserve_native(object(), ID, on_end=ends); assert d.begin_native_start(res.owner.token)
    assert td._wait_for(entered.is_set)
    assert d.stop() is None and len(ends.records) == 1        # delivered NOW, not after the load
    assert ends.records[0].stage is Stage.STARTING and mt.cancelled                 # watchdog retired
    gate.set(); d._native_worker.join(timeout=5.0)
    assert len(ends.records) == 1 and all(not on for on, _ in mic)


def test_start_cap_timer_ends_reservation_as_timeout():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); gate, res = _start_blocked(d); d._native_end_cb = ends
    fc.advance(START_CAP_S + 0.001); mt.fire(mt.armed[0][0])
    assert len(ends.records) == 1 and ends.records[0].reason == "timeout" and ends.records[0].cause == "start-cap"
    gate.set(); d._native_worker.join(timeout=5.0)
    assert len(ends.records) == 1 and all(not on for on, _ in mic) and d._arming is None


def test_late_commit_after_cap_is_refused_host_left_idle():
    """Timer NEVER fires; the worker returns from spawn after the deadline → the commit block itself
    ends the reservation ('timeout') and aborts; host stays resident+idle; seed cleaned by _abort_start."""
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); gate, res = _start_blocked(d, seed="seed text")
    d._native_end_cb = ends
    fc.advance(START_CAP_S + 1.0); gate.set(); d._native_worker.join(timeout=5.0)
    assert not d._native_worker.is_alive() and len(ends.records) == 1
    assert ends.records[0].reason == "timeout" and all(not on for on, _ in mic)
    assert d._host is not None and d._arming is None and d._seed_active is False and d._listening.is_set() is False


def test_early_or_stale_timer_fire_is_ignored():
    d, fc, mt, _, _ = _native_daemon(); gate, res = _start_blocked(d); ends = _Ends(); d._native_end_cb = ends
    mt.fire(mt.armed[0][0])                                   # clock NOT advanced → early fire
    assert d._native.stage is Stage.STARTING and not ends.records
    gate.set(); d.stop(); assert d._native.end.reason == "stopped"


# ---- E. commit is atomic with capture; end paths ----
def test_commit_hook_flips_stage_in_same_lock_hold_as_mic_open():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); res = d.reserve_native(object(), ID, on_end=ends)
    assert d.begin_native_start(res.owner.token) is True
    d._native_worker.join(timeout=10.0)                       # warm fake host: load + arm complete
    assert not d._native_worker.is_alive() and d._native.stage is Stage.LISTENING and d._listening.is_set()
    assert mic and mic[0] == (True, Stage.LISTENING)          # stage already LISTENING when the mic opened
    assert len(mt.cancelled) == 1 and not ends.records and d._arming is None


def test_disarm_ends_listening_owner_with_drain_reason_via_parked_worker():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); res = d.reserve_native(object(), ID, on_end=ends)
    d.begin_native_start(res.owner.token); d._native_worker.join(timeout=10.0)
    d.stop()                                                  # _request_stop tags 'stopped' → _disarm stashes
    d._native_worker.join(timeout=5.0)
    assert not d._native_worker.is_alive() and len(ends.records) == 1
    assert ends.records[0].stage is Stage.DRAINING and ends.records[0].reason == "stopped"
    assert d._native.stage is Stage.ENDED and not d._listening.is_set()


def test_idle_auto_stop_path_records_idle_reason():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); res = d.reserve_native(object(), ID, on_end=ends)
    d.begin_native_start(res.owner.token); d._native_worker.join(timeout=10.0)
    d._native_drain_or_stop("idle"); d.stop(); d._native_worker.join(timeout=5.0)
    assert len(ends.records) == 1 and ends.records[0].reason == "idle"


def test_host_death_and_shutdown_end_the_reservation():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); res = d.reserve_native(object(), ID, on_end=ends)
    d.begin_native_start(res.owner.token); d._native_worker.join(timeout=10.0)
    d._handle_dead_host()
    assert len(ends.records) == 1 and ends.records[0].reason == "disconnected" and ends.records[0].cause == "host-died"
    res2 = d.reserve_native(object(), ID2, on_end=ends)       # STARTING owner, no worker
    d.request_shutdown()
    assert [r.reason for r in ends.records] == ["disconnected", "shutdown"] and d._native.stage is Stage.ENDED


# ---- F. exactly-once, off-lock delivery ----
def test_three_way_race_delivers_exactly_once():
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); gate, res = _start_blocked(d); d._native_end_cb = ends
    fc.advance(START_CAP_S + 1.0)
    ts = [threading.Thread(target=f) for f in (
        lambda: d.stop(), lambda: mt.fire(mt.armed[0][0]), lambda: d.terminate_native("disconnected", token=1))]
    [t.start() for t in ts]; [t.join(timeout=5.0) for t in ts]
    assert len(ends.records) == 1 and ends.records[0].reason in ("stopped", "timeout", "disconnected")
    gate.set(); d._native_worker.join(timeout=5.0)
    assert len(ends.records) == 1 and all(not on for on, _ in mic)


def test_end_callback_runs_off_lock_and_exceptions_are_swallowed(caplog):
    import logging
    d, fc, mt, _, _ = _native_daemon(); res = d.reserve_native(object(), ID)
    seen = []
    def hook(rec): seen.append(d.status_snapshot())            # takes _lock → would deadlock under it
    d._native_end_cb = hook; d.terminate_native("stopped", token=1); assert len(seen) == 1
    d.reserve_native(object(), ID2)
    def boom(rec): raise RuntimeError("secret seed text must not leak")
    d._native_end_cb = boom
    with caplog.at_level(logging.WARNING):
        d.terminate_native("shutdown", token=2)
    assert d._native.stage is Stage.ENDED and "secret" not in caplog.text
    assert "RuntimeError" in caplog.text                     # type name only


def test_no_text_leaks_in_logs_or_records(caplog):
    d, fc, mt, mic, _ = _native_daemon(); ends = _Ends(); gate, res = _start_blocked(d, seed="SEED-DO-NOT-LOG")
    d._native_end_cb = ends
    import logging
    with caplog.at_level(logging.DEBUG):
        fc.advance(START_CAP_S + 1.0); gate.set(); d._native_worker.join(timeout=5.0)
        d.start_context("CTX-DO-NOT-LOG")
    blob = caplog.text + repr(ends.records) + repr(d.status_snapshot())
    assert "SEED-DO-NOT-LOG" not in blob and "CTX-DO-NOT-LOG" not in blob


def test_scope_and_existing_behavior_without_native_owner():
    d, fc, mt, mic, _ = _native_daemon()                       # no reservation: legacy paths untouched
    d.start(); assert d._listening.is_set() and mic[-1][0] is True and mic[-1][1] is None
    d.stop(); assert not d._listening.is_set()
    assert d.cancel()["ok"] is True and d._native is None
```

Notes for the implementer: the gated factory forwards `*a, **k` to `td._fake_host_factory()`'s
factory (the lazy loader may pass positional args). `_start_blocked` sets `d._host_factory` so the
worker's `_load_host()` picks the gated factory; if the lazy loader caches a factory elsewhere, set the
same attribute `_load_host` reads (grep `host_factory` in `_load_host`, daemon.py:1098-1217). Warm-host
tests use a 10 s join because the fake `spawn` returns immediately. Run the file once with `-x -q` to
fail fast on the first harness mismatch, then the full suite.
