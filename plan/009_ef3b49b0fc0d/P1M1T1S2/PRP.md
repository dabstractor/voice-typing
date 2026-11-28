# PRP — P1.M1.T1.S2: Disconnect daemon bulk routing and activation

## Goal

**Feature Goal**: Finish retiring the Rev-4 bulk-text experiment at the **daemon** layer. S1 made `output.delivery="bulk-text"` unconstructible at config load; S2 removes the now-dead bulk machinery from `VoiceTypingDaemon` — construction (`bulk_target_factory`, `_BulkTargetBundle`, `_build_default_bulk_target`), arm/disarm activation (`vt-bulk-arm`/`vt-bulk-stop`), final/partial routing intercepts, cancel intercept, context-prompt bulk source, shutdown stopper, and the status/guards prose — leaving a **generic-only daemon entry path**: stream partials/finals (`_cmd_streaming` → `_session_streaming` → `_streaming_now`) AND explicit block accepted-final-only, generic stop/cancel/SessionRecovery/explicit copy, recorder identity relay, and the ducking/lifecycle seams, all byte-identical. Bulk-only tests are **quarantined as lab references** (never reintroduced as shipped routing); a migration assertion proves the daemon has no bulk surface.

**Deliverable**: (1) `voice_typing/daemon.py` — the detach (inventory §2, sites A–S) + Mode A docstring rewrite; (2) test quarantine: the three bulk-only suites + the G5 lab test file moved out of default collection (or deleted if duplicated in `tools/`), `tests/test_session_recovery.py`'s bulk Layer-B block removed, `tests/test_daemon.py`'s bulk helpers/arm-worker tests removed; (3) `tests/test_daemon.py` gains `test_daemon_has_no_bulk_surface`. Nothing else: `voice_typing/bulk_controller.py`, `voice_typing/ime/*`, `recorder_host.py`, `feedback.py`, `ctl.py`, config are NOT touched (S3 owns recorder-side wiring).

**Success Definition**: (a) `daemon.py` contains no `_bulk_*` method, no `_BulkTargetBundle`, no `_build_default_bulk_target`, no `bulk_target_factory` parameter, no `BulkController`/`ImeProcess`/`ImeTarget`/`TakeoverWatch` imports, and no `vt-bulk-*` thread names; (b) the generic path is unchanged: `_cmd_streaming`, `_session_streaming`, `_streaming_now`, `_stream`/`_rev1_committed`, `cancel()` with `len(tail)−1`, `SessionRecovery`/`record_final`/`session --copy`, ducking + lifecycle seams, recorder identity — all present, and `tests/test_daemon.py` (minus the removed bulk tests) + `test_session_recovery.py` (minus bulk Layer-B) + `test_control_socket.py` + `test_voicectl.py` + `test_voicectl_session.py` + `test_key_listener.py` + `test_context_prompt_refresh.py` are GREEN; (c) NO bulk test remains in default pytest collection (the 44+4 reds disappear by quarantine, not by deletion of product behavior); (d) the new `test_daemon_has_no_bulk_surface` is green; (e) `voice_typing/` files other than `daemon.py` are untouched; (f) the daemon module docstring states native routing will be a separate surface, not a `delivery` backend.

## User Persona

**Target User**: (1) The maintainer — no dead 154-reference bulk surface masquerading as a product path; (2) downstream subtasks **P1.M1.T1.S3** (recorder-side bulk wiring removal) and **P1.M1.T2.S3 / P1.M1.T4** (native capture/finals), which need a clean generic-only daemon seam to build on.

**Use Case**: `voicectl toggle` → `_arm` → stream/block typing via the existing injector; `voicectl cancel`/`stop`/`session` work as before; nothing named bulk can be constructed, armed, or routed.

**Pain Points Addressed**: dead-but-live bulk code (a maintenance trap: every future daemon change had to reason about a mode that can no longer be configured); 48 permanently-red tests from S1's config retirement; and the ambiguity about whether native editor routing is a "delivery backend" (it is not — PRD §4.5: "native editor sessions do not use this selector").

## Why

