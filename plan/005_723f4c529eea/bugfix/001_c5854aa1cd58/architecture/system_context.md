# System Context — Lite-mode Documentation Defect Remediation

## Project Summary
**voice-typing** is a GPU-accelerated (faster-whisper) voice dictation daemon for Hyprland/Wayland.
It exposes a CLI client `voicectl` over an AF_UNIX control socket. The daemon has two modes:
- **Normal** ("big model"): `distil-large-v3` + `small.en` — high accuracy, slower finals.
- **Lite** ("little model"): `small.en` only — ~half the VRAM, faster finals, lower accuracy.

## Canonical Keybinds (source of truth — `hypr-binds.conf:42,44`)
```
bind = CTRL SUPER ALT, D, exec, .../voicectl toggle       # NORMAL mode (big model)
bind = SUPER ALT, D,      exec, .../voicectl toggle-lite   # LITE mode (small model only)
```
- **Normal toggle**: `Ctrl+Alt+Super+D` (key **D**, has CTRL modifier)
- **Lite toggle**: `Alt+Super+D` (key **D**, NO CTRL modifier)
- Both binds use key **D** — never F.

## Canonical Command Set (source of truth — `ctl.py:35`)
```python
_COMMANDS = ("toggle", "start", "stop", "status", "quit", "toggle-lite", "start-lite")
```
7 commands total. The lite variants: `toggle-lite` and `start-lite`.

## Confirmed Issues (all 4 validated against actual source)

### Issue 1 (MAJOR) — install.sh lines 178-179
**Current (WRONG):**
```
echo "usage  : $REPO/.venv/bin/voicectl toggle|start|stop|status|quit"
echo "          (bind SUPER+ALT+D -> voicectl toggle; see the Hyprland note below)"
```
**Defects:** (a) usage lists 5 commands (missing `toggle-lite`/`start-lite`); (b) bind hint says
`SUPER+ALT+D -> voicectl toggle` which is FALSE — that bind is `toggle-lite`.

### Issue 2 (MINOR) — config.toml line 34
**Current (WRONG):** comment says `SUPER+ALT+F` (key F).
**Correct:** `SUPER+ALT+D` (key D), matching hypr-binds.conf.

### Issue 3 (MINOR) — ctl.py 3 stale help surfaces (all list only 5 of 7 commands)
- Module docstring lines 11-20: `Usage: voicectl <toggle|start|stop|status|quit>`
- argparse epilog line 156: `"subcommands: toggle, start, stop, status, quit ..."`
- Positional `cmd` help line 161: `"toggle | start | stop | status | quit"`
- **Internal inconsistency:** `main()` no-arg error path (lines 177-181) correctly prints all 7
  via `_COMMANDS`, but `--help` shows only 5.

### Issue 4 (MINOR) — daemon.py lines 1410-1411 (toggle_lite docstring)
**Current (WRONG):** 3 occurrences of "pressing F" in the toggle_lite docstring.
**Correct:** "pressing D" (mirrors the sibling `toggle` docstring at lines 1377-1378 which
correctly says "pressing D").

## README Status (ALREADY CORRECT — no changes needed)
README.md is the canonical, correct documentation surface:
- Line 81: "Bind **Ctrl+Alt+Super+D** for the big model (normal mode) and **Alt+Super+D** for **lite mode**"
- Lines 99-100: Correct bind lines matching hypr-binds.conf
- Line 125: "Arm it with `voicectl toggle-lite` / `start-lite`, or the **Alt+Super+D** keybind"
- Line 171: config table says `toggle-lite / Alt+Super+D`
README does NOT copy install.sh's usage line verbatim — it has independent correct content.
The install.sh header comment (lines 21-22) references "keep them stable" for the tmux/hypr snippets,
but the usage/bind hint line has drifted and is NOT mirrored verbatim in README.

## Testing Patterns
- **test_voicectl.py**: Tests `format_result()`, `main()` exit codes, `_COMMANDS` membership.
  Uses `capfd` for stderr capture, `monkeypatch` for env/socket stubbing. Asserts `toggle-lite`/
  `start-lite` are in `_COMMANDS` (line 77) but **NO test asserts the help/epilog/usage strings**.
- **test_config_repo_default.py**: Validates config.toml parsed values. Does NOT check comments.
- **test_status_sh.py**: Tests status.sh shell script (pattern for testing shell output).
- **Implied TDD (per PRD §3):** Each fix subtask implies: write failing test → implement → pass.
