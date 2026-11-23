# PRP — P1.M2.T2.S4: Failure discipline — non-blocking, bounded, idempotent engage/release wrappers

## Goal

**Feature Goal**: Implement the **failure-discipline layer** of media ducking (PRD §4.2quinquies, D1): `voice_typing/ducking_async.py` with `AsyncDucker`, a dispatch wrapper around S1's landed `AudioDucker` whose `engage()`/`release()` **(a) never block the caller** (async dispatch — the arm path runs UNDER the daemon's `self._lock`, so an inline engage would wedge every control command, the validation-NEW-2 wedge class), **(b) survive a hung backend call** (a mocked 5 s backend sleep must not delay the arm beyond bound — PRD test case d), and **(c) stay idempotent under repeated arms** (no stacked pauses or volume writes — PRD test case e). "Ducking is an enhancement, NEVER a gate" (PRD failure discipline) is the invariant every test pins.

> **Pre-verified design (research §2):** a **single-flight latest-wins dispatcher** — the wrapper records the latest desired state under a tiny lock (never held across backend calls) and applies it on at most ONE short-lived daemon worker thread (`vt-ducking`), exactly the fire-and-forget shape the seams doc prescribes for the arm site ("same shape as the signal handler's spawn, daemon.py:2738-2742") but with the ordering race (stale engage surviving a rapid arm→disarm→arm) fixed at the dispatch layer. Plus a bounded `flush(timeout)` seam for T3's quit path.

**Deliverable** (2 NEW files; no edits to existing sources — S1's `audio_ducking.py` is FROZEN, S3's `ducking_volume.py` is parallel, daemon wiring is T3):
1. `voice_typing/ducking_async.py` — module docstring (Mode A: the lock-discipline rationale with the NEW-2 + signal-spawn precedents, the latest-wins rationale, the flush contract, the T3/T4 handoff, the ownership map) + `AsyncDucker` (the exact state machine from research §2).
2. `tests/test_ducking_async.py` — **10 pure-Python tests** (zero subprocess, zero CUDA, zero daemon, zero tier imports) using S1's `_FakeBackend` pattern extended with a `slow={method: seconds}` map for the hung-backend case (d).

