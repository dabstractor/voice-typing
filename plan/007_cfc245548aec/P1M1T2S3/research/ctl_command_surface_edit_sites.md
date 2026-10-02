# Research — P1.M1.T2.S3: ctl.py command surface (drop lite commands)

TEST+CLI task. Drops `toggle-lite`/`start-lite` from the voicectl surface and the dead models line
from status rendering. Source of truth: contract + `daemon_control_map.md` §4/§7 + S2's PRP (parallel
contract) + files read verbatim at HEAD (ctl.py 219L, test_voicectl.py 404L, test_control_socket.py 274L).

## 1. The dependency: S2 lands FIRST (gate before starting)

S2 (daemon.py+recorder_host collapse, parallel) is the INPUT contract. When S3 begins, assume:
- daemon dispatch: the `start-lite`/`toggle-lite` arms are DELETED → `{"ok":false,"error":"unknown command: ..."}`
  (S2 Task 2 dispatch edit; S2 adds `test_dispatch_lite_commands_now_unknown` in tests/test_daemon.py).
- `status_snapshot()` = 13 keys: `"mode": "lite"` (CONSTANT literal), single `"model"` key
  (`dev.get("model","unknown")`), NO `final_model`/`realtime_model`.
- S2 ALSO edits tests/test_control_socket.py: DELETE `test_dispatch_lite_commands_call_daemon` (@131);
  KEEP `test_dispatch_status_response_carries_mode` (@143); update `_StubDaemon`/key-set asserts to 13-key.
GATE (run first):
  grep -q '"mode": "lite"' voice_typing/daemon.py
  grep -c 'start-lite\|toggle-lite' voice_typing/daemon.py   # must be 0
If either fails → S2 not landed → STOP and flag.

## 2. ctl.py edit sites (verified verbatim; navigate by symbol — S2 shifts nothing in ctl.py but keep the habit)

| Site | Current (verbatim essence) | End state |
|---|---|---|
| `_COMMANDS` :37 | `("toggle","start","stop","status","quit","toggle-lite","start-lite")` | `("toggle","start","stop","status","quit")` — do NOT add `cancel` (P1.M2.T7.S1 appends it; final 6) |
| module docstring :15-23 | subcommand block lists `toggle-lite`/`start-lite` + Usage line `<toggle\|start\|stop\|status\|quit\|toggle-lite\|start-lite>` | 5-command block + 5-command Usage line (Mode A; PRD R1 names this surface) |
| `format_result` docstring :47-56 | field list includes `final_model, realtime_model`; "(PRD §4.8 'incl. partial and models loaded'…)" | drop the two; drop the models-loaded prose (mode line stays) |
| `format_result` body :77-79,96 | reads `final_model`/`realtime_model`; renders `models: {final} + {realtime} ({loaded_marker})` | DELETE the models line + the two reads. KEEP `mode = response.get("mode","normal")` + the `mode: {mode}` line (contract: "drop the models line, keep the mode line"). Consequence: the `(loaded)/(not loaded)` marker dies with the line — lifecycle stays visible via `phase:` + `load error:`; `models_loaded`/`model` remain JSON-only. `loaded_marker`/`models_loaded` locals deleted. |
| `_build_parser` epilog :~161 | `subcommands: toggle, start, stop, status, quit, toggle-lite, start-lite` | 5 commands |
| `_build_parser` positional help :~167 | `"toggle \| start \| stop \| status \| quit \| toggle-lite \| start-lite"` | 5 commands |
| `main()` routing :~199 | `if cmd in ("start","toggle","start-lite","toggle-lite"):` → loading hint; comment mentions "(and their lite variants)" + "mode-switch reload (§4.2ter)" | `if cmd in ("start", "toggle"):` + comment updated (loading hint now covers only cold arms, PRD §4.2bis) |
| `_EX_USAGE` :39, exit-2 path, `send_command`, `_send_command_with_loading_hint`, `_LOADING_HINT_DELAY` :42 | — | UNTOUCHED |

No new imports. `mode`/`phase`/mic/uptime/device/partial/last rendering + the quit branch + ok:false
branch + `.get` defensiveness all unchanged. The `.get("mode","normal")` default STAYS (defensive;
a reply missing `mode` still renders).

## 3. tests/test_voicectl.py edit sites

