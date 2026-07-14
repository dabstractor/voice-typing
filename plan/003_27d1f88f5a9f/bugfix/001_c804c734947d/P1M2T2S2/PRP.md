# PRP — P1.M2.T2.S2: Add liveness check to `_load_host()` early-return guard

## Goal

**Feature Goal**: Close the race-window half of bugfix Issue 3 (PRD §4.2bis robustness; selected h3.2). Sibling **S1** (already in-tree) detects a dead recorder-host child in the `run()` loop and `_handle_dead_host()` clears `_models_loaded`. But there is a **race**: if `_load_host()` is called from `start()`/`toggle()` *before* `run()` detects the death, `_models_loaded` is still `True`, so `_load_host()`'s early-return guard `if self._models_loaded: return True` short-circuits and **reuses the dead host**. This task tightens that guard to also require a LIVE host, so a dead host with stale `_models_loaded` falls through to the spawn path and a fresh child is created. A live resident host still short-circuits (instant re-arm, unchanged behavior).

**Deliverable** (1 surgical condition edit to `voice_typing/daemon.py`; no new files, no committed tests):
- `_load_host()` early-return guard (lines 648-650): `if self._models_loaded:` → `if self._models_loaded and self._host is not None and self._host.is_alive:`, with an explanatory comment + updated inline comment.

**Success Definition**:
- (a) A LIVE resident host still short-circuits on `_load_host()` (instant second+ arm — UNCHANGED behavior).
- (b) A DEAD host with stale `_models_loaded=True` does NOT short-circuit — `_load_host()` proceeds to the spawn path and creates a fresh host (proven by the Level-3 throwaway probe).
- (c) The edit is dormant for all 345 existing tests (the `is_alive` term is True for the injected-recorder adapter and for a freshly-spawned `_FakeHost`).
- (d) `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `345 passed` (no regression).
- (e) No out-of-scope files: **no** edits to `run()`/`_handle_dead_host()` (S1), **no** `_unload_host`/`_disarm`/`_arm`/`start`/`toggle`, **no** test file (S3 owns test_daemon.py committed tests; P1.M2.T1.S2 owns the phase tests), **no** `recorder_host.py`/`feedback.py`/`config.py`/README, **no** `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. No new deps. DOCS: none.

## User Persona

Not applicable (internal robustness fix; no user/config/API/doc surface — item DOCS: "none"). The beneficiary is the **operator of the 24/7 systemd service**: even in the tight race where an arm arrives between a child crash and `run()`'s next ~50 ms detection tick, the arm re-spawns a fresh child instead of latching onto a dead one. Combined with S1's detection + surfaced `_load_error`, a child crash self-heals on the next arm with no `quit`+restart.

## Why

- **Issue 3 is silent permanent breakage; S1 fixes the common path, S2 closes the race.** A child crash (CUDA OOM / segfault / OOM-killer) leaves `_models_loaded=True` until something clears it. S1's `run()` loop detects the death within ~50 ms and `_handle_dead_host()` clears `_models_loaded`. But if a `start()`/`toggle()` arrives in that window, it calls `_load_host()`, whose guard sees stale `_models_loaded=True` and returns `True` without checking liveness — the dead host is reused and transcription stays dead. This task removes that window. (bugfix Issue 3, Fix 3B; architecture/bug_analysis.md §Issue 3.)
- **The detection primitive already exists and is cheap.** `RecorderHost.is_alive` (recorder_host.py:156-158) already returns `False` on a dead child (`proc.is_alive() and not _dead`). Reading it under `self._lock` (which the guard already holds) is a microsecond op and introduces no new race — `_handle_dead_host`/`_unload_host` mutate `_host` under the SAME `_lock`.
- **Pure defense-in-depth; zero downside.** In normal operation S1 clears `_models_loaded` first, so the new `is_alive` term is `False` only in the race. The new term is `True` for every existing test (adapter → always True; freshly-spawned `_FakeHost` → True), so the edit is dormant and non-breaking.
- **Cheap, surgical, parallel-safe.** One condition conjunct. Disjoint from S1 (`run()`/`_handle_dead_host`), S3 (committed tests), P1.M2.T1.S2 (phase tests) — all touch different regions of daemon.py / test_daemon.py.

## What

