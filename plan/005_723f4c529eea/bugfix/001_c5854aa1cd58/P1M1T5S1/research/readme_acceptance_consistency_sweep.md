# Research — P1.M1.T5.S1: Verify README.md + overview docs consistent with corrected lite-mode surfaces

## §0 — Task nature

This is a **Mode B changeset-level documentation SYNC task** (per item DOCS). Its job is a
**consistency sweep** of the overview/README docs that span the whole lite-mode delta, against the
**corrected** lite-mode surfaces produced by P1.M1.T1.S1–P1.M1.T4.S1. It is NOT a code task. The
contract INPUT is the now-correct install.sh, config.toml, ctl.py, daemon.py. The LOGIC is a
deterministic grep sweep for three drift criteria. The OUTPUT is "README.md and tests/ACCEPTANCE.md
confirmed consistent (or corrected if a gap is found)."

**Expected outcome (high confidence): NO code changes.** Both target docs are already correct.
This research file is the evidence the implementing agent reproduces to PROVE consistency.

## §1 — The corrected surfaces (the CONTRACT INPUTS — what the docs must agree WITH)

Empirically verified on the live tree (all of T1–T4 outputs land here):

| Surface | File:line | Corrected content (verified) | Source subtask |
|---|---|---|---|
| install.sh usage line | install.sh:178 | `toggle\|start\|stop\|status\|quit\|toggle-lite\|start-lite` (7 cmds) | T1.S1 ✅ complete |
| install.sh bind hint | install.sh:179 | `Ctrl+Alt+Super+D -> voicectl toggle; Alt+Super+D -> voicectl toggle-lite` | T1.S1 ✅ complete |
| config.toml lite_model comment | config.toml:34 | `SUPER+ALT+D` (was F) | T2.S1 ✅ complete |
| ctl.py module docstring | ctl.py:22 | `Usage: voicectl <toggle\|start\|stop\|status\|quit\|toggle-lite\|start-lite>` (7) | T3.S1 ✅ complete |
| ctl.py argparse epilog | ctl.py:158 | `subcommands: toggle, start, stop, status, quit, toggle-lite, start-lite` | T3.S1 ✅ complete |
| ctl.py positional help | ctl.py:163 | `toggle \| start \| stop \| status \| quit \| toggle-lite \| start-lite` | T3.S1 ✅ complete |
| daemon.py toggle_lite docstring | daemon.py:1410-1411 | `pressing D` ×3 (was F) | T4.S1 (Ready; live file ALREADY shows `pressing D`) |

**Source of truth for keybinds** — `hypr-binds.conf:42,44` (untouched, correct):
```
bind = CTRL SUPER ALT, D, exec, .../voicectl toggle       # NORMAL
bind = SUPER ALT, D,      exec, .../voicectl toggle-lite   # LITE
```
Both binds use key **D**, never F. `Ctrl+Alt+Super+D` = normal (has CTRL); `Alt+Super+D` = lite (no CTRL).

**Source of truth for command set** — `ctl.py:37` `_COMMANDS = (toggle, start, stop, status, quit, toggle-lite, start-lite)` (7).

## §2 — README.md verification (CRITERIA a/b/c) — ALREADY CORRECT

Swept README.md (380 lines) against the three drift criteria. **No gap found.**

### (a) Keybind letter is D (not F) everywhere — PASS
```
grep -niE "super\+alt\+f|alt\+super\+f|super alt, f|pressing f|bind .* f," README.md
→ NO wrong-F references found
```
All keybind mentions use key D:
- L81: `Bind **Ctrl+Alt+Super+D** for the big model (normal mode) and **Alt+Super+D** for **lite mode**`
- L103: `**Normal / big mode** (**Ctrl+Alt+Super+D**)`
- L104: `**Lite / little mode** (**Alt+Super+D**)`
- L126: `**Alt+Super+D** keybind`

### (b) All 7 commands listed/mentioned where a command list appears — PASS
README does NOT reproduce install.sh's pipe-delimited usage line at all. It documents commands
**contextually** in prose + code blocks, and all 7 appear (`toggle`, `start`, `stop`, `status`,
`quit`, `toggle-lite`, `start-lite` all occur). There is NO 5-of-7 enumeration — so no place where
lite commands are wrongly omitted. Verified: no `toggle|start|stop|status|quit` (pipe-delimited,
5-cmd) string exists in README. (grep §2b in PRP reproduces this.)

### (c) Keybind→command mappings match hypr-binds.conf — PASS
- README L99-100 (verbatim bind block) EXACTLY matches hypr-binds.conf:42,44:
  `bind = CTRL SUPER ALT, D, ... toggle` and `bind = SUPER ALT, D, ... toggle-lite`.
