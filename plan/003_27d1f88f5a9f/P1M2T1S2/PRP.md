# PRP — P1.M2.T1.S2: Thread the "loading models…" hint through ctl.py + status during first arm

## Goal

**Feature Goal**: Make `voicectl start`/`voicectl toggle` give the user feedback during the lazy-load first arm (PRD §4.2bis / delta_prd line 70). Today the first arm blocks ~1–3 s inside `_load_recorder()` (landed by P1.M2.T1.S1) while voicectl shows **nothing** — it is blocked reading the single-line response. After this task: voicectl prints a `loading models…` hint to stderr if the arm is slow (i.e. actually loading; resident arms reply in ms and print nothing), AND a model-load **failure** is surfaced as `{"ok":false,"error":...}` (PRD §4.2bis: "the arm command returns `{"ok":false,"error":"..."}`") so voicectl prints `error: model load failed: …` + exit 1 instead of a silent `listening: off`.

**Deliverable** (edits to `voice_typing/ctl.py` + `voice_typing/daemon.py` + `tests/test_voicectl.py`; no new files):
1. `voice_typing/ctl.py` — (a) `import threading`; (b) a `_LOADING_HINT_DELAY = 0.3` constant; (c) a new `_send_command_with_loading_hint()` helper that wraps `send_command` with a `threading.Timer` printing `loading models… (first arm, ~1–3 s)` to stderr if no reply within the delay (cancelled in `finally`); (d) `main()` routes `start`/`toggle` through the helper, other commands through plain `send_command`; (e) module/main docstrings note the hint. `format_result` is UNCHANGED (the hint is a stderr side-channel during the block; the failure path already maps `ok:false`→`error:`).
2. `voice_typing/daemon.py` — `ControlServer._dispatch` (start/toggle branches): surface a failed model load as `{"ok":false,"error":...}` via a new `_arm_response()` helper that reads `getattr(self._daemon, "_load_error", None)` (the attr P1.M2.T1.S1 adds). stop/status/quit UNCHANGED.
3. `tests/test_voicectl.py` — ADD: `_SlowStartStubDaemon` + `_FailingLoadStubDaemon` stubs and tests for (hint fires on slow start), (no hint on fast arm), (no hint on status/stop), (load failure → ok:false/exit 1), (`_dispatch` start/toggle-failure unit tests). Existing Layer A/B/C tests pass UNCHANGED.

