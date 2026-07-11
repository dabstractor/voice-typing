# PRP — P1.M2.T2.S1: TTL cache in `_refresh_mic_status` + update mic probe tests

## Goal

**Feature Goal**: Eliminate the ~40 ms PyAudio mic-probe cost paid on **every** mic arm (bugfix Issue 3, PRD §4.2 "instant toggle-on") by adding a **TTL cache** to `VoiceTypingDaemon._refresh_mic_status()`: the probe runs at most once every 30 s, so a single-user arm goes from ~40 ms to ~0 ms (cached) while the mic-health surface (`_mic_ok`/`_mic_error` in `voicectl status`) stays current within 30 s. Today `_arm()` calls `_refresh_mic_status()` → `_probe_mic()` on every arm while holding `self._lock`; the probe does `import pyaudio; PyAudio(); <enumerate>; terminate()` (~39-43 ms), serializing all control commands.

**Deliverable** (4 surgical edits to `voice_typing/daemon.py` + 4 edits to `tests/test_daemon.py`; no new files):
1. `voice_typing/daemon.py` — **Edit D1**: add module constant `_MIC_PROBE_TTL_S: float = 30.0`. **Edit D2**: in `__init__`, add `self._mic_probe_at: float = 0.0` and change the init probe to `force=True`. **Edit D3**: `_refresh_mic_status(self, *, force=False)` — add the TTL gate at the top, stamp `_mic_probe_at` after storing the result, extend the docstring. **Edit D4**: update the `_arm` inline comment (the call stays `self._refresh_mic_status()`, no force).
2. `tests/test_daemon.py` — **Edit T1**: `test_refresh_mic_status_catches_probe_exception` → `force=True`. **Edit T2**: `test_refresh_mic_status_stores_probe_result` → `force=True`. **Edit T3**: `test_arm_refreshes_mic_status` → assert `len(calls) == 1` (cached within TTL). **Edit T4**: NEW `test_mic_probe_cached_within_ttl` (deterministic, `_fixed_clock`, non-zero base).

