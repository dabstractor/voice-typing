# PRP — P1.M3.T1.S1: idle-unload watchdog + `auto_unload_idle_seconds` config knob + auto-stop composition

## Goal

**Feature Goal**: Reclaim GPU VRAM after a one-off use. A new background watchdog thread tears down the resident ASR recorder once the mic has been DISARMED for `asr.auto_unload_idle_seconds` (default `1800.0` = 30 min; `0` disables), composing with the existing idle auto-stop (which disarms at 30 s and starts this slower clock). After unload, `nvidia-smi` shows the daemon PID gone (~0 VRAM); the next `voicectl start` reloads (~1–3 s). PRD §4.2bis (Idle unload) + §4.5 + acceptance §7.9.

**Deliverable** (edits to `voice_typing/config.py` + `config.toml` + `voice_typing/daemon.py` + `tests/test_config_repo_default.py`; optional `tests/test_config.py`; no new files):
1. `config.py` — add `auto_unload_idle_seconds: float = 1800.0` to `AsrConfig` + docstring ([Mode A]).
2. `config.toml` — add the commented `auto_unload_idle_seconds = 1800.0` line to `[asr]`.
3. `daemon.py` — (a) `self._disarmed_monotonic` stamp field in `__init__`, cleared in `_arm()`, set in `_disarm()`; (b) NEW `_idle_unload_watchdog()` (ticks via `_shutdown.wait(1.0)`, mirrors `_idle_watchdog`); (c) NEW `_maybe_idle_unload()` (lock-free pre-check + delegates); (d) NEW `_unload_recorder()` (single-flight under `_lock`: re-check condition incl. `_listening`, run `_bounded_shutdown()` under the lock, null `_recorder`, flip `_models_loaded`, `set_phase('unloaded')` + `set_models_loaded(False)`); (e) start the watchdog from `run()` alongside `_idle_watchdog`.
4. `tests/test_config_repo_default.py` — **REQUIRED**: add `auto_unload_idle_seconds` to the expected `asr` key set (else `test_repo_config_toml_has_no_extra_keys` breaks) + bump the docstring key count.
5. (Optional) `tests/test_config.py` — assert the new default.

**Success Definition**:
- (a) `AsrConfig().auto_unload_idle_seconds == 1800.0`; `<repo>/config.toml` parses to NO overrides over the defaults (the drift guard stays green).
- (b) `_disarm()` stamps `_disarmed_monotonic = time.monotonic()`; `_arm()` clears it to `None`. Both the manual stop/toggle-off AND the 30 s `_maybe_auto_stop()` path set it (composition).
- (c) `_idle_unload_watchdog` ticks ~1 s via `_shutdown.wait(1.0)`, exits promptly on shutdown, swallows its own exceptions.
- (d) When `models_loaded AND not listening AND now - _disarmed_monotonic >= auto_unload_idle_seconds`, `_unload_recorder()` runs: bounded teardown under `_lock`, then `_recorder=None`, `_models_loaded=False`, `phase='unloaded'`, `models_loaded=False`. Logs `voice-typing idle-unload: 1800.0s disarmed; unloading models`.
- (e) `auto_unload_idle_seconds <= 0` disables (the watchdog pre-check short-circuits; `_unload_recorder` also guards).
- (f) **Race safety (structure for S2 to test):** `_unload_recorder()` holds `_lock` during `_bounded_shutdown()`; a concurrent arm's `_load_recorder()` blocks on that lock, then loads fresh. An arm that races the watchdog's pre-check is caught by `_unload_recorder`'s `_listening.is_set()` re-check under the lock (abort the unload).
- (g) `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed (the only test S1 must edit is `test_config_repo_default.py`).
- (h) No out-of-scope files: no `_load_recorder`/`_bounded_shutdown`/`shutdown`/`build_recorder` logic (prerequisites — consume, don't touch), no `feedback.py`/`ctl.py` (P1.M2.T2.S1 owns the surface), no `status.sh`, no README/ACCEPTANCE (P1.M3.T3), no `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. No new deps. No new committed idle-unload behavior tests (those are P1.M3.T1.S2 + P1.M3.T2.S1).

## User Persona

**Target User**: the operator who arms the daemon once, dictates a sentence, then walks away for an hour. Today the ~1.5–3 GB of VRAM stays resident the whole time. With idle-unload, it is reclaimed 30 min after disarm, and the next arm pays only the ~1–3 s reload.

**Use Case**: a desktop that also runs other GPU workloads (gaming, ML) — voice-typing should not tax the GPU when idle for long stretches.

**Pain Points Addressed**: PRD §4.2bis — "stop taxing the GPU … after a one-off use." Without idle-unload, lazy load still leaves models resident forever after the first arm.

## Why

- **PRD §4.2bis (Idle unload) + §7 acceptance criterion 9 mandate it.** "After `auto_unload_idle_seconds` of disarmed idle, the recorder unloads (~0 VRAM, verified via `nvidia-smi`) and a later arm reloads it; the teardown is bounded." The bounded-teardown prerequisite (P1.M1) is COMPLETE; this task is the watchdog that triggers it.
- **Composes with the existing idle auto-stop.** Auto-stop (30 s) disarms; idle-unload (30 min) frees VRAM. The composition is one shared `_disarmed_monotonic` stamp set by `_disarm()` (called by all three disarm paths: stop, toggle-off, auto-stop). No new coupling between the two watchdogs.
- **Single-flight under the existing `_lock` makes it race-safe for free.** `_unload_recorder()` reuses the SAME lock `_load_recorder()` uses, so an arm racing teardown waits, then loads fresh — no new lock, no lock-ordering risk (`_bounded_shutdown` never touches `_lock`).
- **Cheap, additive, parallel-safe.** Disjoint from P1.M2.T2.S1 (feedback/ctl surface — consumes `set_phase`/`set_models_loaded`), from P1.M2.T1 (load logic), and from P1.M1 (bounded teardown). The only file overlap with a sibling is NONE (P1.M2.T2.S1 edits feedback/ctl/test_daemon/test_feedback/test_voicectl; this edits config/config.toml/daemon/test_config_repo_default — and daemon edits are in DIFFERENT regions: `_arm`/`_disarm`/`__init__`/after-`_idle_watchdog`/`run()` watchdog-start, none of which P1.M2.T2.S1 touches).