- **S1's retirement is only half the story.** `config.py:206` rejects bulk-text; the daemon still carries the full bulk stack (154 references: bundle class, factory, 11 methods, 7 ctor attributes, arm/disarm/final/partial/cancel/shutdown intercepts). With `_bulk_mode()` (`daemon.py:2160`) provably False for every constructible config, all of it is unreachable dead code — and it is the direct cause of the 44+4 red tests S1 handed off.
- **The contract's preservation list is the product.** Generic streaming + block mode, generic cancel with tail compensation, session recovery + explicit copy, recorder identity, ducking and lifecycle seams — these are what P1.M1.T2/T4 build native capture on top of. Detaching bulk must not perturb them.
- **Quarantine, not resurrection.** PRD §4.2sexies is "Legacy bulk text delivery experiment (Rev 4 reference, superseded)"; the lab evidence (controller, IM adapters, G5 harness) stays as reference, but no shipped routing may remain.
- **Architecture note is explicit** (system_context.md §8): "bulk still has construction, `_arm`/`_disarm`, final/partial, prompt, cancel, key/guard, feedback/status and quit paths. Audit all of them when detaching, not just config validation." This PRP audits every one.

## What

Remove the daemon-side bulk machinery (sites A–S in the inventory), rewrite the touched docstrings (Mode A), quarantine the bulk-only test files out of default collection, prune the bulk blocks from `test_daemon.py`/`test_session_recovery.py`, and add the no-bulk-surface migration assertion. No product behavior change for the generic path; no edits outside `daemon.py` + tests.

### Success Criteria

- [ ] `daemon.py`: zero `_bulk` identifiers; zero `BulkController|ImeProcess|ImeTarget|TakeoverWatch` imports; no `bulk_target_factory` ctor param; no `_BulkTargetBundle`/`_build_default_bulk_target`; no `vt-bulk-arm`/`vt-bulk-stop`.
- [ ] `daemon.py` keeps: `_cmd_streaming`, `_session_streaming`, `_streaming_now`, `_stream`, `_rev1_committed`, `cancel()`'s tail compensation, `_refresh_context_prompt`'s stream-edit/rev1 sources, `request_shutdown`'s host teardown, ducking seams, `_clear_context_prompt`.
- [ ] `feedback.set_delivery_mode(cfg.output.delivery)` still called at construction (now always `"stream-edit"`); feedback/ctl status surface untouched.
- [ ] Bulk-only test files (test_bulk_dispatch, test_bulk_context_prompt, test_bulk_stage_remediation, test_g5_timing_lab) NOT collected by default pytest; quarantined with a lab-reference README (or deleted if already duplicated under tools/).
- [ ] `test_session_recovery.py`: bulk Layer-B block + `tbd` import removed; the 29 generic tests green.
- [ ] `test_daemon.py`: `_make_s2_bulk_daemon`, `_S2BulkFeedback`, the arm-worker block, `test_default_bulk_target_factory_stays_pure` removed; `test_status_snapshot_reflects_live_delivery_surface` kept/repointed to `stream-edit`; everything else green.
- [ ] New `test_daemon_has_no_bulk_surface` green.
- [ ] `voice_typing/` diff touches ONLY `daemon.py`.

## All Needed Context

### Context Completeness Check

_Pass._ S1's landed state is verified; all 154 bulk references are mapped to 19 detach sites (A–S) with line numbers; the preservation list is enumerated with its owning symbols; the 48 red tests are reproduced and attributed; the quarantine mechanism and the downstream boundary (S3 = recorder side) are explicit.

### Documentation & References

