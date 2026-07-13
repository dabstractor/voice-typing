# PRP — P1.M2.T2.S1: Expose `phase` + `models_loaded` from feedback, `status_snapshot()`, and ctl status rendering

## Goal

**Feature Goal**: Surface the lazy-load model lifecycle (PRD §4.2bis / §4.6 / §4.8) end-to-end so `voicectl status` and `state.json` report `phase` (`unloaded`/`loading`/`idle`/`listening`/`speaking`) and `models_loaded: bool`, plus the last `load_error`. P1.M2.T1.S1 (Complete) already wired the **phase transitions** in `_load_recorder()` + construction and tracks the daemon-side `self._models_loaded` — but it deliberately left `feedback.py` without a `models_loaded` field and `status_snapshot()`/ctl without `phase`/`models_loaded` exposure (live comment daemon.py:460-462: *"The feedback models_loaded FIELD + status_snapshot/ctl exposure is P1.M2.T2.S1"*). This task is that **clean delta**: add `models_loaded` to feedback state + a `set_models_loaded()` method, call it alongside the 4 existing `set_phase` transitions, add `phase`/`models_loaded`/`load_error` to `status_snapshot()`, and render them in ctl `status`.

**Deliverable** (edits to `voice_typing/feedback.py` + `voice_typing/daemon.py` + `voice_typing/ctl.py` + 3 test files; no new files):
1. `feedback.py` — `_state` default: `phase` `idle`→`unloaded` + add `models_loaded: False`; NEW `set_models_loaded(bool)` method; docstring updates ([Mode A]).
2. `daemon.py` — 4 `set_models_loaded(...)` calls alongside the existing `set_phase` calls (construction @463, load-start @506, success @542, failure @549); `status_snapshot()` adds `phase`/`models_loaded`/`load_error` (+ docstring).
3. `ctl.py` — `format_result` status branch: `phase:` line + `(loaded)`/`(not loaded)` marker on the models line + conditional `load error:` line.
4. tests — `test_feedback.py` (2 key-set assertions), `test_daemon.py` (`test_status_snapshot_keys_and_cuda_values` **+ add `set_models_loaded` to the `_FakeFeedback` stub** — without it every `_make_daemon` construction fails AttributeError), `test_voicectl.py` (`_STATUS_ON` + augmented test + 1 new test).

**Success Definition**:
- (a) `Feedback._state` has `models_loaded` (default False) and boot `phase` `unloaded`; `set_models_loaded(bool)` writes + never notifies.
- (b) The 4 daemon lifecycle transitions call `set_models_loaded` alongside T1.S1's existing `set_phase` (loading→False, success→True, failure→False, construction→`recorder is not None`).
- (c) `status_snapshot()` returns `phase`, `models_loaded`, `load_error` (in addition to the existing 10 keys).
- (d) `voicectl status` renders `phase:` + the `(loaded)`/`(not loaded)` marker + (when set) `load error:`.
- (e) `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed (baseline 292 passed).
- (f) No out-of-scope files: no `_load_recorder`/`__init__` recorder-attr logic (T1.S1), no `_arm_response`/`_dispatch`/loading-hint (T1.S2), no config.py/config.toml (P1.M3), no status.sh (reads JSON — unchanged), no README/ACCEPTANCE (P1.M3.T3), no `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. No new deps.

## User Persona

**Target User**: the operator running `voicectl status` (or a wrapper/tmux status reading `state.json`) who needs to know whether models are resident and what lifecycle phase the daemon is in.

**Use Case**: After daemon boot (before first arm), `voicectl status` shows `phase: unloaded` + `(not loaded)` — confirming ~0 VRAM (the lazy-load guarantee). During the first arm it shows `loading`. After a successful arm: `idle`/`listening` + `(loaded)`. After a load failure: `unloaded` + `(not loaded)` + `load error: …`.

**Pain Points Addressed**: today `status` cannot distinguish "booted, never armed" from "armed + loaded" — both can show `device: cuda`. With lazy load (T1.S1), that ambiguity hides whether the ~1–3 s reload cost is pending. `phase` + `models_loaded` remove the ambiguity; `load_error` surfaces §4.2bis's mandated failure reporting.

## Why