**Success Definition**:
- (a) `_refresh_mic_status(self, *, force: bool = False)` skips the probe when the last probe is within `_MIC_PROBE_TTL_S` (30 s); `force=True` (used by `__init__` and by tests that swap the prober) bypasses the gate.
- (b) `_arm()` no longer re-probes PyAudio within the 30 s TTL window (`test_arm_refreshes_mic_status` → `len(calls) == 1` after init+start).
- (c) The TTL boundary is proven deterministic: within-TTL cached, past-TTL re-probes (`test_mic_probe_cached_within_ttl`).
- (d) The mic-health surface still updates: after TTL expiry, an arm re-probes and `_mic_ok`/`_mic_error` refresh.
- (e) `.venv/bin/python -m pytest tests/test_daemon.py -v` → all green (incl. the 4 updated/new tests); `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `0 failed`.
- (f) No out-of-scope files: no `status.sh`/`test_status_sh.py` (P1.M2.T1.S1, parallel), no `_probe_mic` change, no control-flow change to `_arm`/`_disarm`/`start`/`stop`/`toggle`, no new locking, no `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock` changes. No new dependencies.

## User Persona

Not applicable (internal performance optimization; no user-facing API change — item DOCS: "[Mode A] Update the docstring … No external docs files"). The beneficiaries are the **end user** (arm feels instant, PRD §4.2) and the **maintainer** (the mic-health probe no longer serializes control commands under the lock).

## Why

- **PRD §4.2 promises "instant toggle-on".** A ~40 ms probe under the lock on every arm is imperceptible to a single user pressing a hotkey, but it is pure waste: the mic does not change health state in a 30 s window, so re-probing PyAudio/ALSA every keystroke buys nothing. A 30 s TTL preserves the health surface while eliminating the cost. (bugfix Issue 3.)
- **Cheap, surgical, lock-safe.** A 4-line gate + one stamp field. ALL `_arm`/`_disarm`/`_refresh_mic_status` calls already happen under `self._lock` (or single-threaded `__init__`), so the new `_mic_probe_at` field is lock-protected for free — **no extra locking** (scout lock-site audit). The gate mirrors the existing `MicRetryRateLimitFilter._last_seen` 0.0-sentinel + `time.monotonic()` window convention (daemon.py:1111/1123).
- **Latency budget real.** Measured ~39-43 ms per arm with the probe vs ~4 ms with it stubbed (scout). Caching drops the cached path to ~0 ms. The daemon lock is held for the probe today, so this also removes a serialization point for concurrent control commands.
- **Does not regress the health surface.** `voicectl status` reads `_mic_ok`/`_mic_error`, which refresh within at most 30 s (and immediately on construction via `force=True`). A mic that dies mid-session is surfaced on the next arm after the TTL window — an acceptable trade for instant arm (the idle watchdog / a future off-lock probe are out of scope here).

## What

Add a 30 s TTL cache to `_refresh_mic_status`: a module constant `_MIC_PROBE_TTL_S = 30.0`, a `self._mic_probe_at: float = 0.0` stamp field (0.0 == never, matching `MicRetryRateLimitFilter._last_seen`), a `force: bool = False` keyword arg, and a gate `if not force and self._mic_probe_at != 0.0 and (time.monotonic() - self._mic_probe_at) < _MIC_PROBE_TTL_S: return` at the top of the body. `__init__` calls `force=True` (always probes + sets the initial stamp). `_arm()`'s call stays un-forced (respects the TTL). Update 3 existing tests (2 need `force=True` because they swap the prober mid-test; 1 asserts the cache hit) and add 1 deterministic TTL-boundary test.

### Success Criteria

- [ ] `_MIC_PROBE_TTL_S: float = 30.0` exists at module level (after `_PARTIAL_CALLBACK_ATTR`, before `_resolve_device_config`).
- [ ] `__init__` sets `self._mic_probe_at: float = 0.0` and calls `self._refresh_mic_status(force=True)`.
- [ ] `_refresh_mic_status(self, *, force: bool = False)` early-returns when the last probe is within the TTL and `force` is False; stamps `self._mic_probe_at = time.monotonic()` after storing `_mic_ok`/`_mic_error`.
- [ ] `_arm()`'s call is still `self._refresh_mic_status()` (no force); its inline comment notes TTL caching.
- [ ] `test_arm_refreshes_mic_status` asserts `len(calls) == 1` (arm within TTL is cached).
- [ ] `test_refresh_mic_status_catches_probe_exception` and `test_refresh_mic_status_stores_probe_result` call `_refresh_mic_status(force=True)` (bypass the cache so the swapped prober runs).
- [ ] `test_mic_probe_cached_within_ttl` passes: within-TTL arm → 1 call; past-TTL arm → 2 calls (uses `_fixed_clock` with a NON-ZERO base).
- [ ] The existing `test_init_initializes_mic_status_and_calls_probe` still passes (`len(calls) == 1`).
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -v` → all green; `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `0 failed`.
- [ ] `git status --short` == `voice_typing/daemon.py` + `tests/test_daemon.py` (nothing else).

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement it from this PRP + the referenced research. The defect + verified call graph + lock-site audit are in the scout doc and research §1-§2. The **exact current text** of all 4 daemon.py edit sites (module-const block 114-117, `__init__` 453-456, `_refresh_mic_status` 633-648, `_arm` 581) and all 4 test edit sites (1484, 1491, 1506-1516, 1518) are reproduced verbatim so every edit is copy-exact `oldText→newText`. The two non-obvious traps — (a) the `0.0`-sentinel vs frozen-clock-`0.0` collision (research §4, verified live) and (b) the **3** tests that break (not just the 1 the item flagged — research §5) — are documented with the concrete fix. Baseline (117 daemon tests / 7 mic-probe tests pass) verified live.

### Documentation & References

```yaml
# MUST READ — defect, exact edit sites, the sentinel footgun, the 3 breaking tests, test design
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/P1M2T2S1/research/mic_probe_ttl_cache.md
  why: "§1-§2 the defect + verified call graph + lock-site audit (cache fields already lock-protected
        -> NO extra locking). §3 EXACT line numbers + current text for all 4 daemon edits. §4 the
        0.0-sentinel vs frozen-clock=0.0 collision (the item's literal t=0 example FAILS; use base
        1000.0) — verified live. §5 the FULL set of 3 breaking tests (item flagged only 1). §6-§7 the
        test fixtures + the new TTL test design. §9 scope."
  section: "ALL load-bearing. §4 (footgun), §5 (breaking tests), §3 (exact edits)."

# MUST READ — the scout doc (verified code paths + the TTL design the item prescribes)
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/architecture/scout_mic_probe.md
  why: "Maps _arm(575-581) -> _refresh_mic_status(633-648) -> _probe_mic(650-672); the lock audit
        proving _mic_* fields are only touched under self._lock; the MicRetryRateLimitFilter(1080-1127)
        TTL analog to mirror (_last_seen=0.0 sentinel + monotonic window); the _fixed_clock helper;
        and the explicit 'test_arm_refreshes_mic_status MUST UPDATE for TTL' note."
  critical: "The scout's TTL design says gate on '_mic_probe_at == 0.0 or monotonic()-... >= TTL or
             force'. The item flattens this to an early-RETURN form ('not force and != 0.0 and < TTL:
             return') — SEMANTICALLY EQUIVALENT. Implement the item's early-return form verbatim."