Change ONE condition in `_load_host()`'s early-return guard (the first statement inside `with self._lock:`): from `if self._models_loaded:` to `if self._models_loaded and self._host is not None and self._host.is_alive:`. Add an explanatory comment block above it (why the `is_alive` term; that S1 normally clears `_models_loaded` first and this is the belt-and-suspenders for the race; that `is_alive` is always True for the injected-recorder adapter and a freshly-spawned host). Update the inline return comment from "resident → instant" to "resident + alive → instant". Do NOT touch any other line of `_load_host()` (the `_loading` wait path, the spawn path, the publish path) or any other method.

### Success Criteria

- [ ] `_load_host()` guard reads `if self._models_loaded and self._host is not None and self._host.is_alive:` (exactly).
- [ ] The guard remains INSIDE `with self._lock:` (lock-protected `_host`/`is_alive` read).
- [ ] A live resident host still short-circuits (Level-3 probe step 1).
- [ ] A dead host with stale `_models_loaded` re-spawns a fresh host via the factory (Level-3 probe step 3); the dead host is NOT reused.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `345 passed`.
- [ ] `git status --short` == `voice_typing/daemon.py` only.

## All Needed Context

### Context Completeness Check

_Pass._ A developer new to this repo can implement it from this PRP + the research note. The defect (the race window) and the exact fix are documented (research §1). The **exact current guard text** (lines 648-650, reproduced verbatim incl. the `→` U+2192 in the inline comment) is given for a byte-exact edit. The **no-breakage proof** (why the new `is_alive` term is dormant for all 345 tests — adapter always True; `_FakeHost` spawn sets `_alive=True`; `_CountingHost`/`_GatedHost` tests never call `_load_host`) is in research §4, verified live (345 passed, S1 in-tree). The **fix behavior** (live host short-circuits; dead host re-spawns; idempotent re-arm) is VALIDATED by a non-invasive monkeypatch probe (research §5) — no guessing. The is_alive property already exists on both host types (research §2.2) — nothing to add.

### Documentation & References