**Success Definition**:
- (a) `engage()`/`release()` return in < 0.5 s **even while the backend is hung 5 s** (case d); they never raise; `duck_mode="off"` produces zero backend calls end-to-end.
- (b) Repeated `engage()` calls apply the backend work **exactly once** (coalesced at dispatch + no-op inside S1's ducker — case e); `release()` without a prior engage is a full no-op (zero backend calls).
- (c) Rapid arm→disarm→arm ends in the state of the LAST request (latest-wins; no stale engage leaves media ducked while disarmed, no stale release un-ducks an armed session).
- (d) `flush(timeout=2.0)` is bounded: returns `True` fast when drained; returns `False` within the bound (+ a little) when the worker is hung — never hangs.
- (e) `timeout 300 .venv/bin/python -m pytest tests/test_ducking_async.py -q` → **10 passed**; `timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → **no new failures** beyond `tests/G1_BASELINE.md`; `git status --short` == the 2 new files only (plus parallel siblings' files).

## User Persona

Not a user surface yet (`duck_mode` ships `"off"`; T4 flips the default). Beneficiaries: **T3** (P1.M2.T3.S1 wires `AsyncDucker.engage()` at `_arm()`'s toast site and `release()` at every disarm seam — its PRP assumes exactly this non-blocking contract; T3.S2's quit path calls `flush()`), and the end user once enabled: the hotkey arm stays instant even when `playerctl`-class backends misbehave, and repeated arms never stack pauses or volume writes.

## Why

- **The arm path runs under the control lock.** `_arm()` (toast site ~daemon.py:1415, docstring "set_listening(True) fires the transient 'Recording' start toast") and `_disarm()` are called under `self._lock` by start/toggle/stop. An inline ducking engage would hold the CONTROL LOCK across ≤1 s subprocess calls per backend primitive (several players on the mpris tier) — the exact wedge that once made `voicectl start/stop/toggle` hit `timeout`/exit-124 (validation NEW-2; `_disarm` docstring ~1422-1436, `_safe_abort` ~2086-2114). The PRD's "arm latency must not measurably change (engage runs concurrently with recorder arming; the arm does not wait for it)" is only satisfiable with async dispatch. (Research §1.)
- **PRD test cases (d) + (e) are THIS item's gate.** "a hung backend call (mocked 5 s sleep) does not delay arm beyond bound" and "engage/release idempotence" are two of the six §4.2quinquies unit tests; the other four (a)(b)(c)(f) are pinned by S1/S2/S3's landed tests. S4 closes the discipline set and leaves the ducker "ready to wire" (item OUTPUT).
- **Naive per-call threads are not enough — ordering.** Three racing threads (engage, release, engage) acquire the inner ducker's lock in ARRIVAL order; a release that beats the first engage leaves media ducked while disarmed. The single-flight latest-wins design (research §2) fixes the race at the dispatch layer while keeping the prescribed short-lived-daemon-thread shape. (Research §2.)
- **Scope discipline.** S1 owns the bookkeeping/sovereignty (frozen), S2/S3 own the subprocess tiers, T3 owns the daemon seams + crash safety (`ducked` flag, ExecStopPost), T4 owns the default flip. S4 owns ONLY the dispatch discipline between them: non-blocking entry, coalescing, latest-wins ordering, bounded flush. No tier import, no daemon import, no config read at runtime.

## What

`AsyncDucker` wraps any engage/release pair (duck-typed; tests inject S1's real `AudioDucker` over a fake backend). `engage()`/`release()` record desired state under a tiny lock and ensure at most one `vt-ducking` daemon worker is applying pending states; both return immediately, never raise, and coalesce duplicates. The worker applies the LATEST pending state until none remain, then exits (short-lived). `flush(timeout=2.0)` waits bounded for drain (T3's quit seam). An `engaged` property proxies the inner ducker.

### Success Criteria

- [ ] `voice_typing/ducking_async.py` exists; imports = `logging`, `threading`, `typing` only (stdlib; zero subprocess, zero tier imports).
- [ ] `_dispatch` never holds its lock across a backend call; the worker is the ONLY thread that touches the inner ducker's engage/release.
- [ ] Case (d): with `get_sink_volume_pct` sleeping 5 s, `engage()` returns < 0.5 s (and release likewise).
- [ ] Case (e): 3× engage → exactly ONE round of backend application (mpris: one pause per playing player; volume: one `set_sink_volume_pct`); release-without-engage → zero backend calls.
- [ ] Latest-wins: rapid E→R→E ends engaged (volume at duck pct, no pending restore); rapid E→R→R ends released.
- [ ] Everything the wrapper does is swallow-wrapped: an all-raising backend yields normal returns + at most one WARNING per failure path; nothing ever propagates.
- [ ] `flush` bounded (True fast when drained; False within bound when hung); off-mode → zero backend calls; worker thread is `daemon=True`, named `vt-ducking`, gone after drain.
- [ ] 10 tests pass; fast suite shows no new failures vs `tests/G1_BASELINE.md`; only the 2 new files in `git status`.

## All Needed Context

### Context Completeness Check

_Pass._ The design is fully pre-verified: S1's `AudioDucker` was read line-by-line (its `_lock` serialization, `_engaged`-first engage, `_call` swallow, `from_config`); the lock-discipline rationale and the prescribed fire-and-forget shape are quoted from the seams doc (§1c/§1d) with the NEW-2 + signal-handler precedents cited to daemon.py line ranges; the state machine is written verbatim (research §2) including the coalescing, latest-wins, and flush semantics; all 10 tests are enumerated with their PRD-case mapping (research §4); the fake-backend extension (`slow` map) and the `_wait_until` poll helper are specified (research §3). A developer new to the repo needs nothing beyond the research note + S1's 183-line `audio_ducking.py`.

### Documentation & References

```yaml
# MUST READ — the pre-verified design + test matrix
- docfile: plan/008_a47116bb2b79/P1M2T2S4/research/failure_discipline_wrappers.md
  why: "§0 the D1 chain state (what's landed/frozen/parallel). §1 the lock-discipline rationale (arm under
        self._lock; NEW-2 precedent; signal-spawn shape). §2 ★ THE VERBATIM STATE MACHINE (single-flight
        latest-wins: _dispatch/_worker code, coalescing rule, hung-backend semantics, flush contract, engaged
        proxy). §3 the hung-backend fake + poll helper. §4 the 10-test matrix mapped to PRD cases (d)/(e).
        §5 scope guards. §6 verified validation commands."
  section: "ALL load-bearing; §2 is the implementation, §4 is the test plan."