## What

Add the `auto_unload_idle_seconds` knob (config.py dataclass field + config.toml line), a `_disarmed_monotonic` stamp wired into the existing `_arm`/`_disarm`, an `_idle_unload_watchdog` thread (mirroring `_idle_watchdog`) started from `run()`, a `_maybe_idle_unload` decision pre-check, and an `_unload_recorder` actor that runs the bounded teardown under the single-flight `_lock` and flips the lifecycle state to `unloaded`. Update the one config test that pins the `asr` key set.

### Success Criteria

- [ ] `AsrConfig` has `auto_unload_idle_seconds: float = 1800.0`; `AsrConfig().auto_unload_idle_seconds == 1800.0`.
- [ ] `<repo>/config.toml` `[asr]` has `auto_unload_idle_seconds = 1800.0`; `VoiceTypingConfig.from_toml_file(<repo config>) == VoiceTypingConfig()` (drift guard green).
- [ ] `test_config_repo_default.py::test_repo_config_toml_has_no_extra_keys` expected `asr` set includes `auto_unload_idle_seconds` (and the docstring count is bumped to 17).
- [ ] `VoiceTypingDaemon.__init__` sets `self._disarmed_monotonic: float | None = None`.
- [ ] `_arm()` sets `self._disarmed_monotonic = None`; `_disarm()` sets `self._disarmed_monotonic = time.monotonic()`.
- [ ] `_idle_unload_watchdog()` exists, ticks `while not self._shutdown.wait(1.0)`, calls `_maybe_idle_unload()`, swallows exceptions; started from `run()` as a daemon thread named `voice-typing-idle-unload`.
- [ ] `_maybe_idle_unload()` short-circuits on `threshold <= 0`, does a lock-free pre-check, delegates to `_unload_recorder()`.
- [ ] `_unload_recorder()` acquires `_lock`, re-checks `models_loaded AND not listening AND disarmed >= threshold`, runs `_bounded_shutdown()` UNDER the lock, then `_recorder=None`/`_models_loaded=False`/`set_phase('unloaded')`/`set_models_loaded(False)`, logs the pinned line.
- [ ] `_unload_recorder()` re-checks `_listening.is_set()` under the lock (race-safety for S2's test).
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] `git status --short` shows only `config.py`, `config.toml`, `daemon.py`, `tests/test_config_repo_default.py` (+ optional `tests/test_config.py`).

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement it from this PRP + the research note: the two template patterns (`_idle_watchdog` tick + `_maybe_auto_stop` deadline-under-lock) are reproduced verbatim with line numbers; the consumed contracts (`_load_recorder` single-flight, `_bounded_shutdown` bounded/non-lock-touching, the feedback `set_phase`/`set_models_loaded` from the parallel task) are pinned; the concurrency model (teardown-under-lock + the `_listening` TOCTOU re-check) is explained; the ONE required test fix (`test_config_repo_default` key set) is flagged with the exact old→new; every daemon edit is byte-exact oldText→newText against the current file (incl. the `—` em-dash in config.toml). Baseline (fast suite green) verified live.

### Documentation & References

```yaml
# MUST READ — templates, consumed contracts, the concurrency model, the required test fix, scope
- docfile: plan/003_27d1f88f5a9f/P1M3T1S1/research/idle_unload_watchdog.md
  why: "§1 the verbatim templates (_idle_watchdog tick; _maybe_auto_stop deadline-under-lock). §2 what
        to CONSUME (_load_recorder single-flight + Condition-over-_lock -> calling it under _lock
        deadlocks; _bounded_shutdown bounded + reads self._recorder + never touches _lock -> safe under
        _lock; the feedback set_phase/set_models_loaded from P1.M2.T2.S1). §3 THE CONCURRENCY MODEL:
        teardown-under-_lock + the _listening TOCTOU re-check (load-bearing); _disarmed_monotonic
        wiring + composition with auto-stop. §4 the config knob + the REQUIRED test_config_repo_default
        fix. §5 S1 vs S2 vs T2.S1 scope. §6 tooling. §7 the pinned log line."
  section: "ALL load-bearing. §3 (concurrency), §2.1/§2.2 (consume don't touch), §4.3 (required test fix)."

# MUST READ — the file being edited (config.py AsrConfig + the test that pins its key set)
- file: voice_typing/config.py
  why: "AsrConfig (line 49-57) gets the new field after auto_stop_idle_seconds. The field order matters
        only for readability (dataclass; tomllib overlay is by-name). Mirror the auto_stop_idle_seconds
        comment style (tunable + '0 disables')."
  critical: "auto_unload_idle_seconds DEFAULT must be 1800.0 (PRD §4.5/§4.2bis). config.toml MUST mirror
             it or the drift guard (test_repo_config_toml_equals_defaults) fails."

# MUST READ — the drift-guard test that BREAKS when config.toml gains a key (REQUIRED fix)
- file: tests/test_config_repo_default.py
  why: "test_repo_config_toml_has_no_extra_keys asserts the EXACT asr key set (7 keys). Adding
        auto_unload_idle_seconds to config.toml breaks it UNLESS the expected set is updated. This is the
        one REQUIRED test edit. test_repo_config_toml_equals_defaults stays green if config.py+config.toml
        both = 1800.0 (no edit needed there)."
  critical: "Do NOT skip this edit — it is the most likely silent failure. Add 'auto_unload_idle_seconds'
             to the expected asr set + bump the docstring '16 schema keys' -> '17'."

# MUST READ — the file being edited (daemon.py: the templates + the edit sites)
- file: voice_typing/daemon.py
  why: "TEMPLATES: _idle_watchdog (759-770, the tick), _maybe_auto_stop (733-757, the deadline-under-lock),
        _load_recorder (481-563, single-flight via _load_cond over _lock), _bounded_shutdown (947-1003,
        bounded + reads self._recorder + never touches _lock). EDIT SITES: __init__ (_last_speech_monotonic
        ~445 -> add _disarmed_monotonic), _arm (691-698 -> clear it), _disarm (700-722 -> set it),
        run() watchdog-start (~597-598 -> add the unload-watchdog thread), after _idle_watchdog (~770 ->
        add the 3 new methods)."
  critical: "Do NOT edit _load_recorder/_bounded_shutdown/shutdown/build_recorder logic (prerequisites —
             CONSUME). Reproduce the — (em dash) + → Unicode in oldText EXACTLY. _unload_recorder MUST
             re-check _listening.is_set() under the lock (race safety for S2). Call _bounded_shutdown
             BEFORE nulling self._recorder (it reads self._recorder)."

# MUST READ — the config file being edited (the [asr] section + the em-dash)
- file: config.toml
  why: "The [asr] auto_stop_idle_seconds line is the edit anchor (it has an em-dash '— prevents' —
        reproduce EXACTLY in oldText). Add the auto_unload_idle_seconds line right after it, aligned to
        the same = column as the other [asr] keys (cosmetic; TOML ignores whitespace)."
  critical: "The line MUST be `auto_unload_idle_seconds = 1800.0` (PRD §4.5). The comment is the
             [Mode A] documentation (item DOCS). Keep it terse + match the file's comment style."

# MUST READ — the parallel task contract (the feedback surface this task CONSUMES)
- file: plan/003_27d1f88f5a9f/P1M2T2S1/PRP.md
  why: "P1.M2.T2.S1 (IN PARALLEL) adds Feedback.set_models_loaded(bool) + the phase/models_loaded/
        load_error status surface. _unload_recorder calls self._feedback.set_phase('unloaded') +
        set_models_loaded(False) — both provided by that task. Treat as a contract: they WILL exist.
        Its daemon edits (the 4 set_models_loaded calls + status_snapshot) are in DIFFERENT regions
        than this task's (_arm/_disarm/__init__/after-_idle_watchdog/run() watchdog-start)."
  critical: "Do NOT duplicate P1.M2.T2.S1's work (no feedback.py/ctl.py edits, no status_snapshot edit).
             Just CALL set_phase('unloaded') + set_models_loaded(False) in _unload_recorder."

# THE PRD LIFECYCLE (the contract) — READ-ONLY
- docfile: PRD.md
  why: "§4.2bis Idle unload: the rule + the bounded-teardown requirement + the pinned log line
        'voice-typing idle-unload: 1800.0s disarmed; unloading models'. §4.5: auto_unload_idle_seconds
        default 1800.0, 0 disables, composes with auto-stop. §7.9: the acceptance criterion."
  critical: "Do NOT edit PRD.md (forbidden). The log line + the 1800.0 default + the '0 disables' rule
             are verbatim contracts."
```

