# PRP — P1.M1.T2.S2: Verify + test mode-switch reload, set_mode, status_snapshot mode, socket dispatch, ctl, status.sh

## Goal

**Feature Goal**: **Verify** the already-landed Lite-mode (PRD §4.2ter) mode-switch plumbing is correct across all 6 layers (daemon `_load_host(mode)`/`_arm`/`status_snapshot`, socket `_dispatch`, `ctl`, `status.sh`, `feedback`), and **fill the 3 genuine coverage gaps** the live recon found. The lite feature is ~90–100% landed and a concurrent reconciliation pass has already landed most of the §5 test matrix — so this subtask is **verify + gap-fill**, NOT write-from-scratch. (Adding redundant tests would duplicate existing coverage and risk conflicts with the parallel `P1.M1.T2.S1` toggle-semantics work.)

**Deliverable** (2 test files edited, no source changes — the implementation is verified correct):
1. `tests/test_daemon.py` — 2 gap tests: (a) mode-switch reload **tears down the outgoing host** (`stop_calls==1`); (b) **idle-unload → `start_lite()`** reloads in lite.
2. `tests/test_control_socket.py` — 1 gap test: the wire **`status` response carries `mode`** (the dispatch-layer gap; `_StubDaemon` omits `mode` today).
3. A **recorded verification** that all 9 implementation sites are correct (the recon already did this; the implementer re-confirms against the live tree) + a **flagged concurrency note** (S1's handed-off dead-host-check concern) for the live/T7 path.

**Success Definition**:
- (a) Re-verification: the 9 sites (recon PART 1) are all CORRECT against the live tree (re-grep; `P1.M1.T2.S1` is editing `daemon.py`, so navigate by symbol).
- (b) The 3 gap tests are added and PASS; they pin behavior the existing suite does NOT (old-host teardown on switch; lite reload after idle-unload; `mode` in the dispatch wire response).
- (c) The full fast suite is green: `.venv/bin/python -m pytest tests/ -q --ignore=tests/test_feed_audio.py` → **0 failures** (the new tests pass + no regression; baseline `277 passed`).
- (d) No redundant tests — do NOT re-add the toggle×mode / status_snapshot-mode / set_mode / status.sh-⚡ tests (they ALREADY EXIST; see Context).
- (e) No source changes (the implementation is verified correct; if a site is found STALE/WRONG on re-verification, STOP and report rather than silently editing — that may be S1's in-flight work).
- (f) The concurrency note is flagged (not silently "fixed") with a recommendation for T7/live coverage.

> **VERIFICATION VERDICT (recon, 2026-07-16): all 9 implementation sites CORRECT.** Full fast suite at recon time: `277 passed in 9.71s`. Lite coverage already exists in all 5 test files. This subtask adds the 3 gaps below + re-confirms.

## User Persona

Not applicable (internal test + verification work; no user-facing surface change — contract §5 "DOCS: none — these verify already-documented behavior").

## Why

- **PRD §4.2ter + delta §5 mandate the test matrix.** The lite feature shipped a second arming mode (small-model-only, `use_main_model_for_realtime=True`), a mode-switch reload (`_load_host(mode)`), `mode` in state/status/ctl/status.sh, and `toggle-lite`/`start-lite` commands. Each must be pinned by tests before the lite release (P1.M2).
- **The moving target landed most coverage; the 3 gaps are the real risk.** Per the recon, the cmd routing, `_mode` boot, start_lite/toggle_lite set-mode, status_snapshot mode, set_mode, and status.sh ⚡/🎤 are ALL already tested. The gaps that remain are exactly the ones that would let a regression slip: (1) a mode switch that respawns but **forgets to tear down** the old host (a VRAM leak + a dangling child) — the existing test counts spawns but never reads the outgoing host's `stop_calls`; (2) a lite reload-after-idle-unload (only normal is covered); (3) the `mode` key vanishing from the wire status response (the dispatch stub omits it, so the contract "response carries mode" is unverified at the dispatch layer).
- **Verify, don't rebuild.** The implementation sites are correct (recon verified each with quotes). Re-adding tests that exist wastes effort and conflicts with `P1.M1.T2.S1` (which is adding the toggle×mode tests in `test_daemon.py` right now). This subtask's value is the 3 gap tests + the recorded verification + the concurrency flag.
- **Scope discipline.** This subtask owns the END-TO-END mode verification + the 3 gap tests. It does NOT touch source (verified correct), does NOT build the T7 feed-audio integration test (P1.M2.T1), does NOT sync README/ACCEPTANCE (P1.M2.T2), and does NOT change toggle/toggle_lite logic (P1.M1.T2.S1).

## What

1. **Re-verify** the 9 sites (recon PART 1) against the live tree — all should still be CORRECT (re-grep by symbol; S1 is shifting daemon.py line numbers).
2. **Add 2 daemon gap tests** (`tests/test_daemon.py`): mode-switch-teardown-stop + idle-unload→start_lite.
3. **Add 1 control-socket gap test** (`tests/test_control_socket.py`): status wire response carries `mode`.
4. **Flag** the concurrency note (S1 Gotcha #5: dead-host check may fire spuriously mid-switch) — record it; recommend T7/live coverage; do NOT add a workaround.
5. **Run the full fast suite** → confirm 0 failures.

### Success Criteria

- [ ] Re-verification: 9 sites CORRECT (recon quotes re-confirmed by grep on the live tree).
- [ ] `test_mode_switch_stops_outgoing_host` (NEW): a normal→lite switch calls the OUTGOING host's `stop()` exactly once (`spawns[0].stop_calls == 1`); the new host is mode `"lite"`; `d._mode == "lite"`.
- [ ] `test_start_lite_after_idle_unload_reloads_in_lite` (NEW): after idle-unload (no resident), `start_lite()` reloads a lite host (mode `"lite"`).
- [ ] `test_dispatch_status_response_carries_mode` (NEW): `{"cmd":"status"}` → response has `"mode"`.
- [ ] The 3 new tests PASS; full fast suite green (0 failures).
- [ ] No redundant tests added (the existing toggle×mode / status_snapshot-mode / set_mode / status.sh tests are NOT re-added).
- [ ] No source files modified (if a site is found wrong on re-verification, STOP + report — likely S1's in-flight edit).
- [ ] Concurrency note flagged in the implementation report (not silently "fixed").

## All Needed Context

### Context Completeness Check

_Pass._ The recon (`research/mode_coverage_recon.md`) verified all 9 implementation sites CORRECT with current line numbers + quotes, enumerated the existing lite coverage per file (so the implementer knows what NOT to re-add), and gave the exact fake/fixture signatures the 3 gap tests need (`_spawning_factory`, `_make_lazy_daemon`, `_FakeHost.stop_calls`, `_StubDaemon`). A developer new to this repo can add the 3 gap tests from this PRP + the recon alone.

### Documentation & References

```yaml
# MUST READ — the authoritative verification + coverage map (this subtask's primary reference)
- docfile: plan/004_607e9cca32b7/P1M1T2S2/research/mode_coverage_recon.md
  why: "PART 1: the 9-site verification table (all CORRECT, with line numbers + key quotes). PART 2: the
        existing-coverage matrix per file (what EXISTS vs the §5 matrix) + the exact fake signatures
        (_FakeHost/.mode/.spawn_calls/.stop_calls/.is_alive-property, _fake_host_factory, _make_lazy_daemon,
        _spawning_factory, _StubDaemon). PART 3: the 3 gaps + the status.sh mechanism nuance."
  critical: "The 3 gaps (PART 3) ARE this subtask's work. The existing coverage (PART 2) is what NOT to
            re-add. Re-verify PART 1 on the live tree (S1 is editing daemon.py — line numbers shift)."

# MUST READ — the lite spec (mode-switch semantics + the test matrix)
- docfile: plan/004_607e9cca32b7/architecture/system_context.md
  why: "§3.1 DONE table = the 9 sites (with line numbers). §5 = the required test matrix. §3.4 'MOVING
        TARGET NOTE' = why coverage may already exist (a concurrent pass landed it) — re-verify the live
        tree. §4 invariants (single-flight _lock; _bounded_shutdown reuses the idle-unload teardown)."
  critical: "§5's daemon row lists 'arming lite while resident-in-normal triggers teardown-then-respawn'
            — the EXISTING test counts the respawn but NOT the teardown; that's gap (1). §5's
            'idle-unload then arm-lite reloads in lite' is gap (2)."

# MUST READ — the parallel sibling + the handed-off concurrency note
- docfile: plan/004_607e9cca32b7/P1M1T2S1/PRP.md
  why: "S1 owns toggle/toggle_lite SEMANTICS + the 6 toggle×mode tests (test_daemon.py:3472-3547, via
        _spawning_factory). S1's Gotcha #5 hands THIS subtask a CONCURRENCY NOTE: the BUG-B fix is the
        first time _load_host is called while _listening is SET (a mode-switch while armed); the run()
        loop's dead-host check (daemon.py ~831) MAY fire spuriously on the killed resident ('recorder-host
        child died unexpectedly') — benign (end state correct) but noisy. 'T2.S2 owns the live/concurrent
        verification.' S1 defined _spawning_factory — REUSE it, don't redefine."
  critical: "No-conflict boundary: S1 = toggle conditions + 6 toggle tests; T2.S2 = the 3 gaps + dispatch
            test. My daemon tests APPEND after S1's section (additive). The concurrency note is a FLAG +
            T7/live recommendation, NOT a deterministic unit test (the run loop isn't exercised by the
            fast suite)."

# THE TEST SEAM (signatures from the recon — reuse, don't redefine)
- file: tests/test_daemon.py
  why: "_FakeHost @510 (ctor takes mode=; has .mode/.spawn_calls/.stop_calls; .is_alive is a PROPERTY;
        stop(timeout) bumps stop_calls). _spawning_factory(spawns) @3472 (appends each built host to
        `spawns`, respects the mode kwarg — NO closure override). _make_lazy_daemon(cfg=None,
        host_factory=None) @2663 -> (d, fb) (lazy boot: _host None, _mode 'normal'). The EXISTING lite
        tests: test_mode_switch_normal_to_lite_reloads @2766 (counts spawns, NOT stop_calls); test_same_
        mode_arm_is_instant_no_reload @2782; test_status_snapshot_reports_mode @2824; test_cold_arm_after_
        idle_unload_refires_loading_toast @2839 (the idle-unload pattern to MIRROR for lite)."
  pattern: "Use _spawning_factory(spawns) so EVERY built host is retained (the gap is that _fake_host_
            factory drops the old instance). Assert spawns[0].stop_calls == 1 on a switch (the outgoing
            host was torn down). For idle-unload→lite, mirror test_cold_arm_after_idle_unload (2839) but
            call start_lite(); trigger _unload_host() the same way that test does."
  gotcha: "_FakeHost.is_alive is a PROPERTY, not a method (don't call it). _spawning_factory is defined by
           S1 at 3472 — REUSE it; do NOT redefine (a redefinition would shadow/conflict). Re-check it
           exists before relying on it (S1 still editing)."

# THE DISPATCH-LAYER SEAM
- file: tests/test_control_socket.py
  why: "_StubDaemon @27 (status_snapshot() OMITS mode); test_dispatch_lite_commands_call_daemon @131
        (cmd routing EXISTS — start-lite/toggle-lite -> the methods); test_dispatch_status_has_all_keys
        @120 (hard-pins exactly 9 keys, NO mode). The dispatch does {'ok':True, **status_snapshot()} so the
        REAL response carries mode — but the stub doesn't emit it, so the wire contract is unverified."
  pattern: "Add a NEW test with a _StubDaemon SUBCLASS whose status_snapshot() includes 'mode' (don't edit
            the shared _StubDaemon or the 9-key assertion — that ripples). Assert the dispatch 'status'
            response carries 'mode'. Clean, isolated, no ripple."
  gotcha: "Do NOT widen the existing test_dispatch_status_has_all_keys 9-key set by editing _StubDaemon —
           other tests depend on its current shape. Subclass + override status_snapshot() in the new test."

# THE STATUS.SH MECHANISM NUANCE (already tested — do NOT re-test, but note the wording)
- file: tests/test_status_sh.py
  why: "ALL THREE mode branches are ALREADY covered: test_status_sh_lite_mode_prefixes_bolt (lite->⚡🎤,
        normal->🎤) + test_status_sh_listening_renders_partial_and_exits_zero (absent mode -> 🎤). The
        mechanism is `if (.mode == \"lite\")` (jq equality), NOT `(.mode // \"normal\") == \"lite\"` —
        functionally equivalent (null == \"lite\" is false). Do NOT add a status.sh test."
  critical: "status.sh is DONE + TESTED. Skip it entirely. (Listed in the contract only because the
            breakdown preceded the reconciliation pass.)"
```

### Current Codebase tree (relevant slice — S1 editing daemon.py concurrently)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/             # ALL 9 lite sites VERIFIED CORRECT (recon PART 1). NO source edits in this subtask.
│   ├── daemon.py             # _mode@632; _load_host switch@703-754; _arm set_mode@980; start_lite@1326;
│   │                         #   toggle_lite@1368 (S1 rewriting condition); status_snapshot mode@1501;
│   │                         #   _dispatch lite@1829-1834. (LINE NUMBERS SHIFT — S1 editing — navigate by symbol.)
│   ├── ctl.py                # _COMMANDS has toggle-lite/start-lite@35; format_result mode render@67,88. VERIFIED.
│   ├── feedback.py           # _state["mode"]="normal"@99; set_mode@145. VERIFIED.
│   └── status.sh             # ⚡/🎤 render@42-51. VERIFIED + ALREADY TESTED.
└── tests/
    ├── test_daemon.py        # ← ADD 2 gap tests. _spawning_factory@3472; _make_lazy_daemon@2663; existing
    │                         #   lite tests @2756-3547 (DON'T re-add). S1 adds toggle tests @3472-3547 (disjoint).
    └── test_control_socket.py # ← ADD 1 dispatch-mode test. _StubDaemon@27 (omits mode); routing@131.
# test_voicectl.py / test_feedback.py / test_status_sh.py: lite coverage ALREADY EXISTS — NO edits.
```

### Desired Codebase tree with files to be changed

```bash
tests/test_daemon.py          # MODIFY: +2 gap tests (mode-switch teardown stop_calls; idle-unload→start_lite).
tests/test_control_socket.py  # MODIFY: +1 dispatch-mode test (+ a _StubDaemon subclass, local to the test).
# No source files. No test_voicectl/test_feedback/test_status_sh edits (already covered). No new files.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS VERIFY + GAP-FILL, NOT WRITE-FROM-SCRATCH. The recon found the 9 sites CORRECT
# and lite coverage already comprehensive. Adding the §5 tests that ALREADY EXIST (toggle×mode,
# status_snapshot mode, set_mode, status.sh ⚡) is REDUNDANT + risks conflicting with S1's in-flight
# test_daemon.py edits. Add ONLY the 3 gaps. Re-check each gap is still uncovered before adding (the
# moving target may land one).

# CRITICAL #2 — LINE NUMBERS IN daemon.py ARE STALE ON ARRIVAL. S1 (P1.M1.T2.S1) is concurrently editing
# toggle/toggle_lite. Navigate by SYMBOL (grep 'def _load_host', 'def start_lite', '_spawning_factory'),
# NOT by the recon's line numbers (which were current at recon time and will shift).

# CRITICAL #3 — _spawning_factory IS S1's HELPER (test_daemon.py:3472) — REUSE IT, DO NOT REDEFINE.
# It appends each built _FakeHost to a list AND respects the mode kwarg (no closure override). A second
# definition would shadow S1's. Re-confirm it exists (grep 'def _spawning_factory') before relying on it;
# if S1 hasn't landed it yet, define it locally in the new test section (matching S1's signature exactly).

# CRITICAL #4 — _FakeHost.is_alive IS A @property, NOT A METHOD. The _load_host switch-mode guard reads
# `self._host.is_alive` (no parens). In tests, assert `spawns[i].is_alive` (property), not `is_alive()`.
# stop(timeout=5.0) bumps `.stop_calls`; the ctor takes `mode=` and stores `.mode`.

# CRITICAL #5 — THE TEARDOWN GAP IS ABOUT THE OUTGOING HOST. _fake_host_factory (the default) returns a
# FRESH _FakeHost per call, so the previous instance (and its stop_calls) is dropped — that's WHY the
# existing switch test can't see the teardown. _spawning_factory RETAINS every host in the list, so
# spawns[0] (the outgoing normal host) is still queryable: assert spawns[0].stop_calls == 1 after the
# switch. (The _bounded_shutdown in the switch branch calls self._host.stop(timeout=5.0) once.)

# CRITICAL #6 — DON'T EDIT THE SHARED _StubDaemon OR ITS 9-KEY ASSERTION. test_control_socket's _StubDaemon
# is used by many tests; widening its status_snapshot to include 'mode' (and the 9-key set to 10) ripples.
# Instead, in the NEW dispatch-mode test, SUBCLASS _StubDaemon and override status_snapshot() to add 'mode'.
# Isolated, no ripple.

# CRITICAL #7 — NO SOURCE EDITS. The 9 sites are verified CORRECT. If re-verification finds a site
# STALE/WRONG, that is almost certainly S1's in-flight edit (toggle_lite) or a not-yet-landed reconciliation
# — STOP and report it; do NOT silently "fix" source in a test subtask. The only legitimate output is the
# 3 test additions + the recorded verification + the flagged concurrency note.

# GOTCHA #8 — THE CONCURRENCY NOTE (S1 Gotcha #5) IS A FLAG, NOT A UNIT TEST. The dead-host check
# (daemon.py ~831) may log "recorder-host child died unexpectedly" spuriously when a mode-switch-while-
# armed kills the resident — benign (end state correct; _load_host's success path clears _load_error +
# sets _mode). The fast suite does NOT run the run() loop, so this CANNOT be a deterministic unit test.
# FLAG it in the implementation report + recommend T7 (P1.M2.T1, the live feed-audio integration) or a
# manual live check cover it. Do NOT add a workaround or a flaky run-loop test here.

# GOTCHA #9 — STATUS.SH IS DONE + TESTED. The contract lists it (the breakdown preceded the reconciliation),
# but all 3 branches (lite→⚡🎤, normal→🎤, absent→🎤) are already in test_status_sh.py. Do NOT add a
# status.sh test. Note the mechanism is jq equality (if .mode == "lite"), not a // default — equivalent.

# GOTCHA #10 — FULL PATHS. `.venv/bin/python -m pytest` (machine aliases python3->uv run). No ruff/mypy
# configured. The heavy GPU tests (test_feed_audio.py, e2e_virtual_mic.sh, test_idle_and_gpu.sh) are
# --ignore'd in the fast suite.
```

## Implementation Blueprint

### Data models and structure

None. No source/data changes. The only "structure" is 3 new test functions (+ one local `_StubDaemon` subclass in the dispatch test) reusing the existing fakes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RE-VERIFY the 9 implementation sites against the live tree (no mutation)
  - RUN (navigate by SYMBOL — S1 is editing daemon.py, line numbers shift):
      cd /home/dustin/projects/voice-typing
      echo "--- (1) _mode boot 'normal' ---"; grep -n 'self._mode: str = "normal"' voice_typing/daemon.py
      echo "--- (2) _load_host switch_mode + teardown + self._mode=mode ---"
      grep -n 'switch_mode = True\|_bounded_shutdown(timeout=5.0)\|self._mode = mode' voice_typing/daemon.py
      echo "--- (3) _arm set_mode ---"; grep -n 'self._feedback.set_mode(self._mode)' voice_typing/daemon.py
      echo "--- (4) status_snapshot mode ---"; grep -n '"mode": self._mode' voice_typing/daemon.py
      echo "--- (5) start_lite / toggle_lite ---"; grep -n 'def start_lite\|def toggle_lite' voice_typing/daemon.py
      echo "--- (6) _dispatch lite arms ---"; grep -n 'cmd == "start-lite"\|cmd == "toggle-lite"' voice_typing/daemon.py
      echo "--- (7) status.sh ⚡ ---"; grep -n 'mode == "lite"\|⚡' voice_typing/status.sh
      echo "--- (8) ctl _COMMANDS + mode render ---"; grep -n 'toggle-lite\|start-lite\|"mode"' voice_typing/ctl.py
      echo "--- (9) feedback _state mode + set_mode ---"; grep -n '"mode": "normal"\|def set_mode' voice_typing/feedback.py
  - EXPECTED: all 9 present (recon PART 1 confirmed CORRECT). If any is MISSING/STALE, STOP and report
    (likely S1's in-flight edit) — do NOT edit source. Record the verification verdict (all 9 correct) in
    the implementation report.
  - ALSO confirm the baseline is still green: `.venv/bin/python -m pytest tests/ -q --ignore=tests/test_feed_audio.py | tail -1`
    (expect `277 passed` or similar; if there are pre-existing failures, NOTE them — they are NOT this
    subtask's to fix unless they're mode-related regressions).

Task 2: ADD tests/test_daemon.py — gap (1) mode-switch tears down the OUTGOING host
  - PLACE: a new test in the lite section (near test_mode_switch_normal_to_lite_reloads @~2766), under a
    banner citing P1.M1.T2.S2. REUSE _spawning_factory (re-confirm it exists @3472; if S1 hasn't landed
    it, define a local helper matching its signature — appends each built host to a list, respects mode kwarg).
  - ADD:
        def test_mode_switch_stops_outgoing_host():
            """P1.M1.T2.S2: a normal->lite mode switch TEARS DOWN the outgoing resident host
            (host.stop() called exactly once), not just respawns. Pins the switch_mode teardown branch
            (daemon.py: the resident-wrong-mode -> _bounded_shutdown -> host.stop path). The existing
            test_mode_switch_normal_to_lite_reloads counts the NEW host's spawns but never reads the
            OUTGOING host's stop_calls (the default factory drops the old instance); this closes that gap.
            """
            spawns: list = []
            d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
            d.start()                       # resident + armed in normal
            assert len(spawns) == 1 and spawns[0].mode == "normal"
            assert spawns[0].stop_calls == 0
            d.start_lite()                  # switch normal -> lite (teardown normal, spawn lite, arm)
            assert len(spawns) == 2
            assert spawns[1].mode == "lite" and d._mode == "lite" and d._host is spawns[1]
            assert spawns[0].stop_calls == 1, (   # the OUTGOING normal host was torn down exactly once
                f"mode switch did not stop the outgoing host (stop_calls={spawns[0].stop_calls})"
            )
            assert spawns[1].stop_calls == 0     # the new lite host has not been stopped
  - NOTE: if d.start_lite() while armed-in-normal disarms instead of switching in this lazy-daemon seam
    (it shouldn't — start_lite unconditionally loads+arms lite), assert d.is_listening() is True + mode
    lite. start_lite is NOT toggle (it always arms lite), so it takes the _load_host("lite") switch path
    regardless of the listening state. (S1's toggle-condition fix only affects toggle/toggle_lite, not
    start/start_lite.)

Task 3: ADD tests/test_daemon.py — gap (2) idle-unload -> start_lite reloads in lite
  - MIRROR the existing test_cold_arm_after_idle_unload_refires_loading_toast (@~2839) — read it first to
    see HOW it triggers idle-unload (it either calls _unload_host() directly or advances a clock/watchdog;
    mirror that EXACT trigger). Then assert the lite reload.
  - ADD (adjust the trigger to match 2839's mechanism):
        def test_start_lite_after_idle_unload_reloads_in_lite():
            """P1.M1.T2.S2: after idle-unload (no resident), start_lite() reloads in LITE mode (the lite
            counterpart of test_cold_arm_after_idle_unload for normal). Mirrors 2839's idle-unload trigger.
            """
            spawns: list = []
            d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
            d.start_lite()                  # load + arm lite
            assert len(spawns) == 1 and d._mode == "lite"
            d.stop()                        # disarm (still resident in lite)
            # trigger idle-unload the SAME way test_cold_arm_after_idle_unload does (read 2839 first):
            d._unload_host()                # <- if 2839 calls this directly; else mirror its clock/watchdog trigger
            assert d._models_loaded is False and d._host is None
            d.start_lite()                  # reload after idle-unload -> lite again
            assert len(spawns) == 2 and spawns[1].mode == "lite" and d._mode == "lite"
  - CONSTRAINT: read test_cold_arm_after_idle_unload (@2839) FIRST and copy its idle-unload trigger
    verbatim (the comment above says "adjust the trigger to match"). Do NOT invent a new trigger.

Task 4: ADD tests/test_control_socket.py — gap (3) the status wire response carries `mode`
  - PLACE: near test_dispatch_lite_commands_call_daemon (@~131). SUBCLASS _StubDaemon locally (do NOT edit
    the shared _StubDaemon or the 9-key assertion — CRITICAL #6).
  - ADD (json + daemon already imported in this file):
        def test_dispatch_status_response_carries_mode():
            """P1.M1.T2.S2: the wire status response carries the daemon's 'mode' field. The shared
            _StubDaemon.status_snapshot() omits 'mode' (and test_dispatch_status_has_all_keys pins 9 keys),
            so this uses a subclass that emits it — proving the {'ok':True, **status_snapshot()} spread
            surfaces mode on the wire (the PRD §4.2 status-payload contract).
            """
            class _ModeDaemon(_StubDaemon):
                def status_snapshot(self):
                    return {**super().status_snapshot(), "mode": "lite"}
            d = _ModeDaemon(); srv = daemon.ControlServer(d)
            r = srv._dispatch(json.dumps({"cmd": "status"}))
            assert r["ok"] is True
            assert r.get("mode") == "lite", f"status response missing 'mode': {r}"
  - DO NOT: edit _StubDaemon's _snapshot, widen the 9-key assertion, or touch test_dispatch_lite_commands.

Task 5: FLAG the concurrency note (S1 Gotcha #5) — record, do NOT add a workaround
  - In the implementation report, record: "Concurrency note (handed off by P1.M1.T2.S1): the BUG-B fix
    made _load_host callable while _listening is SET (mode-switch-while-armed). The run() loop's dead-host
    check (daemon.py ~831, runs before the _listening check) MAY log 'recorder-host child died
    unexpectedly' spuriously on the killed resident mid-switch. End state is correct (_load_host's success
    path clears _load_error + sets _mode; _arm re-sets _listening). The fast suite does not run the loop,
    so this is NOT a deterministic unit test. Recommendation: cover via T7 (P1.M2.T1 live integration) or a
    manual live mode-switch-while-armed check; if the noise is objectionable, a follow-up could suppress
    the log line when a mode switch is in flight (out of scope here)."
  - DO NOT: add a workaround, a run-loop test, or a source edit for this. It is a documented finding.

Task 6: VALIDATE — run the Validation Loop L1–L4 below; fix until all green. No git commit unless the
  orchestrator directs it. If asked, message:
  "P1.M1.T2.S2: verify 9 lite mode-switch sites (all correct) + add 3 gap tests (switch-teardown,
  idle-unload->lite, dispatch-mode) + flag dead-host concurrency note".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — _spawning_factory RETAINS every host (the key to the teardown gap). The default
# _fake_host_factory drops the outgoing instance; _spawning_factory appends each built _FakeHost to a
# list, so after a normal->lite switch: spawns[0] = outgoing normal host (stop_calls should be 1),
# spawns[1] = new lite host. Assert BOTH the respawn (spawns[1].mode == "lite") AND the teardown
# (spawns[0].stop_calls == 1).
spawns: list = []
d, _fb = _make_lazy_daemon(host_factory=_spawning_factory(spawns))
d.start(); d.start_lite()              # normal resident -> switch to lite
assert len(spawns) == 2
assert spawns[0].stop_calls == 1       # the teardown gap: outgoing host WAS stopped
assert spawns[1].mode == "lite"

# PATTERN 2 — SUBCLASS _StubDaemon for the dispatch-mode test (don't edit the shared stub). The dispatch
# does {'ok': True, **status_snapshot()}; a subclass that adds 'mode' proves the spread surfaces it:
class _ModeDaemon(_StubDaemon):
    def status_snapshot(self):
        return {**super().status_snapshot(), "mode": "lite"}
assert daemon.ControlServer(_ModeDaemon())._dispatch(json.dumps({"cmd": "status"}))["mode"] == "lite"

# PATTERN 3 — MIRROR the existing idle-unload trigger (test_cold_arm_after_idle_unload @2839). Read it
# first; copy its _unload_host() call (or clock/watchdog advance) verbatim, then assert the lite reload.
```

### Integration Points

```yaml
DOWNSTREAM — P1.M2.T1 (T7 lite feed-audio integration):
  - The concurrency note (Task 5) is recommended for T7's live coverage (mode-switch-while-armed with a
    real child + the run loop). T2.S2's 3 gap tests are the deterministic UNIT proof; T7 is the live proof.
  - T7 also asserts the socket mode-switch end-to-end (toggle-lite arms mode:"lite", toggle reloads
    mode:"normal") — T2.S2's dispatch-mode test is the unit-level complement.

DOWNSTREAM — P1.M2.T3 (final full-suite + GPU lifecycle + commit):
  - T2.S2's "full fast suite green (0 failures)" gate feeds P1.M2.T3.S1's final verification. The 3 new
    tests raise the count above the recon's 277 baseline; P1.M2.T3 reconciles the expected count.

PARALLEL — P1.M1.T2.S1 (toggle semantics + 6 toggle×mode tests):
  - S1 edits daemon.py (toggle/toggle_lite conditions) + test_daemon.py (6 toggle tests @3472-3547) +
    hypr-binds.conf. T2.S2 edits test_daemon.py (2 gap tests, appended after S1's section — additive,
    disjoint) + test_control_socket.py (1 test, S1 doesn't touch it). No line conflict. Both REUSE
    _spawning_factory (S1 defines it; T2.S2 reuses — do NOT redefine).

NO SOURCE CHANGES:
  - voice_typing/* : UNCHANGED (9 sites verified CORRECT). config.toml / systemd / recorder_host / ctl /
    feedback / status.sh: UNCHANGED. If a site is found wrong on re-verification, STOP + report.
```

## Validation Loop

> Full paths (machine aliases python3→uv run). All gates are FAST unit tests — NO GPU / models / real
> child / run loop / network. No ruff/mypy configured. Navigate by symbol in daemon.py (S1 editing — line
> numbers shift).

### Level 1: The 9 sites are still correct on the live tree (re-verification)

```bash
cd /home/dustin/projects/voice-typing
echo "--- (1-6) daemon sites ---"
grep -cq 'self._mode: str = "normal"' voice_typing/daemon.py && echo "L1 (1) _mode boot OK" || echo "L1 FAIL (1)"
grep -q 'switch_mode = True' voice_typing/daemon.py && grep -q 'self._mode = mode' voice_typing/daemon.py && echo "L1 (2) _load_host switch OK" || echo "L1 FAIL (2)"
grep -q 'self._feedback.set_mode(self._mode)' voice_typing/daemon.py && echo "L1 (3) _arm set_mode OK" || echo "L1 FAIL (3)"
grep -q '"mode": self._mode' voice_typing/daemon.py && echo "L1 (4) status_snapshot mode OK" || echo "L1 FAIL (4)"
grep -q 'def start_lite' voice_typing/daemon.py && grep -q 'def toggle_lite' voice_typing/daemon.py && echo "L1 (5) start/toggle_lite OK" || echo "L1 FAIL (5)"
grep -q 'cmd == "start-lite"' voice_typing/daemon.py && grep -q 'cmd == "toggle-lite"' voice_typing/daemon.py && echo "L1 (6) dispatch lite OK" || echo "L1 FAIL (6)"
echo "--- (7-9) status.sh / ctl / feedback ---"
grep -q 'mode == "lite"' voice_typing/status.sh && echo "L1 (7) status.sh OK" || echo "L1 FAIL (7)"
grep -q 'toggle-lite' voice_typing/ctl.py && grep -q '"mode"' voice_typing/ctl.py && echo "L1 (8) ctl OK" || echo "L1 FAIL (8)"
grep -q '"mode": "normal"' voice_typing/feedback.py && grep -q 'def set_mode' voice_typing/feedback.py && echo "L1 (9) feedback OK" || echo "L1 FAIL (9)"
# Expected: all 9 OK. Any FAIL -> STOP + report (likely S1's in-flight edit); do NOT edit source here.
```

### Level 2: The 3 new gap tests pass (the deterministic proof)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py tests/test_control_socket.py -v \
  -k "mode_switch_stops_outgoing_host or start_lite_after_idle_unload_reloads_in_lite or dispatch_status_response_carries_mode"
# Expected: 3 PASSED. If test_mode_switch_stops_outgoing_host shows spawns[0].stop_calls == 0: the switch
# did NOT tear down the old host (a real VRAM-leak bug — report it; or _spawning_factory wasn't used / was
# redefined shadowing S1's). If the idle-unload test hangs/fails: re-read test_cold_arm_after_idle_unload
# (2839) and mirror its trigger exactly. If the dispatch test fails on missing 'mode': the subclass
# override didn't take (re-check super().status_snapshot() spread).
```

### Level 3: No regression — full fast suite green

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/ -q --ignore=tests/test_feed_audio.py 2>&1 | tail -3
# Expected: 0 failures. The count = recon baseline (277) + the 3 new tests (+ any S1 toggle tests that
# landed since the recon). A NEW failure means a regression from this subtask's edits or an S1 conflict —
# if a toggle test collides with a gap test (same name), rename the gap test. The existing lite tests
# (toggle×mode, status_snapshot_reports_mode, set_mode, status.sh) must all stay green (untouched).
```

### Level 4: Scope guards — only the 2 test files; no source; no redundant tests; concurrency note flagged

```bash
cd /home/dustin/projects/voice-typing
echo "--- changed files are ONLY the 2 test files ---"
git diff --name-only | grep -vxE 'tests/test_daemon.py|tests/test_control_socket.py' && echo "L4 FAIL: out-of-scope file changed" || echo "L4 PASS: only the 2 test files"
echo "--- NO source files modified ---"
git diff --quiet voice_typing/ config.toml systemd/ hypr-binds.conf install.sh README.md && echo "L4 PASS: no source changes" || echo "L4 FAIL: a source file was modified (this subtask verifies, doesn't edit)"
echo "--- the 3 gap tests are NEW (not renaming/clobbering existing lite tests) ---"
git diff tests/test_daemon.py tests/test_control_socket.py | grep -E '^\+def test_(mode_switch_stops_outgoing_host|start_lite_after_idle_unload_reloads_in_lite|dispatch_status_response_carries_mode)' | wc -l | xargs -I{} echo "new gap test defs added: {} (expect 3)"
echo "--- no redundant re-adds of already-covered tests ---"
git diff tests/ | grep -E '^\+def test_(toggle_lite_while|toggle_while|status_snapshot_reports_mode|set_mode_writes|state_shape_has|status_sh_lite|format_status_multiline|lite_commands_are_accepted)' && echo "L4 WARN: a redundant (already-existing) test may have been re-added — verify it's not a duplicate" || echo "L4 PASS: no obvious redundant re-adds"
echo "--- read-only files UNCHANGED ---"
git diff --exit-code -- PRD.md plan/004_607e9cca32b7/tasks.json plan/004_607e9cca32b7/prd_snapshot.md .gitignore && echo "L4 PASS: read-only files unchanged" || echo "L4 NOTE: tasks.json may show orchestrator bookkeeping (M) — not this subtask"
# Expected: only the 2 test files changed; NO source edits; 3 new gap test defs; no redundant re-adds;
# read-only files unchanged. (daemon.py may show S1's parallel toggle edits in git diff — that is S1's
# work, NOT this subtask's; T2.S2's own diff is the 3 test additions.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: all 9 lite sites CORRECT on the live tree (re-verified by grep; any stale → STOP + report).
- [ ] L2: 3 new gap tests pass (switch-teardown `stop_calls==1`; idle-unload→lite reload; dispatch `mode`).
- [ ] L3: full fast suite green (0 failures); existing lite tests untouched.
- [ ] L4: only the 2 test files changed; no source edits; 3 new test defs; no redundant re-adds.

### Feature Validation
- [ ] A normal→lite mode switch tears down the outgoing host (not just respawns) — gap (1) closed.
- [ ] `start_lite()` after idle-unload reloads in lite — gap (2) closed.
- [ ] The wire `status` response carries `mode` (dispatch layer) — gap (3) closed.
- [ ] The 9 implementation sites are verified correct (the recorded verification).
- [ ] The dead-host concurrency note is flagged (not silently fixed) with a T7/live recommendation.

### Code Quality Validation
- [ ] Gap tests reuse `_spawning_factory`/`_make_lazy_daemon`/`_StubDaemon` (no redefinition of S1's helper).
- [ ] `_FakeHost.is_alive` used as a property (not called); `.stop_calls`/`.mode` asserted correctly.
- [ ] The dispatch test SUBCLASSES `_StubDaemon` (no ripple to the shared stub or its 9-key assertion).
- [ ] The idle-unload test MIRRORS `test_cold_arm_after_idle_unload`'s trigger (no invented mechanism).
- [ ] No bare `python`/`pytest`/`ruff`/`mypy` (use `.venv/bin/python -m pytest`).

### Scope Boundary Validation
- [ ] NO source files modified (verify-only; a found bug → STOP + report, not a silent fix).
- [ ] NO redundant tests (toggle×mode / status_snapshot-mode / set_mode / status.sh already exist — not re-added).
- [ ] NO run-loop/concurrency workaround (the note is flagged for T7/live; no flaky test added).
- [ ] NO test_voicectl/test_feedback/test_status_sh edits (already covered).
- [ ] NO T7 feed-audio integration (P1.M2.T1) or README/ACCEPTANCE sync (P1.M2.T2).
- [ ] PRD.md, tasks.json, prd_snapshot.md, delta_prd.md, system_context.md, .gitignore NOT modified.

### Documentation & Deployment
- [ ] Contract §5 "DOCS: none" — no user-facing docs; the recorded verification + flagged note are the artifacts.
- [ ] The concurrency-note finding is documented for P1.M2.T1 (T7) to consume.

---

## Anti-Patterns to Avoid

- ❌ Don't write the §5 tests from scratch — the moving target ALREADY landed most of them (toggle×mode, status_snapshot mode, set_mode, status.sh ⚡, ctl format). Adding duplicates is redundant and risks conflicting with S1's in-flight `test_daemon.py` edits. Add ONLY the 3 gaps (CRITICAL #1).
- ❌ Don't edit source — the 9 sites are verified CORRECT. A found-stale site is S1's in-flight work or a not-yet-landed reconciliation: STOP + report, don't silently fix in a test subtask (CRITICAL #7).
- ❌ Don't match by line number in daemon.py — S1 is editing it; navigate by symbol (CRITICAL #2).
- ❌ Don't redefine `_spawning_factory` — S1 defined it (@3472); reuse it. A second definition shadows/conflicts (CRITICAL #3).
- ❌ Don't edit the shared `_StubDaemon` or widen its 9-key assertion — subclass it locally in the dispatch test (CRITICAL #6).
- ❌ Don't use `_fake_host_factory` for the teardown test — it drops the outgoing host (that's the gap). Use `_spawning_factory(spawns)` which retains every host (CRITICAL #5).
- ❌ Don't call `_FakeHost.is_alive` as a method — it's a `@property` (CRITICAL #4).
- ❌ Don't add a run-loop test or a workaround for the dead-host concurrency note — the fast suite doesn't run the loop (can't be deterministic); flag it for T7/live (GOTCHA #8).
- ❌ Don't re-test status.sh — all 3 mode branches are already covered in `test_status_sh.py` (GOTCHA #9).
- ❌ Don't invent an idle-unload trigger — mirror `test_cold_arm_after_idle_unload` (@2839) exactly.
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `delta_prd.md`, `system_context.md`, or `.gitignore` (read-only / owned by others).

---

## Confidence Score

**9/10** for one-pass implementation success. This is a verify + gap-fill task whose verification is **already done** (the recon verified all 9 sites CORRECT with quotes + current line numbers, and the full fast suite is green at `277 passed`). The 3 gaps are precisely identified with the exact fakes that close them: `_spawning_factory(spawns)` retains the outgoing host so `spawns[0].stop_calls == 1` pins the teardown (gap 1); mirroring `test_cold_arm_after_idle_unload` (@2839) for `start_lite()` pins the lite reload (gap 2); a local `_StubDaemon` subclass emitting `mode` pins the wire contract without rippling (gap 3). The no-conflict boundary with S1 is explicit (T2.S2 appends 2 daemon tests after S1's section + reuses its `_spawning_factory`; the dispatch test is in a file S1 doesn't touch). The −1 residual is the **moving target**: S1 is concurrently editing `test_daemon.py` (and may adjust `_spawning_factory` or add a test that closes one of the gaps), so the implementer must re-confirm each gap is still uncovered and that `_spawning_factory` still exists before relying on it (the PRP mandates this re-check). The dead-host concurrency note is honestly flagged as a non-unit-test item (deferred to T7/live), not papered over with a flaky test. No GPU/models/run-loop/network required for any gate.