# MUST READ — the PRD clause being implemented
- docfile: plan/008_a47116bb2b79/prd_snapshot.md   # §4.2quinquies (Media ducking)
  why: "'Failure discipline (non-negotiable)': ducking is an enhancement, NEVER a gate; arm latency must not
        measurably change; engage runs concurrently with recorder arming; engage/release idempotent — repeated
        arms must not stack pauses or volume writes, release without a prior engage is a no-op. Tests (d) and
        (e) are this item's gate."
  critical: "Every wrapper decision is judged against 'NEVER a gate'. If a choice could block or break the arm
             path, it is wrong."

# MUST READ — the frozen protocol consumer + the module this wraps
- file: voice_typing/audio_ducking.py
  why: "READ-ONLY (S1, landed, frozen). AudioDucker: engage/release under its own _lock (L148-176), _engaged
        set FIRST so a partially-failed engage unwinds via release, _call (L177+) swallow-wraps every backend
        exception into ONE warning, engaged property, from_config. The wrapper's worker calls exactly these
        two methods; the inner idempotence is the second belt-and-suspenders layer under dispatch coalescing."
  critical: "Do NOT edit this file. Do NOT re-implement bookkeeping in the wrapper — sovereignty stays in S1."

# MUST READ — the wiring context (T3 consumes S4's contract; do not implement it)
- docfile: plan/008_a47116bb2b79/architecture/d1_ducking_seams.md
  why: "§1c the choke points (engage at _arm() toast site ~1415; release at _disarm ~1454 +
        request_shutdown ~2177) — 'engage must be a fire-and-forget spawn ... same shape as the signal
        handler's spawn (2738-2742)'. §1d the lock/thread map at each site (NEW-2 abort-out-of-_lock
        precedent). Confirms WHY the wrapper must exist and what shape T3 expects."
  critical: "S4 delivers the wrapper; T3 delivers the wiring. Do NOT touch daemon.py."

# MUST READ — the sibling contracts (inputs; do not edit, do not import in tests)
- docfile: plan/008_a47116bb2b79/P1M2T2S2/PRP.md
  why: "S2 landed ducking_mpris.py (busctl tier, timeout=1.0 discipline; its docstring explicitly defers
        'engage latency ... to the daemon wiring (spawned, never under the arm) — see P1.M2.T3/S4'). Both
        tiers' ≤1 s timeouts are the SECOND bound under this wrapper's async bound."
  critical: "Zero tier imports in ducking_async.py — the wrapper is tier-agnostic."
- docfile: plan/008_a47116bb2b79/P1M2T2S3/PRP.md
  why: "S3 (parallel, treat as contract): ducking_volume.py + WpctlVolumeBackend. Its Success (f) + scope
        guard pin the same 2-file git discipline S4 mirrors. Its Level-3 smoke shows the fake-runner style."
  critical: "Do NOT import ducking_volume in tests (S3 may not be landed when S4 runs). Fakes only."
- file: tests/test_ducking.py
  why: "READ-ONLY. The _FakeBackend pattern (L34-80: mutating players/volume, fail set, call_log) + the module
        docstring/banner style S4's tests mirror. Extend the pattern in the NEW test file (slow map) — do not
        edit S1's."
  critical: "The fake must MUTATE state (players flip on pause/resume; volume stores on set) so sovereignty
             assertions observe real transitions."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── audio_ducking.py      # LANDED (S1) — READ-ONLY: PlayerState + DuckBackend + AudioDucker.
