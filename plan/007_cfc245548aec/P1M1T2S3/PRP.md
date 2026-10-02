# PRP — P1.M1.T2.S3: ctl.py command surface (drop lite commands)

## Goal

**Feature Goal**: Collapse the `voicectl` CLI to the Rev 2 single-mode surface: `_COMMANDS` becomes
the **5** commands `("toggle","start","stop","status","quit")` — `toggle-lite`/`start-lite` are removed
from `_COMMANDS`, the argparse epilog, the positional help, and the module docstring (Mode A, named by
PRD R1). In `format_result`, DELETE the `models: {final_model} + {realtime_model} ({loaded})` line
(its two status keys died with P1.M1.T2.S2) while KEEPING the `mode: {mode}` line. Update
`tests/test_voicectl.py` (fixture, format tests, command-list tests, help test) and sweep
`tests/test_control_socket.py`'s lite residue. Do NOT add `cancel` — P1.M2.T7.S1 appends it (final 6).

**Deliverable** (3 files, no new files):
1. `voice_typing/ctl.py` — `_COMMANDS` → 5; module docstring + epilog + positional help → 5;
   `format_result` models line + its two key-reads deleted (mode line kept); `main()` loading-hint
   routing tuple → `("start","toggle")` + comment updated.
2. `tests/test_voicectl.py` — `_STATUS_ON` → 13-key shape (`mode:"lite"`, `model:"small.en"`); @62
   format test drops models/marker asserts; @75 rewritten to lite-→-64 usage error; @84 drops marker
   asserts; @383 help test rewritten to the 5-set + negative sweep.
3. `tests/test_control_socket.py` — sweep S2's residue: delete `_StubDaemon.start_lite`/`toggle_lite`
   methods, 13-key stub snapshot + key-set assert, keep @143 mode assert, ADD the single-path
   lite-unknown replacement test.

**Success Definition**:
- (a) `grep -c 'toggle-lite\|start-lite\|final_model\|realtime_model' voice_typing/ctl.py` → 0
  (module docstring, epilog, help, comments included).
- (b) `ctl._COMMANDS == ("toggle","start","stop","status","quit")` — exactly 5, no `cancel`.
- (c) `format_result("status", resp)` renders listening / **mode** / phase / partial / last / uptime /
  device / mic (+ load error if present) and contains NO `models:` line; `mode: lite` renders from the
  response; the `.get("mode","normal")` defensive default stays.
- (d) `voicectl toggle-lite` (no daemon needed) → stderr `invalid command 'toggle-lite'; choose from
  toggle, start, stop, status, quit` + **exit 64** (EX_USAGE; exit 2 stays daemon-not-running only).
- (e) `main()` routes ONLY `start`/`toggle` through `_send_command_with_loading_hint`.
- (f) Full fast suite green: `timeout 600 .venv/bin/python -m pytest tests/ -q --ignore=tests/test_feed_audio.py
  --ignore=tests/e2e_virtual_mic.sh --ignore=tests/test_idle_and_gpu.sh` → 0 failures.
- (g) `git diff --name-only` ⊆ {voice_typing/ctl.py, tests/test_voicectl.py, tests/test_control_socket.py}.

## User Persona

**Target User**: the end user with ONE keybind (`toggle`) arming the single-model engine. Two keybinds
and two arming commands for a mode that no longer exists are confusion surface.
**Pain Points Addressed**: post-S2 the daemon rejects `toggle-lite`/`start-lite` server-side, but ctl
still ADVERTISES them (`--help`, docstring, no-arg error) — a user running `voicectl toggle-lite` would
get exit 1 (`error: unknown command`) from a command their own CLI told them exists. S3 removes the lie.

## Why

- **S2 removed the server side; ctl must follow.** S2 (parallel, lands FIRST) deletes the dispatch arms
  and collapses `status_snapshot` to 13 keys (`mode:"lite"` constant, single `model` key). Until S3,
  ctl.py's 7-command `_COMMANDS`/help/docstring are dead entries, and `format_result`'s models line
  reads `final_model`/`realtime_model` keys that no longer exist on the wire (it survives only via
  `.get` defaults — rendering `models: unknown + unknown (loaded)` against the real daemon). S3 finishes
  the collapse at the user-facing edge.
- **The PRD names this exact surface.** PRD R1 (Mode A docs) names the ctl.py module docstring +
  `--help`/epilog; §4.8's command list is the user-facing contract being reduced to 5.
