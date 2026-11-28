# PRP — P1.M1.T4.S6: Finalize ownership and surface private failure hints

## Goal

**Feature Goal**: Make every way a native editor session (PRD §4.8.1 B/C) can end finish through
**one exactly-once cleanup**, and tell the user *what happened* without ever telling them *what was said*.

| end cause (already produced by S5's `_end_native_locked`) | cleanup S6 adds (off-lock, once) | wire `ended.reason` | desktop warning | status `native` block |
|---|---|---|---|---|
| owner stop / `voicectl stop` / idle | seed clear, recovery finalised, callbacks | `stopped` / `idle` | none | reason + hint (`none` unless unconfirmed text exists) |
| owner cancel | same | `cancelled` | none | hint `none` (unless an unverified edit may have landed) |
| owner `lost`, EOF, lease expiry | same | `target_lost` / `disconnected` / `timeout` | **only for `disconnected` / `timeout`** (transport gone ⇒ editor UI may be gone) | reason + hint |
| shutdown / `quit` / SIGTERM | same + **recovery store expired** | `shutdown` | none | reason + hint (until process exit) |
| recorder-host child death | same, **no drain** | `load_failed` (STARTING) / `disconnected` | none (transport still alive) | reason + hint |
| idle-unload watchdog fires while an owner is live | **unload deferred** (never kills the child under a live owner) | — | — | — |

**Deliverable** (3 files edited, 1 created):
1. `voice_typing/daemon.py` — `NativeEndState` + `NativeStatus`, `_native_finish_locked` inside the terminal
   action, the restructured off-lock `_flush_native_end` (cleanup → `on_end` → teardown callback),
   `set_native_teardown` / `native_last_end`, the always-present lock-free `native` status block, the
   `_unload_host` live-owner guard, recovery expiry at exit, the bounded desktop-warning sink;
   [Mode A] termination/status docstrings.
2. `voice_typing/ctl.py` — `status` rendering of the `native` block + its help line.
3. `tests/test_daemon.py` — **one line**: the expected key set of
   `test_status_snapshot_keys_and_cuda_values` gains `"native"` (the test pins `set(s)` exactly).
4. `tests/test_native_teardown.py` — hermetic CPU-only tests (new).

**Success Definition**:
- (a) Every end path (stop, cancel, lost×3, settle timeout, start-cap, `_stop_native_start`,
  `terminate_native`, dead host, `request_shutdown`, `shutdown`) leaves exactly one `on_end` call,
  exactly one teardown-callback call, `NativeRecovery.active_id() is None`, and `native_last_end()`
  set — and a repeated/late call adds nothing.
- (b) `ended` frame == `{"event":"ended","id":<sid>,"reason":<EndRecord.reason>,"recoverable":<bool>}`
  — exactly those 4 keys; passes `editor_protocol.validate_event`.
- (c) `recoverable` is True iff `NativeRecovery.recover(sid)` returns a snapshot after `end_session`,
  except that a `cancelled` session is never "recoverable" unless `snapshot.possibly_applied`.
  Hint codes: `none` | `recover` | `recover_maybe_applied` (stable, transcript-free).
- (d) Desktop warning is attempted iff reason ∈ {`disconnected`, `timeout`}; text is a fixed template
  containing only the opaque session id — never transcript/seed; sink is injectable and bounded (≤1 s).
- (e) `status_snapshot()["native"]` is always present, built from one immutable attribute (no lock, no
  reservation/queue/recovery access), and carries only `{state, id, reason, recoverable, hint}` codes.
- (f) Shutdown (`request_shutdown` AND `shutdown()`) expires `NativeRecovery` (store empty, reusable);
  shutdown and dead host end a STARTING/LISTENING/DRAINING session with **no drain** (`_drain` False,
  `host.abort()`/`host.cancel()` never called) and retire the settle/start timers.
- (g) `_maybe_idle_unload()` / `_unload_host()` never stop the host while `_native_owner_live_locked()`;
  after the session ends the next tick unloads normally (idle-unload tests in `tests/test_daemon.py`
  stay green).
- (h) `status_snapshot()`, `stop()`, `request_shutdown()` each return < 1 s with an owner in STARTING
  (reserved, no worker), LISTENING, DRAINING and ENDED.
- (i) Content tripwires: after each end path, feedback snapshot, feedback notifications, the injected
  warning sink, `caplog`, the status `native` block, `NativeEndState` and the frame contain neither the
  transcript nor the seed string used in the test.
- (j) With no native reservation ever, `status_snapshot()` differs from today only by the added
  `native` key (`{"state":"inactive","id":None,"reason":None,"recoverable":False,"hint":None}`);
  `tests/test_daemon.py` FAILED set == G1 baseline (set-diff).
- (k) `host.abort()` / `host.cancel()` / `end_session` / callbacks / warning sink never run under
  `d._lock`; only `end_session` (a leaf store with its own lock, no callbacks) runs inside the
  terminal lock hold.
- (l) `timeout 300 .venv/bin/python -m pytest tests/test_native_teardown.py tests/test_native_lifecycle.py
  tests/test_editor_session.py tests/test_native_recovery.py tests/test_editor_offer_queue.py
  tests/test_native_final_route.py -q` → green.
- (m) `git diff --name-only` == `{voice_typing/daemon.py, voice_typing/ctl.py,
  tests/test_native_teardown.py, tests/test_daemon.py}` (+ a test that pins the `status` help text,
  if Task 0 finds one).

## User Persona

**Target User**: the dictation user inside a native editor (Pi prompt, Neovim) — and the same user at a
bare terminal when the editor vanished mid-dictation.
**Use Case**: Start from the editor, speak, then the editor crashes / the lease expires / the daemon is
quit / the recorder child dies. Later the user runs `voicectl status` or reads the journal to learn
*why* dictation stopped and *whether* unconfirmed words can be recovered with `voicectl recover <id>`.
**Pain Points Addressed**: silent stops with no reason; a recovery hint that leaks dictated words into
status/logs/notifications; a quit that leaves recovery text in memory; an idle-unload that kills the
models out from under a starting/draining editor session; a `status` that blocks while the owner is
starting or settling.

## Why

- PRD §4.8.1 C: "Always retain transcript-free last abnormal end reason and recovery hint in
  `voicectl status` and log same diagnostic, even if notifier succeeds." "For suspended/closed editor,
  daemon attempts transcript-free warning with recovery hint via freedesktop notifications (e.g.
  `notify-send` if available). Configured desktop notifier optional fallback, never dependency."
  Warning example: "Dictation stopped: draft or caret changed. Start again here. Unconfirmed text:
  `voicectl recover <id>`." "No durable recovery promised after daemon restart."
- PRD §4.8.1 B: last frame `{"event":"ended","id":"...","reason":"<code>","recoverable":true}`;
  exactly one `ended`; "Shutdown/host failure clean up without promising a recoverable drain."
- `architecture/system_context.md` → "Control/recorder boundaries": "`_handle_dead_host` and
  `request_shutdown` need native teardown; use existing nonblocking ducking and idle-unload transitions
  … no redesign." "Sanitized abnormal reason/hint are metadata only." "Keep status/stop/quit responsive
  while the owner starts, blocks on reads/writes, drains or is lost." → "Buffer ownership and recovery":
  NativeRecovery "stores at most two nonempty ended sessions of 1 MiB UTF-8 … Recovery is one-shot
  explicit read (`voicectl recover [ID]` …), entirely separate from `voicectl session`."
- Chain: T3.S4 supplies `on_end(EndRecord)` exactly once off-lock via `_claim_native_end_locked` /
  `_flush_native_end`, `terminate_native(reason, cause=, token=)`, `_stop_native_start`, the owner-token
  tombstone. T4.S1 supplies `NativeRecovery.end_session(sid, reason)`, `recover(sid)`, `active_id()`,
  `clear()` ("Daemon exit … drop everything … No persistence"). T4.S5 supplies THE terminal action
  `_end_native_locked`, `NativeEndFacts(reason, revoked, recoverable)`, and says verbatim: "T4.S6
  (ended frame + hints): read `d._native_end_facts` when `on_end` fires; … then call
  `d._native_recovery.end_session(sid, reason)`." S5 also assigns the `ended` **frame** and desktop
  hints to this item and leaves `request_shutdown` / `_handle_dead_host` "NO change (terminate_native →
  `_end_native_locked` ends a settling session at once)" — S6 completes and proofs that.

