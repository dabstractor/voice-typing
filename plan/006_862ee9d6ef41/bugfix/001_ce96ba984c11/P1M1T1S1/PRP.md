# PRP — P1.M1.T1.S1: Surface cross-mode toggle load failures as `ok:false` in `_dispatch()`

## Goal

**Feature Goal**: Fix `ControlServer._dispatch()` so that when a `toggle` / `toggle-lite` command triggers a cross-mode model reload that FAILS, the control-socket response is `{"ok": false, "error": "model load failed: ..."}` (routed through the existing `_arm_response()`), instead of the current silent `{"ok": true, "listening": false}`. This makes `voicectl` print `error: model load failed: ...` and exit 1 — matching what `start`/`start-lite` already do (PRD §4.2bis).

**Deliverable**: A TDD change in TWO files:
1. `tests/test_daemon.py` — add TWO failing tests (RED) that dispatch a cross-mode `toggle` / `toggle-lite` through `ControlServer._dispatch()` and assert `{"ok": False}` + `"model load failed"` in the error.
2. `voice_typing/daemon.py` — in `_dispatch()`, add a load-error-aware return to BOTH the `toggle` and `toggle-lite` branches (snapshot `_load_error` before; route through `_arm_response()` if a fresh error was set on the disarm path).

**Success Definition**: (a) the two new tests are RED before the daemon.py edit and GREEN after; (b) `_dispatch("toggle")` on a failed lite→normal reload returns `{"ok": False, "error": "model load failed: ..."}`; (c) `_dispatch("toggle-lite")` on a failed normal→lite reload returns the same; (d) the existing same-mode disarm path still returns `{"ok": True, "listening": false}` (unchanged); (e) `_arm_response()`, `toggle()`, `toggle_lite()`, `_load_host()`, and `ctl.py` are NOT modified; (f) the prescribed pytest suites stay green.

## User Persona

**Target User**: A user who presses the mode-switch hotkey (e.g. Alt+Super+D while armed in normal, or Ctrl+Alt+Super+D while armed in lite) and the target model fails to load (CUDA OOM, missing model, cuDNN error).

**Use Case**: Cross-mode switch via `voicectl toggle` / `toggle-lite` while armed in the other mode.

**Pain Points Addressed**: Today the user sees only `listening: off` (exit 0) with zero indication the mode switch failed; they must separately run `voicectl status` to discover the `load error:` line. After the fix, the failure is surfaced inline as `error: model load failed: ...` (exit 1), matching `start`/`start-lite`.

## Why

- **Major bug (bugfix Issue 1):** the dispatch layer silently swallows cross-mode reload failures. The DAEMON layer is correct (`toggle()`/`toggle_lite()` disarm + set `_load_error`, pinned by `test_toggle_while_armed_in_lite_failed_reload_clears_listening`), but the WIRE response is `{"ok": true, "listening": false}` — the error never reaches `voicectl`.
- **Root cause (verified):** `arm_attempted = not was_listening or self._daemon.is_listening()`. For a cross-mode failure: `was_listening=True`, the failed reload disarms → `is_listening()=False` → `arm_attempted = not True or False = False` → the code returns `{"ok": True, **status_snapshot()}` instead of `_arm_response()`.
- **The fix reuses existing correct machinery:** `_arm_response()` (daemon.py:1901) already returns `{"ok": False, "error": "model load failed: ..."}` when `_load_error` is set and not listening. The `_load_error` attribute is reset to `None` by `_load_host()` at the start of every attempt (daemon.py:726), so snapshotting it before the `toggle()` call and checking it after reliably detects a FRESH failure. The fix just routes that case through `_arm_response()`.
- **Minimal, surgical, no API change:** 2 added lines per dispatch branch (a before-snapshot + a conditional return). `ctl.format_result()` already renders `ok:false` as `error: ...` exit 1 (ctl.py:63) — no client change.

## What

Add two RED tests that drive the real dispatch path with a failing cross-mode reload (via the existing `_failing_second_spawn_factory` + `_make_lazy_daemon` + `ControlServer(d)._dispatch(...)`), watch them fail, then add the load-error-aware return to the `toggle` and `toggle-lite` branches. No other code touched.

