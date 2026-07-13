# Research — expose phase + models_loaded (P1.M2.T2.S1)

This note pins the critical boundary fact (T1.S1 already landed the phase
transitions), the exact edit sites, the FULL set of breaking tests, and the
rendering design. The PRP (../PRP.md) references it as the single source of truth.

## 1. ★ CRITICAL BOUNDARY: T1.S1 (Complete) ALREADY landed the phase transitions ★

The item description's part (b) ("call set_phase('unloaded') at construction …
set_phase('loading') on _load_recorder start … set_phase('idle') on success …
set_phase('unloaded') on failure") describes work that **P1.M2.T1.S1 already
shipped**. Verified in the LIVE daemon.py:

| transition | line | current code (T1.S1) |
|---|---|---|
| construction | 463 | `self._feedback.set_phase("idle" if recorder is not None else "unloaded")` |
| load start | 506 | `self._feedback.set_phase("loading")` (after `self._loading=True; self._load_error=None`) |
| load success | 542 | `self._feedback.set_phase("idle")` (after `_models_loaded=True; _load_error=None`) |
| load failure | 549 | `self._feedback.set_phase("unloaded")` (after `_load_error=...; _models_loaded=False`) |

T1.S1 also added the daemon attrs `self._models_loaded`, `self._loading`,
`self._load_error`, `self._load_cond` (daemon.py:452-458) and the whole
`_load_recorder()` method (480-560). Its PRP explicitly **left feedback.py
untouched** ("T2 owns models_loaded") — confirmed by the live comment at
daemon.py:460-462: *"The feedback models_loaded FIELD + status_snapshot/ctl
exposure is P1.M2.T2.S1; T1 tracks the daemon-side self._models_loaded + drives
phase via the existing set_phase — no feedback.py edit."*

**⇒ T2.S1 (THIS task) is a clean DELTA:** add `set_models_loaded()` to feedback.py
+ call it ALONGSIDE the 4 existing `set_phase` calls (do NOT re-add set_phase —
it is already there). Add `models_loaded`/phase/`load_error` to status_snapshot
+ ctl rendering. Do NOT duplicate or move T1.S1's phase logic.

## 2. T1.S2 (parallel, "Implementing") — ALSO already landed; DISJOINT region

T1.S2's loading-hint (`_send_command_with_loading_hint`, `_LOADING_HINT_DELAY`,
`import threading`) is already in ctl.py — but it touches ctl.py's `main()` +
the helper, NOT `format_result()`. T1.S2's daemon edit is `_arm_response()` in
`_dispatch` (start/toggle ok:false), NOT `status_snapshot()`. **⇒ no overlap.**
This task edits `format_result()`'s `status` branch (a region T1.S2 never
touches) + status_snapshot + feedback.py.

## 3. Exact edit sites

### 3.1 `voice_typing/feedback.py`
- **`_state` default** (line ~99): `{"listening": False, "phase": "idle",
  "partial": "", "last_final": "", "ts": 0.0}`. Change `"phase": "idle"` →
  `"phase": "unloaded"`; ADD `"models_loaded": False`.
- **NEW method `set_models_loaded(self, loaded: bool)`**: mirror `set_phase`
  (set `_state["models_loaded"] = bool(loaded)`; `_write()`; never notify).
  Place between `set_phase` and `record_final`.
- **Augment `set_phase` docstring**: note the lifecycle phases 'unloaded'/
  'loading' (accepted as plain strings — no validation).
- **[Mode A] docs**: module-top STATE FILE example (add `"models_loaded": true`);
  the `# In-memory state mirrors…` comment; the `snapshot()` docstring key list.

### 3.2 `voice_typing/daemon.py` — add `set_models_loaded` at the 4 transitions
- line 463 (construction): after the set_phase call → `set_models_loaded(recorder is not None)`.
- line 506 (load start): after `set_phase("loading")` → `set_models_loaded(False)`.
- line 542 (success): after `set_phase("idle")` → `set_models_loaded(True)`.
- line 549 (failure): after `set_phase("unloaded")` → `set_models_loaded(False)`.
- **`status_snapshot()` (887-913)**: ADD 3 keys — `"phase": snap.get("phase","unloaded")`,
  `"models_loaded": snap.get("models_loaded", False)`, `"load_error": self._load_error or ""`.
  (`snap = self._feedback.snapshot()` is already computed; phase/models_loaded now
  live in `_state` so they flow through `snapshot()` for free. `load_error` reads
  the daemon attr T1.S1 added.)

### 3.3 `voice_typing/ctl.py` — `format_result` status branch
- ADD `phase`/`models_loaded`/`load_error` parsing; add a `phase: {phase}` line;
  augment the models line with a `(loaded)`/`(not loaded)` marker; conditionally
  append a `load error: …` line. Keep `listening:` first (existing substring
  tests). The existing f-string block → keep f-string, append load_error conditionally.