├── ducking_mpris.py      # LANDED (S2) — READ-ONLY: busctl tier.
├── ducking_volume.py     # S3 (parallel) — READ-ONLY per its PRP contract.
└── ducking_async.py      # CREATE (this task): AsyncDucker (the discipline wrappers).
tests/
├── test_ducking.py       # LANDED (S1) — READ-ONLY (12 fake-backend tests).
├── test_ducking_mpris.py # LANDED (S2) — READ-ONLY.
├── test_ducking_volume.py# S3 (parallel) — READ-ONLY.
└── test_ducking_async.py # CREATE (this task): 10 discipline tests (cases d + e + ordering + flush + off).
```

### Desired Codebase tree (unchanged structure — 2 new files)

```bash
# Same tree + voice_typing/ducking_async.py + tests/test_ducking_async.py. Nothing else changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE CALLER RUNS UNDER THE DAEMON'S CONTROL LOCK. _arm()/_disarm() execute under self._lock
#   (seams doc §1c/§1d). The wrapper's own _lock must therefore be a TINY lock: acquired, state flipped,
#   released — NEVER held across a backend call or a thread join. The inner AudioDucker._lock is held across
#   backend calls BY DESIGN (its serialization) — which is exactly why the wrapper must not call it inline.
#   (Research §1/§2.)
# CRITICAL #2 — ORDERING, NOT JUST IDEMPOTENCE. Naive per-call daemon threads race: a release thread can
#   acquire the inner lock BEFORE the first engage thread, leaving media ducked while disarmed. Implement the
#   single-flight latest-wins dispatcher EXACTLY as research §2 (desired-state slot + one worker; worker takes
#   the latest pending state each iteration). Do NOT "simplify" to per-call threads. (Research §2.)
# CRITICAL #3 — COALESCING + INNER NO-OP = CASE (e). Repeated engage() with the worker busy: if desired==True
#   pending → return (coalesced); if the worker already took True (desired=None) → re-queue True; the inner
#   AudioDucker.engage() then no-ops on _engaged. BOTH layers must stay idempotent — do not remove either.
#   Assert ONE backend application after 3 arms in both tiers (mpris: one pause per playing player; volume:
#   one set call). (Research §2/§4.)
# CRITICAL #4 — THE 5 s HANG VIOLATES THE TIERS' CONTRACT; THE WRAPPER DOES NOT KILL IT. S2/S3 enforce
#   timeout=1.0 per subprocess call; the mocked 5 s sleep simulates a backend that broke its own contract.
#   The wrapper guarantees ONLY: caller returns < 0.5 s (case d) + the desired state is eventually applied.
#   NO worker watchdog/kill — thread murder adds risk for zero product value; crash safety is T3.S2's ducked
#   flag + ExecStopPost. flush() is bounded-wait, not force. (Research §2.)
# CRITICAL #5 — NEVER A GATE. Every wrapper entry point (_dispatch, worker body, flush, engaged) is
#   swallow-wrapped: any Exception → ONE logger.warning, continue/return. A dispatch failure must never
#   propagate to the arm path. Mirror S1's _call discipline (one line per failure, no exc_info spam). (PRD
#   §4.2quinquies failure discipline; S1 audio_ducking.py _call.)
# CRITICAL #6 — TIMING ASSERTS: generous bounds under pytest. Caller-return < 0.5 s (not µs-tight); poll with
#   _wait_until(pred, timeout, interval=0.02) (mirrors tests/test_daemon.py's _wait_for); flush-hung < 2.5 s.
#   The whole suite must finish far under the 300 s pytest timeout. Use time.monotonic(). NEVER sleep to
#   "wait" for a state — always poll with a deadline. (Research §3.)
# CRITICAL #7 — WORKER THREAD SHAPE. daemon=True, name="vt-ducking" (the repo's naming convention:
#   voice-typing-idle, vt-recorder-shutdown, voice-typing-signal-shutdown), spawned at most one alive,
#   exits (short-lived) once desired is None. Test observes it via threading.enumerate() during a hung
#   engage and asserts it is GONE after drain. (Research §2/§4.)
# CRITICAL #8 — SCOPE: no audio_ducking.py/test_ducking.py edits (S1 frozen), no ducking_mpris.py (S2
#   landed), no ducking_volume.py (S3 parallel), no daemon/config/feedback/systemd edits (T3/T4 + landed),
#   no new deps, no PRD/tasks/snapshot/.gitignore. ducking_async.py imports ONLY logging/threading/typing.
#   AGENTS.md: every pytest under `timeout N` + the bash-tool timeout; FULL tool paths
#   (.venv/bin/python -m pytest); never bare python/pytest.
```

## Implementation Blueprint

### Data models and structure

```python
class AsyncDucker:
    """Failure-discipline wrapper (PRD §4.2quinquies): non-blocking, bounded, idempotent."""
    _ducker: Any                     # any object with engage()/release() + .engaged (S1's AudioDucker)
    _lock: threading.Lock            # tiny; NEVER held across a backend call (Critical #1)
    _desired: bool | None            # True=engage pending, False=release pending, None=idle
    _alive: bool                     # a worker thread exists
    _applied: threading.Event        # set each time the worker drains (flush waits on drain-of-record)
