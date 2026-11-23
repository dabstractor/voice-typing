# PRP — P1.M4.T1.S2: IM subprocess lifecycle — spawn/monitor/teardown + unavailable handling (`voice_typing/ime/manager.py`)

## Goal

**Feature Goal**: Ship the **subprocess supervisor** for the IM-v2 transport: a `voice_typing/ime/manager.py`
module (`ImeProcess`) that spawns `python -m voice_typing.ime.ime_host` as a **daemon-owned child in its
own process group** (`subprocess.Popen(..., start_new_session=True)`), drives the S1 JSONL protocol over
its stdin/stdout pipes (id-correlated `request()` with a bounded timeout, async `{"ev":...}` events
forwarded to a callback), **monitors** it (reader-thread EOF detection + a `ping` health check), and owns
**bounded single-flight teardown** (SIGTERM → `wait(5s)` → `killpg` SIGKILL) — mirroring the proven
`recorder_host.py` pattern. It maps child outcomes onto delivery states: the seat-exclusivity
`unavailable` event → `unsupported` with ONE reason (**never displaces/retries against a user IME —
stays unsupported until the next arm/spawn**); an unexpected child exit or spawn-timeout → `fault`
(**IM process crash = delivery fault, not daemon death**); NO auto-restart loop anywhere. State
transitions are emitted through an injected `on_delivery_state(state, reason)` callback (the
`feedback.set_delivery_state` seam, P1.M3.T3.S2) — the module itself never imports Feedback/daemon.

**Deliverable** (2 new files; everything else fenced):
1. `voice_typing/ime/manager.py` — `ImeProcess` + constants (see What).
2. `tests/test_ime_manager.py` — fake-proc duplex tests over real `os.pipe()` streams (no compositor,
   no real subprocess, no WAYLAND_DISPLAY).

**Success Definition**:
- (a) `timeout 120 .venv/bin/python -m pytest tests/test_ime_manager.py -q` green; the S1 suite
  `tests/test_ime_protocol.py` (if landed) stays green; `git status --porcelain` shows ONLY the 2 new files.
- (b) `env -u WAYLAND_DISPLAY .venv/bin/python -c "import voice_typing.ime.manager"` succeeds (pure
  import; spawns nothing).
- (c) `spawn()` → `Popen([sys.executable, "-m", "voice_typing.ime.ime_host"], stdin=PIPE, stdout=PIPE,
  start_new_session=True)`, readiness = ONE `ping` request with an id-echo reply within `spawn_timeout`
  (default 10 s); timeout/death → bounded teardown → return False → `FAULT`.
- (d) `request(cmd, timeout=1.0, **fields)` returns the id-echoing reply dict, `None` on timeout or dead
  child — **no resend ever** (byte-count asserted in tests).
- (e) `unavailable` event → `on_delivery_state("unsupported", <one reason>)`; the child's subsequent
  clean exit(0) emits NOTHING further; **no respawn attempt** (asserted).
- (f) unexpected EOF (rc≠0, no unavailable, no deliberate stop) → `on_delivery_state("fault", reason
  naming rc)`; pending requests fail immediately; daemon-side exceptions never propagate out of the
  reader thread.
- (g) `stop()` is **single-flight under a lock** (two concurrent stops = ONE terminate→wait→killpg
  sequence), bounded (`_DEFAULT_STOP_TIMEOUT_S = 5.0`), SIGKILLs the child's **process group**
  (`os.killpg`, guarded by an OSError fallback to `proc.kill()`), is a no-op when never spawned, and
  emits NO delivery_state transition.
- (h) NO out-of-scope code: no acquire/show/verify SEMANTICS (T2/T3), no takeover policy (T4), no
  daemon/feedback/ctl/bulk_* edits (M6 wiring owns feedback writes), no config/pyproject/systemd/
  hypr-binds changes, no edits to `voice_typing/ime/{protocol,wlwire,ime_host}.py` or `tools/im-lab/`.

## User Persona

**Target User**: Internal — P1.M4.T2 (acquire) and P1.M4.T3 (show/finalize) build the IM `DeliveryTarget`
adapter ON this manager's `request()`/`on_event` surface; P1.M6.T2.S1 (daemon wiring) constructs
`ImeProcess(on_delivery_state=feedback.set_delivery_state, ...)` and calls `spawn()`/`stop()` at the
arm/quit seams. No end-user surface in this task.