### Current Codebase tree (state at P1.M3.T1.S1 start — M1 + M2.T1 COMPLETE; M2.T2 IN PARALLEL)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── config.py            # EDIT: AsrConfig + auto_unload_idle_seconds field + docstring.
│   ├── daemon.py            # EDIT: __init__/_arm/_disarm (stamp) + 3 new methods + run() thread start.
│   ├── feedback.py          # OUT OF SCOPE (P1.M2.T2.S1 owns set_models_loaded — CONSUME set_phase/set_models_loaded).
│   └── ctl.py               # OUT OF SCOPE (P1.M2.T2.S1 owns the status rendering).
├── config.toml              # EDIT: [asr] + the auto_unload_idle_seconds line.
└── tests/
    ├── test_config_repo_default.py  # EDIT (REQUIRED): asr key set + docstring count.
    └── test_config.py               # EDIT (OPTIONAL): +assert the new default.
# _load_recorder/_bounded_shutdown/shutdown/build_recorder = prerequisites (CONSUME, do NOT edit).
```

### Desired Codebase tree with files to be added

```bash
voice_typing/config.py                   # MODIFIED: +auto_unload_idle_seconds field (+docstring).
voice_typing/daemon.py                   # MODIFIED: +_disarmed_monotonic (init/arm/disarm); +3 methods; +run() thread.
config.toml                             # MODIFIED: +auto_unload_idle_seconds line in [asr].
tests/test_config_repo_default.py       # MODIFIED (REQUIRED): +key in expected asr set + docstring count.
tests/test_config.py                    # MODIFIED (OPTIONAL): +default assertion.
# NOTHING ELSE. No new files. No feedback/ctl/status.sh/README. No new committed idle-unload tests (S2/T2.S1).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE REQUIRED TEST FIX IS test_config_repo_default.py, NOT test_config.py.
#   test_repo_config_toml_has_no_extra_keys() asserts the EXACT asr key set. Adding a key to config.toml
#   breaks it. You MUST add 'auto_unload_idle_seconds' to the expected asr set (Edit T1) or the fast
#   suite fails. test_repo_config_toml_equals_defaults() stays green if config.py+config.toml both =
#   1800.0. This is the single most likely silent failure — do NOT skip it. (Research §4.3.)

# CRITICAL #2 — _unload_recorder MUST RE-CHECK _listening.is_set() UNDER THE LOCK. The watchdog's
#   _maybe_idle_unload pre-check is lock-free (atomic reads); between it and _unload_recorder acquiring
#   _lock, an arm can happen. _unload_recorder re-checks the FULL condition under _lock (incl.
#   _listening) so a racing arm aborts the unload. Item clause (d) says "if not _models_loaded -> return";
#   the _listening re-check is the race-safety addition (S2 tests it). (Research §3.)

# CRITICAL #3 — CALL _bounded_shutdown() BEFORE nulling self._recorder. _bounded_shutdown reads
#   self._recorder directly (self._recorder.shutdown(); getattr(self._recorder, attr, None)). Null it
#   AFTER. Order: under _lock -> re-check -> _bounded_shutdown() -> self._recorder=None ->
#   _models_loaded=False -> set_phase/set_models_loaded. (Research §2.2.)

# CRITICAL #4 — _bounded_shutdown IS SAFE UNDER _lock (no deadlock). It uses its own threading.Event,
#   spawns a daemon thread for recorder.shutdown(), and NEVER acquires the daemon's _lock. So holding
#   _lock across it is the sanctioned single-flight design. A racing arm's _load_recorder blocks at its
#   first `with self._lock:` (it can't proceed until teardown releases) -> then loads fresh. (Research §2.2, §3.)

