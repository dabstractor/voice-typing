# PRP — P1.M2.T1.S2: Start the production IM route on the bulk arm worker

## Goal

**Feature Goal**: Close the **production-GTK parity gap** (architecture/bulk_delivery_gate.md §4): the default bulk route's `_build_default_bulk_target` builds a pure `ImeProcess`+`ImeTarget` bundle but **nothing ever spawns the IM child**, and `ImeProcess.request` returns `None` unless already RUNNING — so in production `ImeTarget.acquire` always fails (`"ime no reply"`) and the G5 lab masks the gap with a lab-only spawn/activation loop in `GtkRoute.bulk_target_factory`. Fix: **on the `vt-bulk-arm` worker, outside the daemon lock**, start the production IM child (`ImeProcess.spawn`), **boundedly pump read-only activation** (poll `request('ping')` until its reply carries `activated=true`), then acquire — with stale-epoch/disarm-race rejection before publishing `active`, preserved unsupported/held-seat semantics with a concise reason, bounded cleanup on failure, and **no retry of possibly-applied edits** (acquire stays exactly-once).

**Deliverable** (2 source + 1 test file; construction stays pure):
1. `voice_typing/daemon.py` — (a) NEW `_BulkTargetBundle.start(timeout) -> str | None` (spawn + bounded read-only activation pump; `None`=ready, else a concise reason; `_proc is None` ⇒ no-op success — the `attach()` guard precedent); (b) module constants `_IME_ACTIVATE_TIMEOUT_S = 2.0`, `_IME_ACTIVATE_POLL_S = 0.05`; (c) `_arm_work` wiring: after `bundle.attach(ctrl)` and before `ctrl.acquire()` call `bundle.start()`; failure ⇒ `bundle.teardown()` + `set_delivery_state("unsupported", reason)` + return (recording stays armed, R.5 — same shape as today's acquire failure); success ⇒ an epoch+listening re-check (`ctrl.stop(leave=True)` + `bundle.teardown()` on stale — never ghost-arm), then the existing unchanged acquire path; (d) Mode-A docstring fixes (`_BulkTargetBundle`, `_build_default_bulk_target` — the stale "spawn happens lazily inside acquire()" claim).
2. `README.md` — Troubleshooting § "Bulk delivery: the input-method seat is taken" (line ~487): the daemon now starts its own IM child on first bulk arm and waits (bounded ~2 s) for activation; a held seat surfaces as `delivery: unsupported` + the concise reason.
3. `tests/test_daemon.py` — additive hermetic section (mock `ImeProcess`/`request`/`time`; fake target + recorder; NO real Popen) covering: pure factory, spawn→pump→ready, never-activated, held seat, spawn fault, fake-bundle no-op, arm-worker unsupported+stays-armed, stale-epoch-before-acquire, fresh rearm, stop-during-startup.

**Success Definition**:
- (a) Production GTK can acquire through the **default daemon factory** with no lab bridge: a fresh `_build_default_bulk_target` bundle, `attach`ed on the arm worker, `start()`s its own IM child, pumps activation bounded, then acquires. (P1.M2.T1.S4 consumes exactly this route.)
- (b) Construction stays **pure**: `_build_default_bulk_target`'s body is byte-identical (docstring only); no subprocess runs at construction (a Popen-explodes test proves it).
- (c) Failure semantics preserved: held seat / never-activated / spawn fault ⇒ `delivery_state="unsupported"` + ONE concise reason + bounded teardown + recording STAYS armed (R.5); acquire is never retried (R.5); a stale epoch or disarm race never publishes `active`.
- (d) Fake/test bundles (`_proc=None`) are unchanged: `start()` is a no-op success — every existing injected-fake bulk test passes untouched.
- (e) `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q` → 0 failures beyond the documented G1 baseline (P1.M1.T3.S1); the full pure sweep stays green; only `daemon.py`, `README.md`, `tests/test_daemon.py` change.

## User Persona

**Target User**: the bulk-text operator (opt-in `output.delivery="bulk-text"`) and the acceptance harness. Today the default route can NEVER deliver in production (acquire always fails "ime no reply"); only the G5 lab's private bridge worked.
**Use Case**: first bulk arm on a real (disposable-compositor) session: the daemon starts its IM child, waits bounded for compositor activation, acquires the focused editable, and delivers words live.
**Pain Points Addressed**: production parity with the lab route (BUG-002 remediation prerequisite); a stoppable, bounded startup that can never hang the daemon or leave a half-armed ghost.

## Why

- **The default route is dead in production.** Verified: `ImeTarget.acquire` → `ImeProcess.request` returns `None` unless `state=="running"` (manager.py:219-229), and nothing on the default path ever calls `spawn()`. The `_build_default_bulk_target` docstring's "spawn happens lazily inside acquire()" is false — `acquire()` is a `request('acquire')`, not a spawn. The G5 lab admits it (g5_timing_lab.py:303-311: "This factory therefore does the G3 start_adapter…").
- **Route acceptance must exercise the real startup path** (architecture doc §4): S4 wires the isolated route runner to compare REAL recorder builds through the default factory; that requires the production route to actually start here.
- **The machinery already exists — only the wiring is missing.** `ImeProcess.spawn` (child + one ping echo, idempotent-while-running, sanctioned next-arm respawn on unsupported/fault, bounded teardown); `request('ping')` replies carry `activated=` (read-only); `ime_host._acquire` refuses while not activated — hence the bounded pump between spawn and acquire.
- **Safety shape is already established.** The arm worker already runs subprocess round-trips out of `_lock` (G1/G3), already handles acquire-failure as `unsupported` + stays-armed (R.5), already re-checks epoch/listening after round-trips (never ghost-arm), and `bundle.teardown()` is already bounded + never-raises. The fix slots `spawn+pump` into that exact shape.

## What

Add the bounded startup step between takeover-attach and acquire on the `vt-bulk-arm` worker; keep the factory pure; map every startup failure to the existing concise-reason/unsupported/teardown/stays-armed shape; update the two docstrings + the README troubleshooting entry; prove it all with hermetic fakes.

### Success Criteria

- [ ] `_BulkTargetBundle.start(timeout=None) -> str | None` exists: `_proc is None` ⇒ `None`; `spawn()` false ⇒ reason ("ime seat held (unsupported)" for state `unsupported`, else `f"ime spawn failed ({state})"`); ping-pump until `activated=true` within `_IME_ACTIVATE_TIMEOUT_S` ⇒ `None`; deadline ⇒ `"ime not activated"`.
- [ ] `_arm_work` calls `bundle.start()` after `bundle.attach(ctrl)` and before `ctrl.acquire()`; failure ⇒ `bundle.teardown()` + `set_delivery_state("unsupported", reason)` + `logger.info` + return (no acquire); success ⇒ epoch+listening re-check (stale ⇒ `ctrl.stop(leave=True)` + `bundle.teardown()` + return) then the unchanged acquire path.
- [ ] `acquire` is called at most once per lifetime (no retry after any possibly-applied mutation); spawn once per lifetime; the activation pump uses only read-only `ping`.
- [ ] `_build_default_bulk_target` body byte-identical; a Popen-explodes test pins purity.
- [ ] Existing injected-fake bulk tests unchanged and green (fake bundles no-op through `start()`).
- [ ] New tests: the 10 cases in the research note §4 all pass hermetically.
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q` → baseline-only; only `daemon.py`, `README.md`, `tests/test_daemon.py` in `git status`.

## All Needed Context

### Context Completeness Check

_Pass._ The gap, the exact code sites (with HEAD line numbers), the available ImeProcess/ime_host semantics (spawn/ping/activated/state machine), the arm-worker's existing safety shape, the G5 lab bridge it replaces, the verbatim `start()` design + `_arm_work` wiring, the 10 hermetic test cases with their fakes, and the parallel/downstream boundaries are all in the research note with file:line evidence.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S2/research/production_im_startup.md
  why: "§1 the gap (request-returns-None-unless-running; the false 'inside acquire' docstring; the G5 bridge).
        §2 the machinery (spawn semantics, ping/activated, attach-before-spawn, the _arm_work shape, epoch/gen).
        §3 the verbatim start() design + _arm_work wiring + the rule-by-rule rationale. §4 the 10 test cases.
        §5 docs. §6 boundaries."
  section: "§2, §3, §4 are load-bearing."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/bulk_delivery_gate.md
  why: "§4 'Production GTK parity gap confirmed' — the prescription this implements verbatim: 'On vt-bulk-arm
        outside the daemon lock, start the real process and boundedly pump read-only ping activation
        (ime/ime_host.py:handle_line, _dispatch, _acquire) before acquire; retain pure construction,
        epoch/listening guard, bounded teardown including failure, held-seat refusal, and the existing
        fresh-lifetime takeover subscription. No retries of mutations or IM replacement.'"
- file: voice_typing/daemon.py
  why: "_BulkTargetBundle @720-758 (attach @743 guards _proc None — copy that guard in start(); teardown @750);
        _build_default_bulk_target @761-774 (docstring lie to fix; body stays); ctor seam bulk_target_factory
        @800/@1063-1069; state fields @1070-1073; _bulk_begin_delivery/_arm_work @2085-2142 (the wiring site:
        attach @2116 → NEW start+re-check → acquire @2118); _bulk_schedule_stop @2144-2180; _on_bulk_stopped
        @2182 (fault classes — unchanged); module constants precedent (_DRAIN_TIMEOUT_S style)."
  gotcha: "ATTACH MUST PRECEDE start() — the TakeoverWatch late-binds proc._on_event (daemon.py:743-748); attaching
           after spawn could miss a takeover during activation. Do NOT touch _on_bulk_stopped/_bulk_schedule_stop."
- file: voice_typing/ime/manager.py
  why: "ImeProcess.spawn @146-219 (the docstring IS the contract: True iff RUNNING; unsupported=fcitx5 seat;
        unsupported/fault respawn is the sanctioned NEXT-arm path — never spawn twice in-flight; bounded teardown
        on fault). request @219-229 (None unless RUNNING — the gap). state property @133. stop @238. healthy @231.
        _REQUEST_TIMEOUT_S default for ping timeout choice."
- file: voice_typing/ime/ime_host.py
  why: "_dispatch 'ping' @139-141 replies carry activated=self.activated (the read-only probe); _acquire @156-161
        refuses while not activated (why the pump exists); activated flips on activate/deactivate events @86-96."
- file: voice_typing/ime/target.py
  why: "ImeTarget.acquire — the unchanged exactly-once acquire (request('acquire') → AcquireResult with reason
        strings like 'ime no reply'/'acquire refused'/'user selection present')."
- file: tests/g5_timing_lab.py
  why: "GtkRoute.bulk_target_factory @363+ and the @303-311 comment — the lab-only bridge being replaced on the
        acceptance path (S4 will drop it for the default route; do NOT edit the lab in this task)."
- file: tests/conftest.py + tests/test_daemon.py
  why: "hermetic_cfg (P1.M1.T1.S2, imported at test_daemon.py:27) — every new daemon is built media-hermetic via
        _make_daemon (:687); bulk tests use the bulk_target_factory= seam for fake bundles. The G1 baseline
        (P1.M1.T3.S1) is the documented red-set the suite must not exceed."
- file: README.md
  why: ":487 '### Bulk delivery: the input-method seat is taken (fcitx5/ibus)' — the troubleshooting entry to
        update (Mode A). Overview sections stay for P1.M2.T3.S2."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S1/PRP.md
  why: "The parallel sibling (partial_source selector) edits _build_callbacks/_construct/build_recorder/_load_host
        + recorder_host.py + both test files' partial-source sections — DISJOINT from _BulkTargetBundle/_arm_work.
        Confirm no region overlap before editing; both touch test_daemon.py additively."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py            # EDIT: _BulkTargetBundle.start + 2 constants + _arm_work wiring + 2 docstrings.
│   └── ime/{manager,target,ime_host,takeover}.py   # READ-ONLY (the machinery consumed as-is).
├── README.md                # EDIT: Troubleshooting § Bulk delivery (~:487).
└── tests/test_daemon.py     # EDIT: additive hermetic section (fake ImeProcess; the 10 cases).
# g5_timing_lab.py UNTOUCHED (S4 owns the lab). bulk_controller/bulk_delivery UNTOUCHED. No config knob.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — CONSTRUCTION STAYS PURE. _build_default_bulk_target's body is byte-identical (docstring only);
#   the spawn/pump runs in bundle.start() ON THE ARM THREAD. A Popen-explodes monkeypatch test pins it.
# CRITICAL #2 — ATTACH BEFORE START. bundle.attach(ctrl) late-binds proc._on_event (daemon.py:743-748); it must
#   happen BEFORE spawn so no child event (incl. a takeover during activation) is missed.
# CRITICAL #3 — ACQUIRE STAYS EXACTLY-ONCE; THE PUMP IS READ-ONLY. Ping carries no mutation, so polling/repeating
#   it is safe; NEVER re-call acquire after a possibly-applied round-trip, NEVER spawn a second child to "replace"
#   a flaky one in-flight (unsupported/fault respawn is the NEXT arm's sanctioned path — manager.py spawn docstring).
# CRITICAL #4 — FAKE BUNDLES MUST NO-OP. _proc is None for injected fakes — start() returns None immediately (the
#   attach() guard precedent), or every existing bulk test with a fake target breaks.
# CRITICAL #5 — STALE/DISARM RACES NEVER PUBLISH ACTIVE. Re-check epoch+listening after the subprocess round-trips
#   (before acquire) AND keep the existing post-acquire re-check; both paths tear down via ctrl.stop(leave=True) +
#   bundle.teardown() and return WITHOUT setting _bulk_delivery_active or writing "active".
# CRITICAL #6 — FAILURE WRITES EXACTLY ONE CONCISE STATE. set_delivery_state("unsupported", reason) on the arm
#   thread (the existing acquire-failure precedent); do NOT also write "fault" there (child-crash fault flow stays
#   in ImeProcess's on_delivery_state seam + _on_bulk_stopped). Recording stays armed (R.5).
# CRITICAL #7 — BOUND EVERYTHING. spawn uses ImeProcess's own timeout; the pump deadline is _IME_ACTIVATE_TIMEOUT_S
#   (2.0 s) with _IME_ACTIVATE_POLL_S (0.05 s) polls via request('ping', timeout=poll); teardown is bounded and
#   never raises. The arm thread must never hang.
# GOTCHA #8 — HERMETIC TESTS: fake ImeProcess (records spawn/request/stop; scripts ping replies + state), monkeypatch
#   time.monotonic/sleep for the pump, _make_daemon + hermetic_cfg + bulk_target_factory seam; NO real Popen/CUDA/
#   desktop (R.7). pytest>=9.1.1; full paths + functional `timeout` (AGENTS.md). No ruff/mypy.
# GOTCHA #9 — P1.M1.T3.S1 BASELINE: test_daemon.py has a documented ~20-case legacy red set — diff FAILED names
#   against tests/G1_BASELINE.md, don't chase pre-existing reds.
# GOTCHA #10 — LINE NUMBERS DRIFT (S1 lands in parallel): find _arm_work by the `bundle.attach(ctrl)` line and
#   _BulkTargetBundle by the class def, not by absolute line numbers.
```

## Implementation Blueprint

### Data models and structure

None new. `_BulkTargetBundle` gains one method; two module float constants; no schema/config/knob changes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: ADD the failing tests FIRST (RED) — additive hermetic section in tests/test_daemon.py.
  - Fakes: _FakeImeProc (records spawn_calls/request_cmds/stop_calls; scriptable spawn_ok/state/ping_replies list
    of dicts; optional block Event for slow-activation cases); reuse the existing fake-bundle pattern
    (_BulkTargetBundle(target=fake_target, proc=fake_proc) via bulk_target_factory). Monkeypatch
    daemon-module time for pump tests.
  - The 10 cases verbatim in research §4: pure factory (Popen explodes), spawn→pump→ready, never-activated,
    held seat, spawn fault, fake-bundle no-op, arm-worker unsupported+stays-armed+no-acquire, stale-epoch-before-
    acquire, fresh-rearm-spawns-fresh-child, stop-during-startup-tears-down.
  - RUN (RED): timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'bundle_start or ime_start or
    bulk_arm_worker' → fail (no start() today).

Task 2: EDIT voice_typing/daemon.py — the start() method + constants (GREEN, part 1).
  - 2a: module constants near the other timeout constants: _IME_ACTIVATE_TIMEOUT_S=2.0, _IME_ACTIVATE_POLL_S=0.05.
  - 2b: _BulkTargetBundle.start(timeout=None) — the verbatim design in research §3: _proc None ⇒ None;
    spawn() false ⇒ concise reason from proc.state() (unsupported ⇒ "ime seat held (unsupported)"; else
    f"ime spawn failed ({state})"); loop request("ping", timeout=_IME_ACTIVATE_POLL_S) until reply.get("activated")
    ⇒ None, sleeping _IME_ACTIVATE_POLL_S, bounded by monotonic deadline (timeout param overrides); deadline ⇒
    "ime not activated". Update the class docstring (Mode A).
  - 2c: fix _build_default_bulk_target's docstring: spawn + bounded activation run in bundle.start() on the
    vt-bulk-arm thread (body unchanged).
  - DO NOT: spawn in the factory; call healthy() (spawn's ping echo already gates RUNNING; the pump needs the
    activated field); edit ime/ package files; add config.

Task 3: EDIT voice_typing/daemon.py — the _arm_work wiring (GREEN, part 2).
  - FIND the `bundle.attach(ctrl)` line inside _arm_work (_bulk_begin_delivery). INSERT after it, before the
    existing `if not ctrl.acquire():`:
        start_reason = bundle.start()   # production IM child + bounded read-only activation pump (P1.M2.T1.S2)
        if start_reason is not None:
            bundle.teardown()           # bounded cleanup of any leftover child (idempotent, never raises)
            self._feedback.set_delivery_state("unsupported", start_reason)
            logger.info("bulk delivery start failed: gen=%d reason=%s", gen, start_reason)
            return                      # recording STAYS armed (R.5 — the acquire-failure shape)
        if epoch != self._bulk_epoch or not self._listening.is_set():
            ctrl.stop(leave=True)       # stale/disarm raced the subprocess round-trip — never ghost-arm
            bundle.teardown()
            return
    (the existing acquire path + its own post-acquire re-check stay byte-identical after this insert).
  - Update _bulk_begin_delivery's docstring: the arm thread now also starts the IM child + pumps activation
    before acquire (all round-trips off-lock, G1/G3).
  - DO NOT: reorder attach/acquire; retry acquire; touch _on_bulk_stopped/_bulk_schedule_stop/epoch semantics.

Task 4: EDIT README.md — Troubleshooting § Bulk delivery (~:487, Mode A).
  - State the real behavior: on first bulk arm the daemon spawns its own input-method child and waits bounded
    (~2 s) for compositor activation before acquiring; a held seat (fcitx5/ibus) or timeout surfaces as
    `delivery: unsupported` with the concise reason; stopping mid-startup tears the child down. No overview
    claims (P1.M2.T3.S2 owns those).

Task 5: VALIDATE.
  - timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'bundle_start or ime_start or bulk_arm_worker'
  - timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q          # G1 baseline diffs only
  - timeout 600 .venv/bin/python -m pytest tests/ -q --ignore=tests/test_daemon.py --ignore=tests/test_feed_audio.py \
    --ignore=tests/test_recorder_host.py   # the pure sweep (incl. S1's parallel partial_source additions)
  - git status --short → ONLY voice_typing/daemon.py, README.md, tests/test_daemon.py.
    Message if committed: "P1.M2.T1.S2: start the production IM child on the bulk arm worker (bounded read-only
    activation pump before acquire; pure construction preserved)".