- **Downstream consumes the stable surface.** P1.M2.T7.S1 appends `cancel` to this 5-command list
  (final 6) — S3 must leave the list clean and 5-EXACTLY so that append is a one-line change.
- **Scope discipline.** hypr-binds.conf:52 + test_config_repo_default.py:56 are S4's; prefetch is S4's;
  README usage table / ACCEPTANCE.md are P1.M3.T10.S1 / P1.M3.T9.S1's; `cancel` is P1.M2.T7.S1's.

## What

- `_COMMANDS` → `("toggle", "start", "stop", "status", "quit")` (5; NO `cancel`).
- Module docstring: drop the `toggle-lite`/`start-lite` subcommand lines; Usage line →
  `voicectl <toggle|start|stop|status|quit>`; drop the "(single small model — PRD §4.2ter)" prose.
- `format_result`: drop the `final_model`/`realtime_model` reads, the `models_loaded`/
  `loaded_marker` locals, and the `models: …` text line; KEEP the `mode` read + `mode: {mode}` line.
  The `(loaded)/(not loaded)` marker dies with the line — lifecycle stays visible via `phase:` +
  `load error:`; `models_loaded`/`model` remain in the JSON payload (spirit of §4.8 preserved).
  Update the docstring's field list.
- `_build_parser`: epilog → `subcommands: toggle, start, stop, status, quit`; positional help →
  `toggle | start | stop | status | quit`.
- `main()`: `if cmd in ("start", "toggle"):` for the loading hint; rewrite the comment (no lite
  variants, no mode-switch reload — only the cold first arm blocks, §4.2bis).

### Success Criteria

- [ ] (a) zero `toggle-lite|start-lite|final_model|realtime_model` refs in ctl.py (docstrings included).
- [ ] (b) `_COMMANDS` is exactly the 5-tuple (no `cancel`).
- [ ] (c) status text has `mode: {mode}` and NO `models:` line; `.get("mode","normal")` default kept.
- [ ] (d) `ctl.main(["toggle-lite"]) == 64` / `ctl.main(["start-lite"]) == 64`; stderr names the 5.
- [ ] (e) loading-hint routing tuple is `("start", "toggle")`.
- [ ] (f) full fast suite 0 failures (S2's suite state stays green; S3's updated tests green).
- [ ] (g) diff ⊆ the 3 deliverable files.

## All Needed Context

### Context Completeness Check

_Pass._ ctl.py was read in full (219L) and every edit site is quoted with its end state in the research
note; both test files' relevant regions (@31-95, @380-404 voicectl; @25-47, @107-160 control_socket)
were read verbatim; S2's PRP (the parallel contract) pins the exact post-landing daemon shape (13-key
status, mode constant, dispatch arms gone, test_control_socket @131 deleted / @143 kept); the S1/T1.S1
inputs are only transitive (via S2). An agent new to the repo can implement from this PRP + the
research note alone.

### Documentation & References