```yaml
# THE INPUT CONTRACT (S1 — LANDED at 47fda81)
- file: plan/009_ef3b49b0fc0d/P1M1T1S1/PRP.md
  why: S1 rejects bulk-text in OutputConfig.__post_init__ (config.py:206) and REMOVED the top-level
        triple gate (config.py:425-430 note). Its Critical #5 hands test_daemon.py:5758 and the bulk
        suites to S2 as expected fallout.
  critical: "Because no constructible config carries delivery='bulk-text', daemon._bulk_mode() is
            provably False — every bulk branch is dead code. S2 removes it; it does NOT re-admit it."

# THE AUTHORITATIVE SITE MAP
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: §7 (line 7) the per-arm mode flow that MUST survive: _cmd_streaming → ControlServer._dispatch
        → start/toggle → _session_streaming → _streaming_now → _on_partial/on_final. §8 (line 8):
        "bulk still has construction, _arm/_disarm, final/partial, prompt, cancel, key/guard,
        feedback/status and quit paths — audit all of them"; KEEP generation/utterance relay
        stamping, shared executor, session recovery, idle/media/cancel; bulk tests → lab references.
  critical: "recorder_host.augment_kwargs_with_executor's split executor is S3's — do not touch
            recorder_host.py here. d2_bulk_delivery_map.md is evidence, not an adapter to restore."

# THE FILE UNDER EDIT
- file: voice_typing/daemon.py
  why: The detach sites (verified lines): imports :184/:189-191; _BulkTargetBundle :855-936;
        _build_default_bulk_target :937+; ctor kwarg :978; ctor bulk attrs :1256-1278;
        set_delivery_mode call :1287-1289 (KEEP); cfg_to_kwargs bulk branch :517-545; _arm
        :1970-1972 + :2020; _disarm :2076-2080; on_final intercept :1729-1732; _on_partial intercept
        :2139-2140; the 11-method block :2160-2565; _refresh_context_prompt bulk source :2786-2790;
        cancel intercept :2834-2835; request_shutdown stopper :3256-3261; docstrings :88-139,
        :1923-1930, :2741-2760.
  pattern: "Remove each intercept by deleting the `if self._bulk_mode():` branch and letting the
            generic path below it run — the generic code is already written and tested; S2 deletes,
            it does not rewrite."
  gotcha: "Keep the :1287-1289 set_delivery_mode call and the feedback delivery fields — ctl.py
           renders them (always 'stream-edit'/'inactive' now). Keep :1998's shared clear (trim its
           _bulk_cancel comment only)."

# THE TEST-SIDE QUARANTINE
- file: tests/test_bulk_dispatch.py      # 22 tests; bulk_target_factory x2 — QUARANTINE
- file: tests/test_bulk_context_prompt.py # 11 tests — QUARANTINE (S1's prior cfg wrap stays moot)
- file: tests/test_bulk_stage_remediation.py # 14 tests — QUARANTINE (asserts the split executor — S3 territory)
- file: tests/test_g5_timing_lab.py      # 24 tests; build_cfg sets bulk-text — QUARANTINE (G5 lab)
- file: tests/test_session_recovery.py   # :45 `import test_bulk_dispatch as tbd`; Layer-B bulk block :439+ (_make_armed_bulk_daemon) → REMOVE; keep the 29 generic
- file: tests/test_daemon.py             # :5757 _make_s2_bulk_daemon (+ _S2BulkFeedback, _join_vt_threads, _pump_clock if bulk-only), the arm-worker test block, :5794 test_default_bulk_target_factory_stays_pure → REMOVE; :2265 status test → keep/repoint; + NEW test_daemon_has_no_bulk_surface
  pattern: "Quarantine = relocate to tests/lab/ (excluded from collection via pyproject
            [tool.pytest.ini_options] testpaths/norecursedirs — ADD only if not already present;
            prefer a plain move out of tests/ if pytest config would be a new surface) + a
            lab-reference README. Never delete the product modules (bulk_controller.py, ime/)."

# THIS SUBTASK'S RESEARCH NOTE — the full detach inventory
- docfile: plan/009_ef3b49b0fc0d/P1M1T1S2/research/bulk_detach_inventory.md
  why: §1 the live red fallout (44+4) with the intact-generic evidence; §2 the 19-site detach table
       (A–S) + the explicit KEEP list; §3 the test quarantine plan + the new migration assertion;
       §4 the Mode A docstring targets; §5 hazards (feedback fields, S3 boundary, recorder identity);
       §6 downstream.
  section: "§2 (the site table) and §3 (quarantine) are load-bearing — work from them."

# THE SPEC
- docfile: plan/009_ef3b49b0fc0d/prd_snapshot.md
  why: §4.2sexies is "Legacy … superseded"; §4.5 delivery = "existing keyboard-delivery default;
        native editor sessions do not use this selector"; §4.2quater/§4.3 the generic stream +
        block + cancel behavior that is the product.
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py                 # 154 bulk refs; sites A–S (see inventory)  ← EDIT (only voice_typing/ file)
voice_typing/{bulk_controller.py,ime/*,recorder_host.py,feedback.py,ctl.py,session_recovery.py}  ← READ-ONLY (S3 = recorder side)
tests/
├── test_daemon.py                     # 267 tests; bulk helpers :5757+; :5794; :2265     ← EDIT (prune bulk + add pin)
├── test_session_recovery.py           # :45 tbd import; bulk Layer-B :439+ (4 reds)      ← EDIT (remove bulk block)
├── test_bulk_dispatch.py / test_bulk_context_prompt.py / test_bulk_stage_remediation.py / test_g5_timing_lab.py  # 44 reds  ← QUARANTINE (move out of collection)
├── (control_socket / voicectl / voicectl_session / key_listener / context_prompt_refresh — generic, untouched, GATE)
└── lab/ (or equivalent non-collected location)   # ← NEW: quarantined bulk suites + README
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py                 # MODIFY: detach sites A–S; Mode A docstrings
tests/test_daemon.py                   # MODIFY: remove bulk helpers/arm-worker tests/:5794; keep/repoint :2265; +test_daemon_has_no_bulk_surface
tests/test_session_recovery.py         # MODIFY: remove tbd import + bulk Layer-B block
tests/lab/ (or tools/lab-tests/)       # NEW: the 4 bulk-only suites relocated + README (lab reference, not collected)
pyproject.toml                         # ONLY IF needed: [tool.pytest.ini_options] to exclude the quarantine dir (prefer a location pytest already ignores)
# NOTHING ELSE. bulk_controller.py / ime/ / recorder_host.py / feedback.py / ctl.py / config untouched.
```