**Use Case**: Bulk-text arm (M6): wiring calls `spawn()` → child binds the seat IM → readiness ping.
If fcitx5 holds the seat, the child emits `unavailable` and exits 0 → manager emits
`("unsupported", "seat input-method unavailable: another input method holds the seat")` and STOPS —
the user's IME is untouched, the daemon lives, `voicectl status` shows the one reason. Mid-session the
child crashes (EOF rc≠0) → `("fault", "ime subprocess exited (rc=1)")`; recognition/stream-edit paths
are unaffected (bulk delivery fault ≠ daemon death). Quit/teardown → `stop()` kills the group within 5 s.

**Pain Points Addressed**: (1) The S1 host is a library `main()` with no supervisor — nothing spawns,
reads, health-checks, or bounded-terminates it. (2) The one-IM-per-seat collision (d2 §5 open item,
risk §9.3) needed a graceful `unsupported` degradation recipe — not a respawn fight against fcitx5.
(3) The 15 s-SIGKILL systemd lesson (bugfix Issue 1) is baked in as single-flight bounded teardown.

## Why

- **S1's own fence note names this task**: "P1.M4.T1.S2: spawns `python -m voice_typing.ime.ime_host
  <log>`; monitors via ping; owns teardown." T2/T3/T4 cannot run the adapter without a supervised child.
- **Seat exclusivity is a DECIDED degradation, not an error path** (item RESEARCH NOTE; d2 §5/§9.3;
  R.2 matrix): a user IME legitimately owns the seat; the spec's answer is `unsupported` + one reason +
  never displace + stay put until the next arm. Only a supervisor-level state machine can hold that
  discipline (an in-request retry loop inside T3 would fight the user's IME — explicitly forbidden).
- **The recorder_host pattern is proven and prescribed**: "subprocess isolation mirrors the recorder_host
  pattern (bounded join then killpg)" (item). RecorderHost's hard-won invariants — own process group,
  single-flight stop, bounded join→killpg, no half-spawned state, liveness surfaced not self-healed —
  transfer 1:1; this task re-encodes them for a pipes/JSONL child instead of mp queues.
- **`fault` isolation keeps the daemon alive**: PRD R.5 treats delivery failures as disarm-the-route
  events; the manager's crash→fault transition is the substrate M6 maps onto feedback/status.
- **Small, fenced, unblocks T2/T3/T4.** One module + one test file; consumes only S1's pure protocol.

## What

`voice_typing/ime/manager.py` — class `ImeProcess` with the surface below (constants
`_DEFAULT_SPAWN_TIMEOUT_S = 10.0`, `_DEFAULT_STOP_TIMEOUT_S = 5.0`, `_REQUEST_TIMEOUT_S = 1.0`):

```python
class ImeProcess:
    def __init__(self, on_delivery_state=None, on_event=None, python_exe=None,
                 log_path=None, spawn_timeout=10.0, stop_timeout=5.0): ...
    def spawn(self, timeout=None) -> bool: ...          # STARTING -> RUNNING | FAULT
    def request(self, cmd, timeout=_REQUEST_TIMEOUT_S, **fields) -> dict | None: ...
    def healthy(self) -> bool: ...                       # RUNNING + short ping round-trip
    def stop(self, timeout=None) -> None: ...            # single-flight, bounded, killpg; no transition
    @property
    def is_alive(self) -> bool: ...                      # RUNNING and child not dead
    @property
    def state(self) -> str: ...                          # "idle"|"starting"|"running"|"unsupported"|"fault"