## What

### Success Criteria
- [ ] New daemon surface: `NATIVE_HINT_*`, `_NATIVE_DESKTOP_WARN_REASONS`, `NativeEndState`,
      `NativeStatus`, `native_end_hint`, `build_ended_frame`, `set_native_teardown`, `native_last_end`,
      `_native_finish_locked`, `_publish_native_status_locked`, `_desktop_warning`,
      `_native_expire_at_exit`; state `_native_last_end`, `_native_status`, `_native_teardown_cb`,
      `_native_warning_sink`.
- [ ] (a)–(m) hold.
- [ ] Not in scope (owned elsewhere): the `finishing` frame and any socket write — T4.S7's `OwnerPump`
      serialises `state.frame()` via `send_event` and emits `finishing` on `_native_offer_evt`
      (S5 handoff); `voicectl recover` — T5.S1/S2; the editor-side "draft or caret changed" warning —
      the adapters (P1.M2.T1/T2); config keys; `editor_protocol.py`, `session_recovery.py`,
      `feedback.py`, `recorder_host.py` (read-only here); `tests/test_native_lifecycle.py` (S5's).

## All Needed Context

### Context Completeness Check

_Pass._ The current body of the terminal action, end flush, dead-host handler, idle-unload condition,
shutdown paths, status key list, recovery API, protocol validator, harness names and the exact
resolutions of every open contract question (`research/decisions.md`) are given below. The implementer
needs this PRP, `research/seam_census.md`, `research/contract_chain.md`, `research/prd_requirements.md`,
`research/decisions.md`, and the named slices of `daemon.py` / `ctl.py`.

### Documentation & References

```yaml
- url: https://docs.python.org/3/library/dataclasses.html#frozen-dataclasses
  why: "NativeEndState / NativeStatus are frozen value objects read lock-free by status"
  critical: "no dict/list fields on a frozen dataclass that must stay hashable — expose frame as a method returning a fresh dict"
- url: https://docs.python.org/3/library/subprocess.html#subprocess.run
  why: "notify-send attempt in _desktop_warning (precedent: ducking's bounded wpctl/playerctl calls)"
  critical: "timeout=1.0, check=False, DEVNULL stdio; catch TimeoutExpired + OSError; never raise into the end path"
- url: https://docs.python.org/3/library/shutil.html#shutil.which
  why: "'notify-send if available … never dependency' — probe with which(); fall back to feedback.notify"
- url: https://docs.python.org/3/library/threading.html#threading.Event.wait
  why: "responsiveness tests bound calls with time.monotonic(); no code in this task waits on an Event"
  critical: "end_evt.set() already happens in _end_native_locked (S5) — do not wait on it anywhere"

- docfile: plan/009_ef3b49b0fc0d/P1M1T4S6/research/decisions.md
  why: "the six contract-chain open questions RESOLVED (finishing ownership, recoverable source, load_failed code, hint/status schema, teardown callback shape, seed clear, idle-unload rule) — the spec below follows these resolutions"
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S6/research/seam_census.md
  why: "every _native_* attribute with meaning, _FakeFeedback/_FakeHost API, state.json keys, ctl rendering lines"
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S6/research/contract_chain.md
  why: "verbatim T3.S4/T4.S1/S4/S5 contracts this item consumes; section F lists the questions decisions.md closes"
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S6/research/prd_requirements.md
  why: "verbatim PRD §4.8.1 B/C/D, §6 T10b/T10c, §7(7) text; PRD-SILENT topics"
- docfile: plan/009_ef3b49b0fc0d/P1M1T4S5/PRP.md
  why: "CONTRACT — 'Implementation Patterns & Key Details' → HANDOFF CONSUMER CONTRACT and the _end_native_locked blueprint this item extends"
- file: voice_typing/daemon.py
  why: "THE module edited. Read before editing: _end_native_locked, _claim_native_end_locked, _flush_native_end,
        terminate_native, _stop_native_start, native_stop / native_lost (the r.begin_drain lines),
        _native_open_capture_locked, reserve_native, _handle_dead_host, _maybe_idle_unload, _unload_host,
        request_shutdown, shutdown, status_snapshot, _clear_context_prompt, __init__ native block (_native_end_cb …)"
  pattern: "every funnel = one lock hold that decides+stores, then off-lock side effects; on_end via _flush_native_end only"
  gotcha: "_flush_native_end RETURNS EARLY today when on_end is None — cleanup must not depend on a callback being registered"
- file: voice_typing/editor_session.py
  why: "Stage (STARTING|LISTENING|DRAINING|ENDED), EndRecord(owner, stage, reason, cause, ended_at),
        NativeReservation.live / .stage / .owner.id / .owner.token, end_evt"
  gotcha: "READ ONLY. A ended reservation stays in self._native (tombstoned token; _native_owner_live_locked() is False) — never null it"
- file: voice_typing/session_recovery.py
  why: "NativeRecovery.end_session(session_id, reason) :409 ('Nothing retained after the ACKs → DISCARDED'),
        recover(session_id=None) :428 (ended id → that session; None → latest ENDED), active_id() :448, clear() :463 ('Daemon exit … drop everything')"
  pattern: "call end_session UNDER _lock inside the terminal action (leaf store, own lock, no callbacks), then recover(sid) for the truth"
- file: voice_typing/editor_protocol.py
  why: "EVENT key table :317-318 ('ended': {'event','id','reason','recoverable'}), validate_event(obj) :322 (:353 checks reason ∈ END_REASONS),
        END_REASONS :144 (includes load_failed), OwnerPump.send_event :628 (T4.S7's writer — NOT called here)"
- file: voice_typing/ctl.py
  why: "format_result status lines :255-300 (f-string lines: listening/mode/output/phase/partial/…; delivery block reads
        response.get(...) with defaults); _build_parser help :21-35; exit codes 0/1/2/64"
- file: tests/test_daemon.py
  why: "_FakeFeedback :36 (update_partial/set_phase/snapshot/set_models_loaded/set_mode/notify :29),
        _FakeHost :783 (is_alive :52, abort :62, cancel :65 → cancel_calls, stop(timeout) :84 records),
        _FakeBackend :739, _make_daemon :904; test_status_snapshot_keys_and_cuda_values :2196 asserts
        `set(s) == {…}` at :2211 — ADD \"native\" THERE; test_idle_unload_fires_when_disarmed_beyond_threshold :4206;
        test_handle_dead_host_noop_when_host_already_cleared :4637"
- file: tests/test_native_lifecycle.py   # S5's harness — COPY, do not edit
  why: "FakeClock + ManualTimers, _BHost(td._FakeHost) with capture_boundary, _ev(), _listening_native(), _in_flight(),
        _text_returned(), tripwire backend — reuse the same helpers verbatim"
- file: tests/test_editor_session.py
  why: "test_handle_dead_host :258 and test_request_shutdown :261 already assert the T3.S4 end — must stay green"
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py             # ~4800 lines, S5 landing uncommitted; anchor by symbol      ← EDIT
voice_typing/ctl.py                # format_result status lines :255-300; help :21-35            ← EDIT
voice_typing/editor_protocol.py    # ended key set :318, validate_event :322, END_REASONS :144  READ ONLY
voice_typing/editor_session.py     # Stage / EndRecord / NativeReservation                       READ ONLY
voice_typing/session_recovery.py   # NativeRecovery.end_session :409 / recover :428 / clear :463 READ ONLY
voice_typing/feedback.py           # notify(msg) (hyprctl, gated by cfg.feedback.hypr_notify)     READ ONLY
tests/test_daemon.py               # harness + exact status key set :2211                       ← ONE LINE
tests/test_native_lifecycle.py     # S5's harness (untracked while S5 lands)                     do NOT edit
tests/test_native_teardown.py                                                                   ← CREATE
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
voice_typing/daemon.py
  + NATIVE_HINT_NONE / NATIVE_HINT_RECOVER / NATIVE_HINT_RECOVER_MAYBE_APPLIED, _NATIVE_DESKTOP_WARN_REASONS,
    _NATIVE_WARN_TEXT                                                   (next to NATIVE_SETTLE_TIMEOUT_S)
  + @dataclass(frozen=True) class NativeEndState   session_id, reason, cause, recoverable, possibly_applied, hint;
                                                 frame() -> dict; desktop_warning: str | None
  + @dataclass(frozen=True) class NativeStatus    state, session_id, reason, recoverable, hint; as_dict() -> dict
  + def native_end_hint(reason, snapshot) -> tuple[bool, str]           pure
  + def build_ended_frame(session_id, reason, recoverable) -> dict       pure
  + __init__: _native_last_end = None; _native_status = NativeStatus.inactive();
              _native_teardown_cb = None; _native_warning_sink = self._desktop_warning
  + set_native_teardown(cb) / native_last_end() -> NativeEndState | None
  + _native_finish_locked(rec, facts) -> NativeEndState     # inside the terminal lock hold
  + _publish_native_status_locked() -> None
  + _desktop_warning(msg) -> None                           # bounded, best-effort, injectable sink
  + _native_expire_at_exit() -> None                        # self._native_recovery.clear()
  ~ _end_native_locked        → calls _native_finish_locked after the facts stash
  ~ _flush_native_end         → cleanup (seed clear, diagnostic log, desktop warning) THEN on_end THEN teardown cb
  ~ reserve_native / _native_open_capture_locked / native_stop / native_lost → _publish_native_status_locked()
  ~ _unload_host              → live-owner guard in the under-lock condition
  ~ request_shutdown / shutdown → _native_expire_at_exit()
  ~ docstrings [Mode A]: _end_native_locked, _flush_native_end, terminate_native, _handle_dead_host,
                        request_shutdown, shutdown, _unload_host, status_snapshot
voice_typing/ctl.py              ~ format_result: native block lines; help: status line mentions native   ← EDIT
tests/test_daemon.py             ~ :2211 expected key set += "native"
tests/test_native_teardown.py    — (a)–(k)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — _flush_native_end TODAY RETURNS EARLY when self._native_end_cb is None. Restructure so the
# cleanup (seed clear, log, warning) runs for EVERY end, callbacks or not. Exactly-once comes ONLY from
# _claim_native_end_locked (T3.S4) — keep that claim as the first statement.
# CRITICAL #2 — NOTHING BLOCKING UNDER _lock OR ON THE READER. Inside _end_native_locked the only S6 call is
# _native_finish_locked → NativeRecovery.end_session/recover (leaf store, own lock, no callbacks). The seed
# clear (_clear_context_prompt: a queue put), the warning sink (≤1 s) and both callbacks run in
# _flush_native_end AFTER the lock is released. No end path runs on the recorder reader thread.
# CRITICAL #3 — THE ENDED RESERVATION STAYS IN self._native (tombstoned token). Status must not read it
# lock-free: _native_status is an immutable attribute published under _lock and read as ONE reference.
# CRITICAL #4 — status_snapshot's KEY SET IS PINNED by tests/test_daemon.py:2211 (`set(s) == {...}`).
# Add "native" there; grep tests/ for any other exact pin in Task 0.
# CRITICAL #5 — recoverable TRUTH = NativeRecovery.recover(sid) AFTER end_session (a fully-ACKed/empty ending
# is DISCARDED → None). NativeEndFacts.recoverable (S5: q.drain_pending()) is only a cross-check.
# CRITICAL #6 — CANCELLED sessions are never "recoverable" unless snapshot.possibly_applied (the user asked
# to drop the words; only an unverified edit that may have landed must be reported).
# CRITICAL #7 — _handle_dead_host's RACE GUARD returns before terminate_native when _unload_host already ran.
# With the new _unload_host guard no owner can be live at that point; do not weaken the guard.
# CRITICAL #8 — host.abort()/cancel() on a DEAD host or without a thread inside text() block forever
# (_safe_abort gate). Dead-host/shutdown paths end via terminate_native ONLY — never via _disarm/_safe_abort.
# CRITICAL #9 — LATE TIMER FIRE: Timer.cancel() is a flag. S5 already retires both handles in the terminal
# action; S6 adds no timer. A late fire for an ended owner hits `r.live is False` → None (keep it that way).
# CRITICAL #10 — SEED: never write _seed_active / _seed_handoff_pending (T2.S4 rule: set only by the fenced
# seam). "Clear seed" = call the existing best-effort _clear_context_prompt() off-lock (no-op when
# context_prompt is off, capability is not True, or no host) — exactly what a plain _arm does.
# CRITICAL #11 — LOGS: codes/counts/ids only. Never text, seed, or a ProtocolError detail; exception type
# names only (type(exc).__name__).
# CRITICAL #12 — AGENTS.md: every command under `timeout` with the bash-tool timeout above it; .venv/bin/python;
# tests/test_daemon.py = `timeout 500 … --tb=no` with bash timeout ≥ 560; never run the daemon or voicectl.
# CRITICAL #13 — DO NOT EDIT editor_protocol.py, editor_session.py, session_recovery.py, feedback.py,
# recorder_host.py, tests/test_native_lifecycle.py, tests/test_editor_session.py, any plan file, PRD.md,
# tasks.json, README.md. Do not implement T4.S7 (pump/socket writes, finishing) or T5 (voicectl recover).
```

## Implementation Blueprint

### Data models and structure

```python
# module level, next to NATIVE_SETTLE_TIMEOUT_S
NATIVE_HINT_NONE = "none"
NATIVE_HINT_RECOVER = "recover"                                   # unconfirmed text is retained
NATIVE_HINT_RECOVER_MAYBE_APPLIED = "recover_maybe_applied"       # … and an edit may already have landed
_NATIVE_DESKTOP_WARN_REASONS = frozenset({"disconnected", "timeout"})   # transport gone ⇒ editor UI may be gone
_NATIVE_WARN_TEXT = {   # fixed, transcript-free; <id> is the opaque session UUID
    "disconnected": "Dictation stopped: editor connection lost. Start again in your editor.",
    "timeout": "Dictation stopped: editor stopped responding. Start again in your editor.",
}
_NATIVE_ABNORMAL = frozenset({"cancelled", "timeout", "target_lost", "disconnected", "delivery_failed",
                              "load_failed", "shutdown"})          # everything except stopped / idle

@dataclasses.dataclass(frozen=True)
class NativeEndState:
    """Transcript-free end state of ONE native session (P1.M1.T4.S6). Built under _lock in the terminal
    action; consumed off-lock by on_end's caller, the teardown callback, status and the warning."""
    session_id: str
    reason: str            # EndRecord.reason — the wire `ended.reason` (codec-validated)
    cause: str | None      # EndRecord.cause (fixed code)
    recoverable: bool
    possibly_applied: bool
    hint: str              # NATIVE_HINT_*

    def frame(self) -> dict:            # PRD §4.8.1 B — EXACTLY these four keys
        return build_ended_frame(self.session_id, self.reason, self.recoverable)

    @property
    def desktop_warning(self) -> str | None:
        if self.reason not in _NATIVE_DESKTOP_WARN_REASONS:
            return None
        msg = _NATIVE_WARN_TEXT[self.reason]
        if self.recoverable:
            msg += f" Unconfirmed text: voicectl recover {self.session_id}"
            if self.possibly_applied:
                msg += " (may already be partially typed)"
        return msg

@dataclasses.dataclass(frozen=True)
class NativeStatus:
    """The `native` block of status_snapshot(): published under _lock, read lock-free."""
    state: str             # "inactive" | "starting" | "listening" | "draining" | "ended"
    session_id: str | None
    reason: str | None
    recoverable: bool
    hint: str | None
    @classmethod
    def inactive(cls): return cls("inactive", None, None, False, None)
    def as_dict(self): return {"state": self.state, "id": self.session_id, "reason": self.reason,
                               "recoverable": self.recoverable, "hint": self.hint}

def native_end_hint(reason: str, snapshot) -> tuple[bool, str]:
    """(recoverable, hint) from the recovery snapshot taken AFTER end_session. Pure."""
    if snapshot is None:
        return False, NATIVE_HINT_NONE
    if reason == "cancelled" and not snapshot.possibly_applied:
        return False, NATIVE_HINT_NONE
    if snapshot.possibly_applied:
        return True, NATIVE_HINT_RECOVER_MAYBE_APPLIED
    return True, NATIVE_HINT_RECOVER

def build_ended_frame(session_id: str, reason: str, recoverable: bool) -> dict:
    return {"event": "ended", "id": session_id, "reason": reason, "recoverable": bool(recoverable)}

# __init__ — after self._native_end_facts
self._native_last_end: NativeEndState | None = None        # last ended session (survives the next reserve)
self._native_status = NativeStatus.inactive()              # the ONE attribute status reads
self._native_teardown_cb: Callable[[NativeEndState], None] | None = None   # T4.S7 registers it
self._native_warning_sink: Callable[[str], None] = self._desktop_warning  # tests inject a recorder
```

```python
# THE TERMINAL ACTION — S5's _end_native_locked with the S6 insertion (still idempotent, still under _lock)
def _end_native_locked(self, reason, cause, *, now=None):
    r = self._native
    if r is None or not r.live:
        return None
    rec = r.terminate(reason, cause, now=self._native_clock() if now is None else now)
    q = self._native_queue
    self._native_end_facts = NativeEndFacts(...)            # S5 lines unchanged
    ...                                                     # S5: retire settle handle, clear boundary
    self._native_finish_locked(rec, self._native_end_facts) # P1.M1.T4.S6: recovery final + end state + status
    ...                                                     # S5: _native_close_capture_locked, start timer, end_evt.set, log
    return rec

def _native_finish_locked(self, rec: EndRecord, facts: NativeEndFacts) -> NativeEndState:
    sid = rec.owner.id
    self._native_recovery.end_session(sid, rec.reason)      # T4.S1: retains ONLY unconfirmed finals; empty → discarded
    snapshot = self._native_recovery.recover(sid)           # None ⇒ nothing to recover
    recoverable, hint = native_end_hint(rec.reason, snapshot)
    state = NativeEndState(sid, rec.reason, rec.cause, recoverable,
                           bool(snapshot.possibly_applied) if snapshot else False, hint)
    self._native_last_end = state
    self._publish_native_status_locked()
    return state

def _publish_native_status_locked(self) -> None:            # caller holds _lock; attribute store only
    r = self._native
    if r is None or not r.live:
        e = self._native_last_end
        self._native_status = (NativeStatus("ended", e.session_id, e.reason, e.recoverable, e.hint)
                               if e else NativeStatus.inactive())
    else:
        self._native_status = NativeStatus(r.stage.value.lower(), r.owner.id, None, False, None)
```

### Implementation Tasks (ordered by dependencies — TDD: tests FIRST)

```yaml
Task 0: PREFLIGHT (read-only, bounded):
  git log --oneline -1; git status --short | head          # S5 must have LANDED (tests/test_native_lifecycle.py green)
  grep -nE "def (_end_native_locked|_claim_native_end_locked|_flush_native_end|terminate_native|_stop_native_start|
            native_stop|native_lost|_native_open_capture_locked|reserve_native|_handle_dead_host|_maybe_idle_unload|
            _unload_host|request_shutdown|shutdown|status_snapshot|_clear_context_prompt|set_ducked)\b" voice_typing/daemon.py
  sed -n '<_flush_native_end range>p;<_unload_host condition range>p;<request_shutdown range>p' voice_typing/daemon.py
  grep -n "_session_recovery.clear()\|_native_recovery" voice_typing/daemon.py        # :3797 is the exit clear to sit beside
  sed -n '2211,2225p' tests/test_daemon.py                 # the exact `set(s) == {…}` literal to extend
  grep -rnE "set\(s\) ==|\"uptime_s\",\s*\"device\"" tests/ | head                  # any OTHER exact status-key pin
  grep -rnE "context-prompt \+ output|status .*Print|\"status\":" tests/test_voicectl.py tests/test_control_socket.py | head
  grep -n "def notify" -A 3 tests/test_daemon.py          # what _FakeFeedback.notify records (attr name)
  grep -n "def clear_pending" -A 14 voice_typing/editor_session.py   # INFORMATIONAL: does it touch recovery? (hint rule #6 holds either way)
  grep -n "status_snapshot()" voice_typing/daemon.py      # confirm the control-socket `status` reply carries the snapshot keys verbatim
  grep -c "Lock()" voice_typing/daemon.py                 # N — must equal N after the edit (no new lock)
  baseline: timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no 2>&1 | tail -40   # bash timeout ≥ 560
  timeout 300 .venv/bin/python -m pytest tests/test_native_lifecycle.py tests/test_editor_session.py -q   # green BEFORE you start

Task 1: CREATE tests/test_native_teardown.py (RED first). CPU-only; no threads/sockets/subprocess started by a test.
  HARNESS (copy verbatim from tests/test_native_lifecycle.py — do NOT import it): `import test_daemon as td`;
  FakeClock + ManualTimers; `d._native_clock, d._native_timers = fc.now, mt` right after `td._make_daemon(...)`;
  _BHost, _ev, _listening_native, _in_flight, _text_returned, tripwire backend (type_text/press_backspace → pytest.fail).
  SID = "0f8e7c2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b"; TEXT = "hello world"; SEED = "the quick seed phrase".
  Add: class _Sink (records messages; asserts `not d._lock.locked()`); d._native_warning_sink = sink.msg
       class _Teardown (records NativeEndState; asserts not locked); d.set_native_teardown(td_cb.record)
       def _fb_texts(d, fb): every str value of fb.snapshot() + every recorded fb.notify message
       def _no_text(everywhere, *needles): for each str in everywhere: assert all(n not in s for n in needles)
  TESTS (names fixed):
  - test_stop_without_text_ends_once_and_publishes_state         native_stop("stopped") → ENDED; ends.records == 1;
      td_cb.states == 1 (sid, "stopped", recoverable False, hint "none"); active_id() None; native_last_end() is
      that state; sink.msgs == []; second native_stop → None, counters unchanged
  - test_ended_frame_has_exactly_the_prd_keys                     state.frame().keys() == {"event","id","reason",
      "recoverable"}; editor_protocol.validate_event(state.frame()) returns without raising
  - test_unconfirmed_final_sets_recover_hint                      in flight → native_stop → final TEXT queued →
      _text_returned → settle deadline fires (fc.advance(5.0); mt.fire(handle)) → ENDED "timeout";
      recoverable True, hint "recover"; sink.msgs == [] (timeout here is a SETTLE timeout, not a lease loss:
      reason "timeout" IS in the warn set → expect ONE warning) — assert the one message equals
      "Dictation stopped: editor stopped responding. Start again in your editor. Unconfirmed text: voicectl recover <SID>"
      and lacks TEXT
  - test_disconnected_loss_warns_with_recovery_hint               LISTENING + retained final → native_lost("disconnected")
      → ENDED; recoverable True; sink.msgs == [disconnected template + recover hint]; desktop_warning property
      matches the sent text
  - test_target_lost_does_not_desktop_warn                        native_lost("target_lost") → sink.msgs == [];
      reason "target_lost"; hint per snapshot
  - test_acknowledged_final_is_not_recoverable                     queued final → q.ack(applied) → native_stop →
      ENDED; recover(sid) is None; recoverable False; hint "none"
  - test_cancelled_is_not_recoverable_unless_possibly_applied      (i) cancel with an unattempted retained final →
      recoverable False, hint "none", sink.msgs == []; (ii) cancel after mark_offer_attempted/begin_offer
      without ACK → hint "recover_maybe_applied", warning none (cancel is not in the warn set)
  - test_possibly_applied_warning_mentions_partial_typing         loss after begin_offer without ACK →
      recoverable True, hint "recover_maybe_applied"; the disconnected warning ends with
      "(may already be partially typed)"
  - test_shutdown_expires_recovery_and_ends_without_drain         settling + retained final → d.request_shutdown()
      → ENDED "shutdown"; d._native_recovery.recover(SID) is None and counts() == (0, 0); _drain False;
      host.aborts == 0; host.cancel_calls == 0; ends.records == 1; td_cb 1; settle handle in mt.cancelled;
      a second d.shutdown() adds nothing (idempotent) and the store stays empty
  - test_shutdown_method_alone_expires_recovery                    fresh retained session → d.shutdown() only →
      ENDED "shutdown"; store empty
  - test_dead_child_ends_without_drain_exactly_once                LISTENING + in flight; host.is_alive = False;
      d._handle_dead_host() → ENDED "disconnected" cause "host-died"; _drain False; host.aborts == 0;
      host.cancel_calls == 0; host.stop_calls == 0 (dead child is never stopped); _duck_release called once
      (wrap/count); _listening clear; d._load_error set; ends 1; td_cb 1; status native == ended/disconnected;
      second d._handle_dead_host() → all counters unchanged
  - test_dead_child_while_starting_reports_load_failed             reserve only → is_alive False → _handle_dead_host()
      → reason "load_failed", cause "host-died"; frame validate_event ok; sink.msgs == []
  - test_idle_unload_is_deferred_under_a_live_owner               _models_loaded True + host set + _disarmed_monotonic
      far past a 1.0 s threshold; (i) reserve only (STARTING), (ii) LISTENING, (iii) DRAINING settling →
      d._maybe_idle_unload() → host.stop_calls == 0 each time; after the session ends → _maybe_idle_unload()
      → host.stop_calls == 1
  - test_status_is_responsive_and_transcript_free_in_every_phase  for phase in (STARTING reserved, LISTENING with
      partial TEXT in feedback, DRAINING, ENDED): t0 = time.monotonic(); s = d.status_snapshot();
      assert time.monotonic() - t0 < 1.0; s["native"] keys == {"state","id","reason","recoverable","hint"};
      state value per phase; no value contains TEXT or SEED
  - test_stop_and_quit_are_responsive_in_every_phase               same four phases: d.stop(), d.request_shutdown()
      each < 1.0 s on a fresh daemon per phase (request_shutdown ends the session with no drain)
  - test_status_native_block_defaults_when_never_used            fresh daemon → s["native"] == {"state":"inactive",
      "id":None,"reason":None,"recoverable":False,"hint":None}; status reads NO lock (assert d._native_status
      is the object; `d._lock.locked()` is False before/after)
  - test_end_cleanup_never_runs_under_the_lock                    wrap d._native_recovery.end_session is ALLOWED
      under lock (assert d._lock.locked() when called); wrap host.abort/cancel, the sink, td_cb, on_end and
      d._clear_context_prompt → each asserts `not d._lock.locked()`; drive stop/cancel/lost/dead-host/shutdown
  - test_cleanup_runs_without_an_on_end_callback                   reserve with on_end=None → native_stop →
      native_last_end() set, td_cb fired, seed clear attempted (counter), sink per rule
  - test_seed_is_cleared_after_every_native_end                    _context_prompt_active True + host.set_prompt
      recorder → each end path → set_prompt("") called ≥1 time off-lock; with context_prompt config False →
      never called
  - test_feedback_and_logs_carry_no_content                        feed TEXT via on_final + SEED via a seeded reserve;
      every end path → caplog.text, fb.snapshot() values, fb notify msgs, sink msgs, status native values,
      dataclasses.asdict(state) all lack TEXT/SEED; the log line contains "reason=" and "hint="
  - test_abnormal_end_logs_at_warning_level                        caplog: stopped/idle → INFO line only;
      disconnected → WARNING line "voice-typing native: ended id=<sid> reason=disconnected … hint=…"
  - test_duck_is_released_on_every_end_path                       count d._duck_release calls: stop-with-drain
      (via _disarm), cancel, dead host → each ≥1; loss during STARTING → 0 (never engaged)
  - test_ctl_renders_native_state_and_hint                         ctl.format_result({"ok":True, …status keys…,
      "native":{"state":"ended","id":SID,"reason":"disconnected","recoverable":True,"hint":"recover"}}) contains
      "native: ended", "native end: disconnected", f"unconfirmed text: voicectl recover {SID}"; with state
      inactive → no "native" line; hint "recover_maybe_applied" → "(may already be partially typed)"
  - test_ctl_status_help_mentions_native                          parser = ctl._build_parser(); "native" in the
      status help
  - test_generic_paths_unchanged_without_a_native_owner           no reservation: status keys == old set ∪ {"native"};
      _maybe_idle_unload with threshold passed → host.stop_calls == 1 (guard is a no-op); request_shutdown as today
  RUN: timeout 300 .venv/bin/python -m pytest tests/test_native_teardown.py -q   → RED (bash timeout 360)

Task 2: EDIT daemon.py — constants, NativeEndState, NativeStatus, native_end_hint, build_ended_frame, __init__ state
        (Blueprint "Data models"). Place next to S5's NativeEndFacts / NATIVE_SETTLE_TIMEOUT_S.

Task 3: EDIT daemon.py — the terminal action: insert `self._native_finish_locked(rec, self._native_end_facts)`
        in _end_native_locked right AFTER the facts stash and BEFORE the settle-handle retire. Add
        _native_finish_locked + _publish_native_status_locked (Blueprint).

Task 4: EDIT daemon.py — restructure _flush_native_end (behaviour for on_end unchanged; cleanup new):
    def _flush_native_end(self) -> None:
        with self._lock:
            rec = self._claim_native_end_locked()          # T3.S4 exactly-once claim — KEEP FIRST
        if rec is None: return
        state = self._native_last_end
        if state is None or state.session_id != rec.owner.id:
            state = None                                   # defensive: never hand out another session's state
        # 1) seed clear — best-effort, off-lock, no-op when inactive/no host (T2 rule: never write _seed_* flags)
        self._clear_context_prompt()
        # 2) the PRD §4.8.1 C diagnostic — codes/ids only
        line = "voice-typing native: ended id=%s reason=%s cause=%s recoverable=%s hint=%s"
        args = (rec.owner.id, rec.reason, rec.cause, state.recoverable if state else False,
                state.hint if state else NATIVE_HINT_NONE)
        (logger.warning if rec.reason in _NATIVE_ABNORMAL else logger.info)(line, *args)
        # 3) desktop warning (editor UI may be gone) — injectable, bounded, never raises
        if state is not None and state.desktop_warning:
            try: self._native_warning_sink(state.desktop_warning)
            except Exception as exc: logger.warning("native warning sink raised (%s)", type(exc).__name__)
        # 4) callbacks — each isolated by type name
        cb = self._native_end_cb
        if cb is not None:
            try: cb(rec)
            except Exception as exc: logger.warning("native end callback raised (%s)", type(exc).__name__)
        tcb = self._native_teardown_cb
        if tcb is not None and state is not None:
            try: tcb(state)
            except Exception as exc: logger.warning("native teardown callback raised (%s)", type(exc).__name__)
    + set_native_teardown(self, cb) / native_last_end(self) (read one attribute; no lock)
    + _desktop_warning(self, msg): if not self._cfg.feedback.hypr_notify: return;
        exe = shutil.which("notify-send");
        if exe: try subprocess.run([exe, "-a", "voice-typing", "-t", str(int(self._cfg.feedback.notify_ms)), msg],
                                   timeout=1.0, check=False, stdout=DEVNULL, stderr=DEVNULL); return
                except (subprocess.TimeoutExpired, OSError): pass
        self._feedback.notify(msg)                        # configured notifier fallback (hyprctl, fire-and-forget)
        (whole body in try/except Exception → debug log, type name)

Task 5: EDIT daemon.py — publish status + exit expiry + unload guard (one-line insertions, anchor by symbol):
  a) reserve_native: after the accepted reservation is stored under _lock → self._publish_native_status_locked()
  b) _native_open_capture_locked: last statement → self._publish_native_status_locked()   (LISTENING)
  c) native_stop and native_lost: immediately AFTER each `r.begin_drain(reason)` → _publish_native_status_locked()
  d) _unload_host: add to the under-lock `if (… or …)` condition:
         or self._native_owner_live_locked()   # P1.M1.T4.S6: a live owner defers the unload; the clock keeps running
     docstring: add one paragraph (defer, never kill under a live owner; the session is bounded by the start cap /
     drain + settle budgets; the next tick after ENDED unloads).
  e) _native_expire_at_exit(self): self._native_recovery.clear()
     request_shutdown: on the line AFTER `self._session_recovery.clear()` → self._native_expire_at_exit()
     shutdown(): AFTER its `self.terminate_native("shutdown", cause="shutdown")` line → self._native_expire_at_exit()
  f) status_snapshot: add ONE entry to the returned dict (next to the delivery_* keys):
         "native": self._native_status.as_dict(),   # P1.M1.T4.S6: lock-free, transcript-free (§4.8.1 C)

Task 6: EDIT ctl.py — format_result status: after the delivery block:
    native = response.get("native") or {}
    if (native.get("state") or "inactive") != "inactive":
        lines.append(f"native: {native['state']}" + (f" ({native['id']})" if native.get("id") else ""))
    if native.get("reason"):
        hint = native.get("hint") or "none"; sid = native.get("id") or "<id>"
        if hint == "recover":            hint = f"unconfirmed text: voicectl recover {sid}"
        elif hint == "recover_maybe_applied": hint = f"unconfirmed text: voicectl recover {sid} (may already be partially typed)"
        lines.append(f"native end: {native['reason']}  recovery: {hint}")
  help (:22-24 status entry): append " + native editor session (state / last end reason / recovery hint)".
  If Task 0 found a test pinning the old status help, update that assertion (list the file in the diff check).

Task 7: EDIT tests/test_daemon.py:2211 — add "native" to the expected key set literal (ONE line; nothing else).

Task 8: EDIT docstrings [Mode A].
  - daemon.py: _end_native_locked ("…funnels HERE; P1.M1.T4.S6: _native_finish_locked finalises recovery
    (end_session), builds NativeEndState and publishes the `native` status block before the queue is closed"),
    _flush_native_end (the 4-step order; cleanup never depends on a callback; never under _lock),
    terminate_native (used by request_shutdown/shutdown/_handle_dead_host — ends WITHOUT drain; expiry is the
    callers' job), _handle_dead_host (native owner ends 'load_failed' while STARTING else 'disconnected',
    cause 'host-died'; no drain/abort on a dead child; duck released; status shows it),
    request_shutdown / shutdown (recovery store expired — no durable recovery, §4.8.1 C),
    _unload_host (live-owner deferral), status_snapshot (`native` block: always present, codes/ids only, lock-free).
  - ctl.py: status help line + a comment above the native block ("codes only — never dictated text").

Task 9: VERIFY: Task-1 file green; Task-0 suites green; tests/test_daemon.py FAILED set == baseline (set-diff);
        tests/test_voicectl.py green (ctl rendering; CPU hermetic — `timeout 300`).
Task 10: VALIDATE L1–L4. Commit only if the orchestrator directs.
```

### Implementation Patterns & Key Details

```python
# PATTERN — terminal lock hold does ONLY stores + the leaf recovery store; everything else is off-lock.
with self._lock:  rec = self._end_native_locked(reason, cause)      # → _native_finish_locked (end_session, state, status)
self._flush_native_end()                                            # → seed clear, log, warning, on_end, teardown — once

# GOTCHA — end_session BEFORE recover(sid): a fully-ACKed or empty ending is DISCARDED, so recover() is the truth.
# GOTCHA — "timeout" is BOTH the settle-budget end (S5) and the lease-expiry loss reason; both warn on the desktop.
#         "target_lost" arrives over a LIVE transport (the editor warns itself) → no desktop warning.
# GOTCHA — request_shutdown runs terminate_native FIRST (S5/T3.S4), so the end state exists before the store is
#         expired: native_last_end() still reports reason="shutdown", recover(id) → None afterwards.
# GOTCHA — a late _flush_native_end for an already-claimed end returns at the claim; callbacks never fire twice.

HANDOFF — CONSUMER CONTRACT (put it verbatim in the NativeEndState / set_native_teardown docstrings):
  T4.S7 (owner-connection pump):
    d.set_native_teardown(cb)  — ONE daemon-level hook; cb(NativeEndState) fires exactly once per ended session,
        off-lock, AFTER on_end(EndRecord) and AFTER NativeRecovery.end_session — i.e. recover(id) is final.
        In cb: `pump.send_event(state.frame())` (the `ended` frame — EXACTLY {"event","id","reason","recoverable"}),
        then close the owner connection / retire pump timers. Do NOT build the frame yourself.
        `finishing` stays the pump's: emit {"event":"finishing","id":…} ONCE on _native_offer_evt wake while
        d._native.stage is DRAINING (S5 handoff). The daemon core never writes to the socket.
        Keep passing on_end=… to reserve_native if you need the raw EndRecord (cause, stage, ended_at).
    d.native_last_end() → NativeEndState | None (lock-free) for diagnostics; status["native"] for the CLI.
  P1.M1.T5.S1 (owner-only capped recovery reply): no new API — after end_session the snapshot is immutable:
    active_id() == id → busy;  recover(id or None) → None → not_found;  else {ok, id, text, truncated,
    possibly_applied} from NativeRecoverySnapshot (≤ 7 MiB escaped). Daemon exit clears the store (no durable
    recovery promised). Use state.hint only for hints, never for the reply.
  Adapters (P1.M2.T1/T2): on `ended` with reason ∉ {stopped, idle} show the editor-side warning; with
    recoverable == true append "Unconfirmed text: voicectl recover <id>" (§4.8.1 C wording).
```

### Integration Points

```yaml
STATE:
  - add to: voice_typing/daemon.py __init__ (after _native_end_facts)
  - pattern: "_native_last_end | _native_status | _native_teardown_cb | _native_warning_sink"
STATUS:
  - add to: voice_typing/daemon.py status_snapshot return dict
  - pattern: "\"native\": self._native_status.as_dict()"   # always present; ctl.format_result renders it
EXIT:
  - edit: request_shutdown (+1 line beside _session_recovery.clear()), shutdown (+1 line after terminate_native)
IDLE UNLOAD:
  - edit: _unload_host under-lock condition (+ `or self._native_owner_live_locked()`)
NO CHANGES: config keys, state.json shape, ControlServer handlers/replies (the status reply already forwards
the snapshot), editor_protocol.py, editor_session.py, session_recovery.py, feedback.py, recorder_host.py,
media ducking code, generic cancel()/HALT/Backspace, run() loop body, S5's funnels beyond the status publish calls.
```

## Validation Loop

### Level 1: Syntax & Style
```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m py_compile voice_typing/daemon.py voice_typing/ctl.py tests/test_native_teardown.py && echo "L1 PASS"
grep -c "Lock()" voice_typing/daemon.py        # == Task-0 count N (no new lock)
grep -nE "def (native_end_hint|build_ended_frame|set_native_teardown|native_last_end|_native_finish_locked|_publish_native_status_locked|_desktop_warning|_native_expire_at_exit)\b" voice_typing/daemon.py   # 8 hits
grep -nE "_publish_native_status_locked\(\)" voice_typing/daemon.py | wc -l      # 1 def + 4 call sites
.venv/bin/ruff check voice_typing/daemon.py voice_typing/ctl.py tests/test_native_teardown.py 2>&1 | tail -3   # only if ruff is configured
```

### Level 2: Unit Tests
```bash
PY=.venv/bin/python
timeout 300 "$PY" -m pytest tests/test_native_teardown.py -q                                           # bash timeout 360
timeout 300 "$PY" -m pytest tests/test_native_lifecycle.py tests/test_editor_session.py tests/test_native_recovery.py tests/test_editor_offer_queue.py tests/test_native_final_route.py -q 2>&1 | tail -2
timeout 300 "$PY" -m pytest tests/test_voicectl.py tests/test_control_socket.py -q 2>&1 | tail -2     # ctl + status reply shape
timeout 500 "$PY" -m pytest tests/test_daemon.py -q --tb=no 2>&1 | tail -40                            # bash timeout >= 560
# Set-diff rule (tests/G1_BASELINE.md): FAILED set == Task-0 baseline — no new reds, no blanket skips.
# A 124 means wedged: do NOT retry — AGENTS.md "Cleanup".
```

### Level 3: Scope & Integration
```bash
git diff --name-only      # == voice_typing/daemon.py voice_typing/ctl.py tests/test_native_teardown.py tests/test_daemon.py (+ help-text pin, if any)
git diff -- tests/test_daemon.py | grep -E "^[+-]" | grep -vE "^(\+\+\+|---)" | wc -l      # expect 2 (one line changed)
git diff -- voice_typing/daemon.py | grep -E "^\+.*(send_event|begin_offer|encode_line|subprocess\.Popen|threading\.Thread\(|\.wait\(|time\.sleep)" | wc -l   # expect 0
git diff -- voice_typing/daemon.py | grep -E "^\+.*logger\.(info|debug|warning)\(" | wc -l      # small; each audited by the caplog tests
git diff -- voice_typing/daemon.py | grep -nE "^\+.*(notify-send|which)\("                    # only inside _desktop_warning
```

### Level 4: Creative & Domain-Specific Validation
```bash
# The frame the pump will send is codec-valid for EVERY end reason (incl. load_failed):
timeout 60 .venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, ".")
from voice_typing import editor_protocol as ep
for r in sorted(ep.END_REASONS):
    ep.validate_event({"event": "ended", "id": "0f8e7c2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b", "reason": r, "recoverable": False})
print("L4 frame PASS", len(ep.END_REASONS))
EOF
# Negative proof — no socket/injection/clipboard tool reachable from the new code:
grep -nE "wtype|ydotool|wl-copy|hyprctl" voice_typing/daemon.py | grep -i native || echo "L4 PASS"
# No end path calls the host on a dead child (manual read of _handle_dead_host + terminal action):
grep -nE "host\.(abort|cancel|stop)\(" voice_typing/daemon.py
```

## Final Validation Checklist

### Technical Validation
- [ ] L1–L4 pass; Success (a)–(m) hold; `tests/test_daemon.py` FAILED set == G1 baseline (set-diff, not count).
- [ ] No wait/abort/cancel/callback/sink under `_lock` or on the reader thread; no new `Lock()`; no new thread/timer.
- [ ] `_end_native_locked` is still the ONLY place a native session reaches ENDED; `_flush_native_end` still
      claims exactly once.

### Feature Validation
- [ ] Every end cause → one cleanup: seed clear, `end_session`, diagnostic log, (warning), `on_end`, teardown.
- [ ] `ended` frame exact keys; `recoverable`/hint match the retained recovery; cancelled never recoverable
      unless possibly applied.
- [ ] Shutdown / dead child: no drain, timers retired, recovery expired at exit, duck released.
- [ ] Idle-unload deferred under a live owner; reclaims on the next tick after ENDED.
- [ ] Status/stop/quit < 1 s in every phase; `native` block codes/ids only; nothing transcript/seed anywhere.

### Code Quality Validation
- [ ] Helpers placed beside S5's native helpers; names exactly as specified; `tests/test_daemon.py` diff = 1 line.
- [ ] [Mode A] docstrings + the HANDOFF contract verbatim.

### Documentation & Deployment
- [ ] No new config keys or environment variables. `notify-send` is probed, never required.

---

## Anti-Patterns to Avoid

- ❌ Building the `ended` frame anywhere but `NativeEndState.frame()`; adding a 5th key (the codec rejects it).
- ❌ Writing to the owner socket, emitting `finishing`, or registering pump logic here (T4.S7).
- ❌ Reading `self._native`, `_native_queue` or `_native_recovery` from `status_snapshot()`.
- ❌ Calling `end_session` off-lock or after a callback; trusting `NativeEndFacts.recoverable` over `recover(sid)`.
- ❌ A desktop warning for `target_lost`/`stopped`/`cancelled`/`shutdown`/`load_failed` (transport is alive —
      the editor warns itself; a second popup is noise), or any warning text containing dictated words.
- ❌ Nulling `self._native` at end, writing `_seed_*` flags, calling `host.abort/cancel/stop` on a dead host,
      or running the warning sink / callbacks under `_lock`.
- ❌ Letting `_flush_native_end` skip cleanup when no `on_end` was registered.
- ❌ Nulling/undoing `_handle_dead_host`'s race guard; un-timed pytest; foregrounding the daemon; editing
      read-only files; implementing `voicectl recover` (T5) or adapters (P1.M2).

## Confidence Score
**7/10** — the terminal action, end flush, dead-host handler, unload condition, exit paths, recovery API,
codec validator and harness names were read in the working tree; every contract-chain open question is
resolved in `research/decisions.md`. Residuals, each pinned to Task 0: S5 is landing concurrently (line
numbers drift — anchor by symbol; `native_stop`/`native_lost` must expose the `r.begin_drain` lines), whether
`OfferQueue.clear_pending` also drops recovery entries (the hint rule holds either way), the attribute
`_FakeFeedback.notify` records into, and whether `tests/test_voicectl.py` pins the `status` help text.