**Success Definition**:
- (a) `voicectl start` against a daemon whose `start()` blocks > `_LOADING_HINT_DELAY` prints `loading models…` to **stderr** (stdout stays clean for scripts); a resident (instant) arm prints **nothing** extra.
- (b) A failed first-arm load makes `_dispatch` return `{"ok":false,"error":"model load failed: …"}` → `voicectl start` prints `error: model load failed: …` + exits 1 (NOT `listening: off` + exit 0).
- (c) `voicectl status`/`stop`/`quit` behavior is byte-identical (plain `send_command`, no hint).
- (d) All existing `test_voicectl.py` tests pass UNCHANGED; the new tests pass.
- (e) `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- (f) Only `ctl.py`, `daemon.py` (`_dispatch`/`_arm_response` only), `test_voicectl.py` change. No `status_snapshot()` field additions, no `feedback.py`, no config (those are P1.M2.T2.S1 / P1.M3).

## User Persona

**Target User**: the operator running `voicectl start` (or the Hyprland keybind → `voicectl toggle`) for the first time after daemon boot, or after the idle-unload reclaimed VRAM.

**Use Case**: The user arms the mic; on the first arm the daemon spends ~1–3 s loading `small.en` + `distil-large-v3` onto the GPU. The user needs to know the daemon didn't hang.

**User Journey**: User runs `voicectl start` (or taps the hotkey). If models aren't resident, after ~0.3 s voicectl prints `loading models… (first arm, ~1–3 s)` (stderr); ~1–3 s later it prints `listening: on`. If the load fails (CUDA/cuDNN error), voicectl prints `error: model load failed: …` + exits 1.

**Pain Points Addressed**: today the first arm shows no feedback for seconds (looks hung); and a load failure shows `listening: off` with no explanation (looks like the toggle just didn't take).

## Why

- **PRD §4.2bis is explicit**: "`loading` — first arm in progress … The arm command blocks here; `voicectl` prints a `loading models…` hint." and "If the load fails … the arm command returns `{"ok":false,"error":"..."}`." This task delivers exactly those two user-facing requirements; the load *mechanism* is P1.M2.T1.S1 (parallel, "Ready").
- **The hint is necessarily client-side.** `start()`/`toggle()` block *inside* `_load_recorder()` (P1.M2.T1.S1), so the JSON response is built only AFTER the load completes — it can never carry `phase:"loading"` on a success. Under the one-line-request/one-line-response protocol there is no in-band interim signal. So voicectl must print the hint *during its own blocking read*, which only the client can do. (research §2 — the item's part (c) "response carries phase='loading'" cannot fire on success; the delta_prd's "prints it while the first arm blocks" is the operative framing.)
- **Failure must be loud, not silent.** Today `_dispatch` always returns `{"ok":true,...}` even when `start()`'s load failed and suppressed the arm → voicectl renders `listening: off` (exit 0), indistinguishable from a successful stop. PRD §4.2bis mandates `ok:false`. P1.M2.T1.S1 leaves `start()` returning `None` and does NOT touch `_dispatch` — so this falls to T1.S2 (the "thread through ctl + response" surface). (research §1, §4.)
- **Complementary, not conflicting, with T2.S1.** T2.S1 (later) adds `phase`/`models_loaded` to `status_snapshot()` + `feedback.py` + ctl `status` rendering. This task touches none of those; `_arm_response`'s `**status_snapshot()` spread will carry T2.S1's future fields automatically.

## What

**ctl.py** — add a delay-thresholded stderr hint for `start`/`toggle`. `threading.Timer(_LOADING_HINT_DELAY, ...)` prints `loading models… (first arm, ~1–3 s)` to stderr; `send_command` runs normally and the timer is cancelled in `finally` when the reply arrives. The threshold (0.3 s) is far below the ~1 s minimum load and far above local-socket round-trip latency, so it fires only on a real load (no flicker on resident arms). `format_result` is untouched.

**daemon.py** — `_dispatch`'s `start` and `toggle`-arm branches call a new `_arm_response()` that returns `{"ok":false,"error":"model load failed: {load_error}"}` when `getattr(daemon,"_load_error",None)` is set and the daemon is left not-listening; otherwise `{"ok":true,**status_snapshot()}`. `toggle` captures `was_listening` before the call so only an ARM attempt (not a disarm) is checked.

### Success Criteria

- [ ] `import threading` + `_LOADING_HINT_DELAY = 0.3` present in ctl.py; `_send_command_with_loading_hint()` exists; `main()` routes start/toggle through it.
- [ ] `_arm_response()` exists on `ControlServer`; `_dispatch` start/toggle use it (toggle only on the arm path).
- [ ] Slow start (>delay) → `loading models…` on stderr; fast arm → no hint; status/stop → no hint.
- [ ] Load failure → `_dispatch` returns `{"ok":false,"error":"model load failed: …"}`; voicectl exits 1 with `error:` text.
- [ ] All pre-existing `test_voicectl.py` tests pass unchanged.
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] `git status --short` == `voice_typing/ctl.py`, `voice_typing/daemon.py`, `tests/test_voicectl.py` only.

## All Needed Context

### Context Completeness Check

_Pass._ The 3-way boundary is pinned to delta_prd citations; the timing proof (why client-side) is in research §2; the `_load_error`-staleness soundness argument is in research §4.1; the reason a Timer (not socket timeout) is required (`send_command` uses `makefile`, incompatible with `settimeout`) is in research §3; and every edit is given as exact oldText→newText against the current file, with verbatim test additions. The new tests use STUB daemons that simulate T1.S1's `_load_error` attr + blocking start, so they are independent of T1.S1's exact internals.

### Documentation & References

```yaml
# MUST READ — boundary + timing proof + design + test plan (load-bearing)
- docfile: plan/003_27d1f88f5a9f/P1M2T1S2/research/loading_hint_client_side_design.md
  why: "§1 the 3-way boundary (T1.S1=mechanism/_load_error; T1.S2=hint+ok:false response; T2.S1=status_snapshot
        phase/models_loaded + status rendering + feedback). §2 timing proof: start() blocks in _load_recorder ->
        response built AFTER load -> hint MUST be client-side; item part (c) can't fire on success. §3 Timer not
        settimeout (send_command uses makefile). §4 _dispatch ok:false design + _load_error staleness soundness +
        toggle arm-vs-disarm detection. §5 verified code facts. §6 test plan. §7 scope boundaries."
  section: "ALL load-bearing. §1 (boundary), §2 (client-side), §4 (ok:false) are the core."

# MUST READ — the contract for what exists when this task runs (T1.S1, parallel "Ready")
- file: plan/003_27d1f88f5a9f/P1M2T1S2/../../../../PRD.md   # (PRD §4.2bis — see below instead)
- docfile: plan/003_27d1f88f5a9f/P1M2T1S1/PRP.md
  why: "T1.S1 adds self._load_error (str|None), self._models_loaded, self._loading, self._load_cond; makes start()
        call _load_recorder() BEFORE _arm() and return None on failure (arm suppressed). It does NOT edit _dispatch
        (its PRP's edits are __init__/_load_recorder/8 guards/run/main/docstrings + test_daemon.py). It drives phase
        via feedback.set_phase. CONFIRM: start()/toggle() BLOCK on _load_recorder (so the client hint is needed) and
        _load_error is set on failure + reset to None at the start of each fresh _load_recorder attempt."
  critical: "Do NOT duplicate T1.S1's work (no __init__/_load_recorder/8-guard edits here). CONSUME its _load_error
             attr + blocking-start behavior. If T1.S1 lands start() returning a bool instead of None, prefer reading
             that return over the _load_error+is_listening() inference — but the getattr approach is robust either way."

# THE AUTHORITATIVE FEATURE SPEC + the exact task line
- docfile: plan/003_27d1f88f5a9f/delta_prd.md
  why: "Line 70 (M2.T1.S2): 'Thread the loading models… hint through ctl.py (status/loading phase) and ensure voicectl
        prints it while the first arm blocks.' Line 67 (M2.T1): 'On load failure: revert to unloaded, return
        {"ok":false,"error":...}.' Line 74 (M2.T2.S1): status_snapshot phase/models_loaded + ctl STATUS rendering +
        feedback.py — OUT OF SCOPE here. §4.2bis (PRD): the lifecycle + the ok:false mandate."
  critical: "My lane = the ARM-command hint + the ARM-command ok:false response. NOT status_snapshot fields, NOT the
             status command rendering, NOT feedback.py (all T2.S1)."

# THE PRD LIFECYCLE (the contract)
- file: PRD.md
  why: "§4.2bis: 'loading — first arm in progress … The arm command blocks here; voicectl prints a loading models… hint.'
        and 'If the load fails … the arm command returns {\"ok\":false,\"error\":\"...\"}'. §4.8: voicectl exit codes
        (0 success, 1 logical failure, 2 not-running)."

# THE FILES BEING EDITED (current structure — match oldText exactly)
- file: voice_typing/ctl.py
  why: "format_result is PURE (no I/O; UNCHANGED here). send_command uses makefile('r') (NO settimeout). main() does
        parse->validate->resolve->send->format->print. _COMMANDS/_EX_USAGE are the module constants to neighbor the
        new _LOADING_HINT_DELAY. Edit sites: the stdlib import block; after send_command (insert helper); the main()
        try-block around send_command."
  critical: "Do NOT change format_result (the hint is stderr-side in main; the failure path uses format_result's EXISTING
             ok:false->'error:' branch). Do NOT change send_command (it is unit-tested; add a wrapper)."