- README L81/L103/L104 map `Ctrl+Alt+Super+D`→normal/big and `Alt+Super+D`→lite — matches hypr-binds.conf.
- README L125 maps `toggle-lite`/`start-lite` + `Alt+Super+D` — correct (lite bind = toggle-lite).
- README L171 (config table) maps `lite_model` → `toggle-lite` / `Alt+Super+D` — correct.

**system_context.md:51** explicitly states: "## README Status (ALREADY CORRECT — no changes
needed)" and enumerates L81, L99-100, L125, L171 as the canonical correct references. It also
clarifies the install.sh header-comment red herring (L57-59): README does NOT copy install.sh's
usage line verbatim — it has independent correct content. So the corrected install.sh usage line
(T1.S1) does NOT force a README change.

## §3 — tests/ACCEPTANCE.md verification — ALREADY CORRECT (one subtle point)

Swept tests/ACCEPTANCE.md against the three criteria. **No gap found.**

### (a) Keybind letter is D (not F) — PASS (vacuous)
```
grep -niE "super\+alt\+f|alt\+super\+f|super alt, f|pressing f|bind .* f," tests/ACCEPTANCE.md
→ NO wrong-F references found
```
ACCEPTANCE.md does NOT state the keybind LETTERS at all (no `Super+`/`Alt+`/`Ctrl+` strings) — it
references commands (`toggle-lite`, `toggle`) and modes (`mode: lite`), not the hotkey letters. So
criterion (a) is vacuously satisfied (nothing to drift).

### (b) Command-list consistency — PASS (criterion 6 is a faithful PRD §7 QUOTE)
- **Criterion 10** (the lite-mode acceptance criterion) correctly documents `toggle-lite` arms lite,
  `toggle` arms normal, mode reporting, lite silence gate. No drift.
- **Criterion 6** lists `voicectl toggle/start/stop/status/quit` (5 commands). **THIS IS NOT DRIFT.**
  The ORIGINAL PRD §7 criterion 6 (`PRD.md:371`) says verbatim:
  > "6. `voicectl toggle/start/stop/status/quit` all work; daemon runs as a systemd user service,
  > starts un-armed (not listening) and un-loaded (~0 VRAM until first arm, §4.2bis), auto-restarts on failure."

  So ACCEPTANCE.md criterion 6 is a VERBATIM QUOTE of PRD §7 #6. The PRD deliberately splits the
  acceptance criteria: **criterion 6 tests the 5 BASE commands' systemd integration + boot state**;
  **criterion 10 (§4.2ter) tests lite mode specifically** (`toggle-lite`, mode reporting, lite
  silence gate). Changing criterion 6 to 7 commands would DIVERGE FROM THE PRD — it must NOT be
  "fixed". (PRD §4.8 at `PRD.md:286` is the canonical 7-command CLI list; §7 #6 is a narrower
  acceptance check. These are consistent by design.)

### (c) Keybind→command mappings — PASS (vacuous)
ACCEPTANCE.md does not state keybind→command mappings (no keybind letters present), so (c) is
vacuously satisfied. Criterion 10 references `toggle-lite`→`mode: lite` and `toggle`→`mode: normal`,
which is correct.

## §4 — CONCLUSION

**Both README.md and tests/ACCEPTANCE.md are ALREADY CONSISTENT** with the corrected lite-mode
surfaces. No code changes are required for P1.M1.T5.S1. The deliverable is the **verification record
itself**: the implementing agent runs the 3-criteria grep sweep (the validation gates in the PRP),
captures the evidence, and reports "confirmed consistent — no changes needed."

The #1 implementation hazard is the agent MISREADING ACCEPTANCE.md criterion 6's 5-command list as a
gap and "fixing" it to 7 — which would introduce a divergence from PRD §7 #6. The PRP's Gotcha #1
guards against this. The #2 hazard is the agent editing README/ACCEPTANCE "to be thorough" when no
gap exists — the PRP's scope discipline (Gotcha #2) forbids speculative edits.

## §5 — Parallel-execution note (T4.S1 in flight)

T4.S1 (parallel) edits `voice_typing/daemon.py` + `tests/test_daemon.py` (the toggle_lite docstring
F→D + a TDD test). T5.S1 edits NEITHER of those (it only READS README.md + tests/ACCEPTANCE.md and,
if a gap were found, edits one of those two). DISJOINT files — no merge contention. T5.S1 depends on
T1–T4 being complete (the corrected surfaces exist), which the live tree confirms (all four surfaces
read as corrected: install.sh:178-179, config.toml:34, ctl.py:22/158/163, daemon.py:1410-1411).