### 3.4 tests — the FULL breaking set (4 tests + 1 new)
- `tests/test_feedback.py:129` `test_state_shape_has_exactly_the_five_fields`:
  `set(state.keys())` must add `models_loaded`.
- `tests/test_feedback.py:433` `test_snapshot_returns_a_copy_with_the_five_state_keys`:
  `set(snap.keys())` must add `models_loaded`.
- `tests/test_daemon.py:971` `test_status_snapshot_keys_and_cuda_values`:
  `set(s)` must add `phase`, `models_loaded`, `load_error`; assert
  `phase=="idle"`, `models_loaded is True`, `load_error==""` (injected recorder).
- `tests/test_voicectl.py:30` `_STATUS_ON`: add `phase`/`models_loaded`/`load_error`;
  augment `test_format_status_multiline_has_partial_and_models` (assert `phase:`,
  `(loaded)`); ADD `test_format_status_shows_unloaded_state_and_load_error`.

## 4. What does NOT break (verified)

- **No test asserts the default phase is "idle".** All phase assertions in
  test_feedback.py are AFTER explicit `set_phase("speaking")` etc. (lines 135,
  222, 310). Feedback.__init__ does NOT `_write()` (lazy — test_feedback.py:114
  asserts no state.json until the first update), so the default change is inert
  until the daemon's construction set_phase runs.
- **test_voicectl status tests use SUBSTRING checks** (`"listening: on" in text`,
  `"distil-large-v3" in text`), NOT exact-string equality. Adding a `phase:`
  line + `(loaded)` marker keeps every existing substring true. Verified the
  models line: `"distil-large-v3" in text and "small.en" in text` still holds
  when the line becomes `models: distil-large-v3 + small.en (loaded)`.
- **test_daemon lazy-load tests (1908-2024)** assert `d._models_loaded` (daemon
  attr) + `fb.phases[-1]=="idle"` — unaffected (I don't change phase transitions,
  only add set_models_loaded alongside). `_make_daemon` always injects a recorder
  → `_models_loaded=True` at boot → lazy path dormant for them.
- **T1.S2's `_arm_response`** spreads `**status_snapshot()` → the 3 new keys
  flow into start/toggle responses automatically (no T1.S2 edit needed).

## 5. The boot-phase default: why change `idle`→`unloaded` in feedback.py

T1.S1's construction call already writes the correct phase to state.json
(`set_phase("idle" if recorder else "unloaded")`). So why also change the
`_state` *default*? (a) PRD §4.6: boot phase semantics are `unloaded`/`loading`
with `models_loaded:false` — the default should reflect that, not `idle`. (b)
Defensive correctness: any standalone Feedback use (or a window before the
daemon's set_phase) reports `unloaded` rather than the misleading `idle`. (c) The
item explicitly requires it ("Change the boot 'phase' from 'idle' to 'unloaded'").
It is inert for the daemon path (construction overrides it immediately).

## 6. Rendering design (ctl format_result status branch)

```
listening: on
phase: listening           # NEW (unloaded/loading/idle/listening/speaking)
partial: hello wor
last: previous sentence.
uptime: 12.345s
device: cuda (float16)
models: distil-large-v3 + small.en (loaded)   # augmented with (loaded)/(not loaded)
mic: ok
load error: <...>          # NEW, ONLY when load_error non-empty
```
- `listening:` stays first (minimal diff; existing substring tests pass).
- `(loaded)`/`(not loaded)` marker from `models_loaded` bool.
- `load error:` line is CONDITIONAL (only when `load_error` non-empty) — surfaces
  PRD §4.2bis "status reports the error + the CPU-fallback hint" without cluttering
  the happy path.
- All new fields use `.get(..., default)` so an old/minimal response never breaks.

## 7. Tooling & validation (verified)

- pytest 9.1.1 in `.venv`; baseline fast suite = **292 passed**.
  `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q`.
- ruff 0.14.13 at `/home/dustin/.local/bin/ruff` (NOT in .venv); optional lint.
- mypy NOT installed — do NOT list it as a gate. FULL paths (zsh aliases).

## 8. Scope boundaries (do / don't)

DO: feedback.py (`_state` + `set_models_loaded` + docstrings); daemon.py (4
`set_models_loaded` calls alongside existing `set_phase` + status_snapshot 3 keys
+ docstring); ctl.py (`format_result` status branch); 4 test updates + 1 new test.
DON'T: re-add/move T1.S1's `set_phase` transitions (already landed); touch
`_load_recorder` logic, `_arm_response`/`_dispatch` (T1.S2), the loading-hint
helper (T1.S2), `run()`/`__init__` recorder/lock attrs (T1.S1), config.py/
config.toml (P1.M3 idle-unload knob), status.sh (reads JSON — no change needed),
README/ACCEPTANCE (P1.M3.T3). No `PRD.md`/`tasks.json`/`prd_snapshot.md`/
`.gitignore`/`pyproject.toml`/`uv.lock`. No new deps.