# CRITICAL #5 — DO NOT CALL _load_recorder() FROM _unload_recorder (or vice versa). _load_recorder
#   acquire-release-reacquires _lock (Condition.wait needs to release it); nesting it under _lock
#   DEADLOCKS (threading.Lock is NOT reentrant). _unload_recorder only CALLS _bounded_shutdown +
#   _feedback methods (neither takes _lock). The arm path calls _load_recorder OUTSIDE _lock
#   (start():832, toggle():860) — that is what makes the single-flight wait work. (Research §2.1.)

# CRITICAL #6 — _disarm() IS THE SINGLE STAMP POINT (composition). _disarm is called by stop(),
#   toggle()-disarm, AND _maybe_auto_stop() -> all three start the unload clock. _arm() clears it.
#   Do NOT stamp _disarmed_monotonic in stop/toggle/_maybe_auto_stop directly — only in _disarm (one
#   place). (Research §3.)

# CRITICAL #7 — REPRODUCE UNICODE IN oldText. config.toml's auto_stop_idle_seconds line has an em-dash
#   (—) in "go silent — prevents"; daemon.py comments use →/—. The edit tool matches EXACT bytes; copy
#   verbatim oldText from the Implementation Blueprint. (Research §4.2.)

# CRITICAL #8 — THE LOG LINE IS PINNED. PRD §4.2bis + the item quote it verbatim:
#   'voice-typing idle-unload: 1800.0s disarmed; unloading models'. Use %.1fs with the threshold so it
#   reflects the configured value. (Research §7.)

# CRITICAL #9 — DON'T WRITE THE IDLE-UNLOAD BEHAVIOR TESTS HERE. S1 = implementation + the required
#   config-test fix. The race-safety test is P1.M3.T1.S2; the fire/reset/disable fast pytest is
#   P1.M3.T2.S1. S1 validates via py_compile + the existing fast suite (no regression) + a
#   non-committed L3 smoke. (Research §5.)

# GOTCHA #10 — FULL TOOL PATHS (zsh aliases). .venv/bin/python -m pytest ... (never bare python/pytest).
#   Optional ruff at /home/dustin/.local/bin/ruff (NOT in .venv). mypy NOT installed — do NOT run it.

# GOTCHA #11 — run() STARTS THE WATCHDOG (most tests don't call run()). _idle_unload_watchdog is
#   started from run() exactly like _idle_watchdog; tests that don't call run() never start it. The
#   watchdog swallows its own exceptions (mirrors _idle_watchdog) so it can never kill the thread. No
#   existing test asserts a thread count (verified pattern).
```

## Implementation Blueprint

### Data models and structure

The only new state is one daemon instance attribute `self._disarmed_monotonic: float | None` (None == clock inactive / armed; `time.monotonic()` stamped on disarm) and one config field `auto_unload_idle_seconds: float` (default 1800.0). No new classes. `_unload_recorder` reuses the existing `_lock` + `_bounded_shutdown` + the feedback `set_phase`/`set_models_loaded` (P1.M2.T2.S1).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/config.py — AsrConfig field + docstring (Edit C1)
  - Add auto_unload_idle_seconds: float = 1800.0 after auto_stop_idle_seconds (+ comment).
  - EXACT oldText→newText: see Edit C1.

Task 2: EDIT config.toml — [asr] line (Edit C2)
  - Add the auto_unload_idle_seconds = 1800.0 line right after the auto_stop_idle_seconds line.
  - Align the = column to the other [asr] keys (cosmetic). Reproduce the em-dash in oldText EXACTLY.

Task 3: EDIT tests/test_config_repo_default.py — REQUIRED key-set fix (Edit T1)
  - Add auto_unload_idle_seconds to the expected asr set; bump the docstring '16' -> '17'.

Task 4: EDIT voice_typing/daemon.py — _disarmed_monotonic stamp wiring (Edits D1-D3)
  - D1 (__init__): add self._disarmed_monotonic: float | None = None (+ comment) after _last_speech_monotonic.
  - D2 (_arm): add self._disarmed_monotonic = None after the _last_speech_monotonic set.
  - D3 (_disarm): add self._disarmed_monotonic = time.monotonic() after the _last_speech_monotonic clear.
  - EXACT oldText→newText: see Edits D1-D3.

Task 5: EDIT voice_typing/daemon.py — 3 new methods after _idle_watchdog (Edit D4)
  - ADD _idle_unload_watchdog(), _maybe_idle_unload(), _unload_recorder() immediately after _idle_watchdog.
  - EXACT newText: see Edit D4 (anchor: the end of _idle_watchdog / start of _refresh_mic_status).

Task 6: EDIT voice_typing/daemon.py — run() thread start (Edit D5)
  - Add the _idle_unload_watchdog daemon-thread start right after the _idle_watchdog start.
  - EXACT oldText→newText: see Edit D5.

Task 7: (OPTIONAL) EDIT tests/test_config.py — default assertion (Edit T2)
  - Add assert cfg.asr.auto_unload_idle_seconds == 1800.0 after the auto_stop_idle_seconds assertion.

Task 8: VALIDATE (no file change — see Validation Loop)
  - py_compile + grep wiring + the fast suite (no regression) + the L3 wiring smoke.
  - No git commit unless the orchestrator directs it.
```

### Edits — verbatim oldText → newText

#### Edit C1 — `voice_typing/config.py` AsrConfig

`oldText`:
```
    auto_stop_idle_seconds: float = 30.0       # auto-disarm after this many seconds of no recognized
                                               # speech (partials reset the clock); 0 disables
```
`newText`:
```
    auto_stop_idle_seconds: float = 30.0       # auto-disarm after this many seconds of no recognized
                                               # speech (partials reset the clock); 0 disables
    auto_unload_idle_seconds: float = 1800.0   # PRD §4.2bis: after this many seconds DISARMED with
                                               # models loaded, tear down the recorder to free VRAM
                                               # (~0); the clock starts on disarm and resets on arm.
                                               # 0 disables (models stay resident until quit)
```

#### Edit C2 — `config.toml` `[asr]` (add line after `auto_stop_idle_seconds`)