# MUST READ — the issue analysis (Issue 3 root cause + the prescribed TTL approach)
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/architecture/issue_analysis.md
  why: "§'Issue 3' (line 85+) documents the ~40ms-under-lock cost and prescribes 'TTL cache, re-probe
        at most once every N seconds (30s default)' + the thread-safety note (all under self._lock).
        Confirms 30.0 is the intended default."
  critical: "The analysis confirms the TTL approach (not 'move probe off lock' / 'idle watchdog') is
             the chosen fix. Do not invent a different approach."

# MUST READ — the file being edited: __init__(453-456), _refresh_mic_status(633-648), _arm(581)
- file: voice_typing/daemon.py
  why: "The 4 edit sites. import time at :76. _FIXED_KWARGS at :96, _PARTIAL_CALLBACK_ATTR at :114
        (module-const neighborhood for _MIC_PROBE_TTL_S). MicRetryRateLimitFilter at :1080-1127 (the
        convention to mirror). status_snapshot at :714-733 only READS _mic_ok/_mic_error (no probe)."
  critical: "Reproduce the Unicode in existing comments (— em dash, ≠ etc.) EXACTLY in oldText. Do NOT
             touch _probe_mic, _disarm, start/stop/toggle, status_snapshot. The _arm CALL stays
             un-forced; only its trailing comment changes."

# MUST READ — the test file: the 3 breaking tests + insertion site + _fixed_clock
- file: tests/test_daemon.py
  why: "Lines 1484 & 1491 (the 2 tests that need force=True), 1495 (init test, still passes), 1506
        (test_arm_refreshes_mic_status, assert -> ==1), 1518 (insertion anchor
        test_make_daemon_injection_is_hermetic...). _fixed_clock at 1551-1553. _make_daemon at
        424-430. Counting-prober idiom at 1495/1506."
  critical: "Do NOT freeze the clock to 0.0 in the TTL test (sentinel collision -> false re-probe).
             Use base 1000.0. Reference daemon._MIC_PROBE_TTL_S (not a hardcoded 30.0). Do NOT edit
             any test other than the 4 cited."

# MUST READ — the sibling task contract (DISJOINT files — no conflict)
- file: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/P1M2T1S1/PRP.md
  why: "S1 fixes status.sh (Issue 2): edits voice_typing/status.sh + adds tests/test_status_sh.py.
        This task (S1 of T2) edits daemon.py + test_daemon.py. DISJOINT files -> no merge conflict."
  critical: "Do NOT touch status.sh or test_status_sh.py (P1.M2.T1.S1 owns them)."

# THE DEFECT (Issue 3) — the PRD source
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/prd_snapshot.md
  why: "§2.3/§3.2 Issue 3 documents the ~40ms-under-lock arm cost vs PRD §4.2 'instant toggle-on',
        and prescribes the TTL cache (re-probe at most once every ~30s)."
  critical: "The item CONTRACT prescribes the TTL approach + the 0.0 sentinel + force param verbatim.
             Implement exactly that; do not pick an alternative (off-lock probe / idle watchdog)."
