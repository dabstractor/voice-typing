# PRP — P1.M2.T2.S1: Liveness check in `run()` loop + `_handle_dead_host()` recovery method

## Goal

**Feature Goal**: Detect an unexpectedly-dead recorder-host child process (bugfix Issue 3, PRD §4.2bis robustness) and recover. Today `run()` checks `self._host is None` but **never `host.is_alive`**, so a child crash (CUDA OOM / segfault / OOM-killer) leaves the daemon silently stuck reporting `listening: on / models: loaded` while transcribing nothing — and the next arm reuses the dead host (because `_load_host()` short-circuits on `_models_loaded`). After this task: the `run()` loop detects `self._host is not None and not self._host.is_alive` on each ~50 ms idle iteration, a new `_handle_dead_host()` resets the daemon to the `unloaded` lifecycle state (clearing `_host`/`_models_loaded`/`_listening`, setting `_load_error`, surfacing it in status), and the **next arm re-spawns a fresh child** via `_load_host()` (the `_models_loaded=False` reset means its early-return guard no longer short-circuits).

**Deliverable** (2 surgical edits to `voice_typing/daemon.py`; no new files):
1. `run()` while-loop — add a liveness check at the TOP of the loop body (before `if self._host is None`): on a dead host, log a pid-bearing WARNING and call `_handle_dead_host()`.
2. NEW `_handle_dead_host()` method (placed after `run()`, before `_configure_log_level`) — pure state cleanup under `self._lock` (no `host.stop()` — the child is already dead).