### Success Criteria

- [ ] `tests/test_daemon.py` has 2 new tests asserting `_dispatch("toggle")` / `_dispatch("toggle-lite")` on a failed cross-mode reload return `{"ok": False}` + `"model load failed"`.
- [ ] Both new tests FAIL before the daemon.py edit (RED) and PASS after (GREEN).
- [ ] `_dispatch()` toggle + toggle-lite branches snapshot `_load_error` before the call and route a fresh error through `_arm_response()`.
- [ ] Same-mode disarm still returns `{"ok": True, "listening": false}`; first-arm path unchanged.
- [ ] `_arm_response()`, `toggle()`, `toggle_lite()`, `_load_host()`, `ctl.py` unmodified.
- [ ] `tests/test_daemon.py` (cross-mode/toggle tests), `tests/test_control_socket.py`, `tests/test_voicectl.py` all green.

## All Needed Context

### Context Completeness Check

_Pass._ The bug site, the correct machinery to reuse, the `_load_error` lifecycle, the exact test factory + construction pattern, and the client-side rendering are all quoted verbatim below with line numbers (re-verified). An agent new to this codebase can write the two tests and the two-branch fix from this PRP alone.

### Verified Current State (re-verified — bug IS present)

**`voice_typing/daemon.py` `_dispatch()` — the buggy `toggle` branch (1927-1938):**
```python
        if cmd == "toggle":
            was_listening = self._daemon.is_listening()
            self._daemon.toggle()
            # ... comment ...
            arm_attempted = not was_listening or self._daemon.is_listening()
            if arm_attempted:
                return self._arm_response()
            return {"ok": True, **self._daemon.status_snapshot()}   # ← BUG: silent on cross-mode failure
```
The `toggle-lite` branch (1945-1951) is structurally identical (`toggle_lite()`). For a cross-mode failure, `arm_attempted` is False → the `{"ok": True, ...}` fallthrough fires → the error is buried in the status snapshot's `load_error` field, never surfaced as `ok:false`.

**`_arm_response()` (1901-1916) — CORRECT, reuse it, do NOT edit:**
```python
    def _arm_response(self) -> dict:
        load_error = getattr(self._daemon, "_load_error", None)
        if load_error and not self._daemon.is_listening():
            return {"ok": False, "error": f"model load failed: {load_error}"}
        return {"ok": True, **self._daemon.status_snapshot()}
```

**`_load_error` lifecycle:** declared `None` (daemon.py:661); reset to `None` by `_load_host()` at the START of every attempt (daemon.py:726); set to a truthy string only on a fresh failure. → Snapshotting before the `toggle()` call and checking after reliably distinguishes "failure during THIS toggle" from a stale value.

**`ctl.py format_result()` — CORRECT, do NOT edit:** the `ok:false` branch (ctl.py:63) returns `f"error: {response.get('error', 'unknown error')}", 1` and is checked BEFORE the toggle/start/stop `listening: on/off` branch (ctl.py:103). So returning `{"ok": False, "error": "..."}` from `_dispatch` makes `voicectl` print `error: model load failed: ...` and exit 1 — no client change needed.

**Test infra (all in `tests/test_daemon.py`, hermetic, no CUDA):**
- `_failing_second_spawn_factory(spawns)` (test_daemon.py:3843) — host_factory whose 1st spawn succeeds (arms the first mode) and 2nd spawn fails (the cross-mode reload).
- `_make_lazy_daemon(host_factory=...)` (test_daemon.py:2758) — returns `(d, fb)`; real lazy boot; `_load_host` spawns via the factory.
- `daemon.ControlServer(d)` (constructed with just the daemon; socket_path defaults) — `srv._dispatch(json.dumps({"cmd": "toggle"}))` returns the response dict. Pattern confirmed by test_control_socket.py:134.
- Existing daemon-level tests (test_daemon.py:3858/3877/3894) call `d.toggle()` / `d.toggle_lite()` DIRECTLY (they pin daemon behavior, NOT the wire response). The NEW tests must go through `ControlServer._dispatch()` to pin the wire response — that is the uncovered gap.