```yaml
# MUST READ — the defect (race window), exact edit, no-breakage proof, validated fix behavior.
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M2T2S2/research/load_host_liveness_guard.md
  why: "§1 the race (arm between child death and run()'s detection) + the exact guard swap. §2 the EXACT
        current code + line numbers (648-654) + that is_alive ALREADY EXISTS on both host types (adapter
        -> True always; RecorderHost -> False on dead child; _FakeHost -> _alive set True by spawn). §3
        sibling boundary (S1 in-tree edits run()/_handle_dead_host; S2 = this guard ONLY; S3 = committed
        tests; P1.M2.T1.S2 = phase tests — DISJOINT). §4 NO-BREAKAGE PROOF (3 categories; baseline 345).
        §5 VALIDATED fix behavior (monkeypatch probe -> live short-circuits / dead re-spawns / idempotent).
        §6 gotchas (lock-protected read; -> Unicode; spawn-path host_factory fallback; no committed test)."
  section: "ALL load-bearing. §1 (fix), §2 (exact edit), §4 (no-breakage), §5 (validated) are the core."

# MUST READ — the root-cause analysis + prescribed fix (Fix 3B = THIS task; 3A = S1; 3C = in S1).
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/bug_analysis.md
  why: "§Issue 3 Fix Strategy: Fix 3B prescribes EXACTLY this guard change
        (`if self._models_loaded and self._host is not None and self._host.is_alive: return True`).
        Fix 3A (run() loop + _handle_dead_host) = S1 (in-tree). Fix 3C (clear _listening) = in S1."
  critical: "Implement Fix 3B verbatim. Do NOT re-implement 3A/3C (S1 owns them, already landed)."

# MUST READ — the SIBLING task contract (S1 is IN-TREE; complementary, DISJOINT region).
- file: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M2T2S1/PRP.md
  why: "S1 added run()'s liveness check (daemon.py:745) + _handle_dead_host() (daemon.py:773). S1 does NOT
        touch _load_host(). S1 ALONE re-spawns via _models_loaded=False; S2 (THIS) is belt-and-suspenders
        for the race. S1's research §2 verified the RealtimeSTT/no-join concurrency model. DISJOINT region
        -> git merges cleanly."
  critical: "Do NOT edit run() or _handle_dead_host() (S1 owns them). S1 is already in the working tree."

# MUST READ — the file being edited: _load_host() (631-700), the guard site (648-650), the attrs under _lock.
- file: voice_typing/daemon.py
  why: "_load_host() is the method (631). The early-return guard = lines 648-650 (the Edit site). The guard
        is INSIDE `with self._lock:` (648) so self._host/self._host.is_alive reads are lock-protected. The
        _loading wait path (651-654) + spawn path (660: `self._host_factory or RecorderHost`) + publish
        path (667-693) are UNCHANGED. _load_host is called from start() (1152) + toggle() (1182) +
        _load_recorder back-compat (629)."
  critical: "Reproduce the -> (U+2192) in line 650's comment EXACTLY in oldText. Edit ONLY the guard condition
             (649) + the inline comment (650) + add the explanatory comment block above. Do NOT touch the
             _loading path, the spawn path, or any other method."

# MUST READ — the test adapter (why the edit is dormant) + the fake hosts (no-breakage categories).
- file: tests/test_daemon.py
  why: "_LegacyRecorderHostAdapter.is_alive -> True ALWAYS (daemon.py:439-441) -> every recorder= test is
        dormant. _FakeHost.is_alive -> self._alive, set True by spawn() (466-468, 461-464) -> host_factory=
        tests short-circuit identically on re-arm. _CountingHost/_GatedHost (1621-1644) have NO is_alive and
        are used only by the SIGTERM-teardown tests (1647-1745) which call ONLY request_shutdown/shutdown
        (NEVER _load_host/run) -> guard never evaluated -> no AttributeError. _fake_host_factory (501-509)
        + _make_daemon (512-521) + _cuda_resolve (69) are the probe seam."
  critical: "Do NOT edit any test file (S3 owns test_daemon.py committed tests; P1.M2.T1.S2 owns phase tests).
             The Level-3 probe is a THROWAWAY (python -c), not committed."

# Background — the production is_alive (already correct; nothing to add here).
- file: voice_typing/recorder_host.py
  why: "RecorderHost.is_alive (156-158) = `self._proc is not None and self._proc.is_alive() and not
        self._dead` -> False on a dead child. This is what the tightened guard consults in production."
  critical: "OUT OF SCOPE — do NOT edit recorder_host.py. Read-only context confirming is_alive works."

# THE DEFECT (Issue 3) — the PRD/bug source.
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/prd_snapshot.md
  why: "§2.2/§3.2 Issue 3 documents the silent-stuck-on-listening failure + the race where a subsequent
        start() short-circuits on _models_loaded without checking liveness. §4.2bis: 'MUST NOT leave a
        half-constructed recorder behind'."
  critical: "READ-ONLY. Never modify prd_snapshot.md (orchestrator-owned). The item CONTRACT prescribes the
             guard change verbatim — implement exactly that."
```

### Current Codebase tree (relevant slice — the 1 file this task edits)

```bash
/home/dustin/projects/voice-typing/
└── voice_typing/
    └── daemon.py     # EDIT: _load_host() early-return guard (lines 648-650).
# run() (745) + _handle_dead_host() (773) — S1, IN-TREE, UNCHANGED.
# test_daemon.py — S3 + P1.M2.T1.S2, UNCHANGED. recorder_host.py / feedback.py / config.py — UNCHANGED.
```

### Desired Codebase tree (unchanged structure — one condition edit)

```bash
# Same tree. One file's contents change:
#   voice_typing/daemon.py — _load_host() guard condition (line 649) + inline comment (650) + 5-line
#                            explanatory comment block above it. Nothing else.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE GUARD IS INSIDE `with self._lock:` (line 648). Reading self._host / self._host.is_alive
#   here is LOCK-PROTECTED and consistent with _handle_dead_host/_unload_host (which mutate _host under the
#   SAME _lock). So the new term introduces NO new race. Keep the edited condition INSIDE the `with` block.
#   (Research §6.1.)

# CRITICAL #2 — REPRODUCE THE -> (U+2192) IN oldText. Line 650's comment is `# resident → instant (second+ arm)`
#   with a RIGHTWARDS ARROW. The edit tool matches EXACT bytes; typing '->' makes oldText not match and the
#   edit FAILS. Copy the verbatim block. The newText comment keeps -> for style consistency. (Research §6.2.)