```

### Current Codebase tree (relevant slice — the only 2 files this task edits)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py            # EDIT (D1 module const; D2 __init__; D3 _refresh_mic_status; D4 _arm comment).
│   └── status.sh            # OUT OF SCOPE (P1.M2.T1.S1).
└── tests/
    ├── test_daemon.py       # EDIT (T1 1484 force; T2 1491 force; T3 1506 assert; T4 new TTL test).
    └── test_status_sh.py    # OUT OF SCOPE (P1.M2.T1.S1, parallel — may not exist yet).
# NOTHING ELSE. No new files. No pyproject.toml/uv.lock/.gitignore/PRD.md/tasks.json change.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE 0.0-SENTINEL vs FROZEN-CLOCK=0.0 COLLISION. The gate uses '0.0 == never'
#   (matching MicRetryRateLimitFilter._last_seen). In PRODUCTION time.monotonic() is never 0.0, so a
#   real probe never stamps _mic_probe_at = 0.0 — fine. But a TEST that does _fixed_clock(monkeypatch,
#   0.0) then constructs (init's force=True probe stamps _mic_probe_at = 0.0) makes the later
#   within-TTL arm see _mic_probe_at != 0.0 -> FALSE -> does NOT cache -> RE-PROBES -> the test's
#   "still 1 call" assertion FAILS. VERIFIED LIVE: base=0.0 FAILS, base=1000.0 PASSES. FIX: the TTL
#   test MUST use a non-zero base clock (1000.0). Do NOT freeze the clock to exactly 0.0 anywhere a
#   probe stamps _mic_probe_at. (Research §4.) [The real-clock test_arm_refreshes_mic_status is
#   unaffected — real monotonic is never 0.0.]

# CRITICAL #2 — THREE tests break, not one. The item flagged only test_arm_refreshes_mic_status.
#   TWO MORE break: test_refresh_mic_status_catches_probe_exception (1484) and
#   test_refresh_mic_status_stores_probe_result (1491) each swap d._mic_prober mid-test then call
#   d._refresh_mic_status() (no force). With TTL that call is CACHED within 30s (real clock, <1s) so
#   the swapped prober NEVER runs -> _mic_ok stays True -> their assertions fail. FIX: both call
#   _refresh_mic_status(force=True). (Research §5.)

# CRITICAL #3 — NO EXTRA LOCKING. _mic_probe_at/_mic_ok/_mic_error are read/written ONLY under
#   self._lock (via _arm, which start/stop/toggle call under the lock) or in single-threaded __init__.
#   Verified by the scout lock-site audit. Do NOT add a lock around the TTL fields — it is redundant
#   and would couple on_final/proc latency unnecessarily. (Research §2.)

# CRITICAL #4 — _arm's CALL STAYS UN-FORCED. _arm() calls self._refresh_mic_status() (no force) so it
#   RESPECTS the TTL — that is the whole point. Only __init__ uses force=True (construction always
#   probes + sets the initial stamp), and tests that swap the prober use force=True. Do NOT add
#   force=True to _arm. (Item contract (e).)

# CRITICAL #5 — GATE FORM (item's early-return, semantically equivalent to the scout's). Implement
#   EXACTLY: 'if not force and self._mic_probe_at != 0.0 and (time.monotonic() - self._mic_probe_at)
#   < _MIC_PROBE_TTL_S: return'. Stamp _mic_probe_at AFTER storing _mic_ok/_mic_error (so a probe
#   failure still updates the stamp — the next window is measured from the attempted probe, not left
#   stale). (Item contract (c); Research §3.3.)

# CRITICAL #6 — REPRODUCE UNICODE IN oldText. Existing daemon.py comments use — (em dash) and other
#   non-ASCII (e.g. the _refresh_mic_status docstring has —). The edit tool matches EXACT bytes; copy
#   the verbatim oldText from the Implementation Blueprint. (Research §3.)

# CRITICAL #7 — FULL TOOL PATHS (zsh aliases). .venv/bin/python -m pytest ... (never bare
#   python/pytest). Optional ruff at /home/dustin/.local/bin/ruff (NOT in .venv). mypy NOT installed —
#   do NOT run it. (Research §8.)
```

## Implementation Blueprint

### Data models and structure

No data-model change. The only new state is one instance attribute `self._mic_probe_at: float` (0.0 == never sentinel) and one module constant `_MIC_PROBE_TTL_S: float = 30.0`. `_refresh_mic_status` gains a keyword-only `force: bool = False`. No new public API.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/daemon.py — module constant (Edit D1)
  - ADD: '_MIC_PROBE_TTL_S: float = 30.0' after _PARTIAL_CALLBACK_ATTR (line 114), before
    def _resolve_device_config, with a 3-line comment (re-probe at most once / 30s; __init__ and
    force=True bypass the gate).
  - EXACT oldText→newText: see "Edit D1" below. Anchor: _PARTIAL_CALLBACK_ATTR line + 2 blanks + the
    def line (unique).

Task 2: EDIT voice_typing/daemon.py — __init__ (Edit D2)
  - ADD: 'self._mic_probe_at: float = 0.0' after 'self._mic_prober = mic_prober' (line 455), with a
    3-line comment (sentinel convention; lock-protected).
  - CHANGE: line 456 'self._refresh_mic_status()' -> 'self._refresh_mic_status(force=True)'.
  - EXACT oldText→newText: see "Edit D2" below (the 4-line mic-probe block 453-456).