```
No dataclasses, no config surface (S4 reads nothing at runtime; `from_config` composition is T3's:
`AsyncDucker(AudioDucker.from_config(cfg, backend))`).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE voice_typing/ducking_async.py
  - MODULE DOCSTRING (Mode A): the failure discipline (never a gate, one-line failures), the lock-discipline
    rationale (arm under self._lock; NEW-2 abort-out-of-lock precedent; signal-handler spawn shape
    daemon.py:2738-2742), the single-flight latest-wins design (WHY not per-call threads: the ordering race),
    the flush contract for T3's quit path, and the ownership map (S1 bookkeeping / S2+S3 tiers / S4 dispatch /
    T3 wiring + crash safety / T4 default flip).
  - IMPLEMENT AsyncDucker per research §2 VERBATIM: engage()/release() → _dispatch(state); the coalescing rule;
    the single-worker spawn (name="vt-ducking", daemon=True); _worker loop (take latest desired; apply
    engage/release; swallow; set _applied; exit when desired stays None); flush(timeout=2.0) bounded-wait
    returning bool; engaged property proxy. Imports: logging, threading, typing ONLY.
Task 2: CREATE tests/test_ducking_async.py (10 tests per research §4; mirror S1's docstring banner style)
  - _FakeBackend: copy S1's shape (tests/test_ducking.py:34-80) + `slow: dict[str, float]` map (sleep in
    _enter before answering). _wait_until(pred, timeout, interval=0.02) poll helper. Build the wrapper over
    S1's REAL AudioDucker(fake, mode=..., volume_pct=15) — never a tier backend (Critical #8).
  - The 10 tests: (1) engage prompt under 5 s-hung backend [case d]; (2) release prompt likewise; (3) repeated
    arms mpris — one pause round [case e]; (4) repeated arms volume — one set call [case e]; (5) release
    without engage — zero backend calls; (6) arm→disarm→arm latest-wins (ends engaged, no stale restore);
    (7) all-raising backend — normal returns, ≤1 warning per path, nothing propagates; (8) off mode — zero
    backend calls; (9) flush bounded (True fast drained / False within 2.5 s hung); (10) worker thread shape
    (exactly one "vt-ducking" daemon thread during the hang; gone after drain).
Task 3: VALIDATE (research §6 commands, under timeout)
  - timeout 300 .venv/bin/python -m pytest tests/test_ducking_async.py -q          → 10 passed
  - timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q → no NEW failures
  - /home/dustin/.local/bin/ruff check voice_typing/ducking_async.py tests/test_ducking_async.py (optional)
  - git status --short == the 2 new files (+ parallel siblings' only)
```