`oldText` (note the em-dash `—` — reproduce EXACTLY):
```
auto_stop_idle_seconds       = 30.0                # auto-disarm (stop listening) after this many seconds with NO recognized speech. Partials reset the clock while you talk, so it only fires when you truly go silent — prevents a forgotten hot-mic. Fires the normal stop popup + a journal line. 0 disables.
```
`newText` (the existing line unchanged + the new line; align `=` to the `[asr]` column):
```
auto_stop_idle_seconds       = 30.0                # auto-disarm (stop listening) after this many seconds with NO recognized speech. Partials reset the clock while you talk, so it only fires when you truly go silent — prevents a forgotten hot-mic. Fires the normal stop popup + a journal line. 0 disables.
auto_unload_idle_seconds     = 1800.0              # after this many seconds DISARMED (models loaded, NOT listening), tear down the recorder to free VRAM (~0). The clock starts on disarm (manual stop, toggle-off, or the auto-stop above) and resets on any arm; time listening does NOT count. 0 disables (models stay resident until quit). (PRD 4.2bis Idle unload)
```

#### Edit T1 — `tests/test_config_repo_default.py` (REQUIRED — key set + docstring count)

`oldText` (the docstring):
```
    """The repo default must carry only the 16 schema keys (no compute_type etc.)."""
```
`newText`:
```
    """The repo default must carry only the 17 schema keys (no compute_type etc.)."""
```

`oldText` (the expected asr set):
```
        "asr": {
            "final_model",
            "realtime_model",
            "language",
            "device",
            "post_speech_silence_duration",
            "realtime_processing_pause",
            "auto_stop_idle_seconds",
        },
```
`newText`:
```
        "asr": {
            "final_model",
            "realtime_model",
            "language",
            "device",
            "post_speech_silence_duration",
            "realtime_processing_pause",
            "auto_stop_idle_seconds",
            "auto_unload_idle_seconds",   # P1.M3.T1.S1: idle-unload knob (PRD §4.2bis)
        },
```

#### Edit D1 — `voice_typing/daemon.py` `__init__` (add stamp field)

`oldText`:
```
        self._last_speech_monotonic: float | None = None
```
`newText`:
```
        self._last_speech_monotonic: float | None = None
        # Idle UNLOAD clock (P1.M3.T1.S1 / PRD §4.2bis): time.monotonic() of when the mic was last
        # DISARMED; the _idle_unload_watchdog tears the recorder down after cfg.asr.auto_unload_idle_seconds
        # in this state to reclaim VRAM. None while armed/listening (clock inactive). Set in _disarm,
        # cleared in _arm. Float store is atomic in CPython; _unload_recorder re-checks under _lock.
        self._disarmed_monotonic: float | None = None
```

#### Edit D2 — `voice_typing/daemon.py` `_arm` (clear stamp)

`oldText`:
```
        self._listening.set()
        self._last_speech_monotonic = time.monotonic()  # start the idle auto-stop clock fresh
```
`newText`:
```
        self._listening.set()
        self._last_speech_monotonic = time.monotonic()  # start the idle auto-stop clock fresh
        self._disarmed_monotonic = None                  # armed -> idle-UNLOAD clock inactive (P1.M3.T1.S1)
```

#### Edit D3 — `voice_typing/daemon.py` `_disarm` (set stamp)

`oldText`:
```
        self._listening.clear()
        self._last_speech_monotonic = None  # not listening → idle clock is inactive
```
`newText`:
```
        self._listening.clear()
        self._last_speech_monotonic = None  # not listening → idle clock is inactive
        self._disarmed_monotonic = time.monotonic()  # start the idle-UNLOAD clock (P1.M3.T1.S1)
```

#### Edit D4 — `voice_typing/daemon.py` add 3 methods after `_idle_watchdog`

`oldText` (the end of `_idle_watchdog` + the start of `_refresh_mic_status` — unique anchor):
```
    def _idle_watchdog(self) -> None:
        """Background thread: periodically call _maybe_auto_stop(). Started by run(); daemon thread.

        Ticks via _shutdown.wait(1.0) so it both sleeps ~1s AND exits promptly on shutdown. The
        check swallows its own exceptions so a transient error never kills the watchdog.
        """
        while not self._shutdown.wait(1.0):
            try:
                self._maybe_auto_stop()
            except Exception:
                logger.exception("idle auto-stop check raised; continuing")

    def _refresh_mic_status(self, *, force: bool = False) -> None:
```
`newText`:
```
    def _idle_watchdog(self) -> None:
        """Background thread: periodically call _maybe_auto_stop(). Started by run(); daemon thread.

        Ticks via _shutdown.wait(1.0) so it both sleeps ~1s AND exits promptly on shutdown. The
        check swallows its own exceptions so a transient error never kills the watchdog.
        """
        while not self._shutdown.wait(1.0):
            try:
                self._maybe_auto_stop()
            except Exception:
                logger.exception("idle auto-stop check raised; continuing")

    def _idle_unload_watchdog(self) -> None:
        """Background thread: periodically call _maybe_idle_unload(). Started by run(); daemon thread.

        P1.M3.T1.S1 / PRD §4.2bis Idle unload. Mirrors _idle_watchdog: ticks via _shutdown.wait(1.0)
        (sleeps ~1s AND exits promptly on shutdown) and swallows its own exceptions.
        """
        while not self._shutdown.wait(1.0):
            try:
                self._maybe_idle_unload()
            except Exception:
                logger.exception("idle unload check raised; continuing")

    def _maybe_idle_unload(self) -> None:
        """If the mic has been DISARMED long enough, tear down the recorder to reclaim VRAM.

        P1.M3.T1.S1 / PRD §4.2bis. Lock-free pre-check (atomic bool/float/Event reads are safe in
        CPython) so the common path (not time yet) does NOT acquire _lock every tick. When the
        pre-check passes, delegate to _unload_recorder(), which does the authoritative re-check +
        bounded teardown UNDER _lock (single-flight: a racing arm waits, then loads fresh).

        threshold<=0 disables (short-circuit, never calls _unload_recorder). Composes with idle
        auto-stop: _maybe_auto_stop's _disarm() is what stamps _disarmed_monotonic, so the 30s
        auto-stop starts this 30-min clock for free.
        """
        threshold = self._cfg.asr.auto_unload_idle_seconds
        if threshold <= 0:
            return
        # Lock-free pre-check (avoid hammering _lock every 1s). _unload_recorder re-checks under _lock.
        if (
            not self._models_loaded
            or self._listening.is_set()
            or self._disarmed_monotonic is None
            or time.monotonic() - self._disarmed_monotonic < threshold
        ):
            return
        self._unload_recorder()

    def _unload_recorder(self) -> None:
        """Tear down the resident recorder to reclaim VRAM (PRD §4.2bis Idle unload). Single-flight.

        Acquires _lock (the SAME lock _load_recorder uses) and re-checks the FULL unload condition
        UNDER the lock — including self._listening.is_set() — so an arm that raced this call (between
        the watchdog's lock-free pre-check and here) ABORTS the unload. The bounded teardown
        (_bounded_shutdown) runs UNDER _lock so a concurrent arm's _load_recorder() blocks on this
        lock, waits for teardown, then loads fresh (an arm never sees a half-torn-down recorder).
        _bounded_shutdown is bounded (~<=10s) + best-effort + never touches _lock, so holding _lock
        across it is safe (no deadlock). threshold<=0 is handled by _maybe_idle_unload; this method
        also guards for safety if called directly.

        After teardown: _recorder=None, _models_loaded=False, phase 'unloaded', models_loaded False
        (so voicectl status reports it via P1.M2.T2.S1's surface). The run() loop then sees
        _recorder is None -> idle (~0 VRAM); the next arm reloads via _load_recorder().
        """
        threshold = self._cfg.asr.auto_unload_idle_seconds
        with self._lock:
            if (
                not self._models_loaded                     # nothing resident (or a load/unload beat us)
                or self._listening.is_set()                 # user armed — abort the unload (race guard)
                or self._disarmed_monotonic is None         # never disarmed (shouldn't happen here)
                or threshold <= 0                           # disabled
                or time.monotonic() - self._disarmed_monotonic < threshold  # not yet
            ):
                return
            logger.info(
                "voice-typing idle-unload: %.1fs disarmed; unloading models", threshold,
            )
            # _bounded_shutdown reads self._recorder (still set) + never touches _lock -> safe under _lock.
            self._bounded_shutdown()
            self._recorder = None
            self._models_loaded = False
            self._feedback.set_phase("unloaded")          # P1.M2.T2.S1 surface (CONSUME, don't re-add)
            self._feedback.set_models_loaded(False)       # P1.M2.T2.S1 surface

    def _refresh_mic_status(self, *, force: bool = False) -> None:
```