# CRITICAL #3 — is_alive ALREADY EXISTS on both host types — DO NOT add it. Production RecorderHost.is_alive
#   (recorder_host.py:156-158) returns False on a dead child; the test _LegacyRecorderHostAdapter.is_alive
#   (daemon.py:439-441) returns True always; _FakeHost.is_alive returns self._alive (True after spawn).
#   (Research §2.2.)

# CRITICAL #4 — THE EDIT IS DORMANT FOR ALL 345 EXISTING TESTS (verified). The new is_alive term is True for
#   every recorder= test (adapter) and for every freshly-spawned _FakeHost (host_factory= tests) -> the guard
#   short-circuits IDENTICALLY. The recorder_host= tests (_CountingHost/_GatedHost, no is_alive) call ONLY
#   request_shutdown/shutdown -> the guard is NEVER evaluated -> no AttributeError. So 345 -> 345. Do NOT
#   'fix' _CountingHost/_GatedHost (they are irrelevant — they never reach _load_host). (Research §4.)

# CRITICAL #5 — NO COMMITTED TEST IN S2. test_daemon.py is owned by S3 (committed dead-child tests) +
#   P1.M2.T1.S2 (phase tests, parallel). S2 validates via the Level-3 THROWAWAY probe (python -c, not
#   committed) + the 345 non-regression suite. S3 formalizes the committed test. (Research §6.4.)

# CRITICAL #6 — SCOPE = ONE CONDITION. Edit ONLY the guard (649) + inline comment (650) + add the explanatory
#   comment block. Do NOT touch run(), _handle_dead_host (S1), _unload_host, _disarm (P1.M2.T1.S1), _arm,
#   start, toggle, the _loading wait path, or the spawn/publish paths. (Research §6.6.)

# CRITICAL #7 — FULL TOOL PATHS (zsh aliases python/pip). Run pytest as
#   .venv/bin/python -m pytest ... (never bare 'pytest'/'python'). Optional ruff is at
#   /home/dustin/.local/bin/ruff (NOT in .venv). mypy is NOT installed — do NOT run it. (Research §7.)
```

## Implementation Blueprint

### Data models and structure

None. No data-model change, no new attribute, no new state, no new import. The edit tightens one `if` condition (adds two conjuncts: `self._host is not None and self._host.is_alive`) and updates/ adds comments. `_load_host()`'s signature `_load_host(self) -> bool` is unchanged.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/daemon.py — _load_host() early-return guard (the only edit)
  - SWAP the guard condition (line 649) from 'if self._models_loaded:' to
    'if self._models_loaded and self._host is not None and self._host.is_alive:'.
  - UPDATE the inline comment (line 650) from '# resident → instant (second+ arm)' to
    '# resident + alive → instant (second+ arm)'.
  - ADD a 5-line explanatory comment block immediately ABOVE the guard (why is_alive; S1 clears
    _models_loaded first / this is the race belt-and-suspenders; dormant for adapter + fresh host).
  - KEEP the guard INSIDE 'with self._lock:' (line 648). Do NOT touch the _loading wait path (651+),
    the spawn path, or any other method.
  - EXACT oldText->newText: see "Edit 1" verbatim block below.
  - GOTCHA: reproduce the -> (U+2192) in oldText's inline comment EXACTLY (Critical #2).
  - VERIFY: 'grep -n "self._models_loaded and self._host is not None and self._host.is_alive"
    voice_typing/daemon.py' shows exactly ONE hit (the _load_host guard).
```

### Edits — verbatim oldText → newText

#### Edit 1 — `voice_typing/daemon.py` `_load_host()` early-return guard (lines 649-651)

`oldText` (current, verbatim — NOTE the `→` U+2192 in the inline comment):
```
            if self._models_loaded:
                return True                       # resident → instant (second+ arm)
            if self._loading:
```
`newText`:
```
            # Liveness guard (bugfix Issue 3 / P1.M2.T2.S2): a stale _models_loaded with a DEAD host
            # (the child died in the race window before run()/_handle_dead_host cleared it) must NOT
            # short-circuit — fall through to the spawn path for a fresh host. run()'s _handle_dead_host
            # (S1) normally clears _models_loaded first; this is the belt-and-suspenders for that race.
            # is_alive is always True for the injected-recorder adapter and for a freshly-spawned host.
            if self._models_loaded and self._host is not None and self._host.is_alive:
                return True                       # resident + alive → instant (second+ arm)
            if self._loading:
```