Task 3: EDIT voice_typing/daemon.py — _refresh_mic_status (Edit D3)
  - CHANGE signature: def _refresh_mic_status(self) -> def _refresh_mic_status(self, *, force: bool = False).
  - ADD: TTL gate at the TOP of the body (item verbatim — see Critical #5).
  - ADD: 'self._mic_probe_at = time.monotonic()' AFTER 'self._mic_error = error' (line 647).
  - EXTEND: the docstring (TTL behavior, force param, sentinel, thread-safety).
  - EXACT oldText→newText: see "Edit D3" below (the whole method 633-648).
  - VERIFY: 'grep -n "_refresh_mic_status\|_mic_probe_at\|_MIC_PROBE_TTL_S" voice_typing/daemon.py'
    shows the def (now with force), the gate, the stamp, the init force=True call, and the constant.

Task 4: EDIT voice_typing/daemon.py — _arm inline comment (Edit D4)
  - CHANGE: the trailing comment on the _arm _refresh_mic_status() call (line 581) to note TTL. The
    CALL stays self._refresh_mic_status() (no force — Critical #4).
  - EXACT oldText→newText: see "Edit D4" below.

Task 5: EDIT tests/test_daemon.py — force=True on the 2 swap-prober tests (Edits T1, T2)
  - T1 (line 1484, test_refresh_mic_status_catches_probe_exception): d._refresh_mic_status() ->
    d._refresh_mic_status(force=True) (+ brief comment).
  - T2 (line 1491, test_refresh_mic_status_stores_probe_result): same.
  - WHY: both swap d._mic_prober mid-test; without force the TTL cache skips the swapped prober.
  - EXACT oldText→newText: see "Edit T1"/"Edit T2" below.

Task 6: EDIT tests/test_daemon.py — test_arm_refreshes_mic_status assertion (Edit T3)
  - CHANGE: assert len(calls) == 2 -> assert len(calls) == 1 (arm within TTL is cached). Update the
    trailing comments.
  - EXACT oldText→newText: see "Edit T3" below (the 3-line tail of the test).

Task 7: EDIT tests/test_daemon.py — NEW test_mic_probe_cached_within_ttl (Edit T4)
  - ADD: a new test (verbatim below) inserted BEFORE 'def test_make_daemon_injection_is_hermetic...'.
    Uses _fixed_clock with base 1000.0 (NON-ZERO — Critical #1), a counting prober, and references
    daemon._MIC_PROBE_TTL_S. Asserts: init=1 call; arm within TTL=1; arm past TTL=2.
  - EXACT oldText→newText: see "Edit T4" below (anchor on the def line of the next test).
```

### Edits — verbatim oldText → newText

#### Edit D1 — `voice_typing/daemon.py` module constant

`oldText`:
```
_PARTIAL_CALLBACK_ATTR = "on_realtime_transcription_stabilized"


def _resolve_device_config(cfg: VoiceTypingConfig) -> dict[str, str]:
```
`newText`:
```
_PARTIAL_CALLBACK_ATTR = "on_realtime_transcription_stabilized"

# Mic-health probe TTL (bugfix Issue 3 / P1.M2.T2.S1): re-probe at most once every 30s so _arm()
# does NOT pay the ~40ms PyAudio init on every keystroke. _refresh_mic_status() skips the probe
# when the last probe is within this window; __init__ (force=True) and explicit force=True bypass it.
_MIC_PROBE_TTL_S: float = 30.0


def _resolve_device_config(cfg: VoiceTypingConfig) -> dict[str, str]:
```

#### Edit D2 — `voice_typing/daemon.py` `__init__` (add stamp field + force=True)

`oldText` (current lines 453-456):
```
        self._mic_ok: bool = True            # default True: never-probed != broken (PRD §4.4 spirit)
        self._mic_error: str | None = None
        self._mic_prober = mic_prober
        self._refresh_mic_status()
```
`newText`:
```
        self._mic_ok: bool = True            # default True: never-probed != broken (PRD §4.4 spirit)
        self._mic_error: str | None = None
        self._mic_prober = mic_prober
        # TTL cache stamp for _refresh_mic_status (bugfix Issue 3 / P1.M2.T2.S1): time.monotonic()
        # of the last probe; 0.0 == never (sentinel matching MicRetryRateLimitFilter._last_seen).
        # Read/written ONLY under self._lock (via _arm) or here in single-threaded __init__.
        self._mic_probe_at: float = 0.0
        self._refresh_mic_status(force=True)   # construction always probes (sets the initial stamp)
```

#### Edit D3 — `voice_typing/daemon.py` `_refresh_mic_status` (signature + gate + stamp + docstring)

`oldText` (current lines 633-648, reproduced **verbatim incl. `—`**):
```
    def _refresh_mic_status(self) -> None:
        """Run the mic probe (real or injected) and store ok/error. NEVER raises.

        Sanctioned caller of the probe (bugfix Issue 2 / P1.M1.T2.S1): both __init__ and _arm()
        route through here so the try/except + attribute update live in ONE place. A probe failure
        (pyaudio missing, no devices, any exception) degrades to _mic_ok=False + _mic_error=str(exc)
        — the daemon stays runnable (degraded mode is acceptable; PRD §4.4 spirit). Tests inject
        mic_prober to stay hermetic; production leaves it None -> self._probe_mic.
        """
        prober = self._probe_mic if self._mic_prober is None else self._mic_prober
        try:
            ok, error = prober()
        except Exception as exc:  # defensive: a probe must never break startup or arm
            ok, error = False, str(exc)
        self._mic_ok = bool(ok)
        self._mic_error = error
```
`newText`:
```
    def _refresh_mic_status(self, *, force: bool = False) -> None:
        """Run the mic probe (real or injected) and store ok/error. NEVER raises.

        TTL-cached (bugfix Issue 3 / P1.M2.T2.S1): the probe (~40ms PyAudio init in production) runs
        at most once every _MIC_PROBE_TTL_S (30s). When the last probe is within the TTL window this
        method returns early and the cached _mic_ok/_mic_error stay valid. force=True bypasses the
        gate (used by __init__ so construction always probes and sets the initial stamp; tests that
        swap mic_prober also use force=True to bypass the cache). _mic_probe_at is the
        time.monotonic() stamp of the last probe; 0.0 == never (sentinel matching
        MicRetryRateLimitFilter._last_seen) — in production monotonic is never 0.0, so the sentinel
        is unambiguous.

        Sanctioned caller of the probe (bugfix Issue 2 / P1.M1.T2.S1): both __init__ and _arm()
        route through here so the try/except + attribute update live in ONE place. A probe failure
        (pyaudio missing, no devices, any exception) degrades to _mic_ok=False + _mic_error=str(exc)
        — the daemon stays runnable (degraded mode is acceptable; PRD §4.4 spirit). Tests inject
        mic_prober to stay hermetic; production leaves it None -> self._probe_mic.

        Thread safety: called only under self._lock (via _arm) or in single-threaded __init__, so
        _mic_probe_at/_mic_ok/_mic_error need NO extra locking.
        """
        if not force and self._mic_probe_at != 0.0 and (
            time.monotonic() - self._mic_probe_at
        ) < _MIC_PROBE_TTL_S:
            return  # cached: last probe is within the TTL window -> keep _mic_ok/_mic_error
        prober = self._probe_mic if self._mic_prober is None else self._mic_prober
        try:
            ok, error = prober()
        except Exception as exc:  # defensive: a probe must never break startup or arm
            ok, error = False, str(exc)
        self._mic_ok = bool(ok)
        self._mic_error = error
        self._mic_probe_at = time.monotonic()  # stamp AFTER storing the result
```

#### Edit D4 — `voice_typing/daemon.py` `_arm` inline comment (call unchanged)

`oldText` (current line 581):
```
        self._refresh_mic_status()  # bugfix Issue 2 / P1.M1.T2.S1: re-probe mic health on each arm
```
`newText`:
```
        self._refresh_mic_status()  # TTL-cached (Issue 3 / P1.M2.T2.S1): re-probes at most once / 30s
```

#### Edit T1 — `tests/test_daemon.py` line 1484 (force=True)

`oldText`:
```
    d._mic_prober = boom
    d._refresh_mic_status()
    assert d._mic_ok is False and "portaudio exploded" in (d._mic_error or "")
```
`newText`:
```
    d._mic_prober = boom
    d._refresh_mic_status(force=True)  # force: bypass TTL cache so the swapped prober actually runs
    assert d._mic_ok is False and "portaudio exploded" in (d._mic_error or "")
```

#### Edit T2 — `tests/test_daemon.py` line 1491 (force=True)

`oldText`:
```
    d._mic_prober = lambda: (False, "no devices")
    d._refresh_mic_status()
    assert d._mic_ok is False and d._mic_error == "no devices"
```
`newText`:
```
    d._mic_prober = lambda: (False, "no devices")
    d._refresh_mic_status(force=True)  # force: bypass TTL cache so the swapped prober actually runs
    assert d._mic_ok is False and d._mic_error == "no devices"
```

#### Edit T3 — `tests/test_daemon.py` `test_arm_refreshes_mic_status` (assert == 1)

`oldText` (the 3-line tail):
```
    assert len(calls) == 1          # init
    d.start()                       # -> _arm -> _refresh_mic_status
    assert len(calls) == 2          # armed once more
```
`newText`:
```
    assert len(calls) == 1          # init (force=True)
    d.start()                       # -> _arm -> _refresh_mic_status (TTL-cached within 30s)
    assert len(calls) == 1          # arm within TTL -> probe CACHED, not re-run (bugfix Issue 3)
```

#### Edit T4 — `tests/test_daemon.py` NEW test (insert before `test_make_daemon_injection_is_hermetic_no_real_pyaudio`)

`oldText` (anchor — the def line of the next test):
```
def test_make_daemon_injection_is_hermetic_no_real_pyaudio():
```
`newText`:
```
def test_mic_probe_cached_within_ttl(monkeypatch):
    """P1.M2.T2.S1 / bugfix Issue 3: _arm's mic probe is TTL-cached.

    _refresh_mic_status skips the probe within _MIC_PROBE_TTL_S and re-runs it after the window.
    Deterministic via _fixed_clock. NOTE: the base clock MUST be non-zero — _mic_probe_at uses 0.0
    as the 'never' sentinel, so freezing the clock to exactly 0.0 would stamp _mic_probe_at=0.0 and
    collide with the sentinel (the within-TTL cache would never hit). Use a clearly-non-zero base.
    """
    calls = []

    def counting_probe():
        calls.append(1)
        return (True, None)

    _fixed_clock(monkeypatch, 1000.0)   # non-zero base: avoid the 0.0 'never' sentinel collision
    d = daemon.VoiceTypingDaemon(
        VoiceTypingConfig(), _DaemonFakeFeedback(), recorder=_StubRecorder(),
        backend=_FakeBackend(), mic_prober=counting_probe,
    )
    assert len(calls) == 1              # __init__ force-probed; _mic_probe_at == 1000.0

    _fixed_clock(monkeypatch, 1005.0)   # within TTL (5s < 30s)
    d.start()                           # _arm -> _refresh_mic_status -> CACHED
    assert len(calls) == 1, "arm within TTL must NOT re-probe"

    _fixed_clock(monkeypatch, 1000.0 + daemon._MIC_PROBE_TTL_S + 5.0)  # past TTL (35s)
    d.start()                           # _arm -> _refresh_mic_status -> re-probe
    assert len(calls) == 2, "arm past TTL MUST re-probe"


def test_make_daemon_injection_is_hermetic_no_real_pyaudio():
```

> **Why these edits:** D1-D4 implement the TTL (constant + stamp + gate + force-on-init + docstring + comment). T1/T2 keep the two swap-prober tests correct (they MUST bypass the cache). T3 updates the one assertion the item flagged. T4 is the deterministic boundary test that ALSO documents the sentinel-collision footgun (Critical #1) — it uses base 1000.0, NOT the item's literal t=0, and references `daemon._MIC_PROBE_TTL_S` (not a hardcoded 30.0) so it survives tuning.

### Implementation Patterns & Key Details

```python
# The whole change is: 1 constant + 1 field + a 4-line gate + a stamp. Non-obvious details:

# (1) The gate (item verbatim — early-return form, semantically equivalent to the scout's):
if not force and self._mic_probe_at != 0.0 and (time.monotonic() - self._mic_probe_at) < _MIC_PROBE_TTL_S:
    return   # cached
#   Then probe, store _mic_ok/_mic_error, and ONLY THEN stamp _mic_probe_at (so a failed probe
#   still advances the window — no infinite re-probe loop on a persistently-failing mic).

# (2) NO extra locking — _mic_probe_at is touched only under self._lock (via _arm) or in __init__.

# (3) The 0.0 sentinel is safe in production (monotonic is never 0.0); only tests that freeze the
#   clock to exactly 0.0 trip it -> TTL test uses base 1000.0.

# (4) force=True callers: __init__ (always probe + set initial stamp), and any test that swaps
#   _mic_prober mid-test (the two _refresh_mic_status_* unit tests). _arm NEVER uses force.
```

### Integration Points

```yaml
# No database, routes, config, or env-var change. No new public API. Internal perf optimization.

STATE (VoiceTypingDaemon):
  - add attr: "self._mic_probe_at: float  (in __init__, 0.0 == never sentinel)"
  - add module const: "_MIC_PROBE_TTL_S: float = 30.0"
  - change signature: "_refresh_mic_status(self, *, force: bool = False)"
  - invariant: "probe runs at most once / 30s unless force=True; _mic_probe_at stamped after each probe"

CONSUMERS (unchanged behavior within 30s; refreshes after):
  - _arm(): "self._refresh_mic_status()  # now TTL-cached — instant arm within the window"
  - __init__: "self._refresh_mic_status(force=True)  # always probes at construction"
  - status_snapshot(): "reads _mic_ok/_mic_error (unchanged) — values are <=30s stale after the first arm"
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing

# Structural sanity after D1-D4: the new symbols are wired.
grep -n "_MIC_PROBE_TTL_S\|_mic_probe_at\|_refresh_mic_status" voice_typing/daemon.py
# Expected: _MIC_PROBE_TTL_S (def + gate); _mic_probe_at (init + gate + stamp); _refresh_mic_status
# (def w/ force, init force=True call, _arm call). No other callers.

# OPTIONAL lint — ruff at /home/dustin/.local/bin/ruff (NOT in .venv). mypy NOT installed (skip).
/home/dustin/.local/bin/ruff check voice_typing/daemon.py tests/test_daemon.py || true
# Expected: clean (new code uses already-imported `time` + a float literal + a keyword-only bool).
```

### Level 2: Unit Tests (THE gate)

```bash
cd /home/dustin/projects/voice-typing

# The mic-probe tests (the 4 edited + new + the unaffected init/probe_mic tests):
.venv/bin/python -m pytest tests/test_daemon.py -v -k "mic_status or probe_mic or refresh_mic or arm_refreshes or init_initializes_mic or cached_within_ttl"
# Expected: ALL pass — incl. test_mic_probe_cached_within_ttl (NEW), the 2 force=True tests, and
# test_arm_refreshes_mic_status (now asserts == 1).

# Whole daemon suite (no regression):
.venv/bin/python -m pytest tests/test_daemon.py -v

# Documented fast suite (Issue 4's green baseline must hold):
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed. (test_feed_audio.py needs GPU + espeak assets; excluded.)
```

### Level 3: Integration Testing (System Validation)

```bash
cd /home/dustin/projects/voice-typing

# Daemon imports cleanly + the TTL wiring is correct (no service to start for a pure-cache change):
.venv/bin/python - <<'PY'
from voice_typing import daemon
assert daemon._MIC_PROBE_TTL_S == 30.0, "module constant must be 30.0"
import inspect
sig = inspect.signature(daemon.VoiceTypingDaemon._refresh_mic_status)
assert list(sig.parameters) == ["self", "force"], sig.parameters
assert sig.parameters["force"].kind.name == "KEYWORD_ONLY", "force must be keyword-only"
assert sig.parameters["force"].default is False, "force default must be False"
print("OK: _MIC_PROBE_TTL_S=30.0; _refresh_mic_status(self, *, force=False)")
PY
# Expected: prints "OK: ..."; exit 0.
```

### Level 4: Creative & Domain-Specific Validation

```bash
# No live-daemon/GPU/audio path is exercised by a pure-cache change. The end-to-end guarantee ("arm
# does not re-probe PyAudio within 30s") is structurally proven by Level 2's test_mic_probe_cached_
# within_ttl (deterministic clock) + test_arm_refreshes_mic_status (real clock). The live
# ~40ms->~0ms speedup is observable by timing voicectl toggle against the systemd daemon, but that
# is a manual smoke (out of scope for the automated gate). If a GPU IS available, the optional
# full smoke is: .venv/bin/python -m pytest tests/test_feed_audio.py -q   # (optional; GPU-gated)
```

## Final Validation Checklist

### Technical Validation

- [ ] `grep -n "_MIC_PROBE_TTL_S\|_mic_probe_at\|_refresh_mic_status" voice_typing/daemon.py` shows the constant, the stamp (init+gate+after-store), the `force` signature, the init `force=True` call, and the un-forced `_arm` call.
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -v` → all green (incl. the 4 edited/new tests).
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `0 failed`.
- [ ] (Optional) `/home/dustin/.local/bin/ruff check voice_typing/daemon.py tests/test_daemon.py` → clean.
- [ ] (Optional) negative control: remove the TTL gate → `test_mic_probe_cached_within_ttl` and the `test_arm_refreshes_mic_status` `==1` assertion fail; restore → pass.

### Feature Validation

- [ ] `_refresh_mic_status(self, *, force: bool = False)` early-returns within the TTL when `force` is False.
- [ ] `__init__` calls `force=True` (always probes + stamps); `_arm()`'s call is un-forced.
- [ ] `_mic_probe_at` stamped after each probe (incl. failed probes).
- [ ] `test_mic_probe_cached_within_ttl`: within-TTL arm → 1 call; past-TTL arm → 2 calls.
- [ ] The 2 swap-prober tests pass with `force=True`; `test_arm_refreshes_mic_status` asserts `== 1`.
- [ ] `test_init_initializes_mic_status_and_calls_probe` still passes (`== 1`).

### Code Quality Validation

- [ ] Follows existing conventions: `MicRetryRateLimitFilter`'s 0.0 sentinel + monotonic window; counting-prober idiom; `_fixed_clock` for deterministic time.
- [ ] Only `voice_typing/daemon.py` and `tests/test_daemon.py` modified (`git status --short`).
- [ ] No new locking (cache fields already lock-protected); no control-flow change to `_arm`/`_disarm`/`start`/`stop`/`toggle`.
- [ ] Docstring updated (Mode A): TTL behavior, `force` param, sentinel, thread-safety.

### Documentation & Deployment

- [ ] `_refresh_mic_status` docstring documents TTL caching, `force`, `_MIC_PROBE_TTL_S`, the 0.0 sentinel.
- [ ] `_arm` inline comment notes TTL caching.
- [ ] No new env vars, no config keys, no external docs files (internal perf optimization).

---

## Anti-Patterns to Avoid

- ❌ Don't freeze the test clock to exactly `0.0` — it collides with the `0.0 == never` sentinel and breaks the cache (Critical #1). Use a non-zero base (1000.0).
- ❌ Don't forget the **two extra** breaking tests (lines 1484 & 1491) — they need `force=True` because they swap the prober mid-test (Critical #2). The item flagged only one.
- ❌ Don't add locking around `_mic_probe_at` — it's already protected by `self._lock` via `_arm` (Critical #3).
- ❌ Don't pass `force=True` from `_arm()` — that defeats the entire TTL (Critical #4).
- ❌ Don't stamp `_mic_probe_at` BEFORE storing the result — a failed probe must still advance the window (avoid an infinite re-probe loop on a persistently-dead mic).
- ❌ Don't hardcode `30.0` in the new test — reference `daemon._MIC_PROBE_TTL_S` so the test survives tuning.
- ❌ Don't edit the `—`/Unicode in Edit D3's oldText — exact-byte match required (Critical #6).
- ❌ Don't touch `status.sh`/`test_status_sh.py` (P1.M2.T1.S1), `_probe_mic`, or `status_snapshot`.
- ❌ Don't run `mypy` — not installed; pytest is the authoritative gate (Critical #7).