### Documentation & References

```yaml
# THE DEFECT (authoritative)
- docfile: plan/006_862ee9d6ef41/bugfix/001_ce96ba984c11/prd_snapshot.md
  why: §h3.0 Issue 1 documents the silent ok:true cross-mode failure, the root cause (arm_attempted
       computation), and three suggested fixes; the contract picks the "snapshot _load_error before/
       after" variant (simplest, safe). Also see architecture/system_context.md §Issue 1 +
       _scout_test_patterns.md §Issue 1.
  critical: "The bug is ONLY in _dispatch() response shaping. toggle()/toggle_lite()/_load_host()/
            _arm_response()/ctl.py are all correct — do NOT edit them."

# THE FIX SITE
- file: voice_typing/daemon.py
  why: ControlServer._dispatch() — the 'toggle' branch (1927-1938) and 'toggle-lite' branch (1945-
        1951). Add `load_error_before = getattr(self._daemon, "_load_error", None)` BEFORE the
        toggle call, and a conditional `return self._arm_response()` in the not-arm_attempted path
        when a fresh error appeared.
  pattern: "Snapshot _load_error before; after, if arm_attempted is False AND (load_error_before is
            None AND _load_error now truthy) -> route through _arm_response(). Mirror in both
            branches. getattr(...,None) keeps the duck-typed _StubDaemon test (no _load_error) on
            the ok:true path."
  gotcha: "Do NOT change the arm_attempted computation or the arm_attempted=True path. Only ADD a
           branch in the existing fallthrough (the `return {ok:True, **status_snapshot()}` line)."

# THE CORRECT MACHINERY TO REUSE (read-only)
- file: voice_typing/daemon.py
  why: _arm_response() (1901) returns ok:false+error when _load_error set and not listening — the
        exact response we want. _load_error is reset per attempt by _load_host (726), so the
        before/after snapshot detects a fresh failure. Reuse, don't reimplement.

# THE TEST PATTERN TO FOLLOW
- file: tests/test_daemon.py
  why: _failing_second_spawn_factory (3843) + _make_lazy_daemon (2758) + the existing cross-mode
        tests (3858/3877/3894). The new tests mirror these but wrap `daemon.ControlServer(d)` and
        call `srv._dispatch(json.dumps({"cmd": "toggle"}))` to pin the WIRE response.
  pattern: "spawns=[]; d,_fb=_make_lazy_daemon(host_factory=_failing_second_spawn_factory(spawns));
            d.start_lite() (or d.start()); srv=daemon.ControlServer(d);
            resp=srv._dispatch(json.dumps({'cmd':'toggle'})); assert resp['ok'] is False."
  critical: "The existing tests call d.toggle() directly — they do NOT cover _dispatch. The new tests
            MUST go through _dispatch; that is the regression gap being closed."

# THE CLIENT (confirm no change)
- file: voice_typing/ctl.py
  why: format_result() (48) checks ok:false FIRST (63 -> 'error: ...', exit 1) before the
        toggle/start/stop listening branch (103). So an ok:false response from _dispatch renders
        correctly with zero client changes.
  critical: "DO NOT edit ctl.py. The contract is explicit: format_result() already does the right
            thing."

# PRD CONTEXT
- docfile: plan/006_862ee9d6ef41/bugfix/001_ce96ba984c11/prd_snapshot.md
  why: §4.2bis ("the arm command returns {ok:false, error:...}") + §4.2ter (mode switching) + §4.8
        (voicectl exit codes) are the spec basis. The fix makes toggle/toggle-lite match start.
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── daemon.py            # ControlServer._dispatch() toggle @1927 / toggle-lite @1945  ← EDIT (2 branches)
│                            #   _arm_response() @1901 (REUSE, read-only)
│                            #   _load_error @661; _load_host reset @726 (read-only)
│                            #   toggle() @1419 / toggle_lite() @1452 (read-only — correct)
│   └── ctl.py               # format_result() @48 (read-only — ok:false already handled)
└── tests/
    └── test_daemon.py       # _failing_second_spawn_factory @3843; _make_lazy_daemon @2758; cross-mode tests @3858/3877/3894  ← ADD 2 tests
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py       # MODIFY: _dispatch() toggle + toggle-lite branches (snapshot + conditional _arm_response route)
tests/test_daemon.py         # MODIFY: +2 RED-then-GREEN tests (cross-mode toggle/toggle-lite via _dispatch)
# NO other files. ctl.py, _arm_response, toggle/toggle_lite, _load_host — all unchanged.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE BUG IS ONLY IN _dispatch(). toggle()/toggle_lite() correctly disarm + set
# _load_error on a failed cross-mode reload (pinned by test_toggle_while_armed_in_lite_failed_reload_
# clears_listening at test_daemon.py:3877). _arm_response() correctly returns ok:false+error. DO NOT
# edit any of them — the fix is purely the dispatch-layer routing.

# CRITICAL #2 — SNAPSHOT _load_error BEFORE the toggle() call. _load_host() resets _load_error=None
# at the start of every attempt (daemon.py:726). So (None before + truthy after) reliably means "a
# failure happened DURING this toggle". Snapshotting AFTER only would be ambiguous (can't tell fresh
# from stale). Capture load_error_before = getattr(self._daemon, "_load_error", None) BEFORE
# self._daemon.toggle().

# CRITICAL #3 — THE `load_error_before is None` GUARD IS LOAD-BEARING. It ensures you only treat the
# error as fresh when there was NO pre-existing error. Without it, a stale _load_error on a pure
# disarm (no reload) could false-fire. Keep `load_error_before is None and getattr(...,None)`.

# CRITICAL #4 — DON'T DISTURB THE OTHER THREE PATHS. The fix adds ONE branch in the not-arm_attempted
# fallthrough only. Verify all four cases stay correct:
#   - same-mode disarm (was listening, toggle disarms, no reload): _load_error None→None → ok:true listening:off. UNCHANGED.
#   - cross-mode SUCCESS: is_listening() True → arm_attempted True → _arm_response → ok:true. UNCHANGED.
#   - cross-mode FAILURE: arm_attempted False + _load_error None→truthy → NEW branch → _arm_response → ok:false+error. FIXED.
#   - first arm (was_listening False): arm_attempted True → _arm_response. UNCHANGED.

# CRITICAL #5 — ctl.py NEEDS NO CHANGE. format_result() checks ok:false FIRST (ctl.py:63 -> 'error:
# ...', exit 1) before the toggle/start/stop listening branch (ctl.py:103). Returning {ok:false,
# error:...} from _dispatch renders correctly with zero client edits. Do NOT touch ctl.py.

# CRITICAL #6 — MIRROR THE FIX IN BOTH BRANCHES. toggle (1927) AND toggle-lite (1945) have the
# identical bug; both need the snapshot + conditional route. Don't fix only one.

# GOTCHA #7 — THE NEW TESTS MUST GO THROUGH _dispatch(), NOT d.toggle() directly. The existing
# cross-mode tests (3858/3877/3894) call d.toggle()/d.toggle_lite() directly — they pin DAEMON
# behavior and pass today. The wire-response gap is only exercised by ControlServer._dispatch().
# Construct: srv = daemon.ControlServer(d); resp = srv._dispatch(json.dumps({"cmd": "toggle"})).

# GOTCHA #8 — CONTROLSERVER(daemon) NEEDS ONLY THE DAEMON. socket_path has a default (don't set it);
# _dispatch() never touches the socket. Pattern: daemon.ControlServer(d) (test_control_socket.py:134).

# GOTCHA #9 — TDD DISCIPLINE. Write BOTH tests, run them, confirm RED (resp['ok'] is True today),
# THEN apply the daemon.py fix, confirm GREEN. Don't write the fix first — the RED step proves the
# test actually covers the bug.

# GOTCHA #10 — TIMEOUTS (repo AGENTS.md). pytest suites here can touch CUDA mocks; wrap every pytest
# invocation in `timeout 120` AND set the bash-tool timeout above it. Never run the live daemon.
```