```yaml
# MUST READ — this task's verified edit-site tables (source of truth for every change)
- docfile: plan/007_cfc245548aec/P1M1T2S3/research/ctl_command_surface_edit_sites.md
  why: "§1 the S2 gate commands; §2 the ctl.py table (verbatim current → end state, site by site incl.
        docstring/epilog/help/routing); §3 the test_voicectl table; §4 the control_socket residue sweep;
        §5 downstream boundaries; §6 suite-state (no red transient — S3's own TDD red only)."
  critical: "§2's models-line row: the (loaded) marker dies WITH the line (phase + load error carry the
            lifecycle); §3's @75 rewrite uses main() BEFORE the socket connect (returns 64, no daemon needed)."

# MUST READ — the parallel INPUT contract (assume landed exactly as specified)
- docfile: plan/007_cfc245548aec/P1M1T2S2/PRP.md
  why: "Defines the post-landing state S3 consumes: dispatch start-lite/toggle-lite arms DELETED (unknown-
        command reply), status_snapshot 13 keys with 'mode':'lite' constant + single 'model' key, and S2's
        OWN test_control_socket edits (@131 deleted, @143 kept, 13-key asserts). S2's Downstream section:
        'ctl.py STILL lists them (dead entries) until S3 drops _COMMANDS/argparse/loading-hint.'"
  critical: "S2 must land FIRST — Task 0 gates on it. Do NOT duplicate S2's test_daemon.py
            test_dispatch_lite_commands_now_unknown."

# MUST READ — the structural map (§4 = the control-socket/ctl surface, §7 = mode consumers)
- docfile: plan/007_cfc245548aec/architecture/daemon_control_map.md
  why: "§4 cites every ctl.py site this task edits (_COMMANDS :37, _EX_USAGE :39, epilog :~158-165,
        main() validation :~174-183, loading-hint routing :~199, format_result mode :69/:90 + models :96)
        and the dispatch/response shapes; §7 lists the mode consumers (ctl rendering stays; hypr-binds is S4's)."
  critical: "§4's response-shape note: arm cmds → {ok, **status_snapshot()} — the spread is why the
            models line's keys vanished (S2) and only .get defaults kept it from KeyError-ing."

# THE EDIT SITE — read in full before editing
- file: voice_typing/ctl.py
  why: "219L. All sites: _COMMANDS @37; docstring subcommand block @15-23; format_result docstring @47-56;
        format_result body @57-105 (mode read @69, models reads @77-79, text block @90-101, models line @96,
        load_error @103-104); _build_parser @~151-170 (epilog + positional help); main() routing @~196-201."
  pattern: "Keep the existing conventions: defensive .get() everywhere; exit-code table in the docstring
            (0/1/2/64); BSD EX_USAGE comment; choices-NOT-in-argparse (main() validates) so usage errors
            map to 64."
  gotcha: "Do NOT touch send_command, _send_command_with_loading_hint, _LOADING_HINT_DELAY, _EX_USAGE,
           the XDG/exit-2 path, or the quit/ok:false branches in format_result."

# THE TEST FILE A — voicectl
- file: tests/test_voicectl.py
  why: "_STATUS_ON @31-36 (canned 14-key); @62 format-status test (asserts mode normal + models + loaded);
        @75 lite-accepted test; @84 unloaded/load-error test (asserts the marker); @383-404 the 7-command
        help test (asserts _COMMANDS==seven, help text, ctl.__doc__)."
  pattern: "Layer A tests are pure format_result/main calls with canned JSON — keep that style. The @75
            rewrite asserts main() returns 64 BEFORE any socket connect (the usage path returns early —
            no daemon, no socket path resolution needed)."
  gotcha: "The loading-hint block @263-345 and failed-load block @349-372 have NO lite refs — leave them
           untouched; the routing-tuple edit doesn't change their behavior."

# THE TEST FILE B — control socket (S2 owns the primary edits; S3 sweeps the residue)
- file: tests/test_control_socket.py
  why: "_StubDaemon @27-46 (start_lite/toggle_lite METHODS @40-41; default snapshot w/ final_model/
        realtime_model @31-36); test_dispatch_status_has_all_keys @120-123; @131 lite-dispatch (S2
        deletes); @143 status-carries-mode (KEEP)."
  pattern: "After S2 lands, verify its edits are in place; S3 deletes the stub's two dead lite METHODS,
            ensures the stub snapshot + key-set assert are 13-key, keeps @143, and adds the single-path
            replacement test (lite cmds → ok:false unknown-command against the lite-method-free stub)."
  critical: "Do NOT re-delete @131 (S2 did) and do NOT duplicate S2's test_daemon-level unknown-cmd test;
            the new control-socket test pins the STUB SHAPE (lite methods really gone)."
```

### Current Codebase tree (relevant slice — S2 lands before S3 starts)

```bash
voice_typing/ctl.py             # ← EDIT: _COMMANDS 7→5; docstring/epilog/help 7→5; format_result models
#                                  line deleted (mode kept); main() routing tuple; comments.
tests/test_voicectl.py          # ← EDIT: _STATUS_ON 13-key; @62/@75/@84/@383-family rewrites.
tests/test_control_socket.py    # ← EDIT (residue sweep): _StubDaemon lite methods + snapshot/key-set;
#                                  + one single-path replacement test; keep @143.
# AFTER S2 (input): daemon.py dispatch lite arms gone; status_snapshot 13-key (mode:"lite", model);
#                   test_daemon.py single-path family + test_dispatch_lite_commands_now_unknown landed.
# NOT S3's: daemon.py/recorder_host.py (S2), cuda_check.py (S1), prefetch.py/hypr-binds.conf (S4),
#           config.py/config.toml (T1.S1 settled), README/ACCEPTANCE (P1.M3), pyproject (no change).
```

### Desired Codebase tree with files to be changed