> **Why this edit:** the single added conjunction (`and self._host is not None and self._host.is_alive`) makes a dead host with stale `_models_loaded` fall through to the existing spawn path (which builds a fresh host via `self._host_factory or RecorderHost`). For a live host the term is `True`, so the short-circuit is preserved (instant re-arm). The explanatory comment documents the race + the S1/S2 boundary + the dormancy, so a maintainer understands why the term is there even though S1 usually clears `_models_loaded` first. (Validated non-invasively — research §5.)

### Implementation Patterns & Key Details

```python
# (1) The guard stays INSIDE `with self._lock:` (lock-protected _host/is_alive read — no new race):
with self._lock:
    # ... explanatory comment ...
    if self._models_loaded and self._host is not None and self._host.is_alive:
        return True                       # resident + alive → instant (second+ arm)
    if self._loading:
        ...

# (2) is_alive is DORMANT in tests (Critical #4):
#   - injected-recorder adapter  -> is_alive == True always  -> guard behaves identically (short-circuits)
#   - freshly-spawned _FakeHost  -> spawn() set _alive=True   -> guard short-circuits on re-arm (no double-spawn)
#   - _CountingHost/_GatedHost   -> (no is_alive) but their tests never call _load_host -> never evaluated
# So the ONLY behavior change is: dead host + stale _models_loaded -> re-spawn (the fix). 345 -> 345.

# (3) The spawn path already exists and is correct (line 660): `factory = self._host_factory or RecorderHost`.
#   Production re-spawns a real RecorderHost; the S2 probe injects host_factory=_fake_host_factory() so the
#   re-spawn is CUDA-free. No edit to the spawn path is needed.
```

### Integration Points

```yaml
LOAD PATH (daemon._load_host):
  - tighten guard: "if self._models_loaded and self._host is not None and self._host.is_alive: return True"
  - effect: "dead host + stale _models_loaded -> falls through to spawn path -> fresh host (race closed)"
  - invariant: "live resident host still short-circuits (instant re-arm); guard stays under self._lock"
CALLERS (unchanged behavior for the common case):
  - start():   "calls _load_host() before _arm(); re-arm on a live host is instant; on a dead host re-spawns"
  - toggle():  "same; the read/act split around _load_host is unchanged"
  - _load_recorder(): "back-compat alias -> _load_host() (unchanged)"
COORDINATION (sibling / parallel — DISJOINT regions, no conflict):
  - S1 (in-tree):        "run() liveness check + _handle_dead_host (NOT touched here)"
  - S3 (planned):        "committed dead-child tests in test_daemon.py (NOT added here — S2 is probe-only)"
  - P1.M2.T1.S2:         "phase-after-disarm tests in test_daemon.py (NOT touched here)"
```

## Validation Loop

### Level 1: Syntax & Style

```bash
cd /home/dustin/projects/voice-typing
# Structural sanity: exactly ONE hit for the tightened guard (the _load_host early-return).
grep -n "self._models_loaded and self._host is not None and self._host.is_alive" voice_typing/daemon.py
# Expected: one hit at the _load_host guard (~line 649).

# Confirm the stale false guard is GONE (no bare 'if self._models_loaded:' short-circuit remains):
grep -n "if self._models_loaded:" voice_typing/daemon.py
# Expected: NO hit (the only occurrence was the edited guard; the _loading path uses 'if self._loading:').

# Module imports cleanly (no syntax/comment breakage):
.venv/bin/python -c "from voice_typing import daemon; print('daemon imports OK')"

# OPTIONAL lint — ruff is a uv tool at /home/dustin/.local/bin/ruff (NOT in .venv). mypy NOT installed.
/home/dustin/.local/bin/ruff check voice_typing/daemon.py || true
# Expected: clean (one condition change + comments; reuses the already-imported attrs under _lock).
```

### Level 2: Unit Tests (THE non-regression gate)