## Implementation Blueprint

### Data models and structure

None added. The fix reads an existing `_load_error: str | None` attribute and reuses the existing `_arm_response()` return shape. No data model, schema, or API change (`_dispatch()` still returns a `dict`; the response gains an `error` field only on the failure path, which `format_result` already handles).

### Implementation Tasks (ordered — TDD: tests RED first, then fix GREEN)

```yaml
Task 1: ADD the two RED tests (tests/test_daemon.py).
  - PLACE them near the existing cross-mode tests (after test_failed_cross_mode_toggle_status_
    snapshot_is_honest at ~line 3910), in the same section.
  - ADD (verbatim structure; reuses _failing_second_spawn_factory + _make_lazy_daemon + ControlServer):

        def test_dispatch_toggle_cross_mode_lite_to_normal_failure_returns_ok_false():
            """Cross-mode toggle (armed-in-lite → normal reload fails) surfaces ok:false+error.

            Regression for bugfix Issue 1: _dispatch's toggle branch returned {ok:true, listening:false}
            (silent) when a cross-mode reload failed, because arm_attempted was False. The fix routes a
            FRESH _load_error through _arm_response() so voicectl prints 'error: model load failed: ...'
            (exit 1), matching start/start-lite.
            """
            spawns: list = []
            d, _fb = _make_lazy_daemon(host_factory=_failing_second_spawn_factory(spawns))
            d.start_lite()                                              # arm in lite (1st spawn succeeds)
            assert d.is_listening() and d._mode == "lite"
            srv = daemon.ControlServer(d)
            resp = srv._dispatch(json.dumps({"cmd": "toggle"}))         # lite→normal, 2nd spawn FAILS
            assert resp["ok"] is False
            assert "model load failed" in resp["error"]

        def test_dispatch_toggle_lite_cross_mode_normal_to_lite_failure_returns_ok_false():
            """Cross-mode toggle-lite (armed-in-normal → lite reload fails) surfaces ok:false+error.

            The normal→lite mirror of the test above (bugfix Issue 1).
            """
            spawns: list = []
            d, _fb = _make_lazy_daemon(host_factory=_failing_second_spawn_factory(spawns))
            d.start()                                                   # arm in normal (1st spawn succeeds)
            assert d.is_listening() and d._mode == "normal"
            srv = daemon.ControlServer(d)
            resp = srv._dispatch(json.dumps({"cmd": "toggle-lite"}))    # normal→lite, 2nd spawn FAILS
            assert resp["ok"] is False
            assert "model load failed" in resp["error"]

  - VERIFY imports present: `json` and `daemon` (the module) are already imported in test_daemon.py
    (existing tests use json.dumps / daemon.cfg_to_kwargs). If not, add them.
  - RUN (confirm RED — both FAIL today because resp["ok"] is True):
        timeout 120 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'cross_mode_lite_to_normal_failure or cross_mode_normal_to_lite_failure'
    # Expected pre-fix: 2 FAILED (resp["ok"] is True, no "error" key).

Task 2: IMPLEMENT the fix in voice_typing/daemon.py — the 'toggle' branch (1927-1938).
  - FIND the toggle branch. INSERT one snapshot line BEFORE `self._daemon.toggle()` and one
    conditional return BEFORE the final `return {"ok": True, **self._daemon.status_snapshot()}`:
        if cmd == "toggle":
            was_listening = self._daemon.is_listening()
            load_error_before = getattr(self._daemon, "_load_error", None)   # ← ADD (bugfix Issue 1)
            self._daemon.toggle()
            # ... existing comment ...
            arm_attempted = not was_listening or self._daemon.is_listening()
            if arm_attempted:
                return self._arm_response()
            # Cross-mode toggle (was_listening True, now disarmed => arm_attempted False) may have
            # FAILED its reload: _load_host resets _load_error=None per attempt (daemon.py:726), so
            # (None before + truthy after) reliably means a failure during THIS toggle. Route it
            # through _arm_response() so voicectl prints 'error: model load failed: ...' (exit 1)
            # instead of a silent {ok:true, listening:false}. (bugfix Issue 1 / P1.M1.T1.S1)
            if load_error_before is None and getattr(self._daemon, "_load_error", None):   # ← ADD
                return self._arm_response()                                                # ← ADD
            return {"ok": True, **self._daemon.status_snapshot()}
  - DO NOT change the arm_attempted computation, the arm_attempted=True path, or anything else.

Task 3: IMPLEMENT the SAME fix in the 'toggle-lite' branch (1945-1951).
  - Mirror Task 2 exactly: snapshot `load_error_before` before `self._daemon.toggle_lite()`, and add
    the same `if load_error_before is None and getattr(...): return self._arm_response()` before the
    final `return {"ok": True, **self._daemon.status_snapshot()}`.

Task 4: VERIFY GREEN + no regressions (run the gates below). No git commit unless the orchestrator
  directs it. If asked, message: "P1.M1.T1.S1: surface cross-mode toggle load failures as ok:false in _dispatch".
```