```

### Implementation Patterns & Key Details

```python
# PATTERN — the bounded read-only activation pump (R.5-safe: ping mutates nothing; acquire stays exactly-once):
def start(self, timeout=None):
    if self._proc is None: return None                     # fake bundle (the attach() guard precedent)
    if not self._proc.spawn():                             # once per lifetime; idempotent while RUNNING
        st = self._proc.state
        return "ime seat held (unsupported)" if st == "unsupported" else f"ime spawn failed ({st})"
    deadline = time.monotonic() + (timeout if timeout is not None else _IME_ACTIVATE_TIMEOUT_S)
    while time.monotonic() < deadline:
        r = self._proc.request("ping", timeout=_IME_ACTIVATE_POLL_S)   # read-only probe
        if r is not None and r.get("activated"): return None           # ready → caller acquires
        time.sleep(_IME_ACTIVATE_POLL_S)
    return "ime not activated"

# PATTERN — arm-worker slot-in (attach → start → re-check → acquire; failure mirrors acquire-failure exactly):
bundle.attach(ctrl)                # BEFORE spawn: the watch late-binds proc._on_event (G10)
start_reason = bundle.start()      # subprocess round-trips OUTSIDE _lock (G1/G3)
if start_reason is not None:
    bundle.teardown(); self._feedback.set_delivery_state("unsupported", start_reason); return  # stays armed