#### Edit D5 — `voice_typing/daemon.py` `run()` (start the watchdog thread)

`oldText`:
```
        # Idle auto-stop watchdog: disarms after cfg.asr.auto_stop_idle_seconds of no speech.
        threading.Thread(target=self._idle_watchdog, name="voice-typing-idle", daemon=True).start()
```
`newText`:
```
        # Idle auto-stop watchdog: disarms after cfg.asr.auto_stop_idle_seconds of no speech.
        threading.Thread(target=self._idle_watchdog, name="voice-typing-idle", daemon=True).start()
        # Idle UNLOAD watchdog (P1.M3.T1.S1 / PRD §4.2bis): reclaims VRAM after cfg.asr.auto_unload_idle_seconds
        # DISARMED. Mirrors the idle-watchdog start above; same _shutdown.wait(1.0) tick + daemon thread.
        threading.Thread(target=self._idle_unload_watchdog, name="voice-typing-idle-unload", daemon=True).start()
```

#### Edit T2 — (OPTIONAL) `tests/test_config.py` default assertion

`oldText`:
```
    assert cfg.asr.auto_stop_idle_seconds == 30.0
```
`newText`:
```
    assert cfg.asr.auto_stop_idle_seconds == 30.0
    assert cfg.asr.auto_unload_idle_seconds == 1800.0  # P1.M3.T1.S1: idle-unload knob (PRD §4.2bis)
```

> **Why these edits:** C1/C2 add the knob (code + config mirror). T1 is the REQUIRED fix (the drift guard pins the asr key set). D1-D3 wire the disarm stamp (composition with auto-stop via the single `_disarm` path). D4 is the feature (watchdog tick mirrors `_idle_watchdog`; `_unload_recorder` does the bounded teardown under `_lock` with the `_listening` race re-check). D5 starts the thread. The design reuses the existing `_lock` + `_bounded_shutdown` + feedback surface (P1.M2.T2.S1) — no new locks, no new state machine, no prerequisite edits.

### Implementation Patterns & Key Details

```python
# (1) The watchdog tick mirrors _idle_watchdog EXACTLY (Critical #1 in research):
while not self._shutdown.wait(1.0):
    try:
        self._maybe_idle_unload()
    except Exception:
        logger.exception("idle unload check raised; continuing")

# (2) Lock-free pre-check (avoid hammering _lock every 1s) + locked authoritative re-check:
def _maybe_idle_unload(self):
    threshold = self._cfg.asr.auto_unload_idle_seconds
    if threshold <= 0: return
    if (not self._models_loaded or self._listening.is_set() or self._disarmed_monotonic is None
            or time.monotonic() - self._disarmed_monotonic < threshold):
        return                       # lock-free atomic reads; not time yet
    self._unload_recorder()          # does the locked re-check + teardown

# (3) Teardown UNDER _lock (single-flight); re-check _listening for the TOCTOU race (Critical #2/#4):
def _unload_recorder(self):
    with self._lock:
        if (not self._models_loaded or self._listening.is_set() or ...): return
        self._bounded_shutdown()     # bounded (<=10s); reads self._recorder; never touches _lock
        self._recorder = None        # null AFTER _bounded_shutdown (it reads self._recorder)
        self._models_loaded = False
        self._feedback.set_phase("unloaded"); self._feedback.set_models_loaded(False)

# (4) Composition via the single _disarm stamp (Critical #6): _disarm sets _disarmed_monotonic
#     (called by stop/toggle-off/_maybe_auto_stop); _arm clears it. No other stamp site.
```

### Integration Points