### Known Gotchas of our Codebase & Library Quirks

```python
# CRITICAL #1 — DELETE, DON'T REWRITE. Each bulk intercept sits ABOVE an already-complete generic
# path (on_final :1729-1732 above the stream/Rev1 commit; _on_partial :2139-2140 above the engine
# call; cancel :2834-2835 above the len(tail)-1 compensation; _refresh_context_prompt :2786-2790
# above the streaming/rev1 sources). Removing the branch restores the generic path untouched.

# CRITICAL #2 — KEEP THE PER-ARM MODE FLOW. _cmd_streaming (:3650) / _session_streaming (:1190) /
# _streaming_now (:2566) are "stream vs block" — the contract's "preserve stream partial/final AND
# explicit block accepted-final-only". They are NOT bulk. Do not touch ControlServer._dispatch.

# CRITICAL #3 — KEEP THE FEEDBACK DELIVERY SURFACE. feedback.set_delivery_mode/set_delivery_state
# (feedback.py:216) + ctl.py:170-199 render `delivery: stream-edit (inactive)`. Keep the ctor call
# :1287-1289 (value is always "stream-edit" now). Removing it would break test_voicectl/test_feedback.

# CRITICAL #4 — DO NOT EDIT voice_typing/ EXCEPT daemon.py. bulk_controller.py + ime/* are the lab
# implementation (kept as reference); recorder_host.augment_kwargs_with_executor's split executor is
# P1.M1.T1.S3's ("Remove bulk-only recorder wiring"). recorder identity relay (session_gen/utterance
# stamping) is PRESERVED by the contract.

# CRITICAL #5 — QUARANTINE MUST ACTUALLY EXIT COLLECTION. `git mv` alone keeps tests/ collected.
# Verify with `pytest --collect-only -q | grep -c bulk` → 0 after. Prefer a dir pytest ignores by
# default (not tests/, not test_*.py naming) — e.g. tools/lab-tests/ or tests/lab/ + a pyproject
# norecursedirs entry. Keep the files importable as lab references (README explains).

# CRITICAL #6 — THE 48 REDS MUST DISAPPEAR BY QUARANTINE/REMOVAL, NOT BY RE-ADMITTING BULK. After
# S2: `pytest tests/ --collect-only -q | grep -i bulk` → only the new no-bulk pin; no bulk-text
# construction anywhere under tests/ in default collection.

# GOTCHA #7 — test_session_recovery.py's `_draft_keys` "bulk (gen, uid)" docstring in
# session_recovery.py:105 is a product comment in a file S2 does NOT own — leave it (harmless).

# GOTCHA #8 — test_daemon.py:2265 test_status_snapshot_reflects_live_delivery_surface: read it.
# If it asserts delivery_mode=="bulk-text"/state transitions it must be REPINNED to the generic
# surface ("stream-edit"/"inactive"); if it only asserts the keys exist, keep as-is.

# GOTCHA #9 — _pump_clock / _join_vt_threads / _S2BulkFeedback in test_daemon.py: grep their usage;
# remove only if bulk-only (likely — they exist for the arm-worker tests). Don't remove helpers
# generic tests use.

# GOTCHA #10 — AGENTS.md: two timeouts on every pytest (inner timeout 300; bash-tool above);
# .venv/bin/python -m pytest; test_daemon.py is CPU-only (~267 tests, fast) — safe; NEVER run
# test_feed_audio/test_recorder_host/test_cuda_check or the daemon.
```