### Implementation Patterns & Key Details

```python
# (1) The dispatch (Critical #1/#2/#3) — research §2 verbatim core:
def _dispatch(self, engaged: bool) -> None:
    try:                                        # NEVER a gate (Critical #5)
        spawn = False
        with self._lock:                        # tiny lock — no backend call under it
            if self._desired == engaged and self._desired is not None:
                return                          # coalesce: same state already pending (case e)
            self._desired = engaged
            self._applied.clear()
            if not self._alive:
                self._alive = True
                spawn = True
        if spawn:
            threading.Thread(target=self._worker, name="vt-ducking", daemon=True).start()
    except Exception:
        logger.warning("ducking: async dispatch failed; continuing")

# (2) The worker — the ONLY thread that touches the inner ducker; latest-wins each iteration:
def _worker(self) -> None:
    while True:
        with self._lock:
            state, self._desired = self._desired, None
            if state is None:
                self._alive = False
                self._applied.set()
                return                          # short-lived: gone once drained (Critical #7)
        try:
            self._ducker.engage() if state else self._ducker.release()
        except Exception:
            logger.warning("ducking: async %s failed; continuing", "engage" if state else "release")
        with self._lock:
            self._applied.set()

# (3) flush — T3's quit seam; bounded-wait, never force (Critical #4):
def flush(self, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with self._lock:
            if self._desired is None and not self._alive:
                return True
        time.sleep(0.02)
    return False
# GOTCHA: flush needs `import time` too (4 stdlib imports total — update Task 1's import list).

# (4) The hung-backend fake seam (tests) — sleep BEFORE answering, poll never bare-sleep (Critical #6):
def _enter(self, method):
    self.call_log.append(method)
    if method in self.slow:
        time.sleep(self.slow[method])           # e.g. {"get_sink_volume_pct": 5.0} — PRD case (d)
    if method in self.fail:
        raise RuntimeError(f"{method} failed (simulated)")
```

### Integration Points

```yaml
CONSUMED-BY (later tasks — do not implement):
  - T3 (P1.M2.T3.S1): 'daemon wiring: AsyncDucker(AudioDucker.from_config(cfg, backend)); engage() at _arm()
    toast site; release() at _disarm() + request_shutdown(); flush() before teardown on the quit path'
  - T3 (P1.M2.T3.S2): 'crash safety composes: ducked flag + ExecStopPost backstop a hard exit while a worker
    is mid-flight (the wrapper guarantees only best-effort eventual application)'
  - T4 (P1.M2.T4.S1): 'the default-flip acceptance run exercises this wrapper through both tiers'
WRAPS (frozen, S1):
  - calls: 'AudioDucker.engage() / AudioDucker.release() (internally lock-serialized + idempotent + swallowed)'
  - reads: 'AudioDucker.engaged (proxy)'
RUNTIME ENV: 'no new deps; no subprocess; no config read (composition with from_config is T3's)'
PARALLEL-SAFETY: 'zero imports of ducking_mpris/ducking_volume/daemon → S3 (and T3) can land in any order'
```

## Validation Loop

### Level 1–2 (the gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_ducking_async.py -v                  # 10 passed
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q     # no NEW failures
# Optional: /home/dustin/.local/bin/ruff check voice_typing/ducking_async.py tests/test_ducking_async.py
```

### Level 3 (discipline smoke — in-process, NO real audio, NO subprocess)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python - <<'PY'
# Proves: non-blocking under a hung backend (case d), coalesced repeated arms (case e), latest-wins.
import time
from voice_typing.audio_ducking import AudioDucker, PlayerState
from voice_typing.ducking_async import AsyncDucker

class Fake:
    def __init__(self): self.volume, self.set_calls, self.slow = 50.0, [], {"get_sink_volume_pct": 5.0}
    def list_players(self): return []
    def pause_player(self, n): return False
    def resume_player(self, n): return False
    def get_sink_volume_pct(self):
        if "get_sink_volume_pct" in self.slow: time.sleep(self.slow.pop("get_sink_volume_pct"))
        return self.volume
    def set_sink_volume_pct(self, pct): self.set_calls.append(pct); self.volume = pct; return True

f = Fake()
d = AsyncDucker(AudioDucker(f, mode="volume", volume_pct=15))
t0 = time.monotonic(); d.engage(); d.engage(); d.engage()      # 3 arms while the backend hangs 5 s
arm_dt = time.monotonic() - t0
assert arm_dt < 0.5, f"arm delayed {arm_dt:.2f}s — ducking became a gate"
t0 = time.monotic if False else time.monotonic(); d.release()
assert time.monotonic() - t0 < 0.5, "release blocked the caller"
assert d.flush(timeout=8.0) is True                            # hung engage + release eventually applied
assert f.set_calls in ([15.0], [15.0, 50.0]), f.set_calls      # coalesced: no stacked writes
print(f"OK: async discipline smoke (arm {arm_dt*1000:.0f} ms under a 5 s hung backend; sets={f.set_calls})")
PY
```

