# Bug Fix Requirements

## Overview

Creative end-to-end PRD validation of the Lite Mode Silence Gate feature
(`asr.lite_post_speech_silence_duration`, PRD §4.2ter/§4.5) plus a broad sweep of the
surrounding lite-mode implementation against the PRD.

**Methodology:**
- Read the PRD requirements (§4.2ter, §4.5, §4.8, §4.10, §7 #10) and mapped each to code.
- Ran the full unit/integration suite: **363 passed** (test_config, test_config_repo_default,
  test_daemon, test_recorder_host, test_control_socket, test_feedback, test_textproc,
  test_typing_backends, test_voicectl, test_status_sh, test_systemd_unit).
- Directly exercised `cfg_to_kwargs()` across the full matrix
  (normal/lite × cuda/cpu × default/override/force_cpu) — the silence-gate override is correct
  in every path (lite=0.5, normal=0.6, CPU-lite=tiny.en+0.5, override=0.3, normal unaffected).
- Verified the live daemon at runtime: `voicectl status` reports `phase: unloaded`,
  `models: not loaded` (lazy-load guarantee honored), `mode: normal`, exit 0.

**Core finding — the silence-gate feature itself is CORRECT and COMPLETE:**
- `AsrConfig.lite_post_speech_silence_duration` (default `0.5`) with type validation + TOML
  round-trip + wrong-type rejection — all present and tested.
- `cfg_to_kwargs(lite=True)` overrides `post_speech_silence_duration` with the lite value
  (daemon.py:213) and is the ONLY override site; no other code path bypasses it (drain uses a
  fixed `_DRAIN_TIMEOUT_S=5.0`; idle auto-stop uses the separate `auto_stop_idle_seconds`).
- README (Lite-mode section + config table) and `tests/ACCEPTANCE.md` criterion #10 are
  correctly updated; the `_DRAIN_TIMEOUT_S` comment was updated to `~0.6s normal / ~0.5s lite`.

**What was found:** A coherent set of **documentation defects** where the lite-mode
user-facing surfaces contradict the PRD (§4.8 lists 7 commands; §4.10 pins the keybinds to
`Ctrl+Alt+Super+D` = normal and `Alt+Super+D` = lite) and contradict each other. None of these
break functionality — `hypr-binds.conf` and `README.md` are correct, and all lite commands work
— but they actively mislead users about how to discover and invoke lite mode. They slipped past
the standard validation because (a) comments/help text are not covered by the config
drift-guard (which only checks parsed VALUES) and (b) no test asserts the help/usage strings.

---

## Critical Issues (Must Fix)

None. No core functionality is broken. The silence-gate feature and all lite-mode commands work
correctly; 363 unit/integration tests pass.

---

## Major Issues (Should Fix)

### Issue 1: install.sh prints a WRONG keybind→command mapping and omits the lite commands in the primary onboarding output
**Severity**: Major
**PRD Reference**: §4.8 (command list: `toggle|start|stop|status|quit|toggle-lite|start-lite`),
§4.10 (keybinds: `CTRL SUPER ALT, D` → `toggle`; `SUPER ALT, D` → `toggle-lite`)
**Expected Behavior**: After `./install.sh`, the printed usage should (a) list all 7 commands
including `toggle-lite`/`start-lite`, and (b) state the correct keybind for `voicectl toggle`,
which is `Ctrl+Alt+Super+D` (the `CTRL` modifier distinguishes normal from lite).
**Actual Behavior**: `install.sh:178-179` prints:
```
usage  : .../voicectl toggle|start|stop|status|quit
          (bind SUPER+ALT+D -> voicectl toggle; see the Hyprland note below)
```
Two defects:
1. The usage line lists only 5 commands — `toggle-lite` and `start-lite` are missing (PRD §4.8
   specifies 7).
2. The parenthetical states `SUPER+ALT+D -> voicectl toggle`, which is **factually wrong**:
   per `hypr-binds.conf:44` and PRD §4.10, `SUPER ALT, D` (no CTRL) maps to `voicectl
   toggle-lite` (LITE mode). `voicectl toggle` (normal) is `CTRL SUPER ALT, D`.

This is the first thing every user sees after install. A user who binds/presses `SUPER+ALT+D`
expecting normal (big-model) mode will instead arm lite mode, and a user relying on the printed
usage line will never learn the lite commands exist. (The later `source = .../hypr-binds.conf`
instruction is correct, but the inline usage/bind hint is not.)
**Steps to Reproduce**:
1. `cd /home/dustin/projects/voice-typing && grep -n "usage  :\|bind SUPER" install.sh`
2. Compare with `hypr-binds.conf:42-44` and PRD §4.10.
**Suggested Fix**: In `install.sh`, change the usage line to include the lite commands, e.g.
`toggle|start|stop|status|quit|toggle-lite|start-lite`, and correct the bind hint to
`Ctrl+Alt+Super+D -> voicectl toggle` (and optionally note `Alt+Super+D -> voicectl toggle-lite`).
git blame shows this line predates lite mode (commit 3affa86) and was never updated when lite
mode was added (1b91154).

---

## Minor Issues (Nice to Fix)

### Issue 2: config.toml documents the wrong lite-mode keybind letter (`SUPER+ALT+F` instead of `SUPER+ALT+D`)
**Severity**: Minor
**PRD Reference**: §4.10 (`bind = SUPER ALT, D, exec, .../voicectl toggle-lite`)
**Expected Behavior**: The user-facing comment on `lite_model` should name the correct lite
keybind, `Alt+Super+D` (key **D**), matching `hypr-binds.conf`, `README.md`, and PRD §4.10.
**Actual Behavior**: `config.toml:34` says:
```
lite_model = "small.en"   # ... the SINGLE model loaded in LITE mode (`voicectl toggle-lite` / SUPER+ALT+F) ...
```
`SUPER+ALT+F` (key **F**) is not bound anywhere — the lite bind is `SUPER ALT, D` (key **D**).
A user reading the config file to learn the lite hotkey would press the wrong key (F) and
nothing would happen.
**Steps to Reproduce**: `grep -n "SUPER+ALT" config.toml` → `SUPER+ALT+F`; compare with
`grep -n "toggle-lite" hypr-binds.conf` → `SUPER ALT, D`.
**Suggested Fix**: Change `SUPER+ALT+F` → `SUPER+ALT+D` (or `Alt+Super+D`) in the
`config.toml` `lite_model` comment. (Introduced in commit d91a3df.)

### Issue 3: voicectl `--help` and CLI help text omit the lite commands (lists 5 of 7)
**Severity**: Minor
**PRD Reference**: §4.8 (`voicectl <toggle|start|stop|status|quit|toggle-lite|start-lite>`)
**Expected Behavior**: The CLI help surfaces (module docstring, argparse epilog, positional
`cmd` help) should list all 7 commands, matching the actual `_COMMANDS` tuple and PRD §4.8.
**Actual Behavior**: `voice_typing/ctl.py` lists only 5 commands in four help surfaces:
- module docstring (ctl.py:11-18): `Usage: voicectl <toggle|start|stop|status|quit>` and the
  subcommand block omits `toggle-lite`/`start-lite`.
- `_build_parser()` epilog (ctl.py:156): `"subcommands: toggle, start, stop, status, quit ..."`.
- positional `cmd` help (ctl.py:161): `"toggle | start | stop | status | quit"`.

This is **internally inconsistent** with the no-arg error path (ctl.py `main()`), which correctly
prints `choose from toggle, start, stop, status, quit, toggle-lite, start-lite` (all 7, via the
`_COMMANDS` tuple). So `voicectl --help` hides lite mode while `voicectl` (no args) reveals it.
The lite commands themselves work fine (`_COMMANDS` includes them and `main()` routes them
through the loading hint) — only the help text is stale.
**Steps to Reproduce**:
1. `.venv/bin/voicectl --help` → positional help and epilog show 5 commands.
2. `.venv/bin/voicectl` (no args) → error lists 7 commands.
**Suggested Fix**: Add `toggle-lite`/`start-lite` to the epilog, the `cmd` `help=`, and the
module-docstring usage/subcommand block in ctl.py. (The drift is untested: test_voicectl.py
asserts the commands are in `_COMMANDS` but no test asserts the help strings list them.)

### Issue 4: `daemon.py` `toggle_lite` docstring references the wrong key ("pressing F" should be "pressing D")
**Severity**: Minor
**PRD Reference**: §4.10 (`Alt+Super+D` → `toggle-lite`)
**Expected Behavior**: The docstring describing the lite key's behavior should say "pressing D".
**Actual Behavior**: `voice_typing/daemon.py:1410-1411` (`toggle_lite` docstring) says:
```
So: pressing F while idle arms in lite; pressing F while armed-in-lite disarms; pressing F while armed-in NORMAL ...
```
The key is **D**, not F (same thinko as Issue 2). Internal-only (docstring), but misleading to
any maintainer reading the toggle semantics.
**Steps to Reproduce**: `grep -n "pressing F" voice_typing/daemon.py`.
**Suggested Fix**: Replace the three occurrences of "pressing F" with "pressing D" in the
`toggle_lite` docstring (mirror the correct "pressing D" already used in the sibling `toggle`
docstring).

---

## Testing Summary
- Total tests performed: full unit/integration suite (363 test cases) + runtime daemon status
  probe + direct `cfg_to_kwargs` matrix (7 scenarios) + cross-file documentation consistency
  audit (keybind/command references across config.toml, install.sh, ctl.py, daemon.py,
  hypr-binds.conf, README.md).
- Passing: 363/363 automated tests. The silence-gate feature is functionally correct and
  complete in all code paths.
- Failing: 0 automated tests. 4 documentation defects found (1 Major, 3 Minor).
- Areas with good coverage: config schema/validation/round-trip, `cfg_to_kwargs` lite override
  (normal/lite × cuda/cpu × default/override/force_cpu), README + ACCEPTANCE.md sync for the
  silence gate, `_DRAIN_TIMEOUT_S` comment, status.sh `⚡` prefix, runtime lazy-load state.
- Areas needing more attention: user-facing documentation surfaces for lite mode (config.toml
  comment, install.sh onboarding output, voicectl help text) were not synced when lite mode was
  added and now contradict the PRD and each other on the lite keybind (`Alt+Super+D`) and the
  full command set (7 commands). Comments/help strings are not covered by the config
  drift-guard or any test, which is why this drift went undetected.