```bash
cd /home/dustin/projects/voice-typing
# The lazy-load / single-flight tests (the guard's re-entry callers — must stay green):
.venv/bin/python -m pytest tests/test_daemon.py -v \
    -k "load or spawn or lazy or idle_unload or single_flight or rearm or re_arm"
# Expected: all green (the edit is dormant for these — see Critical #4).

# Whole fast suite (no regression — baseline 345):
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 345 passed. (test_feed_audio.py needs a GPU + espeak assets; excluded.)
```

### Level 3: Integration (feature behavior — THROWAWAY probe; S3 owns the committed test)

```bash
cd /home/dustin/projects/voice-typing
# A throwaway killable-host probe (NOT committed — S3 owns the committed pytest). Proves the race fix:
# a pre-built host injected via recorder_host= (so _models_loaded starts True) is killed, and the NEXT
# _load_host() must NOT short-circuit — it re-spawns a fresh host via host_factory. Live host unchanged.
.venv/bin/python - <<'PY'
import tests.test_daemon as td
from voice_typing import daemon
from voice_typing.config import VoiceTypingConfig

# cuda monkeypatch seam (tests stay CUDA-free)
class _MP:
    def setattr(self, t, n, v): setattr(t, n, v)
td._cuda_resolve(_MP(), daemon.cuda_check.CUDA_DEFAULTS)

class _KillableHost:
    """Pre-built host injected via recorder_host= (so _models_loaded starts True). is_alive flips."""
    def __init__(self):
        self._alive = True
        self.recorder = td._StubRecorder()
        self.device = {"device": "cuda", "compute_type": "float16",
                       "final_model": "distil-large-v3", "realtime_model": "small.en"}
    @property
    def is_alive(self): return self._alive
    @property
    def pid(self): return 99999
    def spawn(self, timeout=180.0): self._alive = True; return True
    def set_microphone(self, on): self.recorder.set_microphone(on)
    def abort(self): self.recorder.abort()
    def text(self, on_final): self.recorder.text(on_final)
    def stop(self, timeout=5.0): self._alive = False

# Inject BOTH a pre-built (killable) host AND a fake factory (so the re-spawn path is CUDA-free):
killable = _KillableHost()
factory = td._fake_host_factory(spawn_result=True)
d, _fb, _rec, _be = td._make_daemon(recorder_host=killable, host_factory=factory)
assert d._models_loaded is True and d._host is killable, "init: injected host is loaded"

# (1) LIVE host short-circuits (instant re-arm, UNCHANGED behavior):
assert d._load_host() is True
assert d._host is killable, "live host must be reused (no re-spawn)"
print("(1) OK: live host short-circuits (no re-spawn)")

# (2) Simulate the race: child dies; _models_loaded stays True (run() has NOT cleared it yet):
killable._alive = False
assert d._models_loaded is True and not d._host.is_alive, "stale loaded + dead host"

# (3) _load_host must NOT short-circuit -> spawn path -> fresh _FakeHost via factory:
assert d._load_host() is True
assert d._host is not killable, "FIX FAIL: dead host reused instead of re-spawned"
assert getattr(d._host, "spawn_calls", None) == 1, "factory host spawned exactly once"
assert d._models_loaded is True and d._host.is_alive, "fresh host alive + loaded"
print("(3) OK: dead host (stale _models_loaded) re-spawns a fresh host (race closed)")

# (4) idempotent re-arm on the now-live fresh host:
assert d._load_host() is True
assert getattr(d._host, "spawn_calls", None) == 1, "live re-arm must NOT re-spawn"
print("(4) OK: re-arm on the fresh live host short-circuits (no extra spawn)")
print("ALL OK")
PY
# Expected: prints (1)/(3)/(4)/ALL OK; exit 0.
# (Negative control: against the UN-FIXED guard, step (3) FAILS — d._host is killable is reused.)
```

### Level 4: Creative & Domain-Specific Validation

```bash
# No live-daemon/GPU/audio path is exercised by a one-line guard change. The end-to-end guarantee —
# "an arm that arrives in the race window between a child crash and run()'s detection re-spawns instead
# of latching onto a dead host" — is structurally proven by Level 3's probe (dead host -> fresh host)
# and Level 2's non-regression (345). S1's run() detection + _handle_dead_host (in-tree) handle the
# common path; S2 closes the race. The live smoke (optional, GPU-gated): arm, then
# `kill -9 <child-pid>` (the recorder-host grandchild), then IMMEDIATELY `.venv/bin/voicectl start`
# (before run()'s next tick) -> expect a ~1-3s reload (re-spawn) and working transcription, NOT a silent
# reuse of the dead host. That live smoke is formalized/committed by S3.
```