```yaml
CONFIG (AsrConfig):
  - add field: "auto_unload_idle_seconds: float = 1800.0"  # 0 disables; mirror in config.toml
STATE (VoiceTypingDaemon):
  - add attr: "self._disarmed_monotonic: float | None  (None=armed/inactive; time.monotonic() on disarm)"
  - _arm: "self._disarmed_monotonic = None"
  - _disarm: "self._disarmed_monotonic = time.monotonic()"
THREADS:
  - run() starts: "Thread(target=self._idle_unload_watchdog, name='voice-typing-idle-unload', daemon=True)"
LIFECYCLE (consumes P1.M2.T2.S1 surface — do NOT re-implement):
  - _unload_recorder -> "self._feedback.set_phase('unloaded') + set_models_loaded(False)"
  - effect: "voicectl status reports phase: unloaded + (not loaded) after idle-unload (P1.M2.T2.S1 renders it)"
CONSUMERS (unchanged, auto-benefit):
  - run() loop: "sees self._recorder is None after unload -> time.sleep(0.05) idle (~0 VRAM); next arm reloads"
  - status_snapshot: "**reads phase/models_loaded from feedback (P1.M2.T2.S1) — the unload transition flows through"
```

## Validation Loop

> pytest is the gate (.venv/bin/python). FULL PATHS (zsh aliases). mypy is NOT installed (skip).
> ruff is optional (/home/dustin/.local/bin/ruff, NOT in .venv).

### Level 1: Syntax + wiring (grep)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" -m py_compile voice_typing/config.py voice_typing/daemon.py config.toml 2>&1 | head || true
# config.toml isn't python — py_compile it separately via tomllib:
"$PY" - <<'PY'
import tomllib
with open("config.toml","rb") as f: d = tomllib.load(f)
assert d["asr"]["auto_unload_idle_seconds"] == 1800.0, d["asr"]
print("L1 config.toml parses; auto_unload_idle_seconds=1800.0")
PY
echo "--- wiring ---"
grep -n "auto_unload_idle_seconds" voice_typing/config.py config.toml tests/test_config_repo_default.py
grep -n "_disarmed_monotonic\|_idle_unload_watchdog\|_maybe_idle_unload\|_unload_recorder" voice_typing/daemon.py
# Expected: the field in config.py + the line in config.toml + the key in the test; in daemon.py:
#   _disarmed_monotonic (init + _arm None + _disarm stamp + _maybe_idle_unload + _unload_recorder),
#   _idle_unload_watchdog (def + run() thread start), _maybe_idle_unload (def), _unload_recorder (def).
```

### Level 2: Unit Tests (THE gate — no regression)

```bash
cd /home/dustin/projects/voice-typing
# The config drift guard (the REQUIRED fix lives here):
.venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -v
# Expected: GREEN — incl. test_repo_config_toml_has_no_extra_keys (now 17 asr keys incl. auto_unload_idle_seconds)
#   and test_repo_config_toml_equals_defaults (config.py == config.toml).

# Whole fast suite (no regression — S1 adds no committed idle-unload behavior test; S2/T2.S1 own those):
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed. (test_feed_audio.py is GPU-gated; excluded.) If test_daemon fails, check whether a
# test calls run() and needs the new watchdog accounted for (none should — pattern matches _idle_watchdog).
```

### Level 3: Integration smoke (wiring correctness — non-committed; behavior tests are S2/T2.S1)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
import time, threading
from voice_typing.config import VoiceTypingConfig, AsrConfig
from voice_typing.daemon import VoiceTypingDaemon

# (a) config knob
assert AsrConfig().auto_unload_idle_seconds == 1800.0

# (b) build a daemon with a stub recorder + fake feedback, exercise the unload path WITHOUT a real GPU.
class _StubRecorder:
    def __init__(self): self.shutdown_called = False; self.is_shut_down = False
    def shutdown(self): self.shutdown_called = True
    def set_microphone(self, b): pass
    def abort(self): pass
class _FakeFeedback:
    def __init__(self): self.phases = []; self.models = []
    def set_phase(self, p): self.phases.append(p)
    def set_models_loaded(self, b): self.models.append(b)
    def set_listening(self, b): pass
    def update_partial(self, t): pass
    def record_final(self, t): pass
    def snapshot(self): return {"phase": "idle", "models_loaded": True}

cfg = VoiceTypingConfig()
cfg.asr.auto_unload_idle_seconds = 0.5    # tiny threshold for the smoke
fb = _FakeFeedback()
d = VoiceTypingDaemon(cfg, fb, recorder=_StubRecorder(), backend=object())
# loaded at construction (recorder injected) -> _models_loaded True
assert d._models_loaded is True
# arm then disarm -> _disarmed_monotonic stamped
with d._lock: d._arm()
assert d._disarmed_monotonic is None      # armed clears it
with d._lock: d._disarm()
assert d._disarmed_monotonic is not None  # disarm stamps it
# wait past the threshold -> _maybe_idle_unload fires _unload_recorder
time.sleep(0.7)
d._maybe_idle_unload()
assert d._models_loaded is False, "models should be unloaded"
assert d._recorder is None, "recorder should be None after unload"
assert "unloaded" in fb.phases and False in fb.models, (fb.phases, fb.models)
print("L3 OK: arm clears stamp; disarm stamps; _maybe_idle_unload fires _unload_recorder -> unloaded")

# (c) disable: threshold<=0 -> _maybe_idle_unload is a no-op
cfg2 = VoiceTypingConfig(); cfg2.asr.auto_unload_idle_seconds = 0
d2 = VoiceTypingDaemon(cfg2, _FakeFeedback(), recorder=_StubRecorder(), backend=object())
with d2._lock: d2._disarm()
time.sleep(0.1); d2._maybe_idle_unload()
assert d2._models_loaded is True and d2._recorder is not None, "threshold 0 must NOT unload"
print("L3 OK: auto_unload_idle_seconds=0 disables (no unload)")

# (d) race guard: listening aborts the unload (re-check under lock)
cfg3 = VoiceTypingConfig(); cfg3.asr.auto_unload_idle_seconds = 0.5
d3 = VoiceTypingDaemon(cfg3, _FakeFeedback(), recorder=_StubRecorder(), backend=object())
with d3._lock: d3._disarm(); 
time.sleep(0.7)
with d3._lock: d3._arm()    # user re-arms just before the watchdog fires
d3._unload_recorder()       # authoritative re-check sees _listening set -> abort
assert d3._models_loaded is True and d3._recorder is not None, "armed -> unload must abort"
print("L3 OK: an arm racing the unload aborts it (the _listening re-check)")
PY
# Expected: prints all four "L3 OK" lines; exit 0. This is the structural proof S2/T2.S1 will harden
# into committed pytest (race + fire/reset/disable). It uses stub objects (no GPU, no RealtimeSTT).
```