| Site | Current | End state |
|---|---|---|
| `_STATUS_ON` fixture :31-36 | includes `"final_model":"distil-large-v3","realtime_model":"small.en"`; NO `mode`/`model` | replace the pair with `"mode":"lite","model":"small.en"` (protocol realism post-S2: 13-key shape, mode constant) |
| @62 `test_format_status_multiline_has_partial_and_models` | asserts `mode: normal` (fixture default), `distil-large-v3`+`small.en` in text, `(loaded)` | drop the models/marker asserts; assert `mode: lite` (new fixture value); keep listening/partial/phase/device/uptime asserts. Rename to `..._has_partial_and_mode` (accuracy) |
| @75 `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode` | asserts lite cmds ⊆ `_COMMANDS` + `mode: lite` render | REWRITE → `test_lite_commands_are_rejected_as_usage_errors`: assert `"toggle-lite" not in ctl._COMMANDS and "start-lite" not in ctl._COMMANDS`; `ctl.main(["toggle-lite"]) == 64` and `ctl.main(["start-lite"]) == 64` (the no-socket usage path returns BEFORE any connect — safe, no daemon needed) |
| @84 `test_format_status_shows_unloaded_state_and_load_error` | asserts `phase: unloaded`, `(not loaded)`, `load error:`, `(loaded) not in` | drop the marker asserts (`(not loaded)`, `(loaded)`); KEEP phase + load-error asserts |
| @383-404 `test_help_surfaces_list_all_seven_commands` | `seven` set; asserts 7 cmds in `_COMMANDS`, format_help(), `ctl.__doc__` | REWRITE → `test_help_surfaces_list_all_five_commands`: `five={"toggle","start","stop","status","quit"}`; `set(ctl._COMMANDS)==five`; each in format_help() + `ctl.__doc__`; AND the negative sweep: `"toggle-lite" not in help_text`, `"start-lite" not in help_text`, same for `ctl.__doc__` (catches stale docstring/epilog lines) |
| loading-hint block @263-345, failed-load block @349-372 | uses start/toggle + stubs | UNTOUCHED (no lite refs; the routing-tuple edit doesn't change behavior) |

TDD: rewrite these tests FIRST (red against current ctl.py: 7-command `_COMMANDS`, lite accepted),
then edit ctl.py (green).

## 4. tests/test_control_socket.py edit sites (S2 owns the primary edits; S3 sweeps the residue)

After S2 (assumed landed): @131 deleted, @143 kept, snapshot key-set updated. S3's residue sweep:
- `_StubDaemon.start_lite`/`toggle_lite` METHODS :40-41 — S2's PRP does NOT name them; DELETE (dead
  once dispatch arms are gone; their presence would let a future test re-wire lite silently).
- `_StubDaemon` default snapshot :31-36 — if it still carries `final_model`/`realtime_model`, replace
  with `"mode":"lite","model":"small.en"` (13-key); verify `test_dispatch_status_has_all_keys` @120-123
  expects the 13-key set (`mode`,`model` in; `final_model`/`realtime_model` out).
- KEEP @143 `test_dispatch_status_response_carries_mode` (mode constant still flows — the contract's
  "keep mode-in-status assert").
- ADD the single-path replacement for @131's slot: `test_dispatch_lite_commands_are_unknown` — build a
  `_StubDaemon` (now lite-method-free), `_dispatch({"cmd":"start-lite"})` / `{"cmd":"toggle-lite"}` →
  `ok is False` + `"unknown command"` in error. Complements S2's test_daemon-level test by pinning the
  STUB SHAPE (proves the lite methods are really gone, not just unreached).

## 5. Downstream / boundaries

- P1.M2.T7.S1 appends `cancel` → final surface 6. Do NOT add it here (contract explicit).
- hypr-binds.conf:52 (toggle-lite bind) + `tests/test_config_repo_default.py:56` = S4's. prefetch =
  S4's. README usage table + tests/ACCEPTANCE.md = P1.M3.T10.S1 / P1.M3.T9.S1. NOT S3's.
- `pyproject.toml` console script (`voicectl = voice_typing.ctl:main`) unchanged — no entry-point edit.
- map §7's consumers of `mode`: ctl.py:69/90 rendering STAYS (constant "lite" flows through it);
  test_idle_and_gpu.sh T7 = P1.M3.T9.S1's.

## 6. Suite state around S3 (no red transient to interpret)

S2 lands with the suite GREEN (ctl.py's 7-command `_COMMANDS` are dead-but-harmless entries; voicectl
format tests use the CANNED fixture so they still pass; the lite-dispatch control-socket test is already
deleted by S2). S3 is a clean contract-update: tests-first red → ctl.py edit → green. The only red seen
is S3's OWN new tests against the pre-edit ctl.py.