```bash
# (the same 3 files, MODIFIED — no new files, no deletions of files)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — GATE ON S2 FIRST (Task 0). cfg/format correctness depends on the landed server shape:
#   grep -q '"mode": "lite"' voice_typing/daemon.py          # status constant landed
#   [ "$(grep -c 'start-lite\|toggle-lite' voice_typing/daemon.py)" -eq 0 ]   # dispatch arms gone
# If either fails, S2 hasn't landed — STOP and flag (editing ctl first would leave the surfaces
# inconsistent and S3's 13-key fixture tests unrunnable). Also verify S2's test_control_socket edits
# (@131 gone, @143 present) — S3 sweeps the residue, it does not redo S2's work.

# CRITICAL #2 — DO NOT ADD 'cancel'. The contract is explicit: cancel is P1.M2.T7.S1's append (final 6).
# _COMMANDS ends this task at EXACTLY 5.

# CRITICAL #3 — THE MODE LINE STAYS; THE MODELS LINE GOES — TOGETHER WITH ITS MARKER. Contract: "drop
# the models line, keep the mode line." Delete final_model/realtime_model reads + models_loaded/
# loaded_marker locals + the models text line. The (loaded)/(not loaded) marker dies with the line;
# phase: + load error: remain the lifecycle surfaces; models_loaded/model stay in the JSON. Do NOT
# invent a replacement 'model:' line (not in the contract; keeps the surface minimal for T7.S1's append).

# CRITICAL #4 — TDD ORDER: TESTS FIRST. Rewrite the test_voicectl family to the 5-command/13-key
# expectations and watch them FAIL against current ctl.py (7 commands, lite accepted, models line) —
# that red pins the end state — then edit ctl.py and watch them go green. The suite is GREEN between S2
# and S3 (ctl's lite entries are dead-but-harmless; format tests use the canned fixture), so the ONLY red
# you should see is your own new expectations.

# CRITICAL #5 — THE @75 REWRITE MUST NOT TOUCH A SOCKET. ctl.main() validates cmd BEFORE resolving the
# socket path — main(["toggle-lite"]) returns 64 without any daemon/Environment dependence. That's why
# the usage-error assert is safe as a unit test. (Do NOT test the exit-2/1 paths here — they're covered.)

# CRITICAL #6 — HELP-TEXT NEGATIVE SWEEP. The @383 test family exists because a past bug had --help
# showing 5 while the no-arg error showed 7 (bugfix Issue 3). Rewrite it to the 5-set AND assert
# 'toggle-lite'/'start-lite' are ABSENT from format_help() AND ctl.__doc__ — the negative half is what
# catches a stale epilog/docstring line this time.

# GOTCHA #7 — _STATUS_ON FIXTURE DRIVES MANY TESTS. The toggle/start/stop/quit format tests and the mic/
# phase/load-error tests all spread {**_STATUS_ON, ...} — swapping final_model/realtime_model for
# mode/model keeps them green (they assert only on their own lines). Keep "ok": True and the other keys.

# GOTCHA #8 — COMMENTS ARE PART OF THE SWEEP. main()'s routing comment mentions "(and their lite
# variants)" and "mode-switch reload (PRD §4.2ter)" — rewrite it (the loading hint now fires only on the
# cold first arm, §4.2bis). The module docstring's lite subcommand prose is a named Mode-A doc (R1).

# GOTCHA #9 — FULL PATHS + INNER TIMEOUTS (AGENTS.md): `timeout 600 .venv/bin/python -m pytest ...`.
# Machine aliases python3→uv run. No ruff/mypy configured. Never run the heavy GPU tests (feed_audio /
# e2e_virtual_mic / idle_and_gpu) — they're P1.M3.T9.S1's.
```

## Implementation Blueprint

### Data models and structure

None. No types/schema/config changes — the CLI surface tuple, help strings, and one render branch.
The protocol contract consumed is S2's 13-key `status_snapshot` (`mode:"lite"` constant, single
`model` key, no `final_model`/`realtime_model`).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: GATE — confirm S2 landed (the INPUT contract) + baseline green
  - RUN:
      cd /home/dustin/projects/voice-typing
      grep -q '"mode": "lite"' voice_typing/daemon.py && echo "S2 mode constant landed" || echo "STOP: S2 not landed"
      n=$(grep -c 'start-lite\|toggle-lite' voice_typing/daemon.py); echo "daemon lite refs=$n (expect 0)"
      grep -n 'def test_dispatch_lite_commands_call_daemon' tests/test_control_socket.py && echo "NOTE: S2's @131 deletion not visible" || echo "S2 test edit landed"
      timeout 600 .venv/bin/python -m pytest tests/test_voicectl.py tests/test_control_socket.py -q 2>&1 | tail -2
  - If the gate fails (no mode constant / lite arms still in daemon.py): STOP and report — S3 must not
    run ahead of S2.