### Implementation Patterns & Key Details

```python
# The whole fix is 2 added lines per branch (×2 branches). Correctness rests on ONE invariant:
# snapshot _load_error BEFORE the toggle call; route through _arm_response() iff a FRESH error
# (None→truthy) appeared on the not-arm_attempted (disarm) path.
#
# Why this is correct in all four toggle cases (see Gotcha #4):
#   same-mode disarm  : _load_error None→None (no reload)  → new branch skipped → ok:true listening:off
#   cross-mode SUCCESS: is_listening() True → arm_attempted True → first branch → _arm_response → ok:true
#   cross-mode FAILURE: arm_attempted False + _load_error None→truthy → NEW branch → _arm_response → ok:false+error
#   first arm         : was_listening False → arm_attempted True → first branch → _arm_response
#
# Why reuse _arm_response() (don't reshape inline): it already centralizes the "ok:false+error when
# _load_error set and not listening" logic (daemon.py:1901), including the getattr(...,None) duck-typing
# for the _StubDaemon test double. Routing through it keeps ONE source of truth for arm-failure responses.
#
# Why ctl.py is untouched: format_result() checks ok:false FIRST (ctl.py:63 -> 'error: ...', exit 1)
# before the toggle/start/stop listening branch (ctl.py:103). An ok:false dispatch response renders
# correctly with zero client changes.
```