```

Internal state machine (failure states terminal until the next `spawn()`): `idle` → (spawn) `starting`
→ (ping echo) `running` → { `unsupported` | `fault` | (stop) `idle` }. Reader thread is the SOLE stdout
consumer: id-echoing replies resolve pending `request()`s (per-id Event); `{"ev":...}` lines forward to
`on_event`; `unavailable` latches unsupported (once) and never respawns; EOF distinguishes
deliberate-stop (silent) / after-unavailable (silent) / crash (`fault` + rc in the reason).

Emissions policy (test-pinned): `on_delivery_state` fires ONLY for `unsupported` and `fault` —
`active`/`inactive` belong to T2/M6 (per `feedback.set_delivery_state`'s "written ONLY by the bulk
wiring" docstring).

### Success Criteria

- [ ] Both new files exist; the 10-case test matrix (research §5) green under `timeout 120`.
- [ ] Import purity: manager imports stdlib + `voice_typing.ime.protocol` ONLY; no Feedback/daemon import.
- [ ] `spawn()` readiness ping + Popen args pinned (incl. `start_new_session=True`).
- [ ] `request()` id correlation; timeout/death → None; NO bytes re-sent (write-count assert).
- [ ] unavailable → ONE unsupported reason; clean exit stays silent; NO respawn.
- [ ] crash → fault with rc in the reason; pending requests fail.
- [ ] `stop()` single-flight, bounded, killpg-then-fallback, no-op when idle, no transition.
- [ ] Scope guard: only the 2 new files; `tools/im-lab`, S1 modules, daemon/feedback/bulk_* untouched.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge: the consumed S1 protocol surface is enumerated
verbatim; the recorder_host invariants being mirrored are cited with file:line; the full `ImeProcess`
design (ctor injection, state machine, reader-thread rules, teardown order, emissions policy) is pinned
in research §4; the test matrix (fake proc over real `os.pipe()`, all 10 cases) is in research §5; the
validation commands are executable as written.

### Documentation & References

```yaml
# MUST READ — this task's research (contracts, pattern, design, tests, gates).
- docfile: plan/008_a47116bb2b79/P1M4T1S2/research/ime_subprocess_lifecycle.md
  section: "ALL. §1 the two consumed contracts (S1 protocol/host + feedback.set_delivery_state),
            §2 recorder_host facts to mirror, §3 seat-exclusivity rules, §4 the pinned ImeProcess
            design, §5 the 10-case test matrix, §6 gates."

# MUST READ — the S1 transport PRP (the CONTRACT this consumes; in parallel).
- docfile: plan/008_a47116bb2b79/P1M4T1S1/PRP.md
  why: "protocol.py's exact API (encode/decode/make_reply/make_error/make_event/validate_request/
        ProtocolError; REQUEST_CMDS incl. ping) and ime_host's main()/serve() contract (stdin/stdout,
        one id-echoing reply per request, id-less ev lines interleave, unavailable -> exit(0), quit
        escape). Its Integration seam names THIS task verbatim; its fences (no T2/T3/T4 semantics)
        bind here too."
  critical: "Do NOT edit S1's files (protocol/wlwire/ime_host) or tools/im-lab. If preflight finds
             them absent, S1 has not landed — STOP and report."

# MUST READ — the canonical subprocess pattern being mirrored. READ-ONLY.
- file: voice_typing/recorder_host.py
  why: ":102 _STOP_JOIN_TIMEOUT_S=5.0 + :140/:169 single-flight _stop_lock + :344 stop() and
        :470-483 _terminate_group (killpg after bounded join) — the teardown law. :535 os.setsid
        (Popen start_new_session=True is the equivalent). :199 spawn() bounded readiness, no
        half-spawned state. :191 is_alive."
  gotcha: "RecorderHost uses mp queues; the IM child uses PIPES — do NOT copy the queue code; copy
           the invariants (own group, single-flight stop, bounded join->killpg, liveness surfaced)."

# MUST READ — the status surface seam (LANDED). READ-ONLY.
- file: voice_typing/feedback.py
  why: "set_delivery_state(state, reason) taxonomy inactive|active|unsupported|fault; reason ALWAYS
        overwritten + sanitized to counts/times. Docstring: 'Written ONLY by the bulk-delivery wiring
        (P1.M6.T2.S1)' — hence the manager's callback seam instead of a Feedback import."
  gotcha: "Never import Feedback in manager.py; never emit active/inactive (T2/M6 own them)."

# READ — vocabulary + downstream consumers (READ-ONLY).
- file: voice_typing/bulk_delivery.py
  why: "DeliveryTarget method names (acquire/show/finalize/leave/cancel) that T2/T3 will implement
        over request(); ShowResult words the replies carry. Context only — manager moves dicts."
- docfile: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  section: "§5 open items (one-IM-per-seat collision -> degrade gracefully) + §9 risks 1-3."

# READ — the PRD slice + operational discipline.
- docfile: PRD.md
  section: "§4.2sexies R.4 (route DECIDED; no operator-surface changes), R.5 (never retry an op that
            may have landed; unknown is not delivered; delivery_state taxonomy)."
- docfile: AGENTS.md
  section: "Rules 1-3 (GNU timeout on every command; .venv/bin/python full paths; never foreground
            the daemon; bounded scratch)."