Task 1: REWRITE tests/test_voicectl.py to the 5-command/13-key end state FIRST (TDD)
  - 1a. _STATUS_ON (@31-36): replace `"final_model": "distil-large-v3", "realtime_model": "small.en",`
    with `"mode": "lite", "model": "small.en",` (13-key post-S2 shape; mode constant).
  - 1b. @62 → rename `test_format_status_multiline_has_partial_and_mode`; drop the
    `distil-large-v3`/`small.en`/`(loaded)` asserts; change the mode assert to `"mode: lite" in text`
    (new fixture value); keep listening/phase/partial/device/uptime asserts.
  - 1c. @75 → REPLACE with:
        def test_lite_commands_are_rejected_as_usage_errors():
            """Rev 2 single-mode (P1.M1.T2.S3): toggle-lite/start-lite are gone from the surface;
            main() rejects them with exit 64 (EX_USAGE) BEFORE any socket connect."""
            assert "toggle-lite" not in ctl._COMMANDS and "start-lite" not in ctl._COMMANDS
            assert ctl.main(["toggle-lite"]) == 64      # usage path returns before socket resolution
            assert ctl.main(["start-lite"]) == 64
  - 1d. @84: drop the `(not loaded)` / `(loaded) not in text` asserts; KEEP `phase: unloaded` +
    `load error:` asserts.
  - 1e. @383-404 → REPLACE `test_help_surfaces_list_all_seven_commands` with:
        def test_help_surfaces_list_all_five_commands():
            """Rev 2 surface (P1.M1.T2.S3): exactly 5 commands in _COMMANDS, --help (positional help +
            epilog), and the module docstring — and NO stale lite entries anywhere (bugfix Issue 3's
            consistency guard, inverted for the collapse)."""
            five = {"toggle", "start", "stop", "status", "quit"}
            assert set(ctl._COMMANDS) == five, sorted(ctl._COMMANDS)
            help_text = ctl._build_parser().format_help()
            for cmd in five:
                assert cmd in help_text, f"{cmd!r} missing from --help:\n{help_text}"
                assert cmd in ctl.__doc__, f"{cmd!r} missing from the ctl module docstring"
            for stale in ("toggle-lite", "start-lite"):
                assert stale not in help_text, f"{stale!r} still in --help:\n{help_text}"
                assert stale not in ctl.__doc__, f"{stale!r} still in the module docstring"
    Update the banner comment above it (7→5 story).
  - RUN (expect RED against current ctl.py): timeout 600 .venv/bin/python -m pytest tests/test_voicectl.py -q

Task 2: EDIT voice_typing/ctl.py — the 5-command surface
  - 2a. _COMMANDS @37 → `("toggle", "start", "stop", "status", "quit")`  # Rev 2 single-mode (P1.M1.T2.S3);
    'cancel' is appended by P1.M2.T7.S1.
  - 2b. Module docstring: delete the two lite subcommand lines; Usage line →
    `Usage:  voicectl <toggle|start|stop|status|quit>`; keep the exit-code table + stdlib note.
  - 2c. format_result docstring: drop `final_model, realtime_model` from the field list; drop the
    "'incl. partial and models loaded'" PRD parenthetical (models are JSON-only now; mode stays).
  - 2d. format_result body: delete the `final_model = ...`/`realtime_model = ...` reads, the
    `models_loaded = ...`/`loaded_marker = ...` locals, and the `f"models: {final_model} +
    {realtime_model} ({loaded_marker})\n"` line. KEEP `mode = response.get("mode","normal") or "normal"`
    and the `f"mode: {mode}\n"` line. Result block order: listening / mode / phase / partial / last /
    uptime / device / mic (+ load error).
  - 2e. _build_parser: epilog → `subcommands: toggle, start, stop, status, quit  (see the project README
    for the full usage table)`; positional help → `toggle | start | stop | status | quit`.
  - 2f. main() routing: `if cmd in ("start", "toggle"):`; rewrite the comment above it — arm commands
    may block ~1–3 s on the COLD FIRST ARM (PRD §4.2bis lazy load); resident arms reply in ms; drop the
    lite-variants + mode-switch-reload sentences.
  - RUN: timeout 600 .venv/bin/python -m pytest tests/test_voicectl.py -q   # now GREEN