### Integration Points

```yaml
CONTROL SOCKET (ControlServer._dispatch):
  - toggle (1927) + toggle-lite (1945) branches now surface cross-mode reload failures as
    {ok:false, error:"model load failed: ..."} via _arm_response(). start/start-lite already did.

DAEMON LAYER (voice_typing/daemon.py — UNCHANGED):
  - toggle() (1419) / toggle_lite() (1452): correct — disarm + set _load_error on failed cross-mode
    reload. _load_host() (698) resets _load_error=None per attempt (726). _arm_response() (1901):
    correct. NONE of these are edited.

CLIENT (voice_typing/ctl.py — UNCHANGED):
  - format_result() (48): ok:false -> 'error: ...', exit 1 (ctl.py:63), checked before the listening
    branch. The existing was_listening=False arm-failure path (test_dispatch_toggle_arm_failure_
    returns_ok_false in test_voicectl.py:368) is UNCHANGED — it exercises the arm_attempted=True path,
    which this fix does not touch.

NO INTERFACE CHANGES:
  - No new public API, no config, no state.json change. The fix makes toggle/toggle-lite match the
    ok:false-on-load-failure contract PRD §4.2bis already documents for arm commands.
```

## Validation Loop

> Repo AGENTS.md (voice-typing) MANDATES timeouts: wrap every pytest in `timeout 120` AND set the
> bash-tool `timeout` above it. Use .venv/bin/python (machine aliases python3→uv run). Never run the
> live daemon. No ruff/mypy in this project.

### Level 1: TDD red→green (the load-bearing gate)