**Success Definition**:
- (a) `run()` detects a dead child within ~50 ms (idle path) / immediately (listening path — dead `text()` returns at once) and calls `_handle_dead_host()`.
- (b) `_handle_dead_host()` resets the daemon to `unloaded`: `_host=None`, `_models_loaded=False`, `_listening` cleared, `feedback.set_phase("unloaded")` + `set_models_loaded(False)` + `set_listening(False)`, `_load_error="recorder-host child died unexpectedly"`, both idle clocks cleared — all under `self._lock`.
- (c) `voicectl status` after a crash reports `listening: off`, `models_loaded: false`, `phase: unloaded`, and the `load_error`.
- (d) The next arm re-spawns (because `_models_loaded=False` defeats `_load_host()`'s short-circuit). [The `_load_host()` is_alive guard itself is S2 — complementary.]
- (e) `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed (baseline 345; **verified non-breaking** — see Context).
- (f) No out-of-scope files: no `_load_host()` (S2), no committed tests (S3), no `test_daemon.py` (P1.M2.T1.S2, parallel), no `_disarm()` (P1.M2.T1.S1), no `recorder_host.py`/`feedback.py`/`config.py`/README, no `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. No new deps. DOCS: none (internal robustness fix).

## User Persona

Not applicable (internal robustness fix; no user/config/API/doc surface — item DOCS: "none"). The beneficiary is the **operator of the 24/7 systemd service**: a child crash no longer silently breaks voice typing until a manual `quit`+restart; it self-heals on the next arm and surfaces the crash in `voicectl status`.

## Why

- **Issue 3 is a silent permanent breakage.** A child crash (a real CUDA/segfault/OOM possibility on a 24/7 service) leaves status lying (`listening: on / models: loaded`) and transcription dead — with NO error and NO recovery short of a full restart. That is the worst failure mode for a background service: invisible + unrecoverable. (bugfix Issue 3.)
- **The detection primitive already exists.** `RecorderHost.is_alive` (recorder_host.py:~135) already correctly returns False on a dead child. The only missing piece is the `run()` loop consulting it + a cleanup method. `is_alive` is cheap (proc.is_alive() + `_dead` flag), so checking it on the ~50 ms idle tick is negligible.
- **Self-healing on next arm, no `quit` needed.** Clearing `_models_loaded=False` makes the next `start()`/`toggle()` re-spawn via `_load_host()` — the user just re-arms and it works (after the ~1–3 s reload). Combined with the surfaced `_load_error`, the failure becomes visible + recoverable instead of invisible + permanent.
- **Cheap, surgical, parallel-safe.** Two edits to `run()` + one new method. The new check is **dormant** for every existing test (run-loop tests inject the legacy adapter whose `is_alive=True`; `recorder_host=` tests don't run the loop) — verified 345 passed. Disjoint from S2 (`_load_host`), S3 (tests), P1.M2.T1.S2 (test_daemon phase tests), P1.M2.T1.S1 (`_disarm`).

## What

Add a liveness check at the top of the `run()` while-loop body: `if self._host is not None and not self._host.is_alive:` → log a WARNING with the dead host's pid → call `_handle_dead_host()` → `continue`. Add `_handle_dead_host()`: under `self._lock`, drop the dead host reference and reset the daemon to `unloaded` (clear `_host`/`_models_loaded`/`_listening`, drive feedback `set_phase("unloaded")`/`set_models_loaded(False)`/`set_listening(False)`, set `_load_error`, clear both idle clocks). It does NOT call `host.stop()` (the child is already dead). The run() loop then sees `_host is None` → idles; the next arm re-spawns.

### Success Criteria

- [ ] `run()` while-loop has the liveness check at the TOP of the body, before `if self._host is None`.
- [ ] The check logs `recorder-host child (pid=%s) died; transitioning to unloaded` with `getattr(self._host, "pid", "?")`.
- [ ] `_handle_dead_host()` exists, acquires `self._lock`, and performs the 9 cleanup steps (item LOGIC (a)).
- [ ] `_handle_dead_host()` does NOT call `host.stop()`.
- [ ] `_handle_dead_host()` clears `_listening` (child died WHILE listening) so status reports `listening: off`.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed (baseline 345).
- [ ] `git status --short` == `voice_typing/daemon.py` only.

## All Needed Context

### Context Completeness Check

_Pass._ A developer new to this repo can implement it from this PRP + the research note. The defect + the task boundary (S1 vs S2 vs S3) are documented (research §1-§2). The **exact current `run()` loop text** (line 739) and the **placement anchor** (after run()'s exit log, before `_configure_log_level`) are reproduced verbatim for byte-exact edits. The **four design decisions** (pid-log in run() not the method; no `host.stop()`; idle-unload composition; ~50 ms latency) are in research §4. The **no-breakage proof** (why the new check is dormant for all 345 existing tests — legacy adapter `is_alive=True`; `recorder_host=` tests don't run the loop) is in research §5, verified live (345 passed). The **feature-behavior proof** (dead host → unloaded state → load_error → listening cleared, validated with a throwaway killable-host test) is in research §6. Both edits were applied to a full-repo scratch copy → 345 passed.

### Documentation & References

```yaml
# MUST READ — defect, design decisions, no-breakage proof, feature-behavior proof, exact edit sites
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M2T2S1/research/dead_host_recovery.md
  why: "§1 the defect + why status lies. §2 task boundary (S1=this; S2=_load_host guard; S3=tests; S1 ALONE
        fixes the run()-detected case via _models_loaded=False). §3 exact edit sites (run() line 739; place
        _handle_dead_host after run()). §4 DESIGN: pid-log in run() (not the method); NO host.stop() (child
        already dead); idle-unload composition; ~50ms latency. §5 NO-BREAKAGE PROOF (legacy adapter
        is_alive=True -> dormant; recorder_host= tests don't run the loop) — verified 345 passed. §6
        FEATURE PROOF (killable-host -> unloaded/load_error/listening-off). §9 scope."
  section: "ALL load-bearing. §2 (boundary), §4 (design), §5 (no-breakage) are the core."

# MUST READ — the root-cause analysis + the prescribed fix (Fix 3A = this task; 3B = S2; 3C = included here)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/bug_analysis.md
  why: "§Issue 3 Root Cause: run() never checks host.is_alive; dead child -> _host stays set, _models_loaded
        stays True, _load_host short-circuits. Fix 3A (liveness in run() + _handle_dead_host) = THIS task.
        Fix 3B (_load_host is_alive guard) = S2 (do NOT do here — but note S1's _models_loaded=False reset
        already makes the next arm re-spawn). Fix 3C (clear _listening) = included in _handle_dead_host."
  critical: "is_alive already exists on RecorderHost (recorder_host.py:~135) and works. _handle_dead_host
             does NOT exist. Do NOT implement Fix 3B (that is S2's _load_host edit)."

# MUST READ — the file being edited: run() (702-760), the attrs, the _unload_host analog
- file: voice_typing/daemon.py
  why: "run() while-loop at 739-742 (the edit site). __init__ attrs: _lock (used by _load_host/_unload_host/
        Condition(self._lock) ~596), _listening (548), _models_loaded (593), _load_error (595),
        _disarmed_monotonic (575), _last_speech_monotonic (570), _host (585-591). _unload_host (~975) is the
        STRUCTURAL ANALOG (clears _host/_models_loaded/phase under _lock) — mirror its CLEANUP, but SKIP its
        host.stop() teardown (child already dead). Construction (603-605) already calls set_phase +
        set_models_loaded (P1.M2.T2.S1 landed) -> the feedback surface exists."
  critical: "Reproduce the → Unicode in run()'s existing comment EXACTLY in oldText. Place _handle_dead_host
             AFTER run() (anchor: the 'shutdown requested; run() loop exiting' log + 'def _configure_log_level').
             Do NOT touch _load_host (S2), _disarm (P1.M2.T1.S1), _unload_host, or run()'s other lines."

# MUST READ — _LegacyRecorderHostAdapter (why the new check is dormant in tests) + RecorderHost.is_alive
- file: voice_typing/daemon.py
  why: "_LegacyRecorderHostAdapter.is_alive returns True ALWAYS (+ pid -> None). _make_daemon() injects
        recorder=_StubRecorder -> wrapped in this adapter -> run()'s 'not self._host.is_alive' is always False
        -> the new check NEVER fires in the existing run-loop tests. RecorderHost.is_alive (the production
        host) returns False on a dead child. getattr(self._host,'pid','?') is safe on both (adapter pid=None,
        real host has pid)."
  critical: "Do NOT add is_alive to anything — it already exists on both host types. The check is dormant for
             injected-recorder daemons by design (adapter is_alive=True)."

# MUST READ — the parallel task contracts (DISJOINT regions — no conflict)
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M2T1S1/PRP.md
  why: "P1.M2.T1.S1 adds ONE line (set_phase('idle')) inside _disarm() (~875). This task edits run() (~739) +
        adds _handle_dead_host() (~761). DISJOINT regions of daemon.py -> git merges cleanly."
  critical: "Do NOT edit _disarm()."
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M2T1S2/PRP.md
  why: "P1.M2.T1.S2 APPENDS phase-after-disarm tests to tests/test_daemon.py. This task does NOT touch
        test_daemon.py. No overlap."
  critical: "Do NOT edit test_daemon.py (P1.M2.T1.S2 + S3 own it)."

# THE DEFECT (Issue 3) — the PRD/bug source
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/prd_snapshot.md
  why: "§2.2/§3.2 Issue 3 documents the silent-stuck-on-listening failure + prescribes the liveness check +
        unload transition + load_error surfacing + re-spawn on next arm. §4.2bis (PRD): 'MUST NOT leave a
        half-constructed recorder behind' robustness spirit."
  critical: "The item CONTRACT prescribes the run() check + _handle_dead_host cleanup verbatim. Implement
             exactly that; the _load_host guard (Fix 3B) is S2."
```

### Current Codebase tree (relevant slice — the 1 file this task edits)

```bash
/home/dustin/projects/voice-typing/
└── voice_typing/
    └── daemon.py     # EDIT: run() while-loop liveness check (739) + NEW _handle_dead_host() (after run()).
# _load_host (S2), test_daemon.py (P1.M2.T1.S2 + S3), _disarm (P1.M2.T1.S1), recorder_host.py, feedback.py — UNCHANGED.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE pid-BEARING WARNING LIVES IN run(), NOT IN _handle_dead_host(). The pid is readable ONLY
#   before _handle_dead_host() sets self._host=None (after that self._host is None -> pid='?'). And logging in
#   both places would double-log. So: run() logs 'recorder-host child (pid=%s) died; ...' (self._host still the
#   dead host), THEN calls _handle_dead_host() which is PURE cleanup (no log). This is the literal reading of
#   the item's LOGIC (b). (Research §4.1.)

# CRITICAL #2 — _handle_dead_host() MUST NOT call host.stop(). The child is ALREADY dead (is_alive False ->
#   _dead=True / proc gone); there is nothing to tear down, and stop() on a dead host could block/error. The
#   structural analog _unload_host() calls host.stop() to tear down a LIVE child — do NOT copy that part. Only
#   DROP the reference + reset state. The dead host's reader thread exits on its own when the dead pipe closes.
#   (Research §4.2.)

# CRITICAL #3 — _handle_dead_host() MUST clear _listening (item LOGIC (c)). The child died WHILE listening;
#   without _listening.clear() + feedback.set_listening(False), status would keep reporting 'listening: on'
#   with a dead child — the exact bug. Clear it so status reports 'listening: off'. (Research §4, §6.)

# CRITICAL #4 — THE NEW CHECK IS DORMANT IN ALL EXISTING TESTS (verified 345 passed). Run-loop tests inject the
#   legacy _LegacyRecorderHostAdapter (is_alive=True always) -> 'not self._host.is_alive' is always False. The
#   recorder_host= tests (_CountingHost/_GatedHost/_FakeHost) do NOT run d.run(). So the check never fires in
#   the existing suite — ZERO regressions. Do NOT 'fix' _FakeHost._alive (default False) — it is irrelevant
#   here (those tests don't run the loop) and is S3's test-fake concern. (Research §5.)

# CRITICAL #5 — REPRODUCE THE → UNICODE IN run()'s oldText. The existing loop comment uses → (e.g. 'idle, ~0
#   VRAM'). The edit tool matches EXACT bytes; copy verbatim oldText from the Implementation Blueprint.

# CRITICAL #6 — DO NOT DO S2/S3 WORK. S2 (P1.M2.T2.S2) edits _load_host()'s early-return guard; S3
#   (P1.M2.T2.S3) writes the committed pytest. This task is run() + _handle_dead_host() ONLY. Note: S1 ALONE
#   makes the next arm re-spawn, because _handle_dead_host() sets _models_loaded=False -> _load_host()'s
#   existing 'if self._models_loaded: return True' guard does NOT short-circuit. S2's is_alive guard is
#   complementary defense-in-depth. (Research §2.)

# CRITICAL #7 — COMPOSES WITH IDLE-UNLOAD (no conflict). _unload_host() re-checks 'not self._models_loaded'
#   FIRST under _lock -> no-ops if _handle_dead_host() already ran. And _handle_dead_host clears
#   _disarmed_monotonic -> the idle-unload clock resets. No double-teardown, no deadlock. (Research §4.3.)

# CRITICAL #8 — FULL TOOL PATHS (zsh aliases). .venv/bin/python -m pytest ... (never bare python/pytest).
#   Optional ruff at /home/dustin/.local/bin/ruff (NOT in .venv). mypy NOT installed — do NOT run it.
```

## Implementation Blueprint

### Data models and structure

No data-model change. The only new artifact is one method `_handle_dead_host(self) -> None` on `VoiceTypingDaemon`. It reuses existing attrs (`_host`, `_models_loaded`, `_listening`, `_load_error`, `_disarmed_monotonic`, `_last_speech_monotonic`, `_feedback`, `_lock`) — all already initialized in `__init__`. No new attrs, no new state.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/daemon.py — run() liveness check (Edit R1)
  - ADD: at the TOP of the run() while-loop body (before 'if self._host is None'), the liveness check:
    'if self._host is not None and not self._host.is_alive:' -> logger.warning(... pid ...) ->
    self._handle_dead_host() -> continue.
  - EXACT oldText→newText: see Edit R1 below. Anchor: the 4-line while-loop head (unique).
  - GOTCHA: the pid-bearing WARNING is HERE (not in _handle_dead_host) — Critical #1. Reproduce → Unicode.

Task 2: EDIT voice_typing/daemon.py — NEW _handle_dead_host() method (Edit R2)
  - ADD: the method after run() (anchor: 'shutdown requested; run() loop exiting' log + 'def _configure_log_level').
  - BODY: 'with self._lock:' then the 9 cleanup steps (item LOGIC (a) verbatim). NO host.stop() (Critical #2).
    NO log (the WARNING is in run() — Critical #1).
  - EXACT oldText→newText: see Edit R2 below.
  - VERIFY: 'grep -n "_handle_dead_host\|is_alive" voice_typing/daemon.py' shows the def + the run() call.
```

### Edits — verbatim oldText → newText

#### Edit R1 — `voice_typing/daemon.py` `run()` while-loop liveness check

`oldText` (current lines 739-742, reproduced **verbatim incl. `→`**):
```
        while not self._shutdown.is_set():
            if self._host is None:
                time.sleep(0.05)   # no models loaded yet → idle, ~0 VRAM (PRD §4.2(1)/§4.2bis)
                continue
```
`newText`:
```
        while not self._shutdown.is_set():
            # Liveness check (bugfix Issue 3 / P1.M2.T2.S1): detect a crashed recorder-host child
            # (CUDA OOM / segfault / OOM-killer) on each ~50ms idle iteration. is_alive is cheap
            # (proc.is_alive() + _dead flag) and always True for the legacy injected-recorder adapter,
            # so this is dormant in unit tests. On a real death: log the pid, reset to 'unloaded', and
            # idle — the next arm re-spawns via _load_host() (_models_loaded=False => no short-circuit).
            if self._host is not None and not self._host.is_alive:
                logger.warning(
                    "recorder-host child (pid=%s) died; transitioning to unloaded",
                    getattr(self._host, "pid", "?"),
                )
                self._handle_dead_host()
                continue
            if self._host is None:
                time.sleep(0.05)   # no models loaded yet → idle, ~0 VRAM (PRD §4.2(1)/§4.2bis)
                continue
```

#### Edit R2 — `voice_typing/daemon.py` NEW `_handle_dead_host()` (after `run()`)

`oldText` (the run() exit log + the next method def — unique anchor):
```
        logger.info("shutdown requested; run() loop exiting")

    def _configure_log_level(self) -> None:
```
`newText`:
```
        logger.info("shutdown requested; run() loop exiting")

    def _handle_dead_host(self) -> None:
        """Recover from an unexpected recorder-host child death (bugfix Issue 3 / PRD §4.2bis).

        Called from run() when the resident host's `is_alive` is False (the child crashed: CUDA OOM,
        segfault, uncaught exception, OOM-killer). The child is ALREADY gone, so this does NOT call
        host.stop() (nothing to tear down — and stop() on a dead host could block/error); it drops the
        dead reference and resets the daemon to the 'unloaded' lifecycle state UNDER self._lock so a
        consistent snapshot is published. Clears _listening (the child died WHILE listening) so
        voicectl status reports listening: off, sets _load_error so status surfaces the crash, and
        clears both idle clocks. The run() loop then sees self._host is None -> idles (~0 work); the
        NEXT arm re-spawns a fresh child via _load_host() (the _models_loaded=False reset means
        _load_host()'s `if self._models_loaded: return True` guard does NOT short-circuit). Composes
        with idle-unload: _unload_host() re-checks `not self._models_loaded` first -> no-op if this
        ran first. Mirrors the cleanup half of _unload_host() (without the host.stop() teardown).
        """
        with self._lock:
            self._host = None
            self._models_loaded = False
            self._listening.clear()
            self._feedback.set_phase("unloaded")
            self._feedback.set_models_loaded(False)
            self._feedback.set_listening(False)
            self._load_error = "recorder-host child died unexpectedly"
            self._disarmed_monotonic = None
            self._last_speech_monotonic = None

    def _configure_log_level(self) -> None:
```

> **Why these two edits:** R1 is the detection (run() loop top, ~50 ms cadence; pid logged here while `self._host` is still the dead host). R2 is the recovery (`unloaded` reset under `_lock`; no `host.stop()` since the child is already dead; clears `_listening` so status is consistent). S1 alone makes the next arm re-spawn (via `_models_loaded=False`). Both edits were applied to a full-repo scratch copy → 345 passed + the dead-host recovery behavior validated with a throwaway killable-host probe.

### Implementation Patterns & Key Details

```python
# (1) Detection at the loop TOP (Critical #4: dormant in tests via the legacy adapter is_alive=True):
while not self._shutdown.is_set():
    if self._host is not None and not self._host.is_alive:   # cheap; True only for a real crash
        logger.warning("recorder-host child (pid=%s) died; ...", getattr(self._host, "pid", "?"))
        self._handle_dead_host()    # pid read HERE (before _host is cleared)
        continue
    ...

# (2) Recovery = cleanup UNDER _lock, NO host.stop() (Critical #2/3):
with self._lock:
    self._host = None
    self._models_loaded = False       # => next _load_host() won't short-circuit => re-spawn
    self._listening.clear()           # died WHILE listening => status must say listening: off
    self._feedback.set_phase("unloaded"); self._feedback.set_models_loaded(False)
    self._feedback.set_listening(False)
    self._load_error = "recorder-host child died unexpectedly"   # surfaced in voicectl status
    self._disarmed_monotonic = None; self._last_speech_monotonic = None   # reset both idle clocks

# (3) Composes with idle-unload: _unload_host() re-checks `not self._models_loaded` first -> no-op.
```

### Integration Points

```yaml
RUN LOOP (daemon.run):
  - add check: "top of while body: if self._host is not None and not self._host.is_alive: ..."
  - latency: "~50ms idle path; immediate on the listening path (dead text() returns at once)"
STATE (VoiceTypingDaemon._handle_dead_host):
  - reset: "_host=None, _models_loaded=False, _listening cleared, phase 'unloaded', models_loaded False,
            listening False, _load_error set, both idle clocks None — all under self._lock"
  - invariant: "no host.stop() (child already dead); next arm re-spawns via _load_host()"
CONSUMERS (auto-benefit, unchanged):
  - status_snapshot: "load_error field already surfaces self._load_error (P1.M2.T2.S1) -> voicectl status
                      shows the crash + listening: off + models not loaded"
  - _load_host: "_models_loaded=False -> 'if self._models_loaded' guard does NOT short-circuit -> re-spawn
                 (S2 adds the is_alive guard as defense-in-depth)"
  - _unload_host: "re-checks 'not self._models_loaded' first -> no-ops if dead-host handling ran first"
```

## Validation Loop

### Level 1: Syntax & Style

```bash
cd /home/dustin/projects/voice-typing
grep -n "_handle_dead_host\|host.is_alive" voice_typing/daemon.py
# Expected: _handle_dead_host def + the run() call site; host.is_alive in the run() check.
# OPTIONAL ruff (uv tool, NOT in .venv); mypy NOT installed (skip):
/home/dustin/.local/bin/ruff check voice_typing/daemon.py || true
```

### Level 2: Unit Tests (THE gate — non-regression)

```bash
cd /home/dustin/projects/voice-typing
# The run-loop tests (the ones that exercise the new check's code path — must stay green):
.venv/bin/python -m pytest tests/test_daemon.py -v -k "run_loop or run_closes or stop_while_run or quit_while_run or sigterm or shutdown"
# Whole fast suite (no regression — baseline 345):
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed. (The new check is dormant for all existing tests — verified.)
```

### Level 3: Integration (feature behavior — throwaway probe; S3 owns the committed test)

```bash
cd /home/dustin/projects/voice-typing
# A throwaway killable-host probe (NOT committed — S3 owns the committed pytest). Proves: dead child
# detected -> unloaded state -> load_error set -> listening cleared.
.venv/bin/python - <<'PY'
import threading, time
from voice_typing import daemon
from voice_typing.config import VoiceTypingConfig
import tests.test_daemon as td
class _KillableHost:
    def __init__(self):
        self._alive=True; self.recorder=td._StubRecorder(); self.device={"device":"cuda","compute_type":"float16","final_model":"distil-large-v3","realtime_model":"small.en"}
    @property
    def is_alive(self): return self._alive
    @property
    def pid(self): return 12345
    def spawn(self, timeout=180.0): self._alive=True; return True
    def set_microphone(self,on): self.recorder.set_microphone(on)
    def abort(self): self.recorder.abort()
    def text(self, on_final): self.recorder.text(on_final)
    def stop(self, timeout=5.0): self._alive=False
class _MP:
    def setattr(self, t, n, v): setattr(t, n, v)
td._cuda_resolve(_MP(), daemon.cuda_check.CUDA_DEFAULTS)
host=_KillableHost(); fb=td._DaemonFakeFeedback()
d=daemon.VoiceTypingDaemon(VoiceTypingConfig(), fb, recorder_host=host, backend=td._FakeBackend(), mic_prober=td._ok_probe)
t=threading.Thread(target=d.run, daemon=True); t.start()
_dl=time.time()+2
while time.time()<_dl and d._start_monotonic is None: time.sleep(0.01)
d.start(); assert d.is_listening() and d._models_loaded
host._alive=False  # KILL the child
_dl=time.time()+2
while time.time()<_dl and d._host is not None: time.sleep(0.01)
assert d._host is None and d._models_loaded is False and not d.is_listening()
assert d._load_error=="recorder-host child died unexpectedly"
assert fb.phases[-1]=="unloaded" and fb.listening_states[-1] is False
print("OK: dead child -> unloaded/models_loaded=False/listening=False/load_error set")
d.request_shutdown()
_dl=time.time()+2
while time.time()<_dl and t.is_alive(): time.sleep(0.01)
assert not t.is_alive(); print("OK: clean shutdown after recovery")
PY
# Expected: prints both "OK:" lines; exit 0.
```

### Level 4: Creative & Domain-Specific

```bash
# No live-daemon/GPU path exercised by a pure-state reset. The end-to-end "kill the recorder-host
# grandchild -> voicectl status shows unloaded + load_error -> re-arm reloads" guarantee is structurally
# proven by Level 3's probe + Level 2's non-regression. A live smoke (optional, GPU-gated): arm, then
# `kill -9 <child-pid>` (the recorder-host grandchild under the MainPID), then `.venv/bin/voicectl status`
# -> expect 'phase: unloaded' + '(not loaded)' + 'load error: recorder-host child died unexpectedly' +
# 'listening: off'; then `.venv/bin/voicectl start` reloads. That live smoke is formalized by S3/T6.
```

## Final Validation Checklist

### Technical Validation
- [ ] `grep _handle_dead_host voice_typing/daemon.py` → the def + the run() call site.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed (baseline 345).
- [ ] Level 3 throwaway probe prints both "OK:" lines (dead child → unloaded + load_error + listening off).
- [ ] (Optional) `/home/dustin/.local/bin/ruff check voice_typing/daemon.py` → clean.

### Feature Validation
- [ ] `run()` liveness check is at the TOP of the while body (before `if self._host is None`).
- [ ] The pid-bearing WARNING is in run() (not `_handle_dead_host`).
- [ ] `_handle_dead_host()` performs the 9 cleanup steps under `self._lock`; does NOT call `host.stop()`.
- [ ] `_handle_dead_host()` clears `_listening` (status reports `listening: off` after a crash).
- [ ] `_load_error` is set (surfaced in `voicectl status`).

### Code Quality Validation
- [ ] No S2 work (`_load_host` guard), no S3 work (committed tests), no `test_daemon.py`/`_disarm`/`recorder_host.py`/`feedback.py` edits.
- [ ] Only `voice_typing/daemon.py` modified (`git status --short`).
- [ ] `_handle_dead_host` mirrors `_unload_host`'s cleanup (minus the teardown); reuses existing attrs.

### Documentation & Deployment
- [ ] `_handle_dead_host` docstring documents: no `host.stop()` (child dead), clears `_listening`, next-arm re-spawn, idle-unload composition.
- [ ] `run()` comment documents the ~50 ms cadence + dormancy in unit tests.
- [ ] No new env vars, no config keys, no external docs (internal robustness fix).

---

## Anti-Patterns to Avoid

- ❌ Don't log the WARNING inside `_handle_dead_host()` — the pid is unreadable after `_host=None`, and it would double-log with run() (Critical #1). Log in run(); `_handle_dead_host` is pure cleanup.
- ❌ Don't call `host.stop()` from `_handle_dead_host()` — the child is already dead; nothing to tear down, and it could block/error (Critical #2).
- ❌ Don't forget `_listening.clear()` (+ `set_listening(False)`) — the child died WHILE listening; status must report `listening: off` (Critical #3).
- ❌ Don't do S2 (`_load_host` is_alive guard) or S3 (committed tests) — those are separate tasks (Critical #6). S1 alone re-spawns via the `_models_loaded=False` reset.
- ❌ Don't touch `_disarm` (P1.M2.T1.S1), `test_daemon.py` (P1.M2.T1.S2 + S3), `_unload_host`, or run()'s other lines.
- ❌ Don't mangle the `→` Unicode in run()'s oldText — exact-byte match required (Critical #5).
- ❌ Don't "fix" `_FakeHost._alive` (default False) — irrelevant here (those tests don't run the loop) and is S3's concern (Critical #4).
- ❌ Don't run `mypy` — not installed; pytest is the gate (Critical #8).