if epoch != self._bulk_epoch or not self._listening.is_set():
    ctrl.stop(leave=True); bundle.teardown(); return      # never ghost-arm
if not ctrl.acquire(): ...          # UNCHANGED exactly-once acquire path
```

### Integration Points

```yaml
DOWNSTREAM — P1.M2.T1.S4 (route runner): consumes THIS route (default factory + bundle.start) in the disposable
  compositor; drops the GtkRoute lab bridge from the acceptance path (the lab file itself is NOT edited here).
DOWNSTREAM — P1.M2.T2.S3 / S6: the qualified production route their measurements assume.
PARALLEL — P1.M2.T1.S1 (partial_source): disjoint daemon regions (_build_callbacks/_construct/build_recorder/
  _load_host + recorder_host) vs. here (_BulkTargetBundle/_arm_work/constants); both add test_daemon.py sections.
UNCHANGED: _build_default_bulk_target body, ime/ package, BulkController, _on_bulk_stopped, _bulk_schedule_stop,
  config (no knob), ctl, g5_timing_lab.py (S4's), stream-edit.
```

## Validation Loop

> Full paths + functional `timeout` on every command (AGENTS.md). Run from `/home/dustin/projects/voice-typing`.
> Hermetic only — NO real Popen/CUDA/desktop in tests (R.7). pytest>=9.1.1; no ruff/mypy.

### Level 1: the mechanism is in place (static + purity)

```bash
cd /home/dustin/projects/voice-typing
grep -nE 'def start\(' voice_typing/daemon.py | head -3                      # _BulkTargetBundle.start present
grep -nE '_IME_ACTIVATE_(TIMEOUT|POLL)_S' voice_typing/daemon.py              # the two constants
sed -n "$(grep -n 'bundle.attach(ctrl)' voice_typing/daemon.py | head -1 | cut -d: -f1),+12p" voice_typing/daemon.py
#   → start_reason wiring visible between attach and acquire
timeout 60 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'bundle' 2>/dev/null | tail -1
# Expected: start()+constants present; the wiring sits between attach and acquire; the purity test green.
```

### Level 2: the new hermetic cases (the contract)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'bundle_start or ime_start or bulk_arm_worker'
# Expected: all new cases pass (the 10 in research §4). A failure in stays-armed/no-acquire means the wiring
# leaks a mutation or a state write on the failure path — re-check Task 3's insert.
```

### Level 3: no regression (baselines + pure sweep)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q
#   → diff FAILED names against tests/G1_BASELINE.md (P1.M1.T3.S1) — no NEW reds (S1's parallel additions may
#     add greens).
timeout 600 .venv/bin/python -m pytest tests/ -q \
  --ignore=tests/test_daemon.py --ignore=tests/test_feed_audio.py --ignore=tests/test_recorder_host.py
# Expected: 0 failures (the injected-fake bulk tests — dispatch/controller/context — pass unchanged because
# fake bundles no-op through start()).
```

### Level 4: scope guard

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: ONLY voice_typing/daemon.py, README.md, tests/test_daemon.py. NO ime/ files, NO bulk_controller.py,
# NO bulk_delivery.py, NO g5_timing_lab.py, NO config.py/config.toml, NO ctl.py.
grep -n 'seat is taken' README.md | head -2   # the troubleshooting entry was updated (Mode A)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `start()` + 2 constants present; wiring between `attach` and `acquire`; purity test green.
- [ ] L2: the 10 new hermetic cases pass.
- [ ] L3: `test_daemon.py` matches the G1 baseline (no new reds); the pure sweep is green.
- [ ] L4: only `daemon.py`, `README.md`, `tests/test_daemon.py` changed.

### Feature Validation
- [ ] Production GTK can acquire through the default factory (spawn → bounded activation pump → acquire), no lab bridge needed on the path S4 will drive.
- [ ] Held seat / never-activated / spawn fault ⇒ `unsupported` + ONE concise reason + bounded teardown + recording stays armed.
- [ ] Stale epoch / disarm race ⇒ teardown, no `active` publish, no acquire after staleness.
- [ ] Acquire exactly-once; pump read-only; spawn once per lifetime; fresh rearm gets a fresh child.

### Code Quality Validation
- [ ] `_build_default_bulk_target` body byte-identical (docstring only); fake bundles no-op.
- [ ] Docstrings (Mode A) updated on `_BulkTargetBundle` + `_build_default_bulk_target` + `_bulk_begin_delivery`; README troubleshooting entry current.
- [ ] Hermetic tests only; full paths + `timeout` everywhere; baselines diffed, not eyeballed.

### Scope Boundary Validation
- [ ] `ime/` package, `bulk_controller.py`, `bulk_delivery.py`, `g5_timing_lab.py`, config, ctl untouched.
- [ ] No region overlap with S1's parallel edits (different daemon functions; both test sections additive).
- [ ] No config/env/CLI knob added.

---

## Anti-Patterns to Avoid

- ❌ Don't spawn in `_build_default_bulk_target` — construction stays pure; startup lives in `bundle.start()` on the arm thread.
- ❌ Don't attach the takeover watch after `start()` — the watch late-binds `proc._on_event`; attach must precede spawn.
- ❌ Don't retry `acquire`, re-spawn to "replace" a flaky child mid-lifetime, or write `fault` from the arm thread — exactly-once mutations; held-seat/timeout map to `unsupported`; child faults flow through the existing seams.
- ❌ Don't forget the `_proc is None` no-op guard — every injected-fake bulk test depends on it.
- ❌ Don't publish `active` (or acquire) when the epoch went stale during the subprocess round-trips — tear down and return.
- ❌ Don't use `healthy()` as the activation probe — it only re-checks RUNNING; the pump needs the ping reply's `activated` field.
- ❌ Don't edit the `ime/` package, `BulkController`, the stopper/fault paths, or the G5 lab; don't add a config knob.
- ❌ Don't run real Popen/CUDA or touch the live desktop in tests (R.7); no pytest without `timeout`; no bare python/pytest; no ruff/mypy; diff the G1 baseline instead of chasing pre-existing reds.

---

## Confidence Score

**8/10** — the gap and its exact prescription are quoted from the architecture doc and verified against the live code (request-returns-None-unless-running; the false "inside acquire" docstring; the G5 bridge comment); the machinery consumed (`spawn` semantics, ping/`activated`, the arm-worker safety shape) is read with line numbers; the `start()` design and `_arm_work` wiring are given verbatim with the rule-by-rule rationale; and the 10 hermetic cases pin the failure matrix. The −2: (a) `_arm_work` runs on a real thread, so the arm-worker tests need a deterministic drive (join the thread or a synchronous seam) — the PRP allows either and the fake proc's scriptable replies make both reliable; (b) S1 lands in parallel touching the same files' other regions — line numbers will drift (find by `bundle.attach(ctrl)` / the class def) and the additive test sections must not collide, which the disjoint-region map guards but cannot fully guarantee.