### Level 4 (scope guard)

```bash
git status --short   # == voice_typing/ducking_async.py + tests/test_ducking_async.py (new; parallel
                     #    siblings' files only besides). NO audio_ducking.py / ducking_mpris.py /
                     #    ducking_volume.py / daemon / config / feedback / systemd edits.
grep -nE '^import|^from' voice_typing/ducking_async.py   # stdlib only: logging, threading, time, typing
```

## Final Validation Checklist

- [ ] 10 tests pass; fast suite shows no new failures vs `tests/G1_BASELINE.md` (both under `timeout`).
- [ ] Level-3 smoke prints OK (arm < 0.5 s under a 5 s hung backend; coalesced sets; flush True).
- [ ] Case (d) + case (e) + latest-wins + off-mode + never-raises + bounded-flush all pinned by named tests.
- [ ] Module docstring states the lock rationale, latest-wins rationale, flush contract, ownership map (Mode A).
- [ ] Imports stdlib-only; zero tier/daemon imports; worker named `vt-ducking`, daemon=True, short-lived.
- [ ] Only the 2 new files in `git status --short`.

## Anti-Patterns to Avoid

- ❌ Don't call the inner ducker inline from engage()/release() — the caller holds the daemon control lock (Critical #1).
- ❌ Don't spawn one thread per call without latest-wins — the ordering race leaves media ducked while disarmed (Critical #2).
- ❌ Don't hold the wrapper's `_lock` across a backend call, a thread spawn join, or a sleep (Critical #1).
- ❌ Don't add a worker watchdog/kill or force-flush — the wrapper's contract is caller-bounded + eventual; crash safety is T3.S2's (Critical #4).
- ❌ Don't let anything raise out of any public method, and don't log more than one line per failure (Critical #5).
- ❌ Don't write µs-tight timing asserts or bare sleeps — poll with `_wait_until` and use generous bounds (Critical #6).
- ❌ Don't import ducking_mpris/ducking_volume/daemon/config in the module or its tests — tier-agnostic, parallel-safe (Critical #8).
- ❌ Don't edit `audio_ducking.py`/`test_ducking.py` (S1 frozen), S2/S3 files (landed/parallel), or daemon/config (T3/T4) (Critical #8).
- ❌ Don't run un-timed commands or bare `python`/`pytest` (AGENTS.md; Critical #8).

---

## Confidence Score

**9/10** — one-pass success likelihood. The wrapped component (S1's `AudioDucker`) is LANDED and read line-by-line; the state machine is written verbatim (research §2) with the coalescing, latest-wins, and flush semantics spelled out and each behavior pinned by an enumerated test; the lock-discipline rationale cites the in-repo precedents (NEW-2, `_safe_abort`, signal-spawn); the fake-backend + `slow`-map seam and the poll helper mirror S1's landed test style. Residual risk: the exact coalescing edge (worker took the state, desired=None, duplicate arrive → re-queue) is the one fiddly spot — mitigated by the verbatim code, the inner ducker's idempotence, and tests 3/4 asserting ONE backend application after 3 arms.