```bash
cd /home/dustin/projects/voice-typing
echo "--- (RED, before Task 2/3) the two new tests FAIL ---"
timeout 120 .venv/bin/python -m pytest tests/test_daemon.py -q \
  -k 'cross_mode_lite_to_normal_failure or cross_mode_normal_to_lite_failure' 2>&1 | tail -6
# Expected pre-fix: 2 failed (resp["ok"] is True). [After Task 1 only, before the daemon.py edit.]
echo "--- (GREEN, after Task 2/3) the two new tests PASS ---"
timeout 120 .venv/bin/python -m pytest tests/test_daemon.py -q \
  -k 'cross_mode_lite_to_normal_failure or cross_mode_normal_to_lite_failure' 2>&1 | tail -6
# Expected post-fix: 2 passed.
```

### Level 2: The fix is in both branches + the four paths behave correctly (one-off functional check)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
import json, inspect
from voice_typing import daemon
src = inspect.getsource(daemon.ControlServer._dispatch)
# both branches snapshot _load_error before the toggle call
assert src.count('load_error_before = getattr(self._daemon, "_load_error", None)') == 2, \
    "expected the load_error_before snapshot in BOTH toggle and toggle-lite branches"
# both branches route a fresh error through _arm_response (2 occurrences of the new conditional)
assert src.count('if load_error_before is None and getattr(self._daemon, "_load_error", None):') == 2, \
    "expected the fresh-error route in BOTH branches"
# _arm_response itself is UNCHANGED (still returns ok:false+error when _load_error set + not listening)
ar = inspect.getsource(daemon.ControlServer._arm_response)
assert 'model load failed' in ar and '"ok": False' in ar
print("L2 PASS: fix present in both branches; _arm_response unchanged")
PY
# Expected: "L2 PASS". (Counts == 2 proves both toggle and toggle-lite were fixed, not just one.)
```

### Level 3: No regressions across the dispatch / socket / voicectl suites

```bash
cd /home/dustin/projects/voice-typing
echo "--- cross-mode + toggle daemon tests (incl. the existing daemon-level ones) ---"
timeout 120 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'cross_mode_toggle or toggle_failed or toggle_while_armed or cross_mode_lite_to_normal_failure or cross_mode_normal_to_lite_failure' 2>&1 | tail -6
echo "--- full control-socket suite (dispatch logic; _StubDaemon paths) ---"
timeout 120 .venv/bin/python -m pytest tests/test_control_socket.py -q 2>&1 | tail -6
echo "--- voicectl suite (format_result ok:false rendering; the arm-failure path stays green) ---"
timeout 120 .venv/bin/python -m pytest tests/test_voicectl.py -q 2>&1 | tail -6
# Expected: all PASS. If test_dispatch_toggle_arm_failure_returns_ok_false (test_voicectl.py:368)
# fails, the fix accidentally changed the arm_attempted=True path — re-read the diff.
```

### Level 4: Scope — only daemon.py (_dispatch) + test_daemon.py changed

```bash
cd /home/dustin/projects/voice-typing
echo "--- git diff touches ONLY voice_typing/daemon.py + tests/test_daemon.py ---"
git diff --name-only
git diff --name-only | grep -vE 'voice_typing/daemon\.py|tests/test_daemon\.py' | grep -E '\.py$|\.toml$|\.md$' && echo "L4 FAIL: out-of-scope file" || echo "L4 PASS: only daemon.py + test_daemon.py"
echo "--- confirm the correct machinery is UNTOUCHED ---"
git diff voice_typing/daemon.py | grep -E '^[+-].*(_arm_response|def toggle\b|def toggle_lite|def _load_host|_load_error = None  # per attempt)' && echo "L4 CHECK: review — did you accidentally edit correct machinery?" || echo "L4 PASS: _arm_response/toggle/toggle_lite/_load_host untouched"
git diff --name-only | grep -E 'ctl\.py' && echo "L4 FAIL: ctl.py edited (should be unchanged)" || echo "L4 PASS: ctl.py untouched"
# Expected: "only daemon.py + test_daemon.py" + the correct machinery untouched + ctl.py untouched.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: 2 new tests RED before the fix, GREEN after (TDD proof).
- [ ] L2: the snapshot + conditional route present in BOTH branches (count == 2 each); `_arm_response` unchanged.
- [ ] L3: test_daemon.py (cross-mode/toggle), test_control_socket.py, test_voicectl.py all green.
- [ ] L4: only `voice_typing/daemon.py` + `tests/test_daemon.py` changed; `_arm_response`/`toggle`/`toggle_lite`/`_load_host`/`ctl.py` untouched.