### Level 4: Creative & Domain-Specific Validation

```bash
# No live-GPU path is required for S1 (the ~0-VRAM reclamation is asserted end-to-end by the rewritten
# T6 in P1.M3.T2.S2). An OPTIONAL live smoke (GPU-gated, manual) is:
#   1. systemctl --user restart voice-typing          # boots unloaded
#   2. voicectl start; sleep 2; voicectl stop          # arm (loads ~2.8GB) then disarm -> _disarmed_monotonic set
#   3. nvidia-smi --query-compute-apps=pid,used_memory --format=csv | grep <daemon pid>   # ~2.8GB resident
#   4. wait 31 min (or temporarily set auto_unload_idle_seconds=60 in config + restart for a faster check)
#   5. nvidia-smi ... | grep <daemon pid>              # PID GONE (~0 VRAM reclaimed)
#   6. voicectl start                                  # reloads (~1-3s); PID reappears
# This is out of scope for S1's automated gate (it's P1.M3.T2.S2's T6 + the idle-unload behavior tests
# in P1.M3.T2.S1). S1's correctness is proven by Level 2 (no regression) + Level 3 (wiring + race guard).
```

## Final Validation Checklist

### Technical Validation
- [ ] `grep auto_unload_idle_seconds voice_typing/config.py config.toml tests/test_config_repo_default.py` → all three present.
- [ ] `grep -n "_disarmed_monotonic\|_idle_unload_watchdog\|_maybe_idle_unload\|_unload_recorder" voice_typing/daemon.py` → stamp (init/arm/disarm) + 3 method defs + run() thread start.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] (Optional) `/home/dustin/.local/bin/ruff check voice_typing/config.py voice_typing/daemon.py` → clean.

### Feature Validation
- [ ] `AsrConfig().auto_unload_idle_seconds == 1800.0`; config.toml parses to the same (drift guard green).
- [ ] `_arm()` clears `_disarmed_monotonic`; `_disarm()` stamps it (single stamp site → composition with auto-stop).
- [ ] `_idle_unload_watchdog` ticks `_shutdown.wait(1.0)` + swallows exceptions; started from `run()`.
- [ ] `_unload_recorder()` re-checks the full condition under `_lock` (incl. `_listening`), runs `_bounded_shutdown` under the lock, nulls `_recorder`, flips `_models_loaded`, sets phase `unloaded` + `models_loaded False`.
- [ ] `auto_unload_idle_seconds <= 0` disables (L3 smoke (c)).
- [ ] An arm racing the unload aborts it (L3 smoke (d) — the `_listening` re-check).
- [ ] Level 3 smoke prints all four "L3 OK" lines.

### Code Quality Validation
- [ ] No edits to `_load_recorder`/`_bounded_shutdown`/`shutdown`/`build_recorder` (prerequisites — consume).
- [ ] No edits to `feedback.py`/`ctl.py` (P1.M2.T2.S1 owns the surface — consume `set_phase`/`set_models_loaded`).
- [ ] No new committed idle-unload behavior tests (S2/T2.S1 own them).
- [ ] `_bounded_shutdown()` called BEFORE `self._recorder = None`; no `_load_recorder()` call under `_lock`.
- [ ] Only the cited files modified (`git status --short`).

### Documentation & Deployment
- [ ] [Mode A] AsrConfig docstring/comment on `auto_unload_idle_seconds` (the 0-disables rule); config.toml comment IS the documentation.
- [ ] No new env vars; no README/ACCEPTANCE edits (P1.M3.T3 owns the doc sweep).

---

## Anti-Patterns to Avoid

- ❌ Don't skip the `test_config_repo_default.py` key-set fix (Edit T1) — adding the config.toml line breaks `test_repo_config_toml_has_no_extra_keys` without it (Critical #1).
- ❌ Don't null `self._recorder` BEFORE `_bounded_shutdown()` — it reads `self._recorder` (Critical #3).
- ❌ Don't omit the `_listening.is_set()` re-check in `_unload_recorder` — that's the race guard S2 tests (Critical #2).
- ❌ Don't call `_load_recorder()` from under `_lock` (or `_unload_recorder` from `_load_recorder`) — `Condition.wait` needs to release the non-reentrant `_lock`; nesting deadlocks (Critical #5).
- ❌ Don't stamp `_disarmed_monotonic` in stop/toggle/_maybe_auto_stop directly — only in `_disarm()` (the single composition point) (Critical #6).
- ❌ Don't edit `_load_recorder`/`_bounded_shutdown`/`shutdown`/`build_recorder`/`feedback.py`/`ctl.py` — prerequisites or the parallel task own them; consume, don't touch.
- ❌ Don't write the committed idle-unload behavior tests here — the race test is P1.M3.T1.S2; fire/reset/disable is P1.M3.T2.S1 (Critical #9). S1 ships implementation + the required config-test fix.
- ❌ Don't mangle the `—` (em-dash) in the config.toml oldText or the `→`/`—` in daemon.py — exact-byte match required (Critical #7).
- ❌ Don't change the pinned log line `voice-typing idle-unload: %.1fs disarmed; unloading models` (Critical #8).
- ❌ Don't run `mypy` — not installed; pytest is the gate (Gotcha #10).

---

**Confidence Score: 9/10** for one-pass success. The feature reuses three landed/parallel contracts (`_lock` single-flight, `_bounded_shutdown`, the feedback surface) and mirrors two verbatim templates (`_idle_watchdog`, `_maybe_auto_stop`); every edit is byte-exact oldText→newText; the one required test fix (`test_config_repo_default` key set) is explicitly flagged; and the non-committed L3 smoke proves the wiring + the disable path + the `_listening` race guard with stub objects (no GPU). The −1 reserves: the teardown-under-lock design is structurally sound but the dedicated race-safety + fire/reset/disable pytest suites live in S2/T2.S1 (not S1), so S1's automated coverage is the existing-fast-suite-no-regression + the L3 smoke rather than a full behavior suite — by design, per the plan's task split.