Task 3: SWEEP tests/test_control_socket.py (S2's residue)
  - 3a. Verify S2's edits: @131 family absent; @143 `test_dispatch_status_response_carries_mode` present.
  - 3b. DELETE `_StubDaemon.start_lite`/`toggle_lite` methods (@40-41 — dead after S2's dispatch edit).
  - 3c. `_StubDaemon` default snapshot: replace `"final_model": "distil-large-v3", "realtime_model":
    "small.en"` with `"mode": "lite", "model": "small.en"` (if S2 didn't already); align
    `test_dispatch_status_has_all_keys` (@120-123) to the 13-key set (mode + model in; the two model
    keys out).
  - 3d. ADD the single-path replacement for @131's slot:
        def test_dispatch_lite_commands_are_unknown():
            """Rev 2 (P1.M1.T2.S3): lite commands are gone server-side; the stub no longer carries the
            lite arm methods, and _dispatch rejects the cmds with ok:false unknown-command."""
            srv = daemon.ControlServer(_StubDaemon())
            r = srv._dispatch(json.dumps({"cmd": "start-lite"}))
            assert r["ok"] is False and "unknown command" in r["error"]
            r2 = srv._dispatch(json.dumps({"cmd": "toggle-lite"}))
            assert r2["ok"] is False and "unknown command" in r2["error"]
  - 3e. KEEP @143 unchanged (the contract's "keep mode-in-status assert").
  - RUN: timeout 600 .venv/bin/python -m pytest tests/test_control_socket.py -q

Task 4: VALIDATE — the Validation Loop below. No git commit unless directed. If asked, message:
  "P1.M1.T2.S3: voicectl surface → 5 commands (drop toggle-lite/start-lite + models line; mode kept);
   help/docstring synced; voicectl+control-socket tests updated".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the 5-command surface (the whole CLI contract; T7.S1 appends 'cancel' later):
_COMMANDS: tuple[str, ...] = ("toggle", "start", "stop", "status", "quit")  # Rev 2 (P1.M1.T2.S3)

# PATTERN 2 — the slimmed status block (mode KEPT, models GONE, marker GONE with it):
        text = (
            f"listening: {listening}\n"
            f"mode: {mode}\n"                     # kept (contract); daemon constant "lite" post-S2
            f"phase: {phase}\n"
            f"partial: {partial}\n"
            f"last: {last_final}\n"
            f"uptime: {uptime}s\n"
            f"device: {device} ({compute_type})\n"
            f"{mic_line}"
        )
        if load_error:
            text += f"\nload error: {load_error}"

# PATTERN 3 — usage validation stays in main() (NOT argparse choices) so 64 never collides with 2:
    if cmd not in _COMMANDS:          # missing or unknown -> 64 (EX_USAGE); lists the 5 on stderr
# The @75 rewrite relies on this returning BEFORE socket-path resolution (unit-testable, no daemon).
```

### Integration Points

```yaml
UPSTREAM — P1.M1.T2.S2 (parallel, MUST land first; Task 0 gate):
  - S2 deletes the daemon dispatch arms (lite cmds → unknown-command) and collapses status_snapshot to
    13 keys (mode:"lite" constant, single "model"). S2 also deletes test_control_socket @131 + keeps
    @143. S3 consumes that state and finishes the edge (CLI surface + rendering + tests).

DOWNSTREAM — P1.M2.T7.S1 (cancel):
  - Appends "cancel" to _COMMANDS (5→6), its help/docstring surfaces, routing, and daemon dispatch.
    S3 leaves the list clean and exactly-5 so that append is minimal. Do NOT pre-add it.

DOWNSTREAM — P1.M1.T2.S4 (prefetch/binds/ACCEPTANCE) + P1.M3.T10.S1 (README sync):
  - hypr-binds.conf:52's toggle-lite bind + test_config_repo_default.py:56 = S4's. README's voicectl
    usage table + ACCEPTANCE.md = the P1.M3 doc tasks. NOT S3's.

NO INTERFACE CHANGES BEYOND THE SURFACE:
  - pyproject console script (voicectl = voice_typing.ctl:main) unchanged; exit-code table 0/1/2/64
    unchanged; send_command/_send_command_with_loading_hint/exit-2 path unchanged; JSON protocol
    untouched (ctl only renders the 13-key snapshot it receives).
```

## Validation Loop

> Full paths + inner timeouts (AGENTS.md). Hermetic fast tests only. Run from `/home/dustin/projects/voice-typing`. Line numbers move — match on TEXT.

### Level 1: The collapse is complete (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- L1a: zero lite/model-key refs in ctl.py (docstrings/help/comments included) ---"
n=$(grep -c 'toggle-lite\|start-lite\|final_model\|realtime_model' voice_typing/ctl.py); echo "ctl.py refs=$n (expect 0)"
echo "--- L1b: _COMMANDS is exactly 5 (no cancel) ---"
.venv/bin/python -c "
from voice_typing import ctl
assert ctl._COMMANDS == ('toggle','start','stop','status','quit'), ctl._COMMANDS
assert 'cancel' not in ctl._COMMANDS
print('L1b PASS: 5 commands, no cancel')"
echo "--- L1c: format_result has mode line, NO models line, defensive default kept ---"
grep -q 'f"mode: {mode}\\n"' voice_typing/ctl.py && grep -q 'response.get("mode", "normal")' voice_typing/ctl.py && echo "L1c PASS: mode kept + default" || echo "L1c FAIL"
grep -q 'models:' voice_typing/ctl.py && echo "L1c FAIL: a models line survived" || echo "L1c PASS: no models line"
echo "--- L1d: routing tuple + ctl.py parses ---"
grep -q 'cmd in ("start", "toggle")' voice_typing/ctl.py && echo "L1d PASS: routing" || echo "L1d FAIL"
timeout 60 .venv/bin/python -c "import ast; ast.parse(open('voice_typing/ctl.py').read()); print('L1d PASS: parses')"
# Expected: 0 refs; 5-tuple; mode kept + default; no models line; routing tuple; parses.
```

### Level 2: The focused suites (S3's own tests)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_voicectl.py -q 2>&1 | tail -3
timeout 600 .venv/bin/python -m pytest tests/test_control_socket.py -q 2>&1 | tail -3
# Expected: both green. Load-bearing: test_lite_commands_are_rejected_as_usage_errors (main→64),
# test_help_surfaces_list_all_five_commands (incl. the NEGATIVE lite sweep), the renamed mode format
# test, test_dispatch_lite_commands_are_unknown, test_dispatch_status_response_carries_mode (kept).
# If the help test fails on 'toggle-lite' still in help_text/docstring: the epilog/docstring lines
# weren't swept (Task 2b/2e). If main(['toggle-lite']) returns 2/1 instead of 64: _COMMANDS still has 7.
```

### Level 3: Full fast suite green (S2's state preserved; no consumer missed)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/ -q --ignore=tests/test_feed_audio.py --ignore=tests/e2e_virtual_mic.sh --ignore=tests/test_idle_and_gpu.sh 2>&1 | tail -3
# Expected: 0 failures. Remaining red means a missed lite/models consumer in the FAST suite — re-run L1a
# across tests/ (grep -rn 'toggle-lite\|start-lite' tests/test_voicectl.py tests/test_control_socket.py)
# and check test_daemon.py is green (it should be post-S2; if not, S2 hasn't fully landed — flag it).
```

### Level 4: Scope guards

```bash
cd /home/dustin/projects/voice-typing
git diff --name-only | grep -vxE 'voice_typing/ctl.py|tests/test_voicectl.py|tests/test_control_socket.py' \
  && echo "L4 FAIL: out-of-scope file changed" || echo "L4 PASS: only the 3 deliverables"
git diff --quiet voice_typing/daemon.py voice_typing/recorder_host.py voice_typing/cuda_check.py voice_typing/prefetch.py voice_typing/feedback.py voice_typing/config.py config.toml hypr-binds.conf tests/ACCEPTANCE.md pyproject.toml \
  && echo "L4 PASS: sibling files untouched" || echo "L4 FAIL: a sibling file was modified"
git diff --exit-code -- PRD.md plan/007_cfc245548aec/tasks.json plan/007_cfc245548aec/prd_snapshot.md .gitignore \
  && echo "L4 PASS: read-only files unchanged" || echo "L4 NOTE: tasks.json orchestrator bookkeeping is not this subtask"
# Expected: only the 3 files; siblings/read-only untouched. (daemon.py diffs visible here = S2's parallel
# work, not S3's — S3's own diff must not include it.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: 0 lite/model-key refs in ctl.py; `_COMMANDS` == 5-tuple (no cancel); mode line + `.get` default kept; no models line; routing tuple; parses.
- [ ] L2: test_voicectl + test_control_socket green (lite→64, 5-command help + negative sweep, mode kept, lite-unknown dispatch).
- [ ] L3: full fast suite 0 failures.
- [ ] L4: diff ⊆ the 3 deliverables; siblings/read-only untouched.

### Feature Validation
- [ ] `voicectl --help` / no-arg error / module docstring all list exactly the 5 commands (no lite entries).
- [ ] `voicectl toggle-lite` → stderr `invalid command 'toggle-lite'…` + exit 64 (2 stays daemon-not-running only).
- [ ] `voicectl status` renders `mode: lite` (post-S2 constant) and NO `models:` line; `load error:` still appends when present.
- [ ] Only `start`/`toggle` route through the loading-hint sender (cold-arm hint preserved, §4.2bis).

### Code Quality Validation
- [ ] Tests rewritten FIRST (TDD; the only red pre-edit is S3's own expectations).
- [ ] Defensive `.get()` style preserved; exit-code table + BSD EX_USAGE rationale intact.
- [ ] Canned `_STATUS_ON` matches the real 13-key protocol shape (mode/model in, two model keys out).

### Scope Boundary Validation
- [ ] No `cancel` (P1.M2.T7.S1's); no hypr-binds/prefetch/ACCEPTANCE (S4's); no README (P1.M3.T10.S1's).
- [ ] No daemon.py/recorder_host.py/cuda_check/config/feedback edits (S2/S1/T1.S1 ground).
- [ ] No duplication of S2's test_daemon unknown-cmd test (the control_socket addition pins the STUB shape).
- [ ] PRD.md, tasks.json, prd_snapshot.md, .gitignore not modified.

### Documentation & Deployment
- [ ] Mode A: ctl.py module docstring + epilog + positional help tell the 5-command story (PRD R1 surface).

---

## Anti-Patterns to Avoid

- ❌ Don't start before S2 lands — the 13-key status and gone dispatch arms are the input contract (Task 0 gate; CRITICAL #1).
- ❌ Don't add `cancel` — P1.M2.T7.S1 appends it; the list ends this task at exactly 5 (CRITICAL #2).
- ❌ Don't keep or reinvent a models line — the contract drops it, marker included; phase + `load error:` carry the lifecycle; don't invent a `model:` render (CRITICAL #3).
- ❌ Don't drop the MODE line or its `.get("mode","normal")` default — it stays; the daemon's constant "lite" flows through it.
- ❌ Don't edit source before tests — rewrite the voicectl family first and watch it pin the end state red (CRITICAL #4).
- ❌ Don't test lite rejection through a socket — `main()` validates BEFORE socket resolution; assert `== 64` directly (CRITICAL #5).
- ❌ Don't skip the negative help sweep — asserting the lite names are ABSENT from `format_help()` + `__doc__` is what catches a stale line (CRITICAL #6).
- ❌ Don't touch `_StubDaemon`'s non-lite surface, `send_command`/loading-hint internals, the exit-2 path, or the quit/ok:false branches.
- ❌ Don't re-delete S2's @131 or duplicate S2's test_daemon unknown-cmd test — S3 sweeps residue + pins the stub shape only.
- ❌ Don't run/edit the heavy GPU tests (AGENTS.md; P1.M3.T9.S1's). Don't modify PRD.md / tasks.json / prd_snapshot.md / .gitignore.

---

## Confidence Score

**9/10** for one-pass implementation success. The task is small and fully mapped: ctl.py was read in
full (219L) and every edit site is quoted with its verbatim current text and end state (research §2);
both test files' relevant regions were read verbatim with per-test rewrite dispositions (§3/§4); the
input contract is precisely pinned (S2's PRP specifies the exact post-landing daemon shape — 13-key
status with `mode:"lite"` constant, dispatch arms gone, and its OWN test_control_socket edits — so S3's
residue sweep is the only remaining work there); and the ambiguity that mattered (what happens to the
`(loaded)` marker when the models line dies) is resolved explicitly by the contract ("drop the models
line, keep the mode line") with the consequence documented (marker dies; phase + load error carry the
lifecycle; JSON keys remain). The suite is green between S2 and S3 (canned fixtures keep the old format
tests passing), so the only red during TDD is S3's own expectations — no transient to misread. The −1
is the parallel-execution residual: S2 must land first (gated in Task 0 with exact grep checks), and
test_control_socket.py is a SHARED surface (S2 deletes @131; S3 sweeps the stub methods + adds the
replacement) — the PRP splits that seam explicitly to avoid double-editing or re-deleting. Every gate
is hermetic and fast; no GPU/daemon/socket is needed for any validation.