### Feature Validation
- [ ] `_dispatch("toggle")` on a failed lite→normal reload → `{"ok": False, "error": "model load failed: ..."}`.
- [ ] `_dispatch("toggle-lite")` on a failed normal→lite reload → same.
- [ ] Same-mode disarm still → `{"ok": True, "listening": false}`; first-arm path unchanged.
- [ ] `voicectl toggle`/`toggle-lite` on a cross-mode failure prints `error: model load failed: ...` exit 1 (via the unchanged `format_result`).

### Code Quality Validation
- [ ] Fix mirrors exactly in both branches; `getattr(..., "_load_error", None)` keeps `_StubDaemon` on the ok:true path.
- [ ] `load_error_before` snapshotted BEFORE the toggle call; `load_error_before is None` guard preserved.
- [ ] No inline response reshaping — routes through the existing `_arm_response()` (single source of truth).

### Scope Boundary Validation
- [ ] `_arm_response()`, `toggle()`, `toggle_lite()`, `_load_host()`, `ctl.py` unmodified.
- [ ] No config / state.json / README / systemd changes (Mode A: no user-facing surface change).
- [ ] No live daemon run; all gates use hermetic test doubles (`_failing_second_spawn_factory` + `_FakeHost`).

---

## Anti-Patterns to Avoid

- ❌ Don't edit `_arm_response()`, `toggle()`, `toggle_lite()`, `_load_host()`, or `ctl.py` — they are all correct (the bug is ONLY in `_dispatch()` response routing).
- ❌ Don't snapshot `_load_error` AFTER the toggle only — `_load_host` resets it per attempt, so you can't tell fresh from stale. Capture `load_error_before` BEFORE the call.
- ❌ Don't drop the `load_error_before is None` guard — it prevents a stale error on a pure disarm (no reload) from false-firing.
- ❌ Don't fix only ONE branch — `toggle` and `toggle-lite` have the identical bug; mirror the fix in both (L2 asserts count == 2).
- ❌ Don't change the `arm_attempted` computation or the `arm_attempted=True` path — add ONE branch in the not-arm_attempted fallthrough only (Gotcha #4).
- ❌ Don't reshape the response inline — route through `_arm_response()` so there's one source of truth for arm-failure responses.
- ❌ Don't write the new tests to call `d.toggle()` directly — the existing tests already do that and pass today; the gap is the WIRE response, which only `_dispatch()` exercises. Use `ControlServer(d)._dispatch(...)`.
- ❌ Don't skip the TDD RED step — run the two tests against unfixed daemon.py first and confirm they FAIL (proves they cover the bug).
- ❌ Don't run the live systemd daemon or unwrapped `voicectl` as a gate — use the hermetic test doubles; wrap every pytest in `timeout 120` (repo AGENTS.md).

---

## Confidence Score

**9.5/10** for one-pass implementation success. The bug, the correct reuse target (`_arm_response()`), the `_load_error` per-attempt reset, the exact test factory + `ControlServer(d)._dispatch()` construction pattern, and the client-side `ok:false` rendering are all verified verbatim with line numbers. The fix is 2 lines × 2 branches, guarded by the `load_error_before is None` check, and the four toggle paths are enumerated (Gotcha #4) so the agent can confirm none regress. The TDD red→green is concrete (the tests assert `resp["ok"] is False`, which is `True` today → RED). The −0.5 is the standard "moving tree" caveat (the cited line numbers can drift): mitigated by L1 (RED proves the tests target the live bug) + L2 (counts prove both branches fixed) + L4 (the correct machinery untouched).