```

### Current Codebase tree (excerpt; S1 in flight — preflight asserts it landed)

```bash
voice_typing/ime/              # S1: __init__.py, wlwire.py, protocol.py, ime_host.py (REQUIRED by preflight)
tests/test_ime_protocol.py     # S1 (REQUIRED by preflight; must stay green)
tests/test_ime_wlwire.py       # S1
tests/test_ime_host.py         # S1
voice_typing/recorder_host.py  # pattern source (READ-ONLY)
voice_typing/feedback.py       # status surface (READ-ONLY)
# NO manager.py / test_ime_manager.py yet.
```

### Desired Codebase tree with files to be added

```bash
voice_typing/ime/manager.py    # CREATE: ImeProcess supervisor (spawn/request/events/stop + states)
tests/test_ime_manager.py      # CREATE: 10-case fake-proc duplex suite
# NOTHING ELSE.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — NEVER RETRY. A timed-out request returns None; a dead child fails pending requests
#   instantly; unavailable NEVER triggers a respawn. R.5: "NEVER retry an operation that may already
#   have landed" — and a respawn loop against fcitx5 is the seat-fight the item forbids.

# CRITICAL #2 — SINGLE-FLIGHT stop() UNDER A LOCK (bugfix Issue 1's lesson, mirrored): the quit path
#   may call stop() from the signal thread AND main() finally. Plain threading.Lock; second caller
#   sees idle and no-ops. Deliberate-stop latched BEFORE terminating so the reader's EOF stays silent.

# CRITICAL #3 — start_new_session=True, NOT child-side os.setsid: with Popen it puts the child in its
#   own session/pgroup at fork; killpg(os.getpgid(pid), SIGKILL) after the bounded wait then reaches
#   any of the child's own subprocesses. Guard killpg with except OSError -> proc.kill() (fake pids
#   in tests raise ProcessLookupError — the fallback is also the test seam).

# CRITICAL #4 — THE READER THREAD IS THE ONLY stdout CONSUMER. request() never reads the pipe; it
#   waits on a per-id Event resolved by the reader. Reader callbacks (on_event/on_delivery_state)
#   run on the reader thread — keep them tiny; wrap in try/except so a bad callback never kills the
#   reader (log + continue).

# CRITICAL #5 — UNAVAILABLE IS DISTINGUISHED FROM CRASH BY THE EVENT, NOT THE EXIT CODE: unavailable
#   event -> unsupported (emit ONCE); then exit(0) EOF stays silent. EOF rc!=0 without unavailable ->
#   fault (reason contains rc). Deliberate stop -> silent. A test pins all three EOF flavors.

# CRITICAL #6 — spawn() WHILE UNSUPPORTED/FAULT IS THE "NEXT ARM" RESPAWN (item: stay unsupported
#   until next arm): allowed — implicit stop() of any leftover, then a fresh Popen. spawn() while
#   already running -> True (idempotent). Never two children.

# CRITICAL #7 — WRITE SIDE: stdin writes under a send lock, encode() + flush; a dead child's broken
#   pipe (BrokenPipeError/OSError) marks the child dead and fails the request (None) — never raises
#   to the caller.

# GOTCHA #8 — TIMEOUTS + FULL PATHS (AGENTS.md): every command under GNU timeout; pytest via
#   .venv/bin/python. Tests never spawn a real compositor, never run ime_host's main(), never
#   foreground the daemon. python_exe defaults to sys.executable (the daemon venv).

# GOTCHA #9 — DON'T SHIP FENCED SEMANTICS: acquire/show/verify/leave BEYOND transport pass-through,
#   takeover policy, feedback writes, daemon wiring are T2/T3/T4/M6. The manager moves protocol
#   dicts; it does not interpret them.
```

## Implementation Blueprint

### Data models and structure

```python
# Module constants + the states; requests/replies/events are plain dicts (S1 protocol).
_DEFAULT_SPAWN_TIMEOUT_S: float = 10.0   # wayland connect+bind is fast; 10 s is generous
_DEFAULT_STOP_TIMEOUT_S: float = 5.0     # mirrors recorder_host _STOP_JOIN_TIMEOUT_S
_REQUEST_TIMEOUT_S: float = 1.0
_STATES = ("idle", "starting", "running", "unsupported", "fault")
_UNAVAILABLE_REASON = "seat input-method unavailable: another input method holds the seat"
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT (no mutation)
  - RUN: test -f voice_typing/ime/protocol.py && test -f voice_typing/ime/ime_host.py && echo ok \
      || echo "PREFLIGHT FAIL: S1 not landed"
    test ! -e voice_typing/ime/manager.py && test ! -e tests/test_ime_manager.py && echo "ok: targets free"
    env -u WAYLAND_DISPLAY .venv/bin/python -c "from voice_typing.ime import protocol; \
      print(protocol.REQUEST_CMDS)"
    timeout 120 .venv/bin/python -m pytest tests/test_ime_protocol.py -q | tail -1
  - EXPECTED: S1 present + green; targets free. If S1 absent: STOP, report the blocker.

