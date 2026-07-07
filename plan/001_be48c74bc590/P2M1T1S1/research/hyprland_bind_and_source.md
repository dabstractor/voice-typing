# Research note — P2.M1.T1.S1 (hypr-binds.conf + source instruction)

Scope: a single committed Hyprland config file at repo root + a one-line truth-up of the stale
"after P2.M1" lead-in phrase in `install.sh`. Nothing else. This note captures the load-bearing
facts the implementer needs.

## 1. Hyprland bind + source syntax (authoritative)

- **Binds** — Hyprland Wiki, *Configuring/Basics/Binds*:
  https://wiki.hypr.land/Configuring/Basics/Binds/
  > "Basic `bind = MODS, key, dispatcher, params` — for example,
  > `bind = SUPER_SHIFT, Q, exec, firefox` binds SUPER+SHIFT+Q to launch Firefox."

  - The MODS token accepts **multiple modifiers**; Hyprland's parser splits the MODS field on
    **whitespace OR underscore** — so `SUPER ALT` (PRD §4.10's exact spelling) and `SUPER_ALT`
    are equivalent. The PRD is the contract ⇒ use `SUPER ALT` (space) verbatim. Do not "normalize"
    it to `SUPER_ALT`.
  - The `exec` dispatcher runs the remainder of `params` as a shell command line. A path with no
    spaces (`/home/dustin/projects/voice-typing/.venv/bin/voicectl`) + a single arg (`toggle`)
    needs **no quoting**. Correct as written.

- **source** — Hyprland Wiki, *Configuring* (the `source` keyword):
  https://wiki.hypr.land/Configuring/
  - `source = <path>` reads another config file inline. Relative paths resolve against
    `~/.config/hypr/`; **absolute paths work as-is**. ⇒ `source = /home/dustin/projects/voice-typing/hypr-binds.conf`
    (absolute) is correct and matches what `install.sh` already prints.
  - Both `source=...` (no space) and `source = ...` (spaces) parse — the user's own config mixes
    both. The PRD + install.sh use `source = ...` (spaces) ⇒ keep that spelling exactly.

- **Bind precedence** — Hyprland uses the **LAST** matching bind when two `bind =` lines claim the
  same MODS+key. This matters because the user's `hyprland.conf` already sources
  `custom/keybinds.conf` and `hyprland/keybinds.conf` (see §3). ⇒ document "source this file LAST"
  in the conf comment, and a fallback rebind (`SUPER+ALT+V`).

## 2. install.sh — exact current state (truth-up target)

`install.sh` (P1.M6.T1.S1, COMPLETE) already prints the Hyprland source instruction. Computed path:
- `REPO="$SCRIPT_DIR"` where `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"` (install.sh:31-32).
- `install.sh` lives at `/home/dustin/projects/voice-typing/install.sh` ⇒ `REPO=/home/dustin/projects/voice-typing`.

Current lines (install.sh:136-138):
```bash
echo "Hyprland (after P2.M1 creates hypr-binds.conf), add to ~/.config/hypr/hyprland.conf:"
echo "  source = $REPO/hypr-binds.conf"
```

- The **snippet** (`source = $REPO/hypr-binds.conf` → `source = /home/dustin/projects/voice-typing/hypr-binds.conf`)
  is ALREADY correct and matches the path of the file this task creates. The contract's "ensure the
  snippet printed by install.sh matches this file" is satisfied by the path being identical; verify
  with a grep (see PRP validation).
- The **lead-in phrase** `(after P2.M1 creates hypr-binds.conf)` becomes factually stale the moment
  this task creates the file. Truth it up by dropping the parenthetical (keep the `source =` line
  byte-for-byte identical). This is a 1-line edit, fully in scope, keeps Mode-A docs honest, and is
  the natural reading of "ensure … matches this file."
- DO NOT touch any other install.sh line (the tmux snippet, the `usage` line, the daemon-status
  echo, etc. are stable surfaces the README copies).

## 3. The user's real hyprland.conf (`~/.config/hypr/hyprland.conf`) — verified

It is a thin dispatcher that `source`s modular files (both `source=rel/path` and `source = rel/path`):
```
source=hyprland/env.conf
source=hyprland/keybinds.conf
source=custom/keybinds.conf   # ← user's custom binds land here
...
source=monitors.conf
```
Implications:
- Adding `source = /home/dustin/projects/voice-typing/hypr-binds.conf` **anywhere** in this file
  works (absolute path). Placing it at the BOTTOM makes its `bind =` win precedence over any
  earlier SUPER+ALT+D bind. Document this in the conf comment.
- We must NOT auto-edit the user's hyprland.conf (PRD §4.10). We only print the instruction.
- If SUPER+ALT+D is already bound in `custom/keybinds.conf` / `hyprland/keybinds.conf`, our bind may
  be shadowed (or shadow theirs) depending on order. ⇒ the conf comment + README troubleshooting
  (P2.M1.T2.S1) note: check those two files for a conflicting `bind` if the hotkey is inert.

## 4. The Mode-A doc convention to mirror: `voice_typing/status.sh`

`status.sh` (P1.M3.T2.S1) established the project's Mode-A documentation pattern: a header COMMENT
BLOCK inside the artifact itself IS the user-facing doc, titled `USER INTEGRATION (item DOCS: Mode A
— this comment IS the … doc)`, with the exact lines to paste, the "we never edit your …conf" promise,
and copy-pasteable snippets. **Mirror this structure verbatim in `hypr-binds.conf`** so the hotkey
doc is self-contained in the file the user sources. This is exactly what the item's DOCS contract
demands ("The file itself + its comment IS the user-facing hotkey doc").

## 5. Scope boundaries (no conflicts)

- **Parallel item P1.M7.T4.S1** (Implementing): ships ONLY `tests/test_idle_and_gpu.sh` +
  `tests/ACCEPTANCE.md`. This task ships `hypr-binds.conf` (repo root, NEW) + a 1-line `install.sh`
  edit. **Zero file overlap** — safe to land in parallel.
- **README (P2.M1.T2.S1, Planned)** will copy the hotkey snippet verbatim from this file +
  install.sh. ⇒ make the `source = …/hypr-binds.conf` line and the bind line **stable / final**
  (no TBDs), so the README can lift them without reconciliation.
- **voicectl (P1.M5.T1.S1, COMPLETE)**: the console script exists at
  `/home/dustin/projects/voice-typing/.venv/bin/voicectl` (verified executable). Its `toggle`
  subcommand arms/disarms the mic (ctl.py `format_result` → `listening: on|off`, exit 0). This is
  the exact command the bind execs.

## 6. The bind path's correctness

`bind = SUPER ALT, D, exec, /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle`
- The `.venv/bin/voicectl` absolute path is what `[project.scripts]` (pyproject.toml) installs via
  `uv sync`. It matches the path the systemd unit's launcher (`launch_daemon.sh`) and `install.sh`'s
  own `usage` line reference (`$REPO/.venv/bin/voicectl toggle|start|stop|status|quit`). Consistent.
- If the venv were ever relocated, the bind, the systemd unit, and install.sh would all need the
  same update — that is a known, documented coupling, not a defect of this task.