- file: voice_typing/daemon.py
  why: "ControlServer._dispatch (1079): start/toggle/stop -> {'ok':True,**status_snapshot()}; quit -> shutting_down;
        errors -> {'ok':False,'error':...}. _handle (1048) per-connection thread. is_listening() exists on the daemon."
  critical: "Edit ONLY the start + toggle branches + add _arm_response. Leave stop/status/quit/error branches UNCHANGED.
             Use getattr(self._daemon,'_load_error',None) so the duck-typed test _StubDaemon (no _load_error) stays on
             the ok:true path. Do NOT touch status_snapshot()'s field set (T2.S1)."

# THE TEST FILE (stubs + fixtures to mirror)
- file: tests/test_voicectl.py
  why: "_StubDaemon (duck-type: start/toggle/stop/request_shutdown/is_listening/status_snapshot; NO _load_error).
        running_server fixture: ControlServer(_StubDaemon(), socket_path=tmp) + srv.start()/stop(). Layer A=format_result
        (pure), Layer B=round-trip (fast stub), Layer C=exit-2 paths. capsys is the capture fixture used."
  critical: "Existing Layer A/B/C tests must pass UNCHANGED: the fast stub replies in ms (≪0.3s) so the hint never fires;
             format_result is untouched. ADD a _SlowStartStubDaemon (sleep in start) + _FailingLoadStubDaemon (start sets
             _load_error, doesn't arm). ADD `import json` + `import time` to the top import block."
```

### Current Codebase tree (relevant slice — the 3 files this task edits)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── ctl.py           # EDIT: +import threading, +_LOADING_HINT_DELAY, +_send_command_with_loading_hint, main() branch, docstrings.
│   └── daemon.py        # EDIT: ControlServer._dispatch (start/toggle) + NEW _arm_response. status_snapshot UNCHANGED.
└── tests/
    └── test_voicectl.py # EDIT: +import json/time, +2 stubs, +new tests. Existing tests unchanged.
# P1.M2.T1.S1 (parallel) edits daemon.py (__init__/_load_recorder/guards/run/main) + test_daemon.py — different regions.
# P1.M2.T2.S1 (later) edits status_snapshot + feedback.py + ctl status rendering — different regions.
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/ctl.py           # +threading import, +_LOADING_HINT_DELAY, +_send_command_with_loading_hint, main() start/toggle branch.
voice_typing/daemon.py        # ControlServer: +_arm_response, _dispatch start/toggle use it.
tests/test_voicectl.py        # +import json/time, +_SlowStartStubDaemon/_FailingLoadStubDaemon, +tests.
# NOTHING ELSE. status_snapshot fields/feedback.py/config/README = T2.S1 / P1.M3. _load_recorder = T1.S1.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE HINT IS CLIENT-SIDE, NOT A RESPONSE RENDER. start()/toggle() BLOCK inside _load_recorder()
#   (P1.M2.T1.S1), so _dispatch builds the response ONLY AFTER the load completes. The response can therefore
#   never carry phase:'loading' on a SUCCESS (phase is already 'idle'). The item's part (c) ("if phase='loading',
#   augment 'listening: on (loading models…)'") cannot fire on success — do NOT try to implement it as a
#   format_result branch (it would be dead code). Print the hint DURING the blocking read, from the client.
#   (research §2.)

# CRITICAL #2 — USE threading.Timer, NOT socket.settimeout. send_command uses sock.makefile('r').readline(); its
#   docstring states makefile is INCOMPATIBLE with settimeout ("makefile raises if the socket has a timeout"). A
#   socket timeout would break send_command. Start a daemon threading.Timer; cancel it in `finally` when send_command
#   returns. send_command itself is UNCHANGED (it is unit-tested directly). (research §3.)

# CRITICAL #3 — THE HINT GOES TO STDERR, result to stdout. main() does `print(text)` (stdout). The hint on stderr
#   keeps the structured stdout clean for scripts/wrappers (consistent with the exit-2/exit-64 messages, already on
#   stderr). On a terminal both render, reading naturally: "loading models…\nlistening: on".

# CRITICAL #4 — THE 0.3 s THRESHOLD MUST NOT FLICKER ON RESIDENT ARMS. A resident arm replies in ~ms; the timer
#   (0.3 s) is cancelled in `finally` before it fires. Keep _LOADING_HINT_DELAY well above socket RTT (~ms) and well
#   below the ~1 s minimum load. Do NOT set it near either boundary. (research §2.)

# CRITICAL #5 — _dispatch MUST STILL RETURN ok:true FOR THE FAST STUB IN TESTS. The duck-typed _StubDaemon has NO
#   _load_error attr. Use getattr(self._daemon, "_load_error", None) (default None) so the absence of the attr (the
#   stub, or a real daemon that never tried to load) stays on the ok:true path. Never do `self._daemon._load_error`
#   directly (AttributeError on the stub). (research §4.)

# CRITICAL #6 — _load_error STALENESS IS SELF-CLEANING ON THE ARM PATH. _load_recorder (T1.S1) resets _load_error=None
#   at the start of each fresh load and sets it only on a fresh failure. A disarm toggle requires the daemon to have
#   been listening (a prior SUCCESS → _load_error=None); a failed-load state is never listening → a toggle there ARMS
#   (re-running _load_recorder, resetting _load_error). So a set _load_error read on an arm attempt is always THIS
#   attempt's failure. Detect arm-vs-disarm for toggle via was_listening=is_listening() BEFORE toggle(). (research §4.1.)

# CRITICAL #7 — DO NOT TOUCH format_result. The hint is a stderr side-channel in main(); the failure path uses
#   format_result's EXISTING `if response.get("ok") is not True: return f"error: {…}", 1` branch. Adding a
#   format_result branch for phase='loading' would be dead code (see CRITICAL #1). The status-command model/phase
#   rendering is T2.S1's lane — leave it.

# CRITICAL #8 — DO NOT ADD phase/models_loaded TO status_snapshot(). That is T2.S1 (delta_prd line 74). This task's
#   _arm_response does `**status_snapshot()` (spreads whatever T2.S1 later adds) — complementary, not conflicting.

# CRITICAL #9 — DO NOT EDIT feedback.py, config.py/config.toml, __init__/_load_recorder/the 8 guards/run/main,
#   status_snapshot's body, or any test_daemon.py test. Those are T1.S1 / T2.S1 / P1.M3.

# GOTCHA #10 — FULL PATHS in every bash command (zsh aliases: python3->uv run). .venv/bin/python, never bare
#   python/pytest/uv. (research §5; system_context.)

# GOTCHA #11 — pytest>=9.1.1 is the runner; NO ruff/mypy configured. Validation = py_compile + pytest. (research §5.)

# GOTCHA #12 — NEW TESTS USE STUB DAEMONS (no GPU, no RealtimeSTT). _SlowStartStubDaemon sleeps in start() to simulate
#   the blocking load; _FailingLoadStubDaemon sets _load_error + doesn't arm. They simulate T1.S1's contract so the
#   tests are independent of T1.S1's exact _load_recorder internals. ControlServer handles each connection in its own
#   thread, so a sleeping stub blocks only that handler (voicectl blocks on readline — exactly the real first-arm timing).
```

## Implementation Blueprint

### Data models and structure

None. No schema/config/types change. New ctl.py module constant `_LOADING_HINT_DELAY: float`; new ctl.py function `_send_command_with_loading_hint`; new `ControlServer._arm_response` method. `format_result` unchanged. Consumes P1.M2.T1.S1's `self._load_error` attr (read-only, via `getattr`).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/ctl.py — 4 edits in ONE edit call (import, constant, helper, main branch + docstrings).
  EDIT 1a — stdlib import block: add `import threading`.
    OLD:
      import argparse
      import json
      import socket
      import sys
    NEW:
      import argparse
      import json
      import socket
      import sys
      import threading
  EDIT 1b — add the delay constant after _EX_USAGE.
    OLD:
      _EX_USAGE: int = 64
    NEW:
      _EX_USAGE: int = 64
      # Seconds an arm command (start/toggle) may block before voicectl prints a 'loading models…' hint to stderr.
      # The FIRST arm blocks ~1–3 s while the daemon lazy-loads models (PRD §4.2bis); a resident arm replies in ms,
      # so this fires ONLY on a real load (no flicker on instant arms). Tuned well below the ~1 s minimum load and
      # well above local socket round-trip latency. (P1.M2.T1.S2.)
      _LOADING_HINT_DELAY: float = 0.3
  EDIT 1c — insert _send_command_with_loading_hint between send_command and _build_parser.
    OLD:
          return json.loads(line)         # json.JSONDecodeError is a ValueError subclass


      def _build_parser() -> argparse.ArgumentParser:
    NEW:
          return json.loads(line)         # json.JSONDecodeError is a ValueError subclass


      def _send_command_with_loading_hint(socket_path: str, cmd: str) -> dict:
          """send_command for start/toggle: print a 'loading models…' hint to stderr if the daemon doesn't reply
          within _LOADING_HINT_DELAY (PRD §4.2bis — "voicectl prints a loading models… hint" while the first arm blocks).

          Why CLIENT-SIDE: start()/toggle() block inside the daemon's _load_recorder() (~1–3 s), so the JSON response
          is produced only AFTER the load completes — an in-band 'loading' signal is impossible under the one-line-
          request/one-line-response protocol. Why a Timer (not socket timeout): send_command uses makefile('r'),
          which is incompatible with settimeout. The hint goes to STDERR so stdout (the structured result) stays
          clean for scripts; the Timer is cancelled in `finally`, so a fast (resident) arm never prints it.
          """
          timer = threading.Timer(
              _LOADING_HINT_DELAY,
              lambda: print("loading models… (first arm, ~1–3 s)", file=sys.stderr, flush=True),
          )
          timer.daemon = True
          timer.start()
          try:
              return send_command(socket_path, cmd)
          finally:
              timer.cancel()


      def _build_parser() -> argparse.ArgumentParser:
  EDIT 1d — main() routes start/toggle through the helper.
    OLD:
          # 2. Talk to the daemon. Connect OSError -> exit 2; protocol ValueError -> exit 1.
          try:
              response = send_command(socket_path, cmd)
          except OSError as exc:                       # FileNotFoundError / ConnectionRefusedError / PermissionError
    NEW:
          # 2. Talk to the daemon. Connect OSError -> exit 2; protocol ValueError -> exit 1.
          #    start/toggle may block ~1–3 s on the first arm while the daemon lazy-loads models (PRD §4.2bis); route
          #    them through _send_command_with_loading_hint so voicectl prints a 'loading models…' hint if the reply is
          #    slow (resident arms reply in ms → no hint). stop/status/quit use plain send_command.
          try:
              if cmd in ("start", "toggle"):
                  response = _send_command_with_loading_hint(socket_path, cmd)
              else:
                  response = send_command(socket_path, cmd)
          except OSError as exc:                       # FileNotFoundError / ConnectionRefusedError / PermissionError
  - WHY: threading (stdlib) for the non-blocking timer; the wrapper keeps send_command pure; the main branch localizes
    the hint to arm commands only. format_result is NOT touched (CRITICAL #7).
  - DO NOT: use settimeout (CRITICAL #2); print the hint to stdout (CRITICAL #3); set the delay near a boundary
    (CRITICAL #4); change format_result/send_command (CRITICAL #7); add phase/models_loaded to status (CRITICAL #8).

Task 2: EDIT voice_typing/daemon.py — 2 edits (add _arm_response; rewire _dispatch start/toggle).
  EDIT 2a — add _arm_response immediately before _dispatch.
    OLD:
          def _dispatch(self, line: str) -> dict:
              """Parse one request line -> dispatch cmd -> response dict. Never raises (robustness)."""
    NEW:
          def _arm_response(self) -> dict:
              """Build the response after a start/toggle ARM attempt (PRD §4.2bis / P1.M2.T1.S2).

              After P1.M2.T1.S1, start()/toggle() call _load_recorder() BEFORE arming; on a load failure the arm is
              suppressed (daemon stays not-listening) and self._load_error is set. Per §4.2bis the arm command MUST
              then return {"ok":false,"error":...} (NOT ok:true with listening:false, which voicectl would render as a
              silent 'listening: off'). _load_error is reset by _load_recorder on each fresh attempt and set only on a
              fresh failure, so a set value read on an arm attempt is always THIS attempt's failure (never stale — see
              P1.M2.T1.S2 research §4.1). getattr(..., None) keeps the duck-typed test _StubDaemon (no _load_error) on
              the ok:true path. The 'loading models…' hint itself is printed CLIENT-SIDE by ctl.py during the block;
              this method only shapes the (eventual) post-load response.
              """
              load_error = getattr(self._daemon, "_load_error", None)
              if load_error and not self._daemon.is_listening():
                  return {"ok": False, "error": f"model load failed: {load_error}"}
              return {"ok": True, **self._daemon.status_snapshot()}

          def _dispatch(self, line: str) -> dict:
              """Parse one request line -> dispatch cmd -> response dict. Never raises (robustness)."""
  EDIT 2b — rewire the start/toggle branches to use _arm_response.
    OLD:
              if cmd == "toggle":
                  self._daemon.toggle()
                  return {"ok": True, **self._daemon.status_snapshot()}
              if cmd == "start":
                  self._daemon.start()
                  return {"ok": True, **self._daemon.status_snapshot()}
              if cmd == "stop":
    NEW:
              if cmd == "toggle":
                  was_listening = self._daemon.is_listening()
                  self._daemon.toggle()
                  if not was_listening:            # this toggle attempted to arm -> a load may have failed (§4.2bis)
                      return self._arm_response()
                  return {"ok": True, **self._daemon.status_snapshot()}
              if cmd == "start":
                  self._daemon.start()
                  return self._arm_response()      # ok:false+error if the first arm's model load failed (§4.2bis)
              if cmd == "stop":
  - WHY: surfaces load failure as ok:false (PRD §4.2bis); toggle only checks on the arm path (was_listening False);
    getattr keeps the stub on the ok:true path (CRITICAL #5); stop/status/quit UNCHANGED.
  - DO NOT: read self._daemon._load_error directly (CRITICAL #5); check _load_error on a disarm toggle (CRITICAL #6);
    touch status_snapshot's body (CRITICAL #8); change stop/status/quit branches.

Task 3: EDIT tests/test_voicectl.py — add `import json` + `import time` to the top import block (which ALREADY has
        `import subprocess` from the bugfix-001 purity test — do NOT remove/duplicate it), then APPEND the new stubs +
        tests at END of file (verbatim in "Task 3 SOURCE").
  EDIT 3a — top import block: add json + time (keep the existing subprocess).
    OLD:
      import importlib.util
      import subprocess
      import sys
    NEW:
      import importlib.util
      import json
      import subprocess
      import sys
      import time
  PART B — APPEND the "Task 3 SOURCE" block at END of file.
  - WHY: stubs simulate T1.S1's contract (slow start, failed-load _load_error) so tests are hermetic (no GPU/models);
    existing tests use the fast stub → hint never fires → unchanged.
  - DO NOT: modify existing tests/stubs/fixtures; import RealtimeSTT/torch; depend on T1.S1's real _load_recorder.

Task 4: VALIDATE — run the Validation Loop L1-L4; fix until green. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M2.T1.S2: client-side 'loading models…' hint for start/toggle + _dispatch ok:false on load failure".
```

#### Task 3 SOURCE — APPEND at END of `tests/test_voicectl.py` (verbatim)

```python
# ===========================================================================
# P1.M2.T1.S2 — 'loading models…' hint (client-side, during the blocking first arm)
# + _dispatch ok:false on model-load failure (PRD §4.2bis). Stubs simulate T1.S1's
# contract (start() blocks on _load_recorder; _load_error set on failure) so these
# tests are hermetic — NO GPU / NO RealtimeSTT.
# ===========================================================================


class _SlowStartStubDaemon(_StubDaemon):
    """A _StubDaemon whose start() blocks briefly to simulate the ~1–3 s lazy model load."""
    def __init__(self, delay: float = 0.4):
        super().__init__()
        self._delay = delay

    def start(self):
        time.sleep(self._delay)   # simulate _load_recorder() blocking the arm (PRD §4.2bis)
        super().start()


class _FailingLoadStubDaemon(_StubDaemon):
    """Simulates T1.S1's failed-load state: start() does NOT arm + _load_error is set (§4.2bis)."""
    def __init__(self, error: str = "cuda init failed: no device"):
        super().__init__()
        self._load_error = error   # the attr P1.M2.T1.S1 adds on a failed _load_recorder()

    def start(self):
        self.calls.append("start")
        # load failed → arm suppressed → stays not-listening (mirrors T1.S1 start() when _load_recorder() is False)


def _server_for(stub, monkeypatch, tmp_path):
    """A ControlServer on a tmp socket backed by `stub` (mirrors the running_server fixture)."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    socket_path = str(tmp_path / "voice-typing" / "control.sock")
    srv = daemon.ControlServer(stub, socket_path=socket_path)
    srv.start()
    return srv, socket_path


def test_start_prints_loading_hint_when_arm_is_slow(monkeypatch, tmp_path, capsys):
    """voicectl start prints 'loading models…' to stderr when the arm blocks (PRD §4.2bis)."""
    monkeypatch.setattr(ctl, "_LOADING_HINT_DELAY", 0.02)   # fire well under the stub's 0.4 s
    srv, _socket_path = _server_for(_SlowStartStubDaemon(0.4), monkeypatch, tmp_path)
    try:
        code = ctl.main(["start"])
    finally:
        srv.stop()
    out, err = capsys.readouterr()
    assert code == 0
    assert "listening: on" in out
    assert "loading models" in err


def test_start_does_not_print_loading_hint_for_fast_arm(capsys, running_server):
    """A resident (instant) arm replies before the threshold → no hint (no flicker)."""
    code = ctl.main(["start"])
    out, err = capsys.readouterr()
    assert code == 0
    assert "listening: on" in out
    assert "loading models" not in err


def test_status_and_stop_do_not_print_loading_hint(capsys, running_server):
    """status/stop use plain send_command → never the loading-hint wrapper."""
    assert ctl.main(["status"]) == 0
    assert ctl.main(["stop"]) == 0
    _out, err = capsys.readouterr()
    assert "loading models" not in err


def test_start_load_failure_returns_ok_false_and_exit_one(monkeypatch, tmp_path, capsys):
    """A failed model load → _dispatch ok:false → voicectl 'error:' + exit 1 (PRD §4.2bis)."""
    srv, _socket_path = _server_for(_FailingLoadStubDaemon(), monkeypatch, tmp_path)
    try:
        code = ctl.main(["start"])
    finally:
        srv.stop()
    out, _err = capsys.readouterr()
    assert code == 1
    assert "error" in out and "model load failed" in out


def test_dispatch_start_returns_ok_false_with_load_error():
    """Unit: _dispatch('start') on a failed-load daemon → {'ok':False,'error':...} (the §4.2bis contract)."""
    srv = daemon.ControlServer(_FailingLoadStubDaemon(), socket_path="/tmp/unused-p1m2t1s2")
    resp = srv._dispatch(json.dumps({"cmd": "start"}))
    assert resp["ok"] is False
    assert "model load failed" in resp["error"]


def test_dispatch_toggle_arm_failure_returns_ok_false():
    """A toggle that attempts to arm + load fails → ok:false (was_listening=False path)."""
    srv = daemon.ControlServer(_FailingLoadStubDaemon(), socket_path="/tmp/unused-p1m2t1s2")
    resp = srv._dispatch(json.dumps({"cmd": "toggle"}))
    assert resp["ok"] is False and "model load failed" in resp["error"]


def test_dispatch_start_ok_true_when_no_load_error_attr():
    """The duck-typed _StubDaemon (no _load_error) → ok:true (existing-behavior guard)."""
    srv = daemon.ControlServer(_StubDaemon(), socket_path="/tmp/unused-p1m2t1s2")
    resp = srv._dispatch(json.dumps({"cmd": "start"}))
    assert resp["ok"] is True
    assert resp["listening"] is True   # _StubDaemon.start() arms
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — client-side delay-thresholded hint (the only way, given start() blocks on load). A daemon Timer prints
# to stderr only if the reply is slow; cancelled in finally so a fast (resident) arm prints nothing.
timer = threading.Timer(_LOADING_HINT_DELAY, lambda: print("loading models…", file=sys.stderr, flush=True))
timer.daemon = True; timer.start()
try: return send_command(socket_path, cmd)
finally: timer.cancel()

# PATTERN 2 — surface a model-load failure as ok:false (PRD §4.2bis). getattr default keeps duck-typed stubs on the
# ok:true path; is_listening() confirms the arm was suppressed (a successful arm would be listening).
load_error = getattr(self._daemon, "_load_error", None)
if load_error and not self._daemon.is_listening():
    return {"ok": False, "error": f"model load failed: {load_error}"}
return {"ok": True, **self._daemon.status_snapshot()}

# PATTERN 3 — toggle arm-vs-disarm. Only an ARM attempt can fail to load; capture was_listening BEFORE toggle().
was_listening = self._daemon.is_listening()
self._daemon.toggle()
if not was_listening: return self._arm_response()    # arm attempt
return {"ok": True, **self._daemon.status_snapshot()}  # disarm (fast, no load)

# ANTI-PATTERN — do NOT render the hint from the response (format_result branch on phase:'loading'). start() blocks
# inside _load_recorder, so by the time the response is built, phase is already 'idle' on success. Such a branch is
# dead code. Print the hint client-side DURING the blocking read. (CRITICAL #1, #7.)
```

### Integration Points

```yaml
UPSTREAM CONSUMED — P1.M2.T1.S1 (parallel "Ready"): self._load_error (str|None, set on failed _load_recorder, reset
  None on each fresh attempt); start()/toggle() block on _load_recorder before arming + suppress the arm on failure.
  This task READS _load_error (getattr) + relies on the blocking start; it does NOT edit T1.S1's regions.

DOWNSTREAM — P1.M2.T2.S1 (later): adds phase/models_loaded to status_snapshot() + feedback.py + ctl status rendering.
  _arm_response's **status_snapshot() spread carries T2.S1's future fields automatically. No overlap (this task does
  not touch status_snapshot's field set, feedback.py, or the status command).

UNCHANGED: format_result (ctl.py), send_command (ctl.py), status_snapshot's body (daemon.py), feedback.py, config.py/
  config.toml, _load_recorder/__init__/the 8 guards/run/main (daemon.py = T1.S1), typing_backends.py, systemd, README.

BUILD ARTIFACTS: NO new files, NO pyproject/uv.lock/.venv changes, NO new deps (threading is stdlib). Validation =
  py_compile + pytest.
```

## Validation Loop

> Full paths in every bash command (zsh aliases — Gotcha #10). Run from `/home/dustin/projects/voice-typing`.
> pytest>=9.1.1 is the runner; NO ruff/mypy (Gotcha #11). All gates are fast/unit (stub daemons; no GPU/RealtimeSTT).

### Level 1: the edits are in place (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- ctl.py: threading import + delay constant + helper + main branch ---"
grep -nE '^import threading$' voice_typing/ctl.py && echo "L1 import OK"
grep -nE '_LOADING_HINT_DELAY' voice_typing/ctl.py
grep -nE 'def _send_command_with_loading_hint' voice_typing/ctl.py
grep -nE 'if cmd in \("start", "toggle"\)' voice_typing/ctl.py
echo "--- daemon.py: _arm_response + _dispatch start/toggle use it ---"
grep -nE 'def _arm_response' voice_typing/daemon.py
grep -nA2 'if cmd == "start":' voice_typing/daemon.py | grep '_arm_response'
echo "--- test_voicectl.py: new stubs + tests ---"
grep -cE 'class _SlowStartStubDaemon|class _FailingLoadStubDaemon|test_start_prints_loading_hint_when_arm_is_slow|test_start_load_failure_returns_ok_false_and_exit_one' tests/test_voicectl.py
# Expected: import threading present; _LOADING_HINT_DELAY + _send_command_with_loading_hint + main branch present;
# _arm_response present; _dispatch start branch calls _arm_response; 4 new test/stub symbols present.
```

### Level 2: the new behavior (the contract)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# (a) NEW tests pass (slow-start hint, fast-arm no-hint, status/stop no-hint, load-failure ok:false, _dispatch units):
"$PY" -m pytest tests/test_voicectl.py -q -k "loading_hint or load_failure or dispatch_start or dispatch_toggle or does_not_print"
# (b) The two defining properties, run explicitly:
"$PY" -m pytest \
  "tests/test_voicectl.py::test_start_prints_loading_hint_when_arm_is_slow" \
  "tests/test_voicectl.py::test_start_load_failure_returns_ok_false_and_exit_one" -v
# Expected: (a) all selected pass; (b) 2 passed. If the hint test is flaky, the stub delay (0.4) ≫ the patched threshold
# (0.02) — re-check monkeypatch.setattr(ctl,"_LOADING_HINT_DELAY",0.02) runs BEFORE ctl.main.
```

### Level 3: no regression (existing tests + full fast suite)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# (a) ALL existing test_voicectl.py tests still pass (fast stub → hint never fires; format_result untouched):
"$PY" -m pytest tests/test_voicectl.py -q
# (b) Full fast suite (the PRD §6 documented sweep; test_feed_audio.py is the heavy GPU suite, ignored on a fast sweep):
"$PY" -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed for both. (Assert by pass/fail, not a hard count — T1.S1/other parallel work may shift the total.)
```

### Level 4: scope guard — only ctl.py + daemon.py(_dispatch) + test_voicectl.py changed

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: ONLY voice_typing/ctl.py, voice_typing/daemon.py, tests/test_voicectl.py modified.
# Belt-and-suspenders: status_snapshot's field set is UNCHANGED (T2.S1 owns additions); feedback.py untouched:
grep -cE '"phase"|"models_loaded"' voice_typing/daemon.py | xargs echo "phase/models_loaded literals in daemon.py (expect 0 — T2.S1's job):"
git diff --name-only voice_typing/daemon.py >/dev/null && echo "daemon.py changed (verify the diff is ONLY _dispatch + _arm_response):"
git diff voice_typing/daemon.py | grep -E '^[+-]' | grep -vE '^[+-]{3}|def _arm_response|_dispatch|_arm_response|was_listening|load_error|return \{"ok"|return self|if cmd ==|self\._daemon\.(start|toggle|status_snapshot|is_listening)|"""|^\+$|^-$' | head
# Expected: the filtered diff shows ONLY the intended lines (no stray status_snapshot/feedback edits).
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: ctl.py has `import threading` + `_LOADING_HINT_DELAY` + `_send_command_with_loading_hint` + main start/toggle branch; daemon.py has `_arm_response` + `_dispatch` start/toggle use it.
- [ ] L2: new tests pass — slow start → hint on stderr; fast arm → no hint; status/stop → no hint; load failure → ok:false/exit 1; `_dispatch` start/toggle-failure unit tests.
- [ ] L3: `pytest tests/test_voicectl.py -q` → 0 failed (existing tests unchanged); `pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] L4: `git status` == ctl.py + daemon.py + test_voicectl.py only; daemon.py diff is only `_dispatch`/`_arm_response`.

### Feature Validation
- [ ] `voicectl start` on a blocking (loading) daemon prints `loading models…` to stderr; on a resident daemon prints nothing extra.
- [ ] A model-load failure makes `voicectl start` print `error: model load failed: …` + exit 1 (not `listening: off` + 0).
- [ ] `voicectl status`/`stop`/`quit` behavior byte-identical (plain send_command).
- [ ] stdout stays clean (hint on stderr) so scripts/wrappers are unaffected.

### Code Quality Validation
- [ ] `format_result` UNCHANGED; `send_command` UNCHANGED (a wrapper added).
- [ ] `_LOADING_HINT_DELAY` tuned away from both boundaries (ms RTT ≪ 0.3 ≪ ~1 s load).
- [ ] `getattr(self._daemon, "_load_error", None)` used (duck-typed stub stays on ok:true path).
- [ ] Full paths in every bash command; no bare python/pytest/uv.

### Scope Boundary Validation
- [ ] No `status_snapshot()` field additions (phase/models_loaded = T2.S1).
- [ ] No `feedback.py` edit (= T2.S1); no config.py/config.toml (= P1.M3); no README (= P1.M3.T3); no systemd (= P1.M1.T2.S1).
- [ ] No T1.S1 regions edited (`__init__`/`_load_recorder`/8 guards/`run`/`main`/test_daemon.py).
- [ ] No `pyproject.toml`/`uv.lock`/`.gitignore`/`PRD.md`/`tasks.json`/`prd_snapshot.md`/`delta_prd.md` changes.

---

## Anti-Patterns to Avoid

- ❌ Don't render the hint from the response (`format_result` branch on `phase:'loading'`) — `start()` blocks inside `_load_recorder`, so on success `phase` is already `'idle'` by response time; such a branch is dead code. Print it **client-side during the blocking read**. (CRITICAL #1, #7.)
- ❌ Don't use `socket.settimeout` for the hint — `send_command` uses `makefile('r')`, incompatible with timeouts. Use `threading.Timer`. (CRITICAL #2.)
- ❌ Don't print the hint to **stdout** — it would pollute the structured result for scripts. Use stderr. (CRITICAL #3.)
- ❌ Don't set `_LOADING_HINT_DELAY` near either boundary (ms RTT or ~1 s load) — it would flicker on resident arms or miss real loads. (CRITICAL #4.)
- ❌ Don't read `self._daemon._load_error` directly — the duck-typed `_StubDaemon` has no such attr. Use `getattr(..., None)`. (CRITICAL #5.)
- ❌ Don't check `_load_error` on a **disarm** toggle — only an arm attempt can fail. Capture `was_listening` first. (CRITICAL #6.)
- ❌ Don't touch `format_result`, `send_command`, `status_snapshot()`'s body, `feedback.py`, or T1.S1's daemon regions. (CRITICAL #7, #8, #9.)
- ❌ Don't add `phase`/`models_loaded` to `status_snapshot()` or the `status` command rendering — that's T2.S1. (CRITICAL #8.)
- ❌ Don't invent ruff/mypy gates (not configured). Validate with pytest. (Gotcha #11.)
- ❌ Don't use bare `python`/`pytest`/`uv` (zsh aliases) — use `.venv/bin/python -m pytest`. (Gotcha #10.)
- ❌ Don't edit `PRD.md`/`delta_prd.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`.

---

## Confidence Score

**8/10** for one-pass implementation success. The boundary is pinned to delta_prd citations (T1.S2 = arm hint + ok:false response; T2.S1 = status_snapshot fields + status rendering + feedback; T1.S1 = load mechanism + `_load_error`), the timing proof forces a client-side design (verified: `start()` blocks on `_load_recorder`, response built after load), the `makefile`-vs-`settimeout` constraint mandates a `threading.Timer`, every edit is given as exact oldText→newText, and the new tests use hermetic stubs that simulate T1.S1's contract (so they're independent of T1.S1's exact internals). Residual uncertainty (−2): (a) this task runs AFTER P1.M2.T1.S1 lands — if T1.S1's actual `start()` returns a bool or names the attr differently than `_load_error`, the `getattr` + `is_listening()` inference still works but the implementer should prefer T1.S1's actual signal if cleaner (the PRP's CRITICAL #5/getattr makes this robust either way); (b) the timer-thread hint has a benign cancel race (a fired print may land just as `send_command` returns) — harmless because if it fired the arm was genuinely slow, but worth noting. Neither blocks a green suite.