Task 2: WRITE tests/test_ime_manager.py FIRST (TDD RED) — the 10-case matrix in research §5.
  - _FakeProc with REAL os.pipe() streams + a scripted writer thread; inject via a
    popper seam (ImeProcess takes injectable `_popen` factory returning the proc double — the ONLY
    private-injection seam, mirroring S1's sock=).
  - DO NOT: spawn real subprocesses/compositors; import Feedback.

Task 3: CREATE voice_typing/ime/manager.py — per research §4 / What. GREEN the suite.
  - DO NOT: edit S1 files, feedback, daemon, bulk_*, config, pyproject; break Critical #1-#7.

Task 4: VALIDATE — run L1-L4; iterate until green. If the orchestrator directs a commit:
  "P1.M4.T1.S2: ImeProcess supervisor — spawn/monitor/bounded-killpg teardown + unsupported/fault".
```

### Implementation Patterns & Key Details

```python
# PATTERN: the correlating duplex request (reader resolves; sender waits; no resend):
with self._send_lock:
    rid = self._next_id(); self._pending[rid] = ev = _Pending()
    try: self._proc.stdin.write(protocol.encode({"id": rid, "cmd": cmd, **fields})); self._proc.stdin.flush()
    except (BrokenPipeError, OSError): self._mark_dead(...); return None
return ev.reply if ev.wait(timeout) else None   # _Pending = Event + reply slot

# PATTERN: the reader's three EOF flavors (Critical #5):
#   if self._deliberate_stop: pass            # caller-owned transition
#   elif self._unavailable: pass              # already emitted unsupported
#   else: self._emit("fault", f"ime subprocess exited (rc={rc})")

# PATTERN: single-flight bounded teardown (Critical #2/#3):
with self._stop_lock:
    if self._state == "idle": return
    self._deliberate_stop = True; proc = self._proc; self._proc = None; self._state = "idle"
proc.terminate()
try: proc.wait(timeout=self._stop_timeout)
except subprocess.TimeoutExpired:
    try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except OSError: proc.kill()
```

### Integration Points

```yaml
PACKAGE SEAM (consumed downstream; nothing wired here):
  - P1.M4.T2/T3: "ImeProcess.request('acquire'|'show'|'verify'|'leave', ...) + on_event feed"
  - P1.M4.T4: "takeover detection subscribes via on_event (id-less ev lines)"
  - P1.M6.T2.S1: "constructs ImeProcess(on_delivery_state=feedback.set_delivery_state, ...);
                  spawn() at bulk arm; stop() at quit; healthy() at arm-time re-check"
NO INTEGRATION TOUCHED: "no daemon.py / feedback.py / ctl.py / bulk_* / config / pyproject /
                          systemd / hypr-binds / S1 files / tools/im-lab changes."
```

## Validation Loop

### Level 1: Syntax & purity

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m py_compile voice_typing/ime/manager.py tests/test_ime_manager.py && echo "L1 OK"
env -u WAYLAND_DISPLAY .venv/bin/python -c "import voice_typing.ime.manager as m; \
  print('pure import ok', m._DEFAULT_STOP_TIMEOUT_S)"
```

### Level 2: Unit tests (the gate)

```bash
timeout 120 .venv/bin/python -m pytest tests/test_ime_manager.py -q
timeout 120 .venv/bin/python -m pytest tests/test_ime_protocol.py -q | tail -1   # S1 unregressed
# Expected: 0 failed both. A reader-thread failure = read which case (unavailable/crash/stop flavor).
```

### Level 3: Teardown law smoke (fake proc, no real child)

```bash
timeout 60 .venv/bin/python - <<'EOF'
import os, threading, time
from voice_typing.ime.manager import ImeProcess
made = []
class FakeProc:  # minimal: terminate/wait/kill recorded; pgid invalid -> fallback
    pid = 999999999; returncode = None
    def __init__(self): self.calls = []
    def terminate(self): self.calls.append("term"); self.returncode = 0
    def wait(self, timeout=None): return 0
    def kill(self): self.calls.append("kill")
def fake_popen(*a, **k):
    r, w = os.pipe(); p = FakeProc(); p.stdout = os.fdopen(r, "rb"); p.stdin = os.fdopen(w, "wb")
    made.append(p); return p
states = []
m = ImeProcess(on_delivery_state=lambda s, r: states.append((s, r)), _popen=fake_popen)
threading.Thread(target=lambda: (time.sleep(0.2), os.write(m._proc_stdin_fd if False else 0)),
                 daemon=True).start()
assert m.spawn() in (True, False)
m.stop(); m.stop()                       # idempotent
print("L3 OK", states, made[0].calls if made else None)
EOF
# Expected: no exception; double stop() safe; terminate recorded; no crash transition from stop.
```

### Level 4: Scope & lineage guards

```bash
cd /home/dustin/projects/voice-typing
git status --porcelain      # ONLY voice_typing/ime/manager.py + tests/test_ime_manager.py
git diff --stat tools/im-lab | wc -l                                        # 0
git diff --stat voice_typing/daemon.py voice_typing/feedback.py voice_typing/bulk_delivery.py \
  voice_typing/bulk_controller.py voice_typing/ime/protocol.py voice_typing/ime/ime_host.py \
  voice_typing/ime/wlwire.py config.toml pyproject.toml | wc -l             # 0
grep -nE "from voice_typing.feedback|import feedback|from voice_typing.daemon" voice_typing/ime/manager.py || echo "ok: no daemon/feedback import"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1-L4 green; both suites pass; import purity (no WAYLAND_DISPLAY, no child at import).
- [ ] `git status --porcelain` = exactly the 2 new files; all fences byte-clean.

### Feature Validation
- [ ] spawn: Popen args pinned; readiness ping; timeout → FAULT; idempotent; unsupported→respawn-on-next-spawn.
- [ ] request: id echo; timeout/death → None; no resend; broken-pipe safe.
- [ ] unavailable → ONE unsupported reason; silent exit(0); NO respawn. Crash → fault + rc. Deliberate stop → silent.
- [ ] stop: single-flight, bounded 5 s, killpg + fallback, no-op idle, no transition.

### Code Quality Validation
- [ ] Mirrors repo style (docstring CONSUMES/CONSUMED BY + fences, `from __future__ import annotations`,
      module constants, logger); stdlib + protocol only.
- [ ] Anti-patterns avoided (no retry loops, no fenced semantics, no feedback writes).

### Documentation & Deployment
- [ ] Module docstring: recorder_host lineage, the three EOF flavors, emissions policy, downstream seams.
- [ ] No new env vars/config/keys/deps.

---

## Anti-Patterns to Avoid

- ❌ Don't retry a timed-out request, respawn after unavailable, or restart on crash — the caller's next
      spawn() IS the restart (Critical #1/#6).
- ❌ Don't emit active/inactive or import Feedback — the callback seam + M6 wiring own those (Critical on emissions).
- ❌ Don't let stop() run twice its teardown or run unbounded — lock + 5 s + killpg (Critical #2/#3).
- ❌ Don't read stdout outside the reader thread or let a callback kill the reader (Critical #4).
- ❌ Don't conflate exit code with unavailable — the EVENT distinguishes; rc only names the fault (Critical #5).
- ❌ Don't edit S1 files / tools/im-lab / daemon / feedback / bulk_* / config / pyproject (fences).
- ❌ Don't run anything without GNU timeout + `.venv/bin/python`; no real compositor or child in tests (Gotcha #8).

---

**Confidence Score: 9/10.** The consumed S1 protocol surface is enumerated verbatim with its PRP as
contract; the pattern being mirrored (recorder_host: single-flight bounded stop, own process group,
killpg, liveness-not-self-healing) is cited to file:line and re-specified for pipes; the design is
pinned to method level (ctor injection, state machine, reader rules, three EOF flavors, emissions
policy) with a 10-case fake-proc test matrix using real pipe streams; all gates are executable as
written. −1: S1 is landing in parallel — preflight blocks if absent, and if S1 renames a protocol
symbol the import fails loudly at Task 1 (cheap to reconcile against the S1 PRP's pinned API).
