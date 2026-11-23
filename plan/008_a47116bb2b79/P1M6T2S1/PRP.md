# PRP — P1.M6.T2.S1: Dispatch wiring + bulk cancel intercept (bulk path mic→field behind the opt-in flag)

## Goal

**Feature Goal**: Wire the G2-passed `BulkController` into `VoiceTypingDaemon` so that
`output.delivery="bulk-text"` becomes the end-to-end path (mic → reader thread → controller →
TargetAdapter → field): partials/finals route to the controller **enqueue-and-return on the
reader thread** (no subprocess/editor wait there or under the daemon control lock), stop/
toggle-off/idle-stop disarm immediately with no late flush, any takeover/refused/unknown/stall
disarms bulk delivery AND recording with ONE reason via `delivery_reason`, and Backspace /
`voicectl cancel` in bulk mode performs **zero physical-character compensation** (the intercept
branches at the top of `cancel()` BEFORE the legacy `press_backspace` math, keeping
`host.cancel` + the suppression-window latch shared). With the default `delivery="stream-edit"`
every new branch is inert — behavior byte-identical (G1 watch set stays at its recorded baseline).

**Deliverable** (2 MODIFY + 1 CREATE — adds-only within them, the plan's house rule):
1. `voice_typing/daemon.py` — the dispatch branches in `on_final`/`_on_partial`, the bulk-cancel
   intercept in `cancel()`, the arm/disarm/fault lifecycle (`_bulk_*` helpers + two short-lived
   worker threads), the adapter-bundle seam (`bulk_target_factory=` + `_build_default_bulk_target`),
   boot `set_delivery_mode`, and a Mode A module-docstring delivery note.
2. `voice_typing/bulk_controller.py` — ONE narrowly-scoped ADDITIVE hook: optional ctor kwarg
   `on_applied=None`, fired (outside `_cond`) at the two existing APPLIED branches so the daemon
   can drive `feedback.record_confirmed_op`. No other change; the G2 suite must stay green.
3. `tests/test_bulk_dispatch.py` — NEW: the dispatch/intercept/lifecycle tests (fake bundle +
   fake host with `relay_identity`; no CUDA, no real subprocess, no live desktop).

**Success Definition**:
- (a) `delivery="bulk-text"`: accepted final → `ctrl.on_final` + `record_final`; rejected final →
  `ctrl.on_final_dropped` (boundary closes; nothing auto-erased); partial → `ctrl.on_partial` +
  partial mirror + latency count; identity (`host.relay_identity`) maps to
  `(gen, utterance=str(uid), seq=<daemon-synthesized monotonic>)`.
- (b) Bulk `cancel()` (socket :2931 AND evdev :1805 — both funnel through `cancel()`, no entry-point
  edits): `ctrl.cancel(gen)` OUTSIDE `_lock`, then the SHARED under-lock recognition cancel
  (suppress latch + `host.cancel()` gated on `_text_in_flight`) + partial-mirror clear. The legacy
  `n = max(tail_len-1, 0)` / `press_backspace(n)` path (:1965-1968) is UNREACHABLE in bulk mode.
- (c) `on_stopped(reason)` (fault-class) → `delivery_state="fault"` + the one reason → disarm
  recording (`_disarm` + `_safe_abort`), one concise reason everywhere (status + fault surface).
- (d) Stop/toggle-off/idle-stop/HALT/quit disarm immediately, no late flush: teardown
  (`ctrl.stop(leave=True)`, `target.leave()` exactly once) runs on a coalesced stopper thread,
  NEVER under `_lock`; post-stop events are rejected by the controller (by construction).
- (e) Acquire failure → `delivery_state="unsupported"` + reason; recording stays armed.
- (f) `delivery="stream-edit"` (default): zero behavior change — the G1 watch set
  (`test_streaming_commit`, `test_zero_diff_rewind`, key-listener, control-socket, config suites)
  reports IDENTICAL results before/after.
- (g) `bulk_controller.py` change is additive-only; `tests/test_bulk_controller.py` +
  `tests/test_g2_bulk_gate.py` green untouched.
- (h) Mode A: daemon module docstring documents the delivery wiring + the cancel intercept.

## User Persona

**Target User**: internal — three consumers: (1) the **operator** dictating with
`output.delivery="bulk-text"` (words appear live in the focused field; Backspace cancels the
live fragment without eating user text; a stall disarms everything with one visible reason);
(2) **P1.M6.T2.S2/S3** (session recovery + `voicectl session`) — they consume
`controller.latest_recognized()/accepted_final()/confirmed_visible()` and the session lifecycle
this item establishes; (3) **P1.M6.T4.S1** (G5 timing) — it measures the wired path.

**Use Case**: arm → the arm thread binds the field (`acquire`) → speak: partial i for utterance 7
(gen 3) → reader thread `ctrl.on_partial(...)` (enqueue, return) → writer thread shows it in the
field; final for 7 → `ctrl.on_final` barrier → one-edit correction; Backspace mid-utterance →
`cancel()` → `ctrl.cancel(gen=3)` removes the owned range in ONE op, mic stays hot; the field's
IM takeover mid-op → `TakeoverWatch` → `halt_for_takeover` → `on_stopped("takeover: key")` →
daemon sets fault+reason and disarms both. Stop → immediate disarm, words stay where they are.

**Pain Points Addressed**: (1) the controller/adapters/identity relay all exist but NOTHING routes
events into them — bulk delivery is unreachable from the daemon; (2) legacy `cancel()` in bulk
mode would fire `press_backspace(len(tail)-1)` — synthesized per-character deletion is FORBIDDEN
in bulk mode (R.1 event-count law) and would eat adjacent user text (the ownership failure class);
(3) the landed feedback delivery surface (`delivery_mode/state/reason/last_confirmed_op`,
ctl-rendered) is documented "written ONLY by the bulk wiring (P1.M6.T2.S1)" — currently dead.

## Why

- **PRD §4.2sexies R.5** (the clause this item implements): `RecorderHost._dispatch` invokes
  `_on_partial`/`on_final` on the reader thread: "bulk mode MUST enqueue and return — no
  subprocess, editor wait, or display polling there or under the daemon control lock"; "Stop/
  toggle-off/idle-stop disarm immediately with no late flush"; "`voicectl cancel` in bulk mode
  performs NO `len(tail)-1` physical-character compensation (route bulk cancel BEFORE
  `daemon.cancel`'s legacy backspace call)"; "Any `unknown`/`refused`/stalled operation … disarms
  bulk delivery AND recording … ONE concise reason via status and the configured fault surface."
- **Everything upstream is landed and contract-stable**: the controller (P1.M3.T2.S3, G2-passed,
  its ctor docstring names this item as the `on_stopped` consumer), the IM adapter
  (P1.M4.T3.S3), the pi-editor adapter (P1.M5.T1.S2), the config gate + status surface
  (P1.M3.T3.S1/S2), and the identity relay (P1.M6.T1.S1 — parallel, `host.relay_identity` is the
  seam per its PRP). This item is pure wiring at pre-verified sites.
- **The repo's lock discipline makes the wiring shape non-optional**: the NEW-2 wedge lesson
  (in `_disarm`'s docstring) + the controller's synchronous `on_stopped` mean bulk teardown and
  `ctrl.cancel()` can NEVER run under `_lock` (deadlock: `on_stopped` → handler takes `_lock`).
  The ducking items established the exact async-dispatch pattern to copy.

## What

Daemon-side additive wiring, inert unless `cfg.output.delivery == "bulk-text"`:

1. **Boot** (`__init__`): `feedback.set_delivery_mode(cfg.output.delivery)`; store
   `bulk_target_factory` (new ctor kwarg, default `_build_default_bulk_target`); bulk state
   fields (`_bulk_ctrl=None`, `_bulk_bundle=None`, `_bulk_gen=0`, `_bulk_epoch=0`,
   `_bulk_delivery_active=False`, `_bulk_seq` map + gen stamp, dropped-identity counter).
2. **Arm** (`_arm()` :1541, under `_lock` — cheap parts only): bump `_bulk_gen`/`_bulk_epoch`;
   schedule the "vt-bulk-arm" daemon thread: lazily build the bundle → `ctrl.acquire()` →
   `ctrl.arm(gen)` → `ctrl.start()` → `feedback.set_delivery_state("active")` /
   `("unsupported", reason)` on failure (recording stays armed).
3. **Dispatch**: `on_final` bulk branch after `cleaned` (:1360), before the rejected-final block;
   `_on_partial` bulk branch after the listening gate. Both read `host.relay_identity`, drop+
   count when identity is missing, and NEVER touch `_stream`/the typing backend.
4. **Cancel intercept**: `cancel()` :1938 branches at the very top (before `with self._lock:`)
   on bulk mode; `_bulk_cancel()` = `ctrl.cancel(gen)` out of lock → shared under-lock
   recognition cancel → mirror clear → reply.
5. **Disarm/fault/quit**: `_disarm()` flips state + schedules the coalesced epoch-guarded
   "vt-bulk-stop" stopper (`ctrl.stop(leave=True)` + watch detach, NEVER under `_lock`);
   `_on_bulk_stopped(reason)` (the `on_stopped` consumer) → fault+reason + disarm recording;
   `request_shutdown()` schedules the stopper + bounded join.
6. **`on_applied` hook** (bulk_controller.py, additive): fires
   `(kind, gen, utterance, seq, revision, chars, elapsed_ms)` on every in-time APPLIED
   show/finalize/cancel → daemon formats `"insert utt=3 seq=7 rev=12 +34ch 41ms"`-style and calls
   `feedback.record_confirmed_op`.

### Success Criteria

- [ ] Bulk-mode dispatch: partial/final/rejected-final/identity-missing all behave per (a)/(D2-D5); zero `StreamingOutput`/backend calls on the bulk path (asserted with a spy backend + spy stream).
- [ ] Bulk cancel: `press_backspace` unreachable in bulk mode; `ctrl.cancel(gen)` called out of lock; suppress latch + `host.cancel()` shared; idempotent when not armed.
- [ ] Fault disarm: each of `queue-overflow | op-deadline | refused | unknown | target-error | takeover: *` → `delivery_state="fault"` + reason + `listening=False`.
- [ ] Clean disarm (stop/toggle-off/idle-stop/HALT/quit): `target.leave()` exactly once, no post-stop writes, teardown never under `_lock`.
- [ ] Acquire failure → `unsupported` + reason; recording stays armed.
- [ ] Default mode: G1 watch set identical before/after.
- [ ] `record_confirmed_op` populated on APPLIED ops (via the hook); G2/controller suites green untouched.

## All Needed Context

### Context Completeness Check

_Pass._ The exact branch sites, the landed controller/adapter/feedback/config APIs with
signatures, the lock/threading design (with the deadlock and wedge hazards called out), the
test-double patterns, and executable validation commands are all below. Line cites were
re-verified live this session and are CURRENT (the item contract's cites pre-date recent merges —
the drift map is in the research notes §1; re-grep before editing anyway).

### Documentation & References

```yaml
# MUST READ — the grounding map (site recipes; §2 is the cancel-intercept spec for THIS item).
- file: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  why: "§2: the cancel() internals (tail_len/n/press_backspace/host.cancel/suppress latch), both
        entry points (socket :2691→2931 now, evdev _on_cancel_backspace), and the lock map
        (_lock vs _on_final_lock vs ControlServer lock). §3: what bulk code must NEVER call
        (type_text/press_backspace/make_backend/StreamingOutput.*) + the _stream.committed
        coupling warning. §4: feedback/ctl recipes (already landed). §5: lab assets."
  critical: "Line cites in the map are @ 2335a9e and have DRIFTED (~+120-240 lines) — use this
             PRP's current cites, re-grep live (Task 0)."

# MUST READ — this item's verified research (design decisions D1-D12 + drift map).
- file: plan/008_a47116bb2b79/P1M6T2S1/research/dispatch_wiring_design.md
  why: "§1 contract→HEAD line mapping. §2 the full BulkController API with the enqueue-and-return
        law + on_stopped contract. §3 adapter/bundle ctors (ImeProcess.on_delivery_state is the
        ready-made feedback seam). §5 the structural facts (on_final order, NEW-2 lock lesson,
        arm-cmd/session_gen 1:1 invariant). §6 design decisions D1-D12 — the rationale for every
        placement decision in the blueprint below."

# MUST READ — the parallel-item CONTRACT (identity relay; assume it lands exactly as specified).
- file: plan/008_a47116bb2b79/P1M6T1S1/PRP.md
  why: "Defines host.relay_identity (read it INSIDE on_final/_on_partial — they run on the reader
        thread where it is valid; G6 there), the additive utterance_id/session_gen payload keys,
        the relay-side discard rules (late post-final partials, duplicate finals, cross-session
        stragglers), and the settle-before-relay boundary rule this item's on_final_dropped
        mapping complements."
  critical: "Do NOT re-implement relay-side discards daemon-side — the controller ALSO dedups
             (closed set, seq high-water). Your job is only identity→(gen,utterance,seq) mapping."

# MUST READ — the PRD clause (verbatim spec).
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: "§4.2sexies R.5 (ordering/takeover/failure — quoted in Why above), R.3 (show/finalize/
        leave/cancel semantics + 'no typing fallback'), R.1 (event-count law: synthesized
        per-character typing FORBIDDEN), R.7 G1 (the regression baseline discipline)."

# MUST READ — the files being modified.
- file: voice_typing/daemon.py
  why: "(1) on_final :1246 (gate :1248, _on_final_lock :1257, suppression window :1262-1359 with
        its early returns, cleaned :1360, rejected-final block :1362-1403, commit :1418-1424,
        record_final :1451, latency INFO line :1457-1471 [carries text=<repr>], prompt refresh
        :1484-1491). (2) _on_partial :1684-1701. (3) cancel :1938-1985. (4) _arm :1541 /
        _disarm :1603 (the in-lock choke points + their out-of-lock _safe_abort discipline).
        (5) _load_host :930-982 (callback wiring: on_final/_on_partial/_touch_speech run on the
        host reader thread). (6) ctor :661-672 (injection-seam pattern to extend).
        (7) _build_default_ducker :146 (the default-factory pattern to mirror).
        (8) status_snapshot :2463-2523 (the delivery keys you now write). (9) module docstring
        :1-91 (Mode A target)."
  critical: "NEVER add anything blocking under self._lock (NEW-2, documented in _disarm's
             docstring). Keep the suppression-window block AHEAD of the bulk branch. Do not touch
             the legacy paths' bodies — insert branches, don't rewrite."

- file: voice_typing/bulk_controller.py
  why: "ctor :219 (add on_applied kwarg beside on_stopped, same 'quick and non-blocking' law);
        cancel()'s APPLIED branch :459-463 and _process_next's APPLIED branch :737-741 (the two
        fire sites); _fire_on_stopped :864 (the once-law to copy); the module docstring's
        threading contract (writer = only dispatcher; entries enqueue-and-return)."
  critical: "ADDITIVE ONLY: default None must leave every existing G2/controller test green.
             Fire the hook OUTSIDE self._cond (callbacks must never run under the condition
             lock — the on_stopped precedent)."

# MUST READ — the landed surfaces this item WRITES (do not re-create).
- file: voice_typing/feedback.py
  why: "set_delivery_mode :216 (call at boot), set_delivery_state :234 (taxonomy + the documented
        reason→state mapping THIS item implements: controller stop reasons → fault; clean stop →
        inactive; acquire failure → unsupported; reason always overwritten + sanitized),
        record_confirmed_op :261 (descriptor format: verb + ids + revision + counts + ms)."
- file: voice_typing/config.py
  why: ":147 delivery key; :416-433 the precondition triple (bulk-text ⇒ streaming=true,
        graceful_stop=false, keypress_action='disarm') — already enforced at construction; your
        tests' cfg fixtures must satisfy it or VoiceTypingConfig raises."

# MUST READ — the adapters behind the bundle seam (construct, don't modify).
- file: voice_typing/ime/manager.py
  why: "ImeProcess ctor :95 (on_delivery_state=None IS the M6 feedback seam — wire it to
        feedback.set_delivery_state; on_event is the takeover feed), spawn()/stop()/healthy()."
- file: voice_typing/ime/target.py
  why: "ImeTarget(proc) :75 — the R.3 DeliveryTarget implementation (acquire/show/finalize/leave/
        cancel; last_reason)."
- file: voice_typing/ime/takeover.py
  why: "TakeoverWatch(proc=, target=, controller=) :196 — leave()-then-halt_for_takeover, one-shot
        latch; construct FRESH per delivery lifetime (the latch does not reset)."
- file: voice_typing/pi_editor.py
  why: "PiEditorTarget(client) :352 / PiEditorClient(sock_path=None, on_event=None) :158 /
        PiEditorTakeoverWatch(controller=, target=) :720 — the second real adapter, reachable via
        the bulk_target_factory seam (no config key in this item)."

# MUST READ — the test patterns to extend.
- file: tests/test_daemon.py
  why: "_FakeHost :561 + _fake_host_factory :665 (mirror the RecorderHost ctor signature — extend
        the fake with a settable relay_identity attribute), _make :683 (daemon construction with
        cfg=/backend=/host_factory=), and the cancel/on_final dispatch tests as templates."
- file: tests/test_g2_bulk_gate.py
  why: "G2FakeTarget :107 (reuse as the dispatch tests' fake target), _controller() :240,
        _wait_until :248 (async-thread assertions), _no_legacy_backend :77 (the
        zero-legacy-backend-calls monkeypatch idiom)."
  critical: "These two suites must pass UNTOUCHED after your bulk_controller.py hook (the
             additive gate g)."

# Hard rules.
- file: AGENTS.md
  why: "Two timeouts on every non-trivial command; voicectl under timeout 30; pytest under
        timeout 600 (bash-tool timeout above); never foreground the daemon; unit tests only —
        no CUDA, no live desktop, no real IM subprocess in THIS item's tests."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── daemon.py            # ← MODIFY: dispatch branches, cancel intercept, _bulk_* lifecycle,
│                        #   bulk_target_factory seam, boot set_delivery_mode, docstring note
├── bulk_controller.py   # ← MODIFY (additive only): on_applied ctor kwarg + 2 fire sites
├── bulk_delivery.py     # READ ONLY (contracts: ShowResult/AcquireResult/DeliveryTarget)
├── streaming.py         # READ ONLY (untouchable per map §3; stays constructed+inert in bulk)
├── typing_backends.py   # READ ONLY (bulk path NEVER calls it)
├── recorder_host.py     # READ ONLY (T1.S1 lands relay_identity; consume, don't edit)
├── ime/{manager,target,takeover,wlwire,protocol,ime_host}.py  # READ ONLY (default bundle)
├── pi_editor.py         # READ ONLY (second bundle, via the seam)
└── feedback.py config.py ctl.py  # READ ONLY (surfaces landed; this item writes them)
tests/
├── test_bulk_dispatch.py  # ← CREATE (all new tests)
└── (test_daemon/test_bulk_controller/test_g2_bulk_gate/...)  # must stay green untouched
```

### Desired Codebase tree with files to be added

```bash
voice_typing/daemon.py        # + ~250 lines: _BulkTargetBundle default factory, _bulk_* helpers
                              #   (begin_delivery/schedule_stop/on_stopped/on_applied/cancel/
                              #   handle_final/handle_partial/next_seq/mode gates), ctor kwarg,
                              #   3 branch insertions (on_final, _on_partial, cancel), docstring §
voice_typing/bulk_controller.py  # + ~20 lines: on_applied kwarg + fire sites + timing stamp
tests/test_bulk_dispatch.py   # + ~15 tests (fake bundle + fake host w/ relay_identity)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (G1) — DEADLOCK: BulkController.cancel()/stop() can fire on_stopped SYNCHRONOUSLY
#   (writer/reader thread) and the daemon's on_stopped handler takes self._lock. Therefore
#   ctrl.cancel() and ctrl.stop(leave=True) must NEVER be called while holding self._lock.
#   The intercept at cancel() branches BEFORE `with self._lock:`; teardown runs on the stopper
#   thread. (ctrl.stop also joins the writer ≤5 s — the NEW-2 wedge class under _lock.)

# CRITICAL #2 (G2) — The suppression-window block (on_final :1262-1359) MUST stay AHEAD of the
#   bulk branch: its early-returns drop the cancelled utterance's racing final + sentinel (the
#   double-type bug class). That is CORRECT for bulk too — ctrl.cancel() already purged+closed
#   the utterance controller-side, so the dropped final needs no controller call; the relay
#   (T1.S1) settled its boundary regardless. Its _stream.freeze absorb calls are gated on
#   _pending_tail_len() > 0 → always 0 in bulk mode (the bulk branch never feeds _stream).

# CRITICAL #3 (G3) — enqueue-and-return ONLY on the reader thread: ctrl.on_partial/on_final/
#   on_final_dropped/arm() are cond+deque ops (non-blocking) — safe there. acquire()/start()/
#   stop()/cancel() do subprocess round-trips → arm thread / control thread / stopper thread
#   ONLY (never reader thread, never under _lock).

# CRITICAL #4 (G4) — seq is NOT in the relay payload: synthesize per-(gen, uid) via a daemon-side
#   counter (partial: +1; final: last+1), lazily cleared when gen advances. utterance must be a
#   STR for the controller (str(uid)); gen = relay session_gen.

# CRITICAL #5 (G5) — gen parity: the daemon bumps its own counter in _arm() BEFORE
#   host.set_microphone(True) (:1593 → ("arm", {}) cmd); the child stamps session_gen per arm
#   cmd (T1.S1) — 1:1 by construction. ctrl.arm(gen) is called by the ARM THREAD after acquire
#   (acquire→arm→start order: arm() needs _active; events before arm() are gen-discarded by the
#   controller — counted, tiny window, by design).

# CRITICAL #6 (G6) — missing identity (relay_identity None — old fakes): drop + count
#   (_bulk_dropped_no_id) and STILL clear _final_pending/_utterance_finalized (drain machinery)
#   + record nothing. NEVER fall back to a constant utterance id (final-closes-key ⇒ every later
#   partial of the session would be dup-discarded — the silent-death fallback).

# CRITICAL #7 (G7) — feedback.set_delivery_state("inactive") in _disarm() must be conditional on
#   the daemon-side _bulk_delivery_active flag (cleared FIRST by the fault path), or it erases a
#   just-written fault reason (feedback overwrites reason on every call by contract).

# CRITICAL #8 (G8) — R.5 log law: NEW bulk-path logs carry counts and times, NEVER recognition
#   text. The legacy latency INFO line (:1457, text=<repr>) is SKIPPED on the bulk path (emit a
#   counts-only line instead). feedback mirrors (partial/last_final) keep their recognition
#   meaning — record_final(cleaned) + update_partial(text) still fire.

# CRITICAL #9 (G9) — scope walls: do NOT touch streaming.py/typing_backends.py/ime//pi_editor.py/
#   recorder_host.py/config.py/feedback.py/ctl.py. The _refresh_context_prompt source stays
#   _stream.committed (empty in bulk mode — harmless no-op pushes; the decoupling is
#   P1.M6.T3.S1, explicitly out of scope here). No new config keys; no voicectl changes
#   (session/--copy is T2.S3).

# CRITICAL #10 (G10) — TakeoverWatch/PiEditorTakeoverWatch latch ONE revocation per object:
#   construct a FRESH watch per delivery lifetime (per acquire). ImeProcess.on_delivery_state
#   emits unsupported/fault on its own (wire → feedback.set_delivery_state; it never raises).

# CRITICAL #11 (G11) — the stopper thread must be EPOCH-GUARDED: capture _bulk_epoch at schedule
#   time; if a newer arm bumped it, skip the teardown (a stale stop must not kill the new
#   delivery lifetime). ctrl.stop()/leave() are idempotent — a no-skip double-stop is still safe.

# CRITICAL #12 (G12) — validation discipline (AGENTS.md): timeout-wrapped pytest, single files,
#   never foreground the daemon, no CUDA/no real IM subprocess in tests (fake bundle + fake
#   ImeProcess duck — the manager's _popen seam exists but is NOT needed here).
```

## Implementation Blueprint

### Data models and structure

No persistent models. Runtime-only daemon state (all created in `__init__`, gated on
`cfg.output.delivery == "bulk-text"` for behavior, constructed unconditionally-cheap):

```python
# daemon.py — new fields (near the ducker/key_listener blocks, ~:843-920):
self._bulk_target_factory = bulk_target_factory          # ctor kwarg (test seam)
self._bulk_ctrl: "bulk_controller.BulkController | None" = None   # built on first arm
self._bulk_bundle: "_BulkTargetBundle | None" = None     # default: IM route (R.4)
self._bulk_gen = 0            # arm generation (bumped in _arm, BEFORE the arm cmd put — G5)
self._bulk_epoch = 0          # stopper guard (bumped in _arm)
self._bulk_delivery_active = False                       # set by arm thread on acquire success
self._bulk_seq: dict[tuple[int, int], int] = {}          # (gen, uid) -> last seq (G4)
self._bulk_seq_gen = -1                                  # lazy clear anchor
self._bulk_dropped_no_id = 0                             # G6 counter (status/debug only)
self._bulk_stop_thread: "threading.Thread | None" = None # test seam: joinable stopper

# The bundle the default factory returns (module level, mirrors _build_default_ducker :146):
class _BulkTargetBundle:
    """One deliverable target + its per-lifetime takeover wiring + bounded teardown."""
    target: "DeliveryTarget"                 # ImeTarget(proc) | PiEditorTarget(client) | fake
    def attach(self, controller) -> None:    # fresh TakeoverWatch per lifetime (G10) +
        ...                                  # ImeProcess.on_delivery_state -> feedback seam
    def teardown(self) -> None:              # bounded: ImeProcess.stop() / client.close()

def _build_default_bulk_target(cfg) -> _BulkTargetBundle:
    proc = ime_manager.ImeProcess(on_delivery_state=...)   # spawn is LAZY (arm thread), not boot
    return _BulkTargetBundle(target=ImeTarget(proc), ...)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — re-verify cites live + record the G1 baseline numbers.
  - RUN: grep -n "def on_final\|def _on_partial\|def cancel\|press_backspace(n)\|def _arm\|def _disarm\|_safe_abort()" voice_typing/daemon.py
  - RUN (baseline, BEFORE any edit): for f in test_streaming_commit test_zero_diff_rewind \
      test_key_listener test_control_socket test_config test_bulk_controller test_g2_bulk_gate; do
      timeout 300 .venv/bin/python -m pytest tests/$f.py -q 2>&1 | tail -1; done
  - EXPECTED: identical numbers post-change (test_streaming_commit has pre-existing reds —
    record them, do not fix; see tests/G1_BASELINE.md for the recorded history).

Task 1: bulk_controller.py — the additive on_applied hook.
  - ADD ctor kwarg on_applied=None (beside on_stopped, same "quick and non-blocking" contract;
    runs on the writer thread / the cancel caller's thread, never under _cond).
  - STAMP t0 = time.monotonic() just before each runner.submit in _process_next (:706) and
    cancel (:427); on each in-time ShowResult.APPLIED result branch (:459 cancel, :737-741
    _process_next), fire OUTSIDE _cond: self._on_applied(kind, gen, utterance, seq, revision,
    chars, elapsed_ms) where kind is "show"|"finalize"|"cancel" and revision is the PRE-op value.
  - GUARD: fire only when the callback is not None; wrap in try/except-log (a feedback failure
    must never kill the writer). Default None ⇒ byte-identical behavior.
  - RUN: timeout 300 .venv/bin/python -m pytest tests/test_bulk_controller.py tests/test_g2_bulk_gate.py -q
    (bash-tool timeout 330). Green, untouched, before proceeding.

Task 2: daemon.py — boot state + ctor seam + default bundle factory.
  - ADD ctor kwarg bulk_target_factory: Callable[[VoiceTypingConfig], Any] | None = None
    (the ducker=/host_factory= pattern, :661-672).
  - __init__ (bulk-gated writes only): feedback.set_delivery_mode(cfg.output.delivery); the
    fields in Data models above. Import bulk_controller lazily OR at module top (it is
    import-pure — pure-python, no torch; VERIFY with the L1 import check).
  - ADD _BulkTargetBundle + _build_default_bulk_target (IM route: ImeProcess + ImeTarget +
    per-lifetime TakeoverWatch in attach(); on_delivery_state forwards to
    self._feedback.set_delivery_state — note it can fire from the manager's reader thread).
  - ADD the mode gates: _bulk_mode() -> bool (cfg check only — cheap, any thread);
    _bulk_wired() -> bool (mode AND _bulk_ctrl is not None).

Task 3: daemon.py — the dispatch branches.
  - on_final: immediately AFTER `cleaned = textproc.clean(text, self._cfg.filter)` (:1360) and
    BEFORE the `if not cleaned:` rejected-final block, insert:
        if self._bulk_mode():
            return self._bulk_handle_final(cleaned, text, t_final_ready)
  - _bulk_handle_final(cleaned, raw, t_final_ready):
      ident = getattr(self._host, "relay_identity", None)   # T1.S1 seam; reader-thread-valid
      self._final_pending = False; self._utterance_finalized = True    # drain flags ALWAYS
      if ident is None or ident.utterance_id is None:
          self._bulk_dropped_no_id += 1; logger.debug(...counts only...); return
      gen, uid = ident.session_gen, ident.utterance_id
      if not cleaned:
          if ctrl active: ctrl.on_final_dropped(utterance=str(uid), gen=gen)
          # parity with the legacy rejected-final UX: the hallucination notify, NO stream calls
          self._feedback.notify("filtered hallucination — not typed; keep dictating")
          return
      if ctrl active:
          ctrl.on_final(cleaned, utterance=str(uid), seq=self._bulk_next_seq(gen, uid, final=True), gen=gen)
      self._feedback.record_final(cleaned)                  # recognition meaning (R.5)
      rec = self._latency.finalize_utterance(text=cleaned, t_final_ready=t_final_ready,
                                             t_typed=time.monotonic())
      logger.info("bulk final gen=%d utt=%d seq=%d chars=%d queue=%s", ..., ctrl.stats()["queue_depth"])
      return   # NO _stream.commit, NO backend.type_text, NO text-bearing latency line, NO prompt refresh
  - _on_partial: after the listening gate (:1691-1694), insert the same shape:
        if self._bulk_mode():
            return self._bulk_handle_partial(text)
    _bulk_handle_partial: identity gate (drop+count, still note nothing — no text delivered);
    if ctrl active: ctrl.on_partial(text, utterance=str(uid), seq=self._bulk_next_seq(gen, uid), gen=gen);
    self._feedback.update_partial(text); self._latency.note_partial(text); return.
  - _bulk_next_seq(gen, uid, final=False): lazily clear self._bulk_seq when gen != _bulk_seq_gen
    (then _bulk_seq_gen = gen); key=(gen,uid); seq = self._bulk_seq.get(key, 0) + 1; store; return seq.

Task 4: daemon.py — arm/disarm lifecycle (the two worker threads).
  - _arm() (under _lock, cheap only): if bulk mode: self._bulk_gen += 1; self._bulk_epoch += 1;
    then AFTER the existing body (still in _arm, thread-spawn is non-blocking — the
    _duck_engage precedent) call self._bulk_begin_delivery().
  - _bulk_begin_delivery(): spawn daemon thread "vt-bulk-arm" capturing (gen, epoch):
      if bundle is None: bundle = factory(cfg); ctrl = BulkController(bundle.target,
          on_stopped=self._on_bulk_stopped, on_applied=self._on_bulk_applied)
      bundle.attach(ctrl)                                   # FRESH takeover watch (G10)
      if ctrl.acquire(): ctrl.arm(gen); ctrl.start()
          self._bulk_delivery_active = True
          self._feedback.set_delivery_state("active")
      else:
          reason = ctrl.stats().get("stopped_reason") or "acquire-failed"
          self._feedback.set_delivery_state("unsupported", reason)   # recording stays armed
      (guard: if epoch stale, a newer arm superseded — return before acquiring)
  - _disarm() (under _lock): if bulk mode and self._bulk_delivery_active:
      self._bulk_delivery_active = False
      self._feedback.set_delivery_state("inactive")         # G7: conditional, fault-safe
    then ALWAYS (bulk mode): self._bulk_schedule_stop()      # thread spawn only — non-blocking
  - _bulk_schedule_stop(): if not bulk mode: return; epoch = self._bulk_epoch; spawn daemon
    thread "vt-bulk-stop" (store on self._bulk_stop_thread for test joins):
      if epoch != self._bulk_epoch: return                  # G11: superseded by a new arm
      if ctrl: ctrl.stop(leave=True)                        # bounded; NEVER under _lock (G1)
      if bundle: bundle.teardown()                          # bounded subprocess stop
  - request_shutdown() (:2341): after the existing _shutdown latch block, add (bulk mode):
    self._bulk_schedule_stop(); then bounded join of self._bulk_stop_thread (timeout=1.0).
  - _on_bulk_stopped(reason):  # the on_stopped consumer — runs on writer/reader thread
      self._bulk_delivery_active = False                    # FIRST (G7)
      fault_reasons = {"queue-overflow","op-deadline","refused","unknown","target-error"}
      if reason in fault_reasons or reason.startswith("takeover:"):
          self._feedback.set_delivery_state("fault", reason)   # ONE concise reason (R.5)
          with self._lock:
              if self._listening.is_set():
                  self._disarm()                            # schedules the stopper; sees flag False
          self._safe_abort()                                # out-of-lock nudge (the :1796 shape)
      else:  # "stopped" / acquire-path reasons — state already written by the disarm/acquire path
          logger.info("bulk delivery stopped: %s", reason)
  - _on_bulk_applied(kind, gen, utterance, seq, revision, chars, elapsed_ms):
      op = "insert" if kind == "show" else kind             # show→insert, finalize→finalize, cancel
      self._feedback.record_confirmed_op(
          f"{op} utt={utterance} seq={seq} rev={revision} +{chars}ch {elapsed_ms:.0f}ms")

Task 5: daemon.py — the cancel intercept.
  - cancel() :1938 — insert BEFORE `with self._lock:`:
      if self._bulk_mode():
          return self._bulk_cancel()
  - _bulk_cancel():
      if not self._listening.is_set():
          return {"ok": True, **self.status_snapshot()}     # idempotent parity (:1961-1964)
      ctrl = self._bulk_ctrl
      if ctrl is not None and ctrl.is_active():
          ctrl.cancel(gen=self._bulk_gen)                   # OUT of _lock (G1); may fire
                                                            # on_stopped → handler disarms
      with self._lock:                                      # the SHARED recognition-side cancel
          if self._listening.is_set():                      # re-check (a fault may have disarmed)
              if self._text_in_flight.is_set() and self._host is not None:
                  host_cancel = getattr(self._host, "cancel", None)
                  if callable(host_cancel):
                      self._cancel_suppress_final = True    # the shared suppression latch
                      self._cancel_suppress_since = time.monotonic()
                      host_cancel()
              self._reset_stream_after_cancel()             # clears the Feedback partial mirror
      return {"ok": True, "listening": self.is_listening(), **self.status_snapshot()}
      # NO tail_len, NO n = max(tail_len-1,0), NO press_backspace — R.5 (contract §1).
      # Entry points need NO edit: socket :2931 and evdev :1805 both call cancel().

Task 6: daemon.py — Mode A docstring note.
  - Extend the module docstring (:1-91) with a §DELIVERY paragraph: the bulk-text gate, the
    reader-thread enqueue-and-return law, the cancel intercept (no physical compensation), the
    disarm/fault lifecycle + one-reason law, the stopper-thread/lock discipline, and the
    bulk_target_factory seam (IM default; pi-editor via the seam).

Task 7: CREATE tests/test_bulk_dispatch.py (fake bundle + fake host; no CUDA/subprocess).
  - FIXTURES: bulk cfg = test_daemon-style construction with output.delivery="bulk-text",
    streaming=True, graceful_stop=False, cancel.keypress_action="disarm" (the triple — else
    VoiceTypingConfig raises); FakeBundle wrapping G2FakeTarget (tests/test_g2_bulk_gate.py:107)
    recording attach/teardown; fake host = _FakeHost + settable `relay_identity` (a tiny
    NamedTuple stand-in) + recorded cancel() calls; spy backend recording type_text/
    press_backspace; daemon built via the _make pattern with backend=, host_factory=,
    bulk_target_factory=.
  - TESTS (each asserts the zero-legacy-call law via the spy backend + a spy/no-op stream):
    1. default mode inert: delivery="stream-edit" → on_final/_on_partial/cancel make ZERO
       ctrl/bundle calls (factory never invoked) — the G1 parity pin at unit level.
    2. bulk accepted final: relay_identity (gen=1, uid=7) → ctrl.on_final(span, utterance="7",
       seq=1, gen=1); record_final called; NO _stream.commit (fake stream records); log line
       has counts only (caplog: "bulk final" present, "text=" absent).
    3. bulk rejected final (blocklist) → ctrl.on_final_dropped(utterance="7", gen=1); no on_final;
       notify fired.
    4. suppression window: latch _cancel_suppress_final via _bulk_cancel, then a final arrives
       → dropped (no ctrl.on_final), sentinel consume path re-arms (mirror the existing
       test_daemon cancel-window tests).
    5. bulk partial: identity → ctrl.on_partial + update_partial + note_partial; NO
       _stream.on_partial; seq increments across partials; new gen resets seq.
    6. identity missing → drop + _bulk_dropped_no_id counted; _final_pending cleared.
    7. cancel intercept: bulk + armed → ctrl.cancel(gen=self._bulk_gen) called; spy backend
       press_backspace NEVER called; fake host.cancel called (with _text_in_flight set);
       suppress latch set; reply ok; NOT armed → no ctrl call (idempotence).
    8. on_stopped fault (drive ctrl with a FakeTarget that refuses) → delivery_state fault +
       reason; listening False; _disarm ran (feedback listening False); stopper joined.
    9. arm lifecycle: _arm → "vt-bulk-arm" thread → acquire→arm→start order recorded; feedback
       active; acquire failure → unsupported + reason, listening stays True.
    10. disarm: _disarm → stopper thread runs ctrl.stop(leave=True) + bundle.teardown() (join
        via _bulk_stop_thread; assert leave called exactly once); a NEW arm before the stopper
        runs → epoch guard skips the stale teardown.
    11. on_applied: FakeTarget APPLIED → feedback last_confirmed_op matches the descriptor
        format (drive via ctrl.drain() for determinism — the G2 deterministic seam).
    12. HALT: note_user_keypress (non-Backspace, past the grace window) in bulk mode → disarm +
        stopper scheduled (join + assert leave).
  - RUN after writing: timeout 300 .venv/bin/python -m pytest tests/test_bulk_dispatch.py -q
    (bash-tool timeout 330).

Task 8: VALIDATE — the full Validation Loop; reconcile the G1 watch set against Task 0's
  baseline (identical numbers required). No git commit unless directed (message if so:
  "P1.M6.T2.S1: bulk dispatch wiring + cancel intercept — reader-thread enqueue, fault disarm,
  no physical compensation on the bulk path").
```

### Implementation Patterns & Key Details

```python
# PATTERN — the on_final insertion (the ONLY body lines added to the legacy method):
            cleaned = textproc.clean(text, self._cfg.filter)
            if self._bulk_mode():                                  # ← NEW (2 lines, that's all)
                return self._bulk_handle_final(cleaned, text, t_final_ready)
            if not cleaned:  # rejected: blocklist hallucination / below min_chars
                ...

# PATTERN — the cancel intercept (top of cancel(), before the lock):
    def cancel(self) -> dict:
        if self._bulk_mode():                 # bulk: NO tail math, NO press_backspace (R.5)
            return self._bulk_cancel()        # ctrl.cancel OUT of _lock — on_stopped deadlock (G1)
        with self._lock:                      # legacy body VERBATIM below this point
            ...

# PATTERN — the on_stopped consumer (ONE reason; disarm BOTH on fault-class only):
def _on_bulk_stopped(self, reason: str) -> None:
    self._bulk_delivery_active = False                        # before any state write (G7)
    if reason in _BULK_FAULT_REASONS or reason.startswith("takeover:"):
        self._feedback.set_delivery_state("fault", reason)    # the ONE concise reason (R.5)
        with self._lock:
            if self._listening.is_set():
                self._disarm()                                # sees flag False → keeps fault state
        self._safe_abort()                                    # the established out-of-lock nudge
    else:
        logger.info("bulk delivery stopped: %s", reason)      # counts/reasons only (G8)

# GOTCHA — the on_applied fire site (bulk_controller.py, OUTSIDE _cond, both branches):
        with self._cond:
            ...
            if result is ShowResult.APPLIED:
                self._expected_revision = revision + 1
                ...
        # --- outside _cond ---
        if result is ShowResult.APPLIED and self._on_applied is not None:
            try:
                self._on_applied(kind, item.gen, item.utterance, item.seq, revision,
                                len(item.span), int((time.monotonic() - t0) * 1000))
            except Exception:
                logger.warning("bulk_controller: on_applied callback failed", exc_info=True)
```

### Integration Points

```yaml
DAEMON → CONTROLLER (the wiring this item adds):
  - "reader thread:  ctrl.on_partial(span, utterance=str(uid), seq, gen) | ctrl.on_final(...) |
                      ctrl.on_final_dropped(utterance=str(uid), gen)   (enqueue-and-return only)"
  - "arm thread:      ctrl.acquire() → ctrl.arm(gen) → ctrl.start()"
  - "stopper thread:  ctrl.stop(leave=True)  (bounded; never under _lock)"
  - "cancel (ctl):    ctrl.cancel(gen=self._bulk_gen)  (out of lock; nothing pending ⇒ no-op)"
  - "callbacks:       on_stopped=daemon._on_bulk_stopped (the disarm seam the ctor docstring
                      names) · on_applied=daemon._on_bulk_applied (new, additive)"

DAEMON → FEEDBACK (surfaces landed in P1.M3.T3.S2 — this item is their only writer):
  - "boot:    set_delivery_mode(cfg.output.delivery)"
  - "arm:     set_delivery_state('active') | ('unsupported', reason)"
  - "disarm:  set_delivery_state('inactive') — ONLY when _bulk_delivery_active was set (G7)"
  - "fault:   set_delivery_state('fault', reason) — the one-reason law"
  - "per-op:  record_confirmed_op('<verb> utt=U seq=S rev=R +Nch Xms')"

DAEMON → ADAPTERS (construct only; IM default per R.4 route assignment):
  - "bundle = bulk_target_factory(cfg) | _build_default_bulk_target(cfg)"
  - "attach(ctrl): fresh TakeoverWatch(proc, target, controller) per lifetime (G10);
                   ImeProcess(on_delivery_state=...) → feedback seam"
  - "teardown(): ImeProcess.stop() / PiEditorClient.close() — bounded"

NO config keys. NO ctl.py changes. NO entry-point changes (socket :2931 / evdev :1805 already
funnel through cancel()). NO streaming.py / typing_backends.py / recorder_host.py edits.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m py_compile voice_typing/daemon.py voice_typing/bulk_controller.py tests/test_bulk_dispatch.py && echo OK
.venv/bin/python -c "
import voice_typing.daemon as d, voice_typing.bulk_controller as bc
import sys; assert not [m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules]
import inspect; sig = inspect.signature(bc.BulkController.__init__)
assert 'on_applied' in sig.parameters and sig.parameters['on_applied'].default is None
assert 'bulk_target_factory' in inspect.signature(d.VoiceTypingDaemon.__init__).parameters
print('symbols + import purity OK')"
```

### Level 2: Unit Tests (Component Validation)

```bash
# The item's gate:
timeout 300 .venv/bin/python -m pytest tests/test_bulk_dispatch.py -q            # bash-tool 330
# The additive-hook gate (MUST be green UNTOUCHED):
timeout 300 .venv/bin/python -m pytest tests/test_bulk_controller.py tests/test_g2_bulk_gate.py -q
# The dispatch/cancel neighbors:
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "cancel or final or partial or arm or disarm"
# The G1 watch set (compare against Task 0's recorded baseline — identical numbers required):
for f in test_streaming_commit test_zero_diff_rewind test_key_listener test_control_socket test_config; do
  timeout 300 .venv/bin/python -m pytest tests/$f.py -q 2>&1 | tail -1; done
# Expected: all green except test_streaming_commit's PRE-EXISTING reds (same count as baseline;
# tests/G1_BASELINE.md is the recorded history — no new failures, no blanket skips).
```

### Level 3: Integration Testing (System Validation)

```bash
# Structural — the intercept precedes the legacy compensation; branches exist; no stray calls:
grep -n "press_backspace" voice_typing/daemon.py            # legacy site(s) only; bulk path absent
.venv/bin/python - <<'EOF'
import ast, sys
src = open('voice_typing/daemon.py').read()
tree = ast.parse(src)
cancel = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'cancel')
body = ast.dump(cancel)  # the bulk branch must appear BEFORE the 'with self._lock' block
assert body.index('_bulk_cancel') < body.index('_lock'), 'intercept must precede the lock'
assert '_bulk_handle_final' in ast.dump(next(n for n in ast.walk(tree)
    if isinstance(n, ast.FunctionDef) and n.name == 'on_final'))
assert '_bulk_handle_partial' in ast.dump(next(n for n in ast.walk(tree)
    if isinstance(n, ast.FunctionDef) and n.name == '_on_partial'))
print('intercept + dispatch branches structurally OK')
EOF
# Control-socket end-to-end (mock-level): the cancel reply shape through ControlServer:
timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py -q -k cancel
# Expected: structural asserts pass; socket tests green (bulk-mode reply shape covered in
# test_bulk_dispatch via daemon.cancel() directly — NO live daemon is started for this item).
```

### Level 4: Creative & Domain-Specific Validation

```bash
# The zero-legacy-backend-calls pin on the bulk path (the R.1/R.3 law) — asserted per-test via
# the spy backend; verify the suite enforces it by count:
timeout 120 .venv/bin/python -m pytest tests/test_bulk_dispatch.py -q \
  -k "cancel or partial or final" -v 2>&1 | tail -12
# The one-reason law: every fault-class reason maps to exactly ONE set_delivery_state("fault", r):
timeout 120 .venv/bin/python -m pytest tests/test_bulk_dispatch.py -q -k "fault or stopped or takeover" -v
# Expected: each named fault reason has a passing test; takeovers disarm BOTH (listening False +
# delivery fault); clean disarm leaves exactly ONE leave() call and zero post-stop writes.
# NO live daemon / real IM subprocess / CUDA anywhere in this item's validation (AGENTS.md);
# the real-field matrix is ALREADY covered by the landed G3 evidence — this item is wiring only.
```

## Final Validation Checklist

### Technical Validation

- [ ] L1 py_compile + import purity + symbol checks OK.
- [ ] `tests/test_bulk_dispatch.py` green; neighbor `-k` spot-runs green.
- [ ] `tests/test_bulk_controller.py` + `tests/test_g2_bulk_gate.py` green UNTOUCHED (additive hook).
- [ ] G1 watch set numbers IDENTICAL to the Task 0 baseline (incl. the pre-existing
      `test_streaming_commit` reds — reconciled, not newly broken, not skipped).
- [ ] Structural AST checks: intercept before `_lock` in `cancel()`; branches present in
      `on_final`/`_on_partial`.

### Feature Validation

- [ ] Bulk dispatch: partial/final/dropped/identity-missing per spec; zero `_stream`/backend
      calls on the bulk path; seq + gen mapping correct; `record_final` keeps recognition meaning.
- [ ] Cancel: no `press_backspace` on the bulk path; `ctrl.cancel(gen)` out of lock; shared
      suppress latch + `host.cancel()`; idempotent when not armed; both entry points funnel.
- [ ] Lifecycle: acquire→arm→start order; unsupported-on-acquire-failure (recording stays armed);
      fault disarm (one reason, both disarmed); clean disarm (leave exactly once, no late flush,
      epoch-guarded stopper, never under `_lock`); quit teardown bounded-joined.
- [ ] `record_confirmed_op` populated via the additive hook; descriptor = counts+times only.
- [ ] Default mode byte-identical (unit-level inertness pin + G1 watch set).

### Code Quality Validation

- [ ] Adds-only within the 3 declared files; scope walls respected (streaming/typing_backends/
      ime/pi_editor/recorder_host/config/feedback/ctl untouched).
- [ ] Nothing blocking under `_lock` (thread spawns + enqueue only); `on_stopped` handler
      deadlock-free by construction; reader-thread entries are enqueue-and-return.
- [ ] New bulk logs carry counts/times, never recognition text (G8); feedback mirrors keep
      recognition meaning.
- [ ] `on_applied` default None leaves the controller byte-identical for existing callers.

### Documentation & Deployment

- [ ] daemon.py module docstring: Mode A delivery note (gate, enqueue law, intercept, lifecycle,
      lock discipline, seam).
- [ ] No new config keys / env vars / voicectl surface (T2.S3 owns `session`).

---

## Anti-Patterns to Avoid

- ❌ Don't call `ctrl.cancel()`/`ctrl.stop()` under `self._lock` — `on_stopped` fires synchronously
  and the handler takes `_lock` (deadlock) / `stop()` joins ≤5 s (the NEW-2 wedge).
- ❌ Don't put the bulk branch BEFORE the suppression-window block in `on_final` — the window's
  early-returns are the double-type guard; the cancelled utterance is already closed controller-side.
- ❌ Don't synthesize typing on the bulk path (`type_text`/`press_backspace`/`make_backend`) —
  R.1 event-count law; a blocked matrix row is a legitimate result, a typing fallback never is.
- ❌ Don't fall back to a constant utterance id when `relay_identity` is missing — the final
  closes the key and every later partial dup-discards (silent death). Drop + count instead.
- ❌ Don't rewrite the legacy `cancel()`/`on_final` bodies — insert branches; the legacy paths
  must stay byte-identical (G1).
- ❌ Don't write `set_delivery_state("inactive")` unconditionally in `_disarm()` — it erases a
  just-recorded fault reason (feedback always overwrites).
- ❌ Don't let the stopper kill a new delivery lifetime — epoch-guard it (G11).
- ❌ Don't add config keys, voicectl commands, or `session`/recovery logic — T2.S2/T2.S3/T3.S1 own
  those; don't "fix" the bulk prompt source either (`_stream.committed` stays until M6.T3.S1).
- ❌ Don't run the daemon, the E2E scripts, CUDA suites, or a real IM subprocess for this item —
  unit doubles only (AGENTS.md).

---

## Confidence Score

**9/10.** Every integration site was verified live this session (current line cites, not the
drifted contract cites); the controller/adapter/feedback/config surfaces are landed with exact
signatures; the two genuinely hazardous interactions (the `on_stopped`↔`_lock` deadlock and the
NEW-2 wedge) have explicit structural solutions (out-of-lock intercept, epoch-guarded stopper
thread) copied from landed precedents (`_safe_abort` discipline, AsyncDucker dispatch); and the
parallel-item dependency (`relay_identity`) is consumed through a narrow getattr seam that
degrades to drop-and-count. Residual risks: (1) the parallel T1.S1 lands a slightly different
accessor shape than its PRP specifies (mitigated: the seam is one getattr + a NamedTuple duck,
trivially adaptable; the drop-path test pins the absence case); (2) thread-timing flakiness in
the arm/stopper tests (mitigated: joinable thread attributes + the G2 `_wait_until` idiom, both
proven in this repo); (3) the additive `on_applied` hook touches a G2-passed file (mitigated:
default-None + the untouched-suite gate in L2 is a hard stop).