- **PRD §4.2bis / §4.8 mandate it.** §4.2bis: "`status` reports `models_loaded: bool` so callers/UI can tell `loading` from `armed`" and "On load failure … `status` reports the error". §4.8: status pretty-prints "`phase` (`unloaded`/`loading`/`idle`/`listening`/`speaking`), and `models_loaded`". §4.6: state.json carries `models_loaded` + the `unloaded`/`loading` boot phases.
- **T1.S1 explicitly deferred this surface.** T1.S1 shipped the phase *transitions* + daemon-side `_models_loaded` but left the feedback field + status/ctl exposure to this task (its PRP's feedback-boundary note + the live code comment). This task closes that loop without re-touching T1.S1's load logic.
- **`status.sh` needs no change.** The tmux helper already reads `state.json` via jq — adding `models_loaded`/`phase` to the JSON makes them available to any future status snippet with zero status.sh edits (item OUTPUT #4).
- **Cheap, additive, parallel-safe.** `set_models_loaded` mirrors `set_phase`; the 4 calls sit alongside existing ones; `status_snapshot` reads fields already in `_state`; ctl adds 3 `.get(...)` parses. Disjoint from T1.S2's `_dispatch`/hint regions and T1.S1's `_load_recorder` logic.

## What

Add a `models_loaded` field + `set_models_loaded()` to `feedback.py` (boot phase `unloaded`); call `set_models_loaded(...)` at the 4 lifecycle transitions T1.S1 already drives with `set_phase`; add `phase`/`models_loaded`/`load_error` to `status_snapshot()`; render `phase` + a loaded marker + a conditional load-error line in ctl `status`.

### Success Criteria

- [ ] `Feedback._state` has `"models_loaded": False` and `"phase": "unloaded"` defaults.
- [ ] `Feedback.set_models_loaded(bool)` exists, writes `_state["models_loaded"]`, calls `_write()`, never notifies.
- [ ] daemon construction (line ~463) calls `set_models_loaded(recorder is not None)` alongside the existing `set_phase`.
- [ ] `_load_recorder()` calls `set_models_loaded(False)` at load-start, `set_models_loaded(True)` at success, `set_models_loaded(False)` at failure (each alongside the existing `set_phase`).
- [ ] `status_snapshot()` returns `phase`, `models_loaded`, `load_error` (13 keys total).
- [ ] ctl `format_result("status", ...)` renders a `phase:` line, a `(loaded)`/`(not loaded)` marker, and a conditional `load error:` line.
- [ ] The 5 test edits (incl. `_FakeFeedback.set_models_loaded` stub — Edit T5) + 1 new test pass; all other tests pass unchanged.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed (baseline 292 → 293 with the new test).

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement it from this PRP + the research note. The decisive fact — **T1.S1 already landed the 4 `set_phase` transitions** (so this task only ADDS `set_models_loaded` alongside, never duplicates set_phase) — is documented with exact line numbers (research §1). The **full breaking-test set** (4 tests, not just the item's 1) is enumerated (research §4). Every edit is byte-exact oldText→newText against the current files (incl. the `→`/`—` Unicode). The rendering design + the substring-test safety argument (why adding a `phase:` line doesn't break test_voicectl) is in research §6/§4. Baseline (292 passed) verified live.

### Documentation & References

```yaml
# MUST READ — the T1.S1-already-landed fact, exact edit sites, the 5 breaking tests (incl. the _FakeFeedback stub), rendering design
- docfile: plan/003_27d1f88f5a9f/P1M2T2S1/research/expose_phase_models_loaded.md
  why: "§1 DECISIVE: T1.S1 already shipped the 4 set_phase transitions (table w/ line numbers) + daemon
        _models_loaded/_load_error attrs; THIS task is a clean delta (add set_models_loaded alongside,
        NOT re-add set_phase). §2 T1.S2 is disjoint (hint/_arm_response, not format_result/status_snapshot).
        §3 exact edit sites. §4 the FULL breaking-test set (4 tests). §5 why change boot default idle->unloaded.
        §6 rendering design. §8 scope."
  section: "ALL load-bearing. §1 (boundary), §4 (breaking tests) are the core."

# MUST READ — the contract for what exists (T1.S1, Complete) — CONSUME, don't duplicate
- docfile: plan/003_27d1f88f5a9f/P1M2T1S1/PRP.md
  why: "T1.S1 added _load_recorder() (480-560), the 4 set_phase transitions (463/506/542/549), and the daemon
        attrs _models_loaded/_loading/_load_error/_load_cond. Its research §5 explicitly: 'do NOT edit
        feedback.py (T2 owns models_loaded)'. So _load_recorder's logic is DONE — only ADD set_models_loaded
        next to its set_phase calls."
  critical: "Do NOT edit _load_recorder's build/lock/Condition logic. Do NOT re-add set_phase. Only insert
             set_models_loaded(...) on the line after each existing set_phase, + status_snapshot keys."

# MUST READ — the parallel task (T1.S2) contract — DISJOINT regions, no conflict
- docfile: plan/003_27d1f88f5a9f/P1M2T1S2/PRP.md
  why: "T1.S2 edits ctl.py main()+_send_command_with_loading_hint (NOT format_result) + daemon _dispatch/
        _arm_response (NOT status_snapshot) + test_voicectl stubs. This task edits format_result status
        branch + status_snapshot + _STATUS_ON/test_format_status. Disjoint."
  critical: "Do NOT touch _send_command_with_loading_hint, _LOADING_HINT_DELAY, _arm_response, or _dispatch.
             T1.S2's _arm_response spreads **status_snapshot() — the 3 new keys flow into start/toggle
             responses automatically (no T1.S2 edit needed)."

# THE PRD LIFECYCLE (the contract)
- file: PRD.md
  why: "§4.2bis: 'status reports models_loaded: bool' + 'On load failure ... status reports the error'.
        §4.6: state.json {listening,phase,models_loaded,partial,last_final,ts}; boot phase unloaded/loading,
        models_loaded false. §4.8: status pretty-prints phase + models_loaded."

# THE FILE — feedback.py (the _state default + set_phase pattern to mirror + docstrings)
- file: voice_typing/feedback.py
  why: "_state (line ~99) is the default to change. set_phase (~130) is the PATTERN for set_models_loaded.
        snapshot() (~176) returns dict(self._state) — models_loaded flows through for free once in _state.
        __init__ does NOT _write() (lazy) so the default change is inert until the daemon's set_phase runs."
  critical: "Mirror set_phase EXACTLY for set_models_loaded (set _state key + _write(); NEVER _notify).
             Do NOT add validation for phase values (set_phase accepts any string; 'loading' just works)."

# THE FILE — daemon.py (the 4 set_phase sites + status_snapshot)
- file: voice_typing/daemon.py
  why: "Line 463 (construction set_phase), 506 (loading), 542 (idle/success), 549 (unloaded/failure) — insert
        set_models_loaded after each. status_snapshot() (887-913) already computes snap=self._feedback.snapshot();
        add phase/models_loaded from snap + load_error from self._load_error."
  critical: "Reproduce Unicode (→/—) in oldText EXACTLY. Each set_phase call site is uniquely identifiable by
             its surrounding lines (see edits). Do NOT touch _load_recorder build/lock logic."

# THE FILE — ctl.py (format_result status branch)
- file: voice_typing/ctl.py
  why: "format_result's 'if cmd == status' branch builds the multi-line text. Add phase/models_loaded/load_error
        parses + a phase line + a (loaded) marker + conditional load error. send_command/_send_command_with_
        loading_hint/_LOADING_HINT_DELAY are T1.S2's — UNCHANGED."
  critical: "Keep 'listening:' FIRST (existing substring tests). Use .get(..., default) for every new field so
             an old/minimal response never KeyErrors. The models line keeps the model-name substrings."

# THE TEST FILES — the 5 breaking sites (4 assertions + the _FakeFeedback stub) + fixtures
- file: tests/test_feedback.py
  why: "Line 129 test_state_shape_has_exactly_the_five_fields + line 433 test_snapshot_returns_a_copy_with_the_
        five_state_keys assert the EXACT key set (no models_loaded). Both must add models_loaded."
  critical: "Their oldText differs only by state/snap — each is unique. Do NOT change any OTHER test_feedback test."
- file: tests/test_daemon.py
  why: "Line 966-978 test_status_snapshot_keys_and_cuda_values asserts set(s)==<10 keys>. _make_daemon_with_
        feedback injects _StubRecorder -> phase 'idle', models_loaded True, load_error None after construction."
  critical: "Add phase/models_loaded/load_error to the set; assert phase=='idle', models_loaded is True, load_error==''."
- file: tests/test_voicectl.py
  why: "_STATUS_ON (30) is the canned status (no phase/models_loaded). test_format_status_multiline (61) uses
        SUBSTRING checks (in text) so adding a phase line is safe; augment it + add a not-loaded/load-error test."
  critical: "Existing substring assertions (listening: on, distil-large-v3, small.en, cuda, float16, 12.345) must
             all still hold. ADD phase/models_loaded/load_error to _STATUS_ON + assert them + add the new test."
```

### Current Codebase tree (relevant slice — the 6 files this task edits)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── feedback.py        # EDIT: _state default (+models_loaded, phase idle->unloaded), +set_models_loaded, docstrings.
│   ├── daemon.py          # EDIT: 4 set_models_loaded calls (463/506/542/549) + status_snapshot 3 keys + docstring.
│   └── ctl.py             # EDIT: format_result status branch (+phase line, +(loaded) marker, +load error line).
└── tests/
    ├── test_feedback.py   # EDIT: 2 key-set assertions (129, 433) +models_loaded.
    ├── test_daemon.py     # EDIT: test_status_snapshot_keys_and_cuda_values (971) +3 keys + value asserts.
    └── test_voicectl.py   # EDIT: _STATUS_ON (30) +3 fields; augment test_format_status_multiline (61); +1 new test.
# T1.S1 (_load_recorder/attrs) + T1.S2 (_arm_response/hint) regions UNCHANGED. No config/status.sh/README.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — T1.S1 ALREADY LANDED THE PHASE TRANSITIONS. The 4 set_phase calls (construction 463, load-start
#   506, success 542, failure 549) and the daemon attrs (_models_loaded/_load_error) ALREADY EXIST. THIS task
#   only ADDS set_models_loaded(...) alongside them + the status_snapshot/ctl/feedback exposure. Do NOT re-add,
#   move, or duplicate set_phase. (Research §1; daemon.py:460-462 comment.)

# CRITICAL #2 — DON'T TOUCH T1.S1's _load_recorder LOGIC. The build/lock/Condition/CPU-fallback code is DONE and
#   concurrency-critical. Insert set_models_loaded as a single line AFTER each existing set_phase (under the same
#   lock-held block). Do not reorder or refactor _load_recorder. (Research §1.)

# CRITICAL #3 — DON'T TOUCH T1.S2's REGIONS. ctl.py's _send_command_with_loading_hint/_LOADING_HINT_DELAY/main()
#   routing + daemon's _arm_response/_dispatch are T1.S2's. Edit ONLY format_result's status branch + status_snapshot.
#   T1.S2's _arm_response spreads **status_snapshot() so the 3 new keys auto-flow to start/toggle responses.
#   (Research §2.)

# CRITICAL #4 — FIVE test edits required, not one. The item flagged only test_status_snapshot_keys_and_cuda_values,
#   but FOUR more break: (a) test_feedback.py:129 (state.keys) and :433 (snap.keys) assert exact key sets
#   (add models_loaded); (b) test_daemon.py:971 status_snapshot set (add phase/models_loaded/load_error);
#   AND (c) VERIFIED IN QA: test_daemon.py's _FakeFeedback STUB lacks set_models_loaded, so EVERY _make_daemon
#   construction fails AttributeError at daemon.py:464 (construction calls set_models_loaded). You MUST add a
#   set_models_loaded method to _FakeFeedback (Edit T5) or ~60 daemon tests fail. (Research §4; QA-proven.)

# CRITICAL #5 — test_voicectl status tests use SUBSTRING checks (in text), NOT exact equality. Adding a 'phase:'
#   line + '(loaded)' marker keeps every existing substring true (listening: on, distil-large-v3, small.en, cuda,
#   float16, 12.345). BUT the models line changes 'models: A + B' -> 'models: A + B (loaded)' — verify no test
#   asserts the bare 'models: ...' line exactly (none do — all substring on the model names). (Research §4/§6.)

# CRITICAL #6 — REPRODUCE UNICODE IN oldText. daemon.py + feedback.py comments use → and — (em dash). The edit tool
#   matches EXACT bytes; copy verbatim oldText from the Implementation Blueprint.

# CRITICAL #7 — set_models_loaded MIRRORS set_phase (set _state key + _write(); NEVER _notify — model-lifecycle is
#   not a start/final/stop event, same anti-spam rule). No phase-value validation (set_phase accepts any string;
#   'loading'/'unloaded' just work). (Research §3.1.)

# CRITICAL #8 — FULL TOOL PATHS (zsh aliases). .venv/bin/python -m pytest ... (never bare python/pytest). Optional
#   ruff at /home/dustin/.local/bin/ruff (NOT in .venv). mypy NOT installed — do NOT run it. (Research §7.)
```

## Implementation Blueprint

### Data models and structure

The only new state is one field in `Feedback._state`: `"models_loaded": bool` (default False), surfaced through `snapshot()` (already returns `dict(self._state)`). Plus a new method `set_models_loaded(bool)`. `status_snapshot()` gains 3 keys (`phase`, `models_loaded`, `load_error`). No new classes, no daemon attrs (T1.S1 added `_load_error`/`_models_loaded` already).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/feedback.py — _state default + set_models_loaded + docstrings (Edits F1-F4)
  - F1: _state dict — phase 'idle'->'unloaded', +models_loaded: False (+ comment).
  - F2: NEW set_models_loaded(bool) method between set_phase and record_final (+ augment set_phase docstring).
  - F3: [Mode A] module-top STATE FILE example — +models_loaded.
  - F4: [Mode A] snapshot() docstring key list — +models_loaded.
  - EXACT oldText→newText: see Edits F1-F4 below.

Task 2: EDIT voice_typing/daemon.py — 4 set_models_loaded calls (Edits D1-D4)
  - D1 (line 463 construction): +set_models_loaded(recorder is not None) after set_phase.
  - D2 (line 506 load-start): +set_models_loaded(False) after set_phase('loading').
  - D3 (line 542 success): +set_models_loaded(True) after set_phase('idle').
  - D4 (line 549 failure): +set_models_loaded(False) after set_phase('unloaded').
  - EXACT oldText→newText: see Edits D1-D4 below. Do NOT touch _load_recorder logic.

Task 3: EDIT voice_typing/daemon.py — status_snapshot 3 keys + docstring (Edit D5)
  - D5: add phase/models_loaded/load_error to the returned dict (+ the docstring Returns line).
  - EXACT oldText→newText: see Edit D5 below.

Task 4: EDIT voice_typing/ctl.py — format_result status branch (Edit C1)
  - C1: +phase/models_loaded/load_error parses; +phase: line; +(loaded)/(not loaded) marker; conditional load error.
  - Keep listening: first; .get(...) for every new field. EXACT oldText→newText: see Edit C1 below.

Task 5: EDIT the 5 test sites + 1 new test (Edits T1-T5)
  - T1 (test_feedback.py:129): state.keys +models_loaded.
  - T2 (test_feedback.py:433): snap.keys +models_loaded.
  - T3 (test_daemon.py:971): set(s) +phase/models_loaded/load_error + value asserts.
  - T4 (test_voicectl.py): _STATUS_ON +3 fields; augment test_format_status_multiline; +test_format_status_shows_
    unloaded_state_and_load_error.
  - T5 (test_daemon.py _FakeFeedback stub): +models_loaded recording list + set_models_loaded method. REQUIRED —
    without it every _make_daemon construction fails (daemon.py:464 calls set_models_loaded; _DaemonFakeFeedback
    inherits _FakeFeedback which lacks it). QA-proven (60+ failures without it).
  - EXACT oldText→newText: see Edits T1-T5 below.
```

### Edits — verbatim oldText → newText

#### Edit F1 — `feedback.py` `_state` default

`oldText`:
```
        # In-memory state mirrors the on-disk JSON shape EXACTLY (PRD §4.6 / item contract).
        self._state: dict[str, object] = {
            "listening": False,
            "phase": "idle",
            "partial": "",
            "last_final": "",
            "ts": 0.0,
        }
```
`newText`:
```
        # In-memory state mirrors the on-disk JSON shape EXACTLY (PRD §4.6 / item contract).
        # Boot state (P1.M2.T2.S1 / §4.2bis): phase 'unloaded' + models_loaded False — models are NOT resident
        # until the first arm's _load_recorder() succeeds. The daemon overrides both at construction + each
        # lifecycle transition (set_phase + set_models_loaded); these are just the safe pre-daemon defaults.
        self._state: dict[str, object] = {
            "listening": False,
            "phase": "unloaded",      # P1.M2.T2.S1: boot phase (models not yet loaded, §4.2bis)
            "models_loaded": False,   # P1.M2.T2.S1: True once _load_recorder succeeds (driven by the daemon)
            "partial": "",
            "last_final": "",
            "ts": 0.0,
        }
```

#### Edit F2 — `feedback.py` NEW `set_models_loaded` (between `set_phase` and `record_final`)

`oldText`:
```
    def set_phase(self, phase: str) -> None:
        """Record a VAD/recording phase (idle/listening/speaking); always write; never notify.

        Phase flips are NOT start/final/stop events, so they never fire hyprctl (the
        anti-spam rule — see module docstring).
        """
        self._state["phase"] = phase
        self._write()

    def record_final(self, text: str) -> None:
```
`newText`:
```
    def set_phase(self, phase: str) -> None:
        """Record a VAD/recording phase (idle/listening/speaking); always write; never notify.

        Phase flips are NOT start/final/stop events, so they never fire hyprctl (the
        anti-spam rule — see module docstring). The lazy-load lifecycle (§4.2bis) also uses
        'unloaded' (boot / failed load) and 'loading' (first arm in progress); the daemon's
        _load_recorder() drives those. This method accepts any string (no validation).
        """
        self._state["phase"] = phase
        self._write()

    def set_models_loaded(self, loaded: bool) -> None:
        """Record whether the ASR models are resident on the GPU (PRD §4.2bis / §4.6).

        Driven by the daemon's _load_recorder() at each lifecycle transition (->False while
        loading / on failure; ->True on success) and at construction. Always writes —
        model-lifecycle transitions are infrequent, so the state file stays current for
        voicectl status + status.sh. Never notifies (not a start/final/stop event — same
        anti-spam rule as set_phase).
        """
        self._state["models_loaded"] = bool(loaded)
        self._write()

    def record_final(self, text: str) -> None:
```

#### Edit F3 — `feedback.py` module-top STATE FILE example ([Mode A])

`oldText`:
```
$XDG_RUNTIME_DIR/voice-typing/state.json (overridable via feedback.state_file):
    {"listening": true, "phase": "speaking", "partial": "...", "last_final": "...", "ts": 1783718400.123}
Consumed by voice_typing/status.sh (the tmux status-right helper) and by voicectl status.
```
`newText`:
```
$XDG_RUNTIME_DIR/voice-typing/state.json (overridable via feedback.state_file):
    {"listening": true, "phase": "speaking", "models_loaded": true, "partial": "...", "last_final": "...", "ts": 1783718400.123}
While models are not yet loaded (boot) or mid-load, phase is 'unloaded' or 'loading' and
models_loaded is false (§4.2bis); once loaded, phase cycles idle/listening/speaking.
Consumed by voice_typing/status.sh (the tmux status-right helper) and by voicectl status.
```

#### Edit F4 — `feedback.py` `snapshot()` docstring key list ([Mode A])

`oldText`:
```
        """A shallow copy of the live in-memory state {listening,phase,partial,last_final,ts}.
```
`newText`:
```
        """A shallow copy of the live in-memory state {listening,phase,models_loaded,partial,last_final,ts}.
```

#### Edit D1 — `daemon.py` construction (line 463)

`oldText`:
```
        self._feedback.set_phase("idle" if recorder is not None else "unloaded")
```
`newText`:
```
        self._feedback.set_phase("idle" if recorder is not None else "unloaded")
        self._feedback.set_models_loaded(recorder is not None)  # P1.M2.T2.S1: mirror phase at boot
```

#### Edit D2 — `daemon.py` `_load_recorder` load-start (line ~506)

`oldText`:
```
            self._loading = True                   # we are the loader
            self._load_error = None
            self._feedback.set_phase("loading")
```
`newText`:
```
            self._loading = True                   # we are the loader
            self._load_error = None
            self._feedback.set_phase("loading")
            self._feedback.set_models_loaded(False)  # P1.M2.T2.S1: models not resident while loading
```

#### Edit D3 — `daemon.py` `_load_recorder` success (line ~542)

`oldText`:
```
                self._feedback.set_phase("idle")
                self._load_cond.notify_all()
                success = True
```
`newText`:
```
                self._feedback.set_phase("idle")
                self._feedback.set_models_loaded(True)  # P1.M2.T2.S1: models now resident
                self._load_cond.notify_all()
                success = True
```

#### Edit D4 — `daemon.py` `_load_recorder` failure (line ~549)

`oldText`:
```
                self._feedback.set_phase("unloaded")
                self._load_cond.notify_all()
                success = False
```
`newText`:
```
                self._feedback.set_phase("unloaded")
                self._feedback.set_models_loaded(False)  # P1.M2.T2.S1: models not resident
                self._load_cond.notify_all()
                success = False
```

#### Edit D5 — `daemon.py` `status_snapshot()` (3 keys + docstring)

`oldText`:
```
        Returns {listening, partial, last_final, uptime_s, device, compute_type, final_model,
        realtime_model, mic_ok, mic_error}. mic_ok/mic_error come from S1's PyAudio probe
```
`newText`:
```
        Returns {listening, phase, models_loaded, load_error, partial, last_final, uptime_s, device,
        compute_type, final_model, realtime_model, mic_ok, mic_error}. phase/models_loaded come from
        the LIVE in-memory Feedback state (the lazy-load lifecycle, §4.2bis — unloaded/loading/idle/
        listening/speaking + models resident bool); load_error is the daemon attr _load_recorder sets
        on failure. mic_ok/mic_error come from S1's PyAudio probe
```

`oldText` (the return dict):
```
        return {
            "listening": self.is_listening(),
            "partial": snap.get("partial", ""),
            "last_final": snap.get("last_final", ""),
            "uptime_s": round(self.uptime_s, 3),
            "device": dev.get("device", "unknown"),
            "compute_type": dev.get("compute_type", "unknown"),
            "final_model": dev.get("final_model", "unknown"),
            "realtime_model": dev.get("realtime_model", "unknown"),
            "mic_ok": self._mic_ok,            # bugfix Issue 2 / P1.M1.T2.S2: surface mic health (S1 detects)
            "mic_error": self._mic_error or "",  # None -> "" so JSON always carries a string
        }
```
`newText`:
```
        return {
            "listening": self.is_listening(),
            "phase": snap.get("phase", "unloaded"),          # P1.M2.T2.S1: lifecycle phase (§4.2bis)
            "models_loaded": snap.get("models_loaded", False),  # P1.M2.T2.S1: models resident?
            "load_error": self._load_error or "",            # P1.M2.T2.S1: last load failure (None -> "")
            "partial": snap.get("partial", ""),
            "last_final": snap.get("last_final", ""),
            "uptime_s": round(self.uptime_s, 3),
            "device": dev.get("device", "unknown"),
            "compute_type": dev.get("compute_type", "unknown"),
            "final_model": dev.get("final_model", "unknown"),
            "realtime_model": dev.get("realtime_model", "unknown"),
            "mic_ok": self._mic_ok,            # bugfix Issue 2 / P1.M1.T2.S2: surface mic health (S1 detects)
            "mic_error": self._mic_error or "",  # None -> "" so JSON always carries a string
        }
```

#### Edit C1 — `ctl.py` `format_result` status branch

`oldText`:
```
    if cmd == "status":
        listening = "on" if response.get("listening") else "off"
        partial = response.get("partial", "") or ""
        last_final = response.get("last_final", "") or ""
        uptime = response.get("uptime_s", 0.0)
        device = response.get("device", "unknown")
        compute_type = response.get("compute_type", "unknown")
        final_model = response.get("final_model", "unknown")
        realtime_model = response.get("realtime_model", "unknown")
        mic_ok = response.get("mic_ok", True)             # bugfix Issue 2 / P1.M1.T2.S2: default True
        mic_error = response.get("mic_error", "") or ""   #   so a missing key never looks broken
        if mic_ok:
            mic_line = "mic: ok"
        elif mic_error:
            mic_line = f"mic: unavailable ({mic_error})"
        else:
            mic_line = "mic: unavailable"
        text = (
            f"listening: {listening}\n"
            f"partial: {partial}\n"
            f"last: {last_final}\n"
            f"uptime: {uptime}s\n"
            f"device: {device} ({compute_type})\n"
            f"models: {final_model} + {realtime_model}\n"
            f"{mic_line}"
        )
        return text, 0
```
`newText`:
```
    if cmd == "status":
        listening = "on" if response.get("listening") else "off"
        phase = response.get("phase", "") or ""                       # P1.M2.T2.S1: lifecycle phase (§4.2bis)
        partial = response.get("partial", "") or ""
        last_final = response.get("last_final", "") or ""
        uptime = response.get("uptime_s", 0.0)
        device = response.get("device", "unknown")
        compute_type = response.get("compute_type", "unknown")
        final_model = response.get("final_model", "unknown")
        realtime_model = response.get("realtime_model", "unknown")
        models_loaded = response.get("models_loaded", False)          # P1.M2.T2.S1: models resident?
        load_error = response.get("load_error", "") or ""            # P1.M2.T2.S1: last load failure
        mic_ok = response.get("mic_ok", True)             # bugfix Issue 2 / P1.M1.T2.S2: default True
        mic_error = response.get("mic_error", "") or ""   #   so a missing key never looks broken
        if mic_ok:
            mic_line = "mic: ok"
        elif mic_error:
            mic_line = f"mic: unavailable ({mic_error})"
        else:
            mic_line = "mic: unavailable"
        loaded_marker = "loaded" if models_loaded else "not loaded"   # distinguishes loaded from loading/unloaded
        text = (
            f"listening: {listening}\n"
            f"phase: {phase}\n"
            f"partial: {partial}\n"
            f"last: {last_final}\n"
            f"uptime: {uptime}s\n"
            f"device: {device} ({compute_type})\n"
            f"models: {final_model} + {realtime_model} ({loaded_marker})\n"
            f"{mic_line}"
        )
        if load_error:                                     # surface §4.2bis load failures (absent on the happy path)
            text += f"\nload error: {load_error}"
        return text, 0
```

#### Edit T5 — `tests/test_daemon.py` `_FakeFeedback` stub (REQUIRED — QA-proven)

The daemon calls `self._feedback.set_models_loaded(...)` at construction (Edit D1). `_make_daemon` constructs with `_DaemonFakeFeedback`, which inherits from `_FakeFeedback` (and calls `super().__init__()`). `_FakeFeedback` has `set_phase` but NOT `set_models_loaded` → **every `_make_daemon`-based test fails AttributeError** without this edit. Add the method + a recording list (mirroring `phases`).

`oldText`:
```
    def __init__(self) -> None:
        self.partials: list[str] = []
        self.phases: list[str] = []

    def update_partial(self, text: str) -> None:
        self.partials.append(text)

    def set_phase(self, phase: str) -> None:
        self.phases.append(phase)
```
`newText`:
```
    def __init__(self) -> None:
        self.partials: list[str] = []
        self.phases: list[str] = []
        self.models_loaded: list[bool] = []   # P1.M2.T2.S1: records set_models_loaded calls

    def update_partial(self, text: str) -> None:
        self.partials.append(text)

    def set_phase(self, phase: str) -> None:
        self.phases.append(phase)

    def set_models_loaded(self, loaded: bool) -> None:   # P1.M2.T2.S1: mirror the real Feedback method
        self.models_loaded.append(loaded)
```

#### Edit T1 — `tests/test_feedback.py:129` (state keys)

`oldText`:
```
    assert set(state.keys()) == {"listening", "phase", "partial", "last_final", "ts"}
```
`newText`:
```
    assert set(state.keys()) == {"listening", "phase", "models_loaded", "partial", "last_final", "ts"}
```

#### Edit T2 — `tests/test_feedback.py:433` (snapshot keys)

`oldText`:
```
    assert set(snap.keys()) == {"listening", "phase", "partial", "last_final", "ts"}
```
`newText`:
```
    assert set(snap.keys()) == {"listening", "phase", "models_loaded", "partial", "last_final", "ts"}
```

#### Edit T3 — `tests/test_daemon.py:971` (status_snapshot keys + values)

`oldText`:
```
    assert set(s) == {"listening", "partial", "last_final", "uptime_s",
                      "device", "compute_type", "final_model", "realtime_model",
                      "mic_ok", "mic_error"}                      # bugfix Issue 2 / P1.M1.T2.S2
    assert s["listening"] is False and s["partial"] == "world" and s["last_final"] == "world"   # record_final writes the final into partial so the status matches the screen
```
`newText`:
```
    assert set(s) == {"listening", "phase", "models_loaded", "load_error", "partial", "last_final",
                      "uptime_s", "device", "compute_type", "final_model", "realtime_model",
                      "mic_ok", "mic_error"}                     # P1.M2.T2.S1: +phase/models_loaded/load_error
    assert s["listening"] is False and s["partial"] == "world" and s["last_final"] == "world"   # record_final writes the final into partial so the status matches the screen
    assert s["phase"] == "idle" and s["models_loaded"] is True and s["load_error"] == ""  # P1.M2.T2.S1: injected recorder -> loaded
```

#### Edit T4a — `tests/test_voicectl.py` `_STATUS_ON` (add 3 fields)

`oldText`:
```
_STATUS_ON = {
    "ok": True, "listening": True, "partial": "hello wor", "last_final": "previous sentence.",
    "uptime_s": 12.345, "device": "cuda", "compute_type": "float16",
    "final_model": "distil-large-v3", "realtime_model": "small.en",
    "mic_ok": True, "mic_error": "",                       # bugfix Issue 2 / P1.M1.T2.S2
}
```
`newText`:
```
_STATUS_ON = {
    "ok": True, "listening": True, "phase": "listening", "models_loaded": True, "load_error": "",
    "partial": "hello wor", "last_final": "previous sentence.",
    "uptime_s": 12.345, "device": "cuda", "compute_type": "float16",
    "final_model": "distil-large-v3", "realtime_model": "small.en",
    "mic_ok": True, "mic_error": "",                       # bugfix Issue 2 / P1.M1.T2.S2
}
```

#### Edit T4b — `tests/test_voicectl.py` augment `test_format_status_multiline_has_partial_and_models` + NEW test

`oldText`:
```
def test_format_status_multiline_has_partial_and_models():
    text, code = ctl.format_result("status", _STATUS_ON)
    assert code == 0
    assert "listening: on" in text
    assert "hello wor" in text                      # partial
    assert "distil-large-v3" in text and "small.en" in text   # models loaded
    assert "cuda" in text and "float16" in text      # device + compute_type
    assert "12.345" in text                          # uptime
```
`newText`:
```
def test_format_status_multiline_has_partial_and_models():
    text, code = ctl.format_result("status", _STATUS_ON)
    assert code == 0
    assert "listening: on" in text
    assert "phase: listening" in text                # P1.M2.T2.S1: lifecycle phase rendered
    assert "hello wor" in text                      # partial
    assert "distil-large-v3" in text and "small.en" in text   # models loaded
    assert "(loaded)" in text                        # P1.M2.T2.S1: models_loaded marker
    assert "cuda" in text and "float16" in text      # device + compute_type
    assert "12.345" in text                          # uptime


def test_format_status_shows_unloaded_state_and_load_error():
    # P1.M2.T2.S1: an unloaded daemon (failed/never-loaded) renders phase + (not loaded) + the load error.
    resp = {**_STATUS_ON, "phase": "unloaded", "models_loaded": False,
            "load_error": "CUDA load failed: RuntimeError('no cudnn')"}
    text, code = ctl.format_result("status", resp)
    assert code == 0
    assert "phase: unloaded" in text
    assert "(not loaded)" in text
    assert "load error: CUDA load failed" in text
    assert "(loaded)" not in text                    # marker flips, not appended
```

> **Why these edits:** F1-F4 add the feedback field + method + docs. D1-D4 add `set_models_loaded` alongside T1.S1's existing `set_phase` (the clean delta — never duplicating phase logic). D5 + C1 expose the 3 fields through status_snapshot + ctl. T1-T5 fix the 5 breaking sites (4 key-set assertions + the _FakeFeedback stub) + add coverage for the unloaded/load-error path. The design keeps every existing substring assertion true (test_voicectl uses `in text`, not exact equality).

### Implementation Patterns & Key Details

```python
# (1) set_models_loaded MIRRORS set_phase (Critical #7):
def set_models_loaded(self, loaded: bool) -> None:
    self._state["models_loaded"] = bool(loaded)
    self._write()           # always write (lifecycle transitions are infrequent); NEVER _notify

# (2) The 4 daemon calls sit ALONGSIDE T1.S1's existing set_phase (Critical #1/2):
self._feedback.set_phase("loading")
self._feedback.set_models_loaded(False)   # <- NEW line, same lock-held block

# (3) status_snapshot reads fields already in _state (snap = self._feedback.snapshot()):
"phase": snap.get("phase", "unloaded"),
"models_loaded": snap.get("models_loaded", False),
"load_error": self._load_error or "",     # daemon attr T1.S1 added

# (4) ctl rendering: listening stays first; (loaded)/(not loaded) marker; conditional load error.
#     Every new field uses .get(..., default) so an old/minimal response never KeyErrors.
```

### Integration Points

```yaml
STATE (Feedback._state):
  - add field: "models_loaded": bool (default False)
  - change default: "phase": "idle" -> "unloaded"
  - add method: set_models_loaded(bool)  # mirrors set_phase; writes; never notifies
STATUS (status_snapshot):
  - add keys: phase, models_loaded, load_error  (13 total)
  - source: phase/models_loaded from feedback.snapshot(); load_error from self._load_error
CTL (format_result status):
  - add lines: "phase: {phase}", "(loaded|not loaded)" marker, conditional "load error: {load_error}"
CONSUMERS (unchanged, auto-benefit):
  - status.sh: "reads state.json via jq — models_loaded/phase now present, no status.sh edit (item OUTPUT #4)"
  - T1.S2 _arm_response: "**status_snapshot() spread auto-carries the 3 new keys to start/toggle responses"
```

## Validation Loop

### Level 1: Syntax & Style

```bash
cd /home/dustin/projects/voice-typing
# Structural sanity:
grep -n "set_models_loaded\|models_loaded" voice_typing/feedback.py   # _state default + the method
grep -n "set_models_loaded" voice_typing/daemon.py                    # 4 calls (463/506/542/549)
grep -n "phase\|models_loaded\|load_error" voice_typing/ctl.py        # format_result status branch
# OPTIONAL ruff (uv tool, NOT in .venv); mypy NOT installed (skip):
/home/dustin/.local/bin/ruff check voice_typing/feedback.py voice_typing/daemon.py voice_typing/ctl.py tests/ || true
```

### Level 2: Unit Tests (THE gate)

```bash
cd /home/dustin/projects/voice-typing
# The directly-affected tests:
.venv/bin/python -m pytest tests/test_feedback.py tests/test_daemon.py tests/test_voicectl.py -v \
  -k "state_shape or snapshot_returns or status_snapshot_keys or format_status or unloaded_state"
# Whole fast suite (no regression — baseline 292):
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed.
```

### Level 3: Integration (wiring correctness)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
from voice_typing.feedback import Feedback
from voice_typing.config import FeedbackConfig
import tempfile, os, json
d = tempfile.mkdtemp()
fb = Feedback(FeedbackConfig(state_file=os.path.join(d,"state.json")))
assert fb._state["phase"] == "unloaded" and fb._state["models_loaded"] is False  # boot defaults
fb.set_models_loaded(True); fb.update_partial("x")  # force a write
st = json.load(open(os.path.join(d,"state.json")))
assert st["models_loaded"] is True and "models_loaded" in st
# ctl rendering (not-loaded + load_error path):
from voice_typing import ctl
text, _ = ctl.format_result("status", {"ok":True,"listening":False,"phase":"unloaded",
    "models_loaded":False,"load_error":"CUDA load failed: X","device":"cuda","compute_type":"float16",
    "final_model":"distil-large-v3","realtime_model":"small.en","mic_ok":True,"mic_error":"",
    "partial":"","last_final":"","uptime_s":0.0})
assert "phase: unloaded" in text and "(not loaded)" in text and "load error: CUDA load failed: X" in text
print("OK: feedback defaults + set_models_loaded + ctl rendering wired correctly")
PY
# Expected: prints "OK: ..."; exit 0.
```

### Level 4: Creative & Domain-Specific

```bash
# No live-daemon/GPU path. The end-to-end "voicectl status shows phase/models_loaded" guarantee is proven by
# Level 2's test_format_status_* + Level 3's wiring probe. A live smoke (optional, GPU-gated):
#   systemctl --user restart voice-typing; .venv/bin/voicectl status   # expect 'phase: unloaded' + '(not loaded)'
# is out of scope for the automated gate (covered by P1.M3.T2/T6).
```

## Final Validation Checklist

### Technical Validation
- [ ] `grep set_models_loaded voice_typing/daemon.py` → 4 calls; `grep models_loaded voice_typing/feedback.py` → default + method.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] (Optional) `/home/dustin/.local/bin/ruff check …` → clean.

### Feature Validation
- [ ] `Feedback._state` has `models_loaded` (False) + `phase` `unloaded` defaults; `set_models_loaded` writes + never notifies.
- [ ] 4 daemon `set_models_loaded` calls alongside the existing `set_phase` transitions.
- [ ] `status_snapshot()` returns `phase`/`models_loaded`/`load_error` (13 keys).
- [ ] ctl `status` renders `phase:` + `(loaded)`/`(not loaded)` + conditional `load error:`.
- [ ] `test_format_status_shows_unloaded_state_and_load_error` passes.

### Code Quality Validation
- [ ] No duplication of T1.S1's `set_phase` transitions (only `set_models_loaded` added alongside).
- [ ] No edits to `_load_recorder` logic, `_arm_response`/`_dispatch`, loading-hint helper, config, status.sh, README.
- [ ] Only the 6 cited files modified (`git status --short`).

### Documentation & Deployment
- [ ] [Mode A] feedback.py module-top STATE FILE example + `snapshot()` docstring + `_state` comment updated.
- [ ] `set_phase` docstring notes the `unloaded`/`loading` lifecycle phases.

---

## Anti-Patterns to Avoid

- ❌ Don't re-add/move/duplicate T1.S1's `set_phase` transitions — they're already landed (Critical #1). Only ADD `set_models_loaded` alongside.
- ❌ Don't touch `_load_recorder`'s build/lock/Condition/CPU-fallback logic (Critical #2) or T1.S2's `_arm_response`/`_dispatch`/loading-hint (Critical #3).
- ❌ Don't forget the **5** test edits (the item flagged 1; QA found 5 — Critical #4): test_feedback:129, test_feedback:433, test_daemon:971, test_voicectl _STATUS_ON, AND the `_FakeFeedback.set_models_loaded` stub (Edit T5 — without it ~60 daemon tests fail AttributeError at construction).
- ❌ Don't change test_voicectl's existing substring assertions to exact equality — they're `in text` by design (Critical #5); just keep the model-name substrings present.
- ❌ Don't make `set_models_loaded` notify — model-lifecycle is not a start/final/stop event (Critical #7).
- ❌ Don't add phase-value validation — `set_phase` accepts any string; `loading`/`unloaded` just work (Critical #7).
- ❌ Don't drop the `.get(..., default)` on new ctl/status_snapshot fields — an old/minimal response must never KeyError.
- ❌ Don't mangle the `→`/`—` Unicode in oldText — exact-byte match required (Critical #6).
- ❌ Don't run `mypy` — not installed; pytest is the gate (Critical #8).