## Implementation Blueprint

### Data models and structure

No schema change. Removed: the ctor kwarg `bulk_target_factory`, 9 `_bulk_*` instance attributes, module class `_BulkTargetBundle`, function `_build_default_bulk_target`, 11 methods, 4 imports. Preserved: everything generic.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PRECHECK — S1 landed + reproduce the fallout.
  - RUN: grep -n 'is retired' voice_typing/config.py (expect :206) ; git log --oneline -1
  - RUN: timeout 300 .venv/bin/python -m pytest tests/test_bulk_dispatch.py tests/test_bulk_context_prompt.py \
           tests/test_bulk_stage_remediation.py tests/test_session_recovery.py -q --tb=no
    EXPECT: 44 failed / 8 passed (3 files) + 4 failed / 29 passed (session_recovery) — the dead-surface fallout.

Task 1: EDIT voice_typing/daemon.py — detach sites A–S (work top-to-bottom; re-grep after each block).
  - A: delete the 4 imports (:184 BulkController, :189 ImeProcess, :190 ImeTarget, :191 TakeoverWatch).
  - B/C: delete class _BulkTargetBundle (:855-936) and def _build_default_bulk_target (:937-~960).
  - D/E: delete the ctor kwarg bulk_target_factory (:978) and the ctor block :1256-1278.
  - F: KEEP :1287-1289 set_delivery_mode (Critical #3).
  - G: rewrite the module docstring bulk prose (:88-139) per Task 4.
  - H: delete cfg_to_kwargs's `if cfg.output.delivery == "bulk-text":` branch (:517-545) + its docstring para.
  - I/J: delete _arm's gen/epoch bump (:1970-1972) + `self._bulk_begin_delivery()` (:2020);
        _disarm's epoch bump + `_bulk_schedule_stop()` (:2076-2080). KEEP :1998's shared clear.
  - K/L: delete on_final's bulk intercept (:1729-1732) and _on_partial's (:2139-2140).
  - M: delete the method block :2160-2565 (_bulk_mode … _bulk_cancel), KEEPING _streaming_now (:2566).
  - N/O: delete _refresh_context_prompt's bulk branch (:2786-2790) and cancel()'s intercept (:2834-2835).
  - Q: delete request_shutdown's bulk stopper block (:3256-3261).
  - R/S: trim the docstrings (:1923-1930, :2741-2760) of bulk mentions.
  - VERIFY: grep -c "_bulk\|BulkController\|ImeProcess\|ImeTarget\|TakeoverWatch\|bulk_target_factory\|vt-bulk" voice_typing/daemon.py → 0;
           .venv/bin/python -c "import voice_typing.daemon" (import purity holds).

Task 2: EDIT tests/test_daemon.py + tests/test_session_recovery.py.
  - test_daemon.py: delete _make_s2_bulk_daemon (:5757) + bulk-only helpers (per Gotcha #9), the
    arm-worker test block (grep "vt-bulk\|_bulk_" to find it), test_default_bulk_target_factory_stays_pure
    (:5794). Read :2265 and keep-or-repin (Gotcha #8). Keep ALL generic tests.
  - ADD (place near the status-surface tests):
        def test_daemon_has_no_bulk_surface():
            """P1.M1.T1.S2: the retired bulk-text path (PRD §4.2sexies) is fully detached from the
            daemon — no routing, no activation, no injection seam; native editor routing is a
            separate future surface, not an output.delivery backend (PRD §4.5)."""
            import inspect
            from voice_typing import daemon
            from voice_typing.config import VoiceTypingConfig
            params = inspect.signature(daemon.VoiceTypingDaemon.__init__).parameters
            assert "bulk_target_factory" not in params
            assert not hasattr(daemon.VoiceTypingDaemon, "_bulk_mode")
            assert not hasattr(daemon, "_build_default_bulk_target")
            with pytest.raises(ValueError, match="retired"):
                VoiceTypingConfig.from_toml({"output": {"delivery": "bulk-text"}})
  - test_session_recovery.py: delete `import test_bulk_dispatch as tbd` (:45), the Layer-B bulk block
    (:439 to its end), and any bulk-only fixtures; keep the 29 generic tests.

Task 3: QUARANTINE the bulk-only suites (Critical #5).
  - git mv tests/test_bulk_dispatch.py tests/test_bulk_context_prompt.py tests/test_bulk_stage_remediation.py \
        tests/test_g5_timing_lab.py  <quarantine-dir>/   (choose tools/lab-tests/ — pytest does not
        collect tools/; confirm no conftest/testpaths pulls it in; otherwise tests/lab/ + pyproject
        [tool.pytest.ini_options] norecursedirs = ["lab"]).
  - ADD <quarantine-dir>/README.md: "Rev-4 bulk-text lab reference (PRD §4.2sexies, superseded).
        Not product acceptance; not collected. Kept for the controller/IM/G5 evidence trail."
  - VERIFY: timeout 120 .venv/bin/python -m pytest tests/ --collect-only -q 2>/dev/null | grep -ci bulk
    → 1 (only the new no-bulk pin) ; the quarantined files still import-lint (py_compile) as references.

Task 4: REWRITE the Mode A docstrings (the contract's DOCS line).
  - Module docstring (daemon.py:88-139): replace the bulk-wiring prose with: "Output is GENERIC
    ONLY: stream partials/finals (output.streaming) or explicit block accepted-final-only via the
    per-arm -stream/-block commands; keyboard injection via output.backend (wtype|ydotool|null).
    output.delivery has ONE value, 'stream-edit' (bulk-text is rejected at config load — P1.M1.T1.S1).
    Native editor routing (PRD §4.8.1) will be a SEPARATE opt-in integration, not a delivery backend."
  - _arm/_disarm/on_final/_on_partial/cancel/status_snapshot/request_shutdown docstrings: remove the
    P1.M6.T2.S1/T3.S1 bulk paragraphs; state the generic behavior. _refresh_context_prompt SOURCE:
    stream-edit `_stream.committed` / block `_rev1_committed` only.

Task 5: VALIDATE (gates below). No git commit unless the orchestrator directs. If asked:
  "P1.M1.T1.S2: disconnect daemon bulk routing/activation; generic-only daemon path; bulk suites quarantined as lab refs".
```

### Implementation Patterns & Key Details

```python
# The detach is subtractive: every bulk hook is an `if self._bulk_mode():` intercept ABOVE a complete
# generic path. Deleting the branch = restoring the generic path. Example (cancel, :2834):
#   BEFORE:  if self._bulk_mode(): return self._bulk_cancel()      # dead since S1
#            with self._lock: ... len(tail)-1 compensation ...       # generic — KEEP
#   AFTER:   with self._lock: ... len(tail)-1 compensation ...       # unchanged
# Same shape at on_final (:1729), _on_partial (:2139), _refresh_context_prompt (:2786), _arm/_disarm/
# request_shutdown (activation blocks only). The 11-method block + bundle class + factory are pure
# deletions. The proof of completeness: grep -c "_bulk|BulkController|ImeProcess|ImeTarget|
# TakeoverWatch|bulk_target_factory|vt-bulk" voice_typing/daemon.py == 0, plus the new pin.
```

### Integration Points

```yaml
DOWNSTREAM (NOT S2):
  - P1.M1.T1.S3 "Remove bulk-only recorder wiring": recorder_host.augment_kwargs_with_executor's
    split realtime executor + the arm_bulk_realtime_executor path. S2 leaves recorder_host.py untouched
    and removes only daemon.py's cfg_to_kwargs dead branch. The quarantined test_bulk_stage_remediation
    asserts that split — S3 may reference it as the lab pin while removing the product wiring.
  - P1.M1.T1.S4 "Align installer and CLI generic usage": consumes S1's migration wording; S2's
    docstring states native routing is separate — S4's usage text mirrors it.
  - P1.M1.T2.S3 / P1.M1.T4 (native capture/finals): build on the generic-only _arm/on_final/_on_partial/
    cancel/request_shutdown seams S2 leaves; SessionRecovery/record_final/explicit copy preserved.
PRESERVED PRODUCT SURFACES: _cmd_streaming/_session_streaming/_streaming_now; StreamingOutput +
  _rev1_committed; cancel tail compensation; context-prompt push (stream/rev1 sources); ducking seams
  (ducker=, _duck_engage/_release); lifecycle (lazy load, idle unload, auto-stop, bounded teardown);
  recorder identity relay; feedback delivery fields (always stream-edit/inactive); ctl status render.
NOT TOUCHED: voice_typing/{bulk_controller.py, ime/*, recorder_host.py, feedback.py, ctl.py,
  session_recovery.py, config.py, typing_backends.py}; config.toml.
```

## Validation Loop

> AGENTS.md two-timeout rule (inner `timeout 300`, bash-tool above). `.venv/bin/python -m pytest`. test_daemon.py is CPU-only and safe; never the CUDA/forbidden suites or the daemon.

### Level 1: The detach is complete (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- zero bulk surface in daemon.py ---"
grep -cE "_bulk|BulkController|ImeProcess|ImeTarget|TakeoverWatch|bulk_target_factory|vt-bulk|_BulkTargetBundle" voice_typing/daemon.py   # EXPECT 0
echo "--- the generic flow survives ---"
for s in "def _cmd_streaming" "def _streaming_now" "_session_streaming" "_rev1_committed" "set_delivery_mode" "def _refresh_context_prompt" "def cancel" "def request_shutdown"; do
  grep -q "$s" voice_typing/daemon.py && echo "  keep: $s" || echo "  L1 FAIL: $s missing"
done
echo "--- import purity holds ---"
.venv/bin/python -c "import voice_typing.daemon; import inspect; p=inspect.signature(__import__('voice_typing.daemon',fromlist=['x']).VoiceTypingDaemon.__init__).parameters; assert 'bulk_target_factory' not in p; print('L1b PASS')"
echo "--- only daemon.py changed under voice_typing/ ---"
git diff --name-only -- voice_typing/ | grep -v "daemon.py" && echo "L1c FAIL" || echo "L1c PASS"
```

### Level 2: Bulk tests exited default collection; the pin is green

```bash
cd /home/dustin/projects/voice-typing
echo "--- bulk in default collection (expect ONLY the new pin) ---"
timeout 120 .venv/bin/python -m pytest tests/ --collect-only -q 2>/dev/null | grep -i bulk
# EXPECT: exactly tests/test_daemon.py::test_daemon_has_no_bulk_surface
echo "--- the pin ---"
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "no_bulk_surface" 2>&1 | tail -2
echo "--- quarantined files still compile (lab references intact) ---"
for f in <quarantine-dir>/test_bulk_dispatch.py <quarantine-dir>/test_g5_timing_lab.py; do .venv/bin/python -c "import py_compile,sys; py_compile.compile('$f', doraise=True)" && echo "  ok: $f"; done
```

### Level 3: The generic path is byte-identical in behavior (the regression gate)

```bash
cd /home/dustin/projects/voice-typing
echo "--- daemon (pruned) + session recovery (pruned) + the generic consumers ---"
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_session_recovery.py -q 2>&1 | tail -3
timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_voicectl.py tests/test_voicectl_session.py tests/test_key_listener.py tests/test_context_prompt_refresh.py tests/test_feedback.py -q 2>&1 | tail -3
echo "--- the streaming/block engine suites (untouched, G1-classified reds unchanged) ---"
timeout 300 .venv/bin/python -m pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q --tb=no 2>&1 | tail -1
# EXPECT: daemon + session_recovery + consumers ALL green (the 4+44 reds are gone via quarantine/
# removal); the 16 legacy lazy-separator reds in the engine suites unchanged (pre-existing, classified).
```

### Level 4: No live activation is possible (behavioral, fakes only)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
# Fake host/keyboard/feedback/media: an ordinary arm→partial→final→cancel→stop cycle never spawns a
# bulk target/thread/subprocess. (Use test_daemon's hermetic helpers.)
import sys; sys.path.insert(0, "tests")
import threading, test_daemon as td
d, fb, rec, be = td._make_daemon()
d.start()
d._on_partial("hello wor"); d.on_final("hello world"); d.cancel(); d.stop()
import time; time.sleep(0.2)
leaked = [t.name for t in threading.enumerate() if "bulk" in t.name.lower()]
assert not leaked, leaked
assert not any(hasattr(d, a) for a in ("_bulk_ctrl", "_bulk_bundle", "_bulk_mode"))
print("L4 PASS: generic cycle ran; no bulk attribute, thread, or target exists")
PY
echo "--- scope ---"
git status --short | grep -vE 'plan/' | grep -vE 'daemon\.py|tests/test_daemon\.py|tests/test_session_recovery\.py|tests/lab/|tools/lab-tests/|pyproject\.toml' | grep -E '\.py$|\.toml$|\.md$' && echo "L4 FAIL: out of scope" || echo "L4 PASS: scope clean"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: zero bulk identifiers/imports/params in `daemon.py`; the generic flow symbols present; import purity holds; only `daemon.py` changed under `voice_typing/`.
- [ ] L2: bulk tests absent from default collection (only the new pin); the pin green; quarantined files compile.
- [ ] L3: `test_daemon.py` + `test_session_recovery.py` + the six generic consumer suites green; engine suites' 16 legacy reds unchanged.
- [ ] L4: an arm→partial→final→cancel→stop cycle spawns no bulk thread/target/attribute; scope clean.

### Feature Validation
- [ ] Stream partial/final + explicit block accepted-final-only preserved (per-arm `-stream`/`-block`).
- [ ] Generic cancel (tail compensation), SessionRecovery/`record_final`/`session --copy`, ducking seams, lifecycle, recorder identity preserved.
- [ ] Feedback delivery surface intact (`stream-edit`/`inactive` rendered by `voicectl status`).
- [ ] Bulk cannot be constructed, injected, armed, or routed by any daemon path.

### Code Quality Validation
- [ ] Subtractive edit: no generic path rewritten; intercepts removed above untouched generic code.
- [ ] Dead docstrings removed; Mode A docstrings describe the generic-only contract + "native routing = separate surface".
- [ ] Quarantine documented (README) and genuinely uncollected.

### Scope Boundary Validation
- [ ] `voice_typing/` diff = `daemon.py` only (bulk_controller.py, ime/, recorder_host.py, feedback.py, ctl.py untouched — S3's recorder-side scope respected).
- [ ] Bulk test files relocated, not re-admitted; product modules not deleted.
- [ ] No config/README/ACCEPTANCE/installer changes (S4 / M2.T4).

### Documentation & Deployment
- [ ] Module + method docstrings updated (Mode A) — native routing stated as separate, not a backend.

---

## Anti-Patterns to Avoid

- ❌ Don't rewrite the generic on_final/_on_partial/cancel/prompt paths — delete the bulk intercept above them and leave the generic code byte-identical (it is the tested product).
- ❌ Don't touch `_cmd_streaming`/`_session_streaming`/`_streaming_now` or ControlServer dispatch — "stream vs block" is the product, not bulk.
- ❌ Don't remove `feedback.set_delivery_mode`/the delivery status fields or `ctl.py`'s rendering — they stay (`stream-edit`/`inactive`).
- ❌ Don't edit `recorder_host.py` (`augment_kwargs_with_executor` split executor is S3's) or delete `bulk_controller.py`/`voice_typing/ime/` (lab reference).
- ❌ Don't re-admit bulk via any seam (a leftover `bulk_target_factory`, a config alias, a "compat" branch) — the point is that no route can activate it; the new pin enforces it.
- ❌ Don't "fix" the 48 reds by re-enabling bulk-text or by skipping — quarantine the lab suites and remove the product-coupled bulk tests; the reds disappear because the surface is gone.
- ❌ Don't leave quarantined tests inside pytest's default collection (`git mv` within `tests/` keeps them collected) — verify with `--collect-only | grep -i bulk`.
- ❌ Don't remove generic helpers in test_daemon.py that non-bulk tests use (`_pump_clock`/`_join_vt_threads` — grep first).
- ❌ Don't run the CUDA/forbidden suites or the live daemon; keep the two-timeout rule.

---

## Confidence Score

**9/10** for one-pass success. The detach is subtractive with every one of the 19 sites enumerated by line number against the live file; the preservation list is explicit with its owning symbols; the red fallout (44+4) is reproduced and attributed to S1's config retirement; the per-arm stream/block flow, the feedback delivery surface, and the S3 recorder-side boundary are all called out as do-not-touch. The −1: the quarantine mechanism depends on the repo's pytest config (a `git mv` to a non-collected dir vs a `norecursedirs` entry — Critical #5 gives both paths and a verification command), and `test_daemon.py:2265`'s exact assertion determines keep-vs-repin (Gotcha #8 instructs reading it).