## Final Validation Checklist

### Technical Validation
- [ ] `grep -n "self._models_loaded and self._host is not None and self._host.is_alive" voice_typing/daemon.py` → exactly ONE hit (the `_load_host` guard).
- [ ] `grep -n "if self._models_loaded:" voice_typing/daemon.py` → NO hits (stale guard removed).
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `345 passed`.
- [ ] Level 3 throwaway probe prints `(1)`/`(3)`/`(4)`/`ALL OK` (live short-circuits; dead re-spawns; idempotent).
- [ ] (Optional) `/home/dustin/.local/bin/ruff check voice_typing/daemon.py` → clean.

### Feature Validation
- [ ] The guard reads `if self._models_loaded and self._host is not None and self._host.is_alive:` and stays INSIDE `with self._lock:`.
- [ ] A live resident host short-circuits (instant re-arm — probe step 1).
- [ ] A dead host with stale `_models_loaded` re-spawns a fresh host via the factory (probe step 3); the dead host is NOT reused.
- [ ] Re-arm on the fresh live host does NOT re-spawn (probe step 4 — idempotent).

### Code Quality Validation
- [ ] Only the guard condition + inline comment + explanatory comment block changed; no other line of `_load_host()` touched.
- [ ] No edits to `run()`, `_handle_dead_host` (S1), `_unload_host`, `_disarm` (P1.M2.T1.S1), `_arm`, `start`, `toggle`, or any test file.
- [ ] No new attribute/import/state; `_load_host` signature unchanged.
- [ ] Only `voice_typing/daemon.py` modified (`git status --short`).

### Documentation & Deployment
- [ ] Explanatory comment block documents the race window, the S1/S2 boundary (S1 clears `_models_loaded` first; this is belt-and-suspenders), and the dormancy (adapter + fresh host → `is_alive=True`).
- [ ] Inline comment updated to "resident + alive → instant".
- [ ] No new env vars, no config keys, no external docs (internal robustness fix; item DOCS: none).

---

## Anti-Patterns to Avoid

- ❌ Don't move the guard OUTSIDE `with self._lock:` — the `_host`/`is_alive` read must stay lock-protected (Critical #1).
- ❌ Don't add `is_alive` to anything — it already exists on both `RecorderHost` and the test adapter/`_FakeHost` (Critical #3).
- ❌ Don't add a committed test in test_daemon.py — S3 owns the committed dead-child tests and P1.M2.T1.S2 owns the phase tests; S2 validates via the throwaway probe + non-regression only (Critical #5).
- ❌ Don't touch `run()` or `_handle_dead_host()` (S1, in-tree), `_unload_host`, `_disarm` (P1.M2.T1.S1), or any other `_load_host` line (the `_loading` wait path, the spawn path, the publish path) (Critical #6).
- ❌ Don't mangle the `→` (U+2192) in oldText's inline comment — exact-byte match required (Critical #2).
- ❌ Don't "fix" `_CountingHost`/`_GatedHost` (add `is_alive`) — their tests never reach `_load_host`, so they're irrelevant; touching them is S3's/out-of-scope (Critical #4).
- ❌ Don't run `mypy` — it's not installed; pytest is the authoritative gate (Critical #7).

---

## Confidence Score

**9/10** — one-pass success likelihood. This is a single-condition edit (add two conjuncts to an existing `if`), validated non-invasively via a faithful monkeypatch probe (live host short-circuits; dead host with stale `_models_loaded` re-spawns; idempotent re-arm — all proven), with a byte-exact `oldText` (including the `→` U+2192, flagged). The no-breakage analysis is categorical (the new `is_alive` term is `True` for every `recorder=` test via the adapter and every freshly-spawned `_FakeHost`; the `recorder_host=` tests never call `_load_host`), confirmed by the 345-green baseline with S1 in-tree. Residual risk is only an exact-byte mismatch on the `→`, which is explicitly flagged and the verbatim block is provided.
