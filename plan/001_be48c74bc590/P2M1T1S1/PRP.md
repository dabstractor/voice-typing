# PRP — P2.M1.T1.S1: hypr-binds.conf (SUPER+ALT+D toggle) + source instruction

> **Scope reminder.** This is a **2-file** change, both tiny and mostly prose: (1) **CREATE**
> `hypr-binds.conf` at repo root — a single Hyprland `bind =` line + a Mode-A header comment that
> **IS** the user-facing hotkey doc; (2) **EDIT** one line in `install.sh` to drop the now-stale
> `(after P2.M1 creates hypr-binds.conf)` lead-in phrase (the `source =` snippet it prints is
> already correct and stays byte-identical). Nothing else. No Python, no tests, no `.gitignore`,
> no README (that is P2.M1.T2.S1), no auto-edit of the user's `hyprland.conf`.

## Goal

**Feature Goal**: Ship a **committed, self-documenting** `hypr-binds.conf` at the repo root that binds
**SUPER+ALT+D** to `voicectl toggle` (arm/disarm the voice-typing mic), plus a copy-pasteable
`source =` instruction the user adds to `~/.config/hypr/hyprland.conf`. The file is **sourced, not
copied** (so `git pull` + `hyprctl reload` propagate changes), and its header comment **is** the
hotkey documentation (Mode A — mirrors the `status.sh` convention). `install.sh`'s printed source
snippet already matches this file's absolute path; this task also truth-ups `install.sh`'s lead-in
phrase, which currently advertises a file that did not yet exist (it now does).

**Deliverable** (2 files — 1 ADD, 1 EDIT; **zero** other changes):
1. `hypr-binds.conf` — **NEW** at repo root (`/home/dustin/projects/voice-typing/hypr-binds.conf`).
   Contains EXACTLY one `bind =` line (PRD §4.10 verbatim) and a leading `#` comment block (the
   Mode-A hotkey doc) that includes the exact `source = /home/dustin/projects/voice-typing/hypr-binds.conf`
   line, the precedence/fallback note, and the "we never edit your hyprland.conf" promise. Plain
   text (Hyprland conf syntax: `#` comments, `key = value` / `bind = …` directives).
2. `install.sh` — **EDIT 1 line** (the Hyprland lead-in echo). Replace
   `"Hyprland (after P2.M1 creates hypr-binds.conf), add to ~/.config/hypr/hyprland.conf:"` with a
   phrase that no longer claims the file is missing. **Keep** the next line
   `echo "  source = $REPO/hypr-binds.conf"` byte-for-byte unchanged (it already prints the correct,
   matching absolute path). Nothing else in `install.sh` moves.

**Success Definition**:
- (a) `hypr-binds.conf` exists at the repo root and contains the **exact** bind line
      `bind = SUPER ALT, D, exec, /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle`.
- (b) The `.venv/bin/voicectl` path in that bind line is an **existing, executable** file (it is —
      `[project.scripts] voicectl` installed by `uv sync`; verified present).
- (c) The `hypr-binds.conf` comment contains the **exact** user line
      `source = /home/dustin/projects/voice-typing/hypr-binds.conf` (the string `install.sh` prints).
- (d) `install.sh` prints a `source =` snippet whose path **equals** the absolute path of the file
      in (a) — i.e. `source = /home/dustin/projects/voice-typing/hypr-binds.conf` (verified by
      resolving `install.sh`'s `$REPO` and grepping its echo).
- (e) `install.sh`'s Hyprland lead-in no longer says "after P2.M1 creates hypr-binds.conf" (the file
      now exists); the `source =` echo line itself is unchanged.
- (f) The file's header comment follows the Mode-A doc pattern from `voice_typing/status.sh`
      (a `USER INTEGRATION` block with the copy-paste line + "we never edit your hyprland.conf").
- (g) **Manual end-to-end proof** (documented, run by the implementer once): after adding the
      `source =` line to `~/.config/hypr/hyprland.conf` and `hyprctl reload`, pressing SUPER+ALT+D
      flips `voicectl status` between `listening: on` and `listening: off`.
- (h) **No out-of-scope edits**: no change to `voice_typing/*`, `pyproject.toml`, `config.toml`,
      `systemd/*`, `tests/*`, `.gitignore`, `PRD.md`, any `tasks.json`, any `prd_snapshot.md`; no
      README (P2.M1.T2.S1); no edit to the user's `~/.config/hypr/hyprland.conf`.

## User Persona

**Target User**: **dustin** (Hyprland + tmux user) who wants a one-key toggle for the voice-typing
mic, and a future **fresh-clone** reader who runs `./install.sh` and needs to be told exactly which
one line to add to `hyprland.conf`. Secondary: the **README author** (P2.M1.T2.S1) who will lift the
hotkey snippet verbatim from this file.

**Use Case**:
```
# after `./install.sh` (daemon running, NOT listening):
# 1) add one line to ~/.config/hypr/hyprland.conf (printed by install.sh; also in hypr-binds.conf):
#      source = /home/dustin/projects/voice-typing/hypr-binds.conf
# 2) hyprctl reload
# 3) press SUPER+ALT+D  ->  mic arms   ->  speak  ->  text types into focused window / tmux pane
# 4) press SUPER+ALT+D  ->  mic disarms (nothing typed while off)
```

**Pain Points Addressed**: (1) PRD §4.10 mandates the bind live in a **repo file** (not appended to
the user's config) so it is versioned and survives re-installs — this is that file. (2) The user
must never have their `hyprland.conf` auto-edited (PRD §4.10); the conf comment + install.sh tell
them the exact line to add themselves. (3) install.sh currently advertises the bind file as
not-yet-created ("after P2.M1 creates hypr-binds.conf") — this task makes that true and removes the
stale caveat.

## Why

- **PRD §4.10 is the contract.** It says: do NOT append to the user's Hyprland config; instead
  create `hypr-binds.conf` in the repo with the single `bind =` line, and **print** a `source =`
  instruction. This item is the literal fulfillment of that section.
- **Sourcing (not copying) keeps the bind versioned.** Because the user `source`s the repo file,
  a `git pull` + `hyprctl reload` updates the hotkey with no per-user copy to drift. The absolute
  path in the `source =` line makes this robust regardless of cwd.
- **install.sh alignment.** install.sh (P1.M6.T1.S1) already prints the source snippet; the item
  contract requires "the snippet printed by install.sh matches this file." The path already matches;
  this task also removes the now-false "(after P2.M1 …)" qualifier so the printed instruction
  describes reality.
- **Sets up the README.** PRD §7 criterion 7 requires the README to document the hotkey snippet.
  P2.M1.T2.S1 will copy the `source =` line and the bind from this file verbatim — so they must be
  final and stable now.
- **Scope discipline.** This is a config + a 1-line doc edit. It consumes the voicectl console
  script (P1.M5.T1.S1) and aligns with install.sh (P1.M6.T1.S1). It does NOT touch any Python
  module, test, or the README.

## What

A plain-text Hyprland config file and a one-line truth-up of `install.sh`.

### The file (`hypr-binds.conf`) — content contract

- **Header comment block** (Mode A — IS the hotkey doc; mirror `voice_typing/status.sh`):
  - One-line title: `hypr-binds.conf — voice-typing Hyprland keybindings (PRD §4.10; P2.M1.T1.S1).`
  - "WHAT THIS IS": a single bind that arms/disarms the mic via `voicectl toggle`; sourced (not
    copied) so edits here take effect on `hyprctl reload`.
  - A `USER INTEGRATION (item DOCS: Mode A — this comment IS the hotkey doc)` block containing the
    **exact** line to add to `~/.config/hypr/hyprland.conf`:
      `source = /home/dustin/projects/voice-typing/hypr-binds.conf`
    plus "reload with `hyprctl reload`", "the daemon must be running (it boots NOT-listening, so the
    first SUPER+ALT+D arms it)", and "we never edit your hyprland.conf for you".
  - A **precedence note**: Hyprland uses the LAST matching bind, so `source` this file LAST (or
    rebind to e.g. `SUPER ALT, V` if SUPER+ALT+D collides with an existing bind in
    `~/.config/hypr/custom/keybinds.conf` or `~/.config/hypr/hyprland/keybinds.conf`).
  - A **mods-syntax note**: MODS are space- OR underscore-separated (`SUPER ALT` == `SUPER_ALT`);
    link the wiki Binds page.
- **The bind line** (PRD §4.10 verbatim — do NOT alter spacing/quoting):
  ```
  bind = SUPER ALT, D, exec, /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle
  ```
- No other directives. (Do NOT add `bindl`, `bindm`, or a submap — out of scope.)

### The `install.sh` edit — content contract

- Replace ONLY the lead-in echo (install.sh:136). New text must drop the "(after P2.M1 creates
  hypr-binds.conf)" qualifier and read as a present-tense instruction, e.g.:
  `"Hyprland — source the repo's hypr-binds.conf from ~/.config/hypr/hyprland.conf (add this line):"`.
- **Leave the next line untouched**: `echo "  source = $REPO/hypr-binds.conf"` (install.sh:137). It
  already expands to the correct absolute path and must stay identical (the README will copy it).

### Success Criteria

- [ ] `hypr-binds.conf` exists at repo root with the exact bind line (PRD §4.10 verbatim).
- [ ] The `.venv/bin/voicectl` path in the bind line is an existing executable.
- [ ] The conf comment contains the exact `source = /home/dustin/projects/voice-typing/hypr-binds.conf`.
- [ ] `install.sh` prints `source = /home/dustin/projects/voice-typing/hypr-binds.conf` (path == the
      file's real path), and its lead-in no longer claims the file is missing.
- [ ] Mode-A header comment present (mirrors `status.sh`): copy-paste line + "we never edit your
      hyprland.conf" + precedence/fallback note.
- [ ] Manual: `source` the file in `hyprland.conf`, `hyprctl reload`, SUPER+ALT+D toggles
      `voicectl status` on/off.
- [ ] No out-of-scope files changed.

## All Needed Context

### Context Completeness Check

_Pass._ A reader with zero codebase knowledge can implement this from the PRP alone: the **exact
bind line** and the **exact `source =` line** are pinned verbatim (PRD §4.10 + this PRP); the
Mode-A comment structure is specified by pointing at `voice_typing/status.sh` (the established
in-repo pattern to mirror); the single `install.sh` edit is pinned by old-text/new-text with line
numbers; the Hyprland syntax (`bind = MODS, key, dispatcher, params`; `source = <abs path>`) is
backed by the wiki URLs; and every validation command is executable as written (greps + a realpath
match + a manual `hyprctl reload` toggle). The "last bind wins" precedence rule — the one real
gotcha — is documented with the concrete files to check.

### Documentation & References

```yaml
# MUST READ #1 — the spec for the file's existence + the exact bind line + the source instruction
#                (it is the contract; copy the bind line verbatim).
- file: PRD.md
  section: "§4.10 Phase 2 (implement after all tests pass — small, do it in the same run)"
  why: "Defines hypr-binds.conf's contents verbatim: `bind = SUPER ALT, D, exec,
        /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle`, plus 'print an instruction
        to source it from ~/.config/hypr/hyprland.conf. Do NOT modify the user's Hyprland config
        automatically.' Acceptance §7 criterion 7 requires the README document the hotkey snippet
        (this file is the source of that snippet for P2.M1.T2.S1)."
  critical: "Use the bind line EXACTLY (space-separated MODS `SUPER ALT`; no quoting). Do NOT
             auto-edit hyprland.conf — only print the source instruction."

# MUST READ #2 — the Mode-A doc pattern to mirror (the header comment block IS the user doc).
- file: voice_typing/status.sh
  why: "Established in-repo convention: a `# USER INTEGRION (item DOCS: Mode A — this comment IS
        the … doc)` block inside the artifact, with the exact paste-able lines and the 'we never
        edit your <x>.conf for you' promise. Mirror this structure in hypr-binds.conf so the hotkey
        doc is self-contained in the file the user sources."
  pattern: "Top-of-file `#` comment: one-line title, WHAT THIS IS, USER INTEGRATION block with the
            copy-paste snippet, then the actual directive(s) at the bottom."
  gotcha: "status.sh uses POSIX-sh `#` comments; Hyprland conf ALSO uses `#` comments — same char,
           so the pattern transfers directly."

# MUST READ #3 — install.sh: the exact line to edit (136) + the line to leave untouched (137).
- file: install.sh
  why: "Lines 136-138 currently print the Hyprland source instruction. install.sh:31-32 define
        REPO=SCRIPT_DIR=/home/dustin/projects/voice-typing (where install.sh lives), so the echo at
        137 (`source = $REPO/hypr-binds.conf`) already prints the correct absolute path. Only line
        136's '(after P2.M1 creates hypr-binds.conf)' qualifier is stale and must go."
  pattern: "Edit ONLY the lead-in echo text; keep the `source = $REPO/hypr-binds.conf` echo
            byte-identical (the README copies it). Do not touch the tmux snippet, usage, or status
            echoes."
  critical: "Do NOT change `$REPO` resolution or the `source =` echo line — that line IS the
             contract's 'snippet printed by install.sh'."

# MUST READ #4 — the command the bind execs (its path + the toggle semantics).
- file: voice_typing/ctl.py
  why: "`voicectl toggle` connects to the control socket and flips the listening gate; on success
        it prints `listening: on` / `listening: off` and exits 0 (ctl.py format_result). The
        [project.scripts] entry installs it at .venv/bin/voicectl (pyproject.toml)."
  critical: "The bind must call the FULL path /home/dustin/projects/voice-typing/.venv/bin/voicectl
             (no PATH reliance) — matches the systemd unit + install.sh usage line."

# External citations — Hyprland syntax authority (anchors for the conf comment's wiki link).
- url: https://wiki.hypr.land/Configuring/Basics/Binds/
  why: "'bind = MODS, key, dispatcher, params' — e.g. bind = SUPER_SHIFT, Q, exec, firefox. Confirms
        the `exec` dispatcher + that MODS split on whitespace OR underscore (SUPER ALT == SUPER_ALT)."
  critical: "The PRD's `SUPER ALT` (space) is valid; do not 'fix' it to SUPER_ALT."
- url: https://wiki.hypr.land/Configuring/
  why: "The `source = <path>` keyword: inlines another config file; relative paths resolve under
        ~/.config/hypr/, absolute paths work as-is. Confirms `source = /abs/path/hypr-binds.conf`."
  critical: "Use the ABSOLUTE repo path (the file is not under ~/.config/hypr)."
```

### Current Codebase tree (state at P2.M1.T1.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── .gitignore                 # READ-ONLY (do NOT touch)
├── PRD.md                     # READ-ONLY (§4.10 = the contract)
├── pyproject.toml uv.lock     # READ-ONLY ([project.scripts] voicectl present; venv-built)
├── config.toml                # READ-ONLY
├── systemd/voice-typing.service  # READ-ONLY
├── install.sh                 # ← EDIT 1 line (136); keep 137 byte-identical
├── voice_typing/              # READ-ONLY (status.sh = the Mode-A pattern to mirror; ctl.py = the
│   ├── ctl.py                 #   command the bind execs; daemon.py = listening gate)
│   ├── status.sh              # ← read this for the comment-block pattern
│   └── ...
├── tests/                     # READ-ONLY (P1.M7 owns it; no test added by THIS task)
└── .venv/bin/voicectl         # EXISTS + executable (verified) — the bind's exec target
# hypr-binds.conf              # ← CREATE at repo root (this task)
# README.md                    # does NOT exist yet (P2.M1.T2.S1, Planned)
# User side: ~/.config/hypr/hyprland.conf EXISTS — READ-ONLY; sources modular files
#             (custom/keybinds.conf, hyprland/keybinds.conf) — possible SUPER+ALT+D collision.
```

### Desired Codebase tree with files to be added/edited

```bash
/home/dustin/projects/voice-typing/
├── hypr-binds.conf            # NEW — repo root; 1 bind line + Mode-A header comment (the hotkey doc)
├── install.sh                 # EDIT — line 136 lead-in only; line 137 (`source = $REPO/…`) unchanged
└── (nothing else changes)
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 (G-BIND-VERBATIM) — copy the bind line EXACTLY from PRD §4.10.
#   bind = SUPER ALT, D, exec, /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle
#   MODS `SUPER ALT` uses a SPACE. Hyprland splits MODS on whitespace OR underscore, so this is
#   valid — do NOT "normalize" to SUPER_ALT. The `exec` params need no quoting (no spaces in the
#   path; `toggle` is one token).

# CRITICAL #2 (G-SOURCE-ABS-PATH) — the source line MUST be the ABSOLUTE repo path.
#   `source = /home/dustin/projects/voice-typing/hypr-binds.conf`. Hyprland resolves relative
#   `source` paths under ~/.config/hypr/ — but this file is in the repo, so absolute is required.
#   This string must EQUAL what install.sh prints (it prints `source = $REPO/hypr-binds.conf` where
#   REPO=/home/dustin/projects/voice-typing). Verify with the realpath grep in Validation.

# CRITICAL #3 (G-NO-AUTOEDIT-HYPRLAND) — do NOT write to ~/.config/hypr/hyprland.conf.
#   PRD §4.10 is explicit. The conf comment + install.sh only TELL the user the line to add. The
#   manual validation step (Level 3) is the ONE place a human edits their own hyprland.conf.

# CRITICAL #4 (G-BIND-PRECEDENCE) — Hyprland uses the LAST matching bind for a given MODS+key.
#   The user's hyprland.conf sources custom/keybinds.conf and hyprland/keybinds.conf, EITHER of
#   which may already bind SUPER+ALT+D. => tell the user to `source` this file LAST (bottom of
#   hyprland.conf), and give a fallback rebind (SUPER ALT, V) in the conf comment + README.

# CRITICAL #5 (G-INSTALL-SNIPPET-STABLE) — install.sh's `source = $REPO/hypr-binds.conf` echo is a
#   STABLE surface: the README (P2.M1.T2.S1) and this conf comment both copy it. Edit ONLY line 136
#   (the stale "(after P2.M1 …)" qualifier); leave line 137 byte-for-byte identical. Do not touch
#   REPO resolution, the tmux snippet, or any other echo.

# CRITICAL #6 (G-MODE-A-DOC) — the conf's header comment IS the user-facing hotkey doc (item DOCS
#   contract). Mirror voice_typing/status.sh: a `# USER INTEGRION (item DOCS: Mode A — this comment
#   IS the hotkey doc)` block with the exact paste line + "we never edit your hyprland.conf".

# CRITICAL #7 (G-VOICECTL-PATH) — the bind execs the FULL venv path, not a bare `voicectl`.
#   systemd + install.sh both use /home/dustin/projects/voice-typing/.venv/bin/voicectl (no PATH
#   reliance under Hyprland's exec, which uses a minimal env). Verified present + executable.

# CRITICAL #8 (G-NO-SCOPE-CREEP) — do NOT add: a README, a pytest for the conf, a submap, bindl/
#   bindm, an install-time hyprctl reload, or any edit to hyprland.conf. tests/ is owned by P1.M7
#   (running in parallel); README is P2.M1.T2.S1. This task = 1 new conf file + 1 install.sh line.
```

## Implementation Blueprint

### Data models and structure

No data models. The artifact is a static Hyprland config file. Its "schema" is: (1) a `#` comment
block (the Mode-A doc) and (2) a single `bind =` directive.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE hypr-binds.conf  (repo root — /home/dustin/projects/voice-typing/hypr-binds.conf)
  - WRITE a plain-text file with a leading `#` comment block (Mode-A doc) followed by ONE bind line.
  - COMMENT BLOCK (mirror voice_typing/status.sh's structure):
      * Line 1: "# hypr-binds.conf — voice-typing Hyprland keybindings (PRD §4.10; P2.M1.T1.S1)."
      * "# WHAT THIS IS": one bind (SUPER+ALT+D -> voicectl toggle); sourced not copied; edits take
        effect on `hyprctl reload`.
      * "# USER INTEGRATION  (item DOCS: Mode A — this comment IS the hotkey doc)" block containing
        the EXACT paste line (G-SOURCE-ABS-PATH):
            source = /home/dustin/projects/voice-typing/hypr-binds.conf
        plus: "reload Hyprland (hyprctl reload)"; "daemon must be running (./install.sh); it boots
        NOT-listening so the first SUPER+ALT+D arms it"; "we never edit your hyprland.conf for you".
      * "# PRECEDENCE / CONFLICTS" note (G-BIND-PRECEDENCE): Hyprland uses the LAST matching bind;
        source this file LAST; if SUPER+ALT+D is inert, check ~/.config/hypr/custom/keybinds.conf
        and ~/.config/hypr/hyprland/keybinds.conf, or rebind to `SUPER ALT, V` in the line below.
      * "# MODS SYNTAX" note: SUPER ALT == SUPER_ALT (space or underscore); see
        https://wiki.hypr.land/Configuring/Basics/Binds/.
  - BIND LINE (G-BIND-VERBATIM — copy PRD §4.10 verbatim, on its own line after a blank separator):
        bind = SUPER ALT, D, exec, /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle
  - FOLLOW pattern: voice_typing/status.sh (the Mode-A `# USER INTEGRATION` block; `#` comments).
  - NAMING: file is `hypr-binds.conf` (kebab-case, matching PRD §4.10 + install.sh's echo).
  - PLACEMENT: repo ROOT (same dir as install.sh, PRD.md) — NOT under voice_typing/ or config/.
  - ENCODING: UTF-8, LF newlines, trailing newline at EOF.

Task 2: EDIT install.sh  (one line — the Hyprland lead-in echo)
  - FIND (install.sh:136): echo "Hyprland (after P2.M1 creates hypr-binds.conf), add to ~/.config/hypr/hyprland.conf:"
  - REPLACE WITH e.g.:   echo "Hyprland — source the repo's hypr-binds.conf from ~/.config/hypr/hyprland.conf (add this line):"
  - PRESERVE the NEXT line (install.sh:137) BYTE-FOR-BYTE: echo "  source = $REPO/hypr-binds.conf"
    (G-INSTALL-SNIPPET-STABLE — it already prints the correct absolute path; the README copies it.)
  - DO NOT touch any other install.sh line (REPO resolution, tmux snippet, usage, status echoes).
  - VERIFY after edit: bash -n install.sh (syntax still clean); then run the grep in Validation L1.

Task 3: VALIDATE (no file written — run the commands in the Validation Loop, then the manual toggle)
  - RUN Level 1 greps (bind line present; source line in comment; install.sh source line resolves to
    the same absolute path; voicectl path exists + executable).
  - RUN Level 2 (shellcheck on install.sh if present; bash -n).
  - RUN Level 3 manual proof (source the file in hyprland.conf, hyprctl reload, SUPER+ALT+D toggles
    voicectl status). Record the on→off flip as the success evidence.
```

### Implementation Patterns & Key Details

```bash
# PATTERN 1 — the Mode-A header comment (mirror voice_typing/status.sh). Hyprland conf uses `#`
# comments (same char as sh), so the status.sh block transfers directly. Skeleton:
#   # hypr-binds.conf — voice-typing Hyprland keybindings (PRD §4.10; P2.M1.T1.S1).
#   #
#   # WHAT THIS IS ...
#   # =====================================================================
#   #  USER INTEGRATION  (item DOCS: Mode A — this comment IS the hotkey doc)
#   # =====================================================================
#   #  Add ONE line to ~/.config/hypr/hyprland.conf (install.sh prints it; we never edit your
#   #  hyprland.conf for you):
#   #
#   #      source = /home/dustin/projects/voice-typing/hypr-binds.conf
#   #
#   #  Then `hyprctl reload`. SUPER+ALT+D arms/disarms the mic. The daemon boots NOT-listening ...
#   #  PRECEDENCE / CONFLICTS ...
#   #  MODS SYNTAX ...
#
#   bind = SUPER ALT, D, exec, /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle

# PATTERN 2 — the install.sh edit is a single old-text/new-text swap; keep line 137 identical.
#   OLD (136): echo "Hyprland (after P2.M1 creates hypr-binds.conf), add to ~/.config/hypr/hyprland.conf:"
#   NEW (136): echo "Hyprland — source the repo's hypr-binds.conf from ~/.config/hypr/hyprland.conf (add this line):"
#   KEEP (137): echo "  source = $REPO/hypr-binds.conf"
```

### Integration Points

```yaml
CONSUMES (READ-ONLY reuse; do NOT modify):
  - voice_typing/ctl.py + [project.scripts] voicectl  -> the command the bind execs (.venv/bin/voicectl toggle)
  - voice_typing/status.sh                            -> the Mode-A comment-block pattern to mirror
  - install.sh (REPO resolution, the source echo)     -> the snippet this file's comment must match

PRODUCES (this task):
  - hypr-binds.conf (repo root)                       -> the sourced bind file + the hotkey doc
  - install.sh line 136 (truth-up)                    -> present-tense Hyprland instruction

REFERENCES (downstream consumers — do NOT implement here):
  - README.md (P2.M1.T2.S1, Planned)                  -> will copy `source = …/hypr-binds.conf` + the
                                                         bind line + the precedence/troubleshooting note
                                                         verbatim from this file; keep them stable.
  - PRD §7 criterion 7                                -> "README documents … hotkey snippet" — this
                                                         file is the canonical source of that snippet.

NO integration with: DATABASE (none), CONFIG (config.toml untouched), ROUTES (none), systemd
  (the unit already starts the daemon; the bind just calls voicectl over the existing socket).
```

## Validation Loop

### Level 1: File-content assertions (deterministic — run after Task 1 + Task 2)

```bash
cd /home/dustin/projects/voice-typing

# (a) the EXACT bind line is present (PRD §4.10 verbatim — space-separated MODS, full venv path).
grep -Fx 'bind = SUPER ALT, D, exec, /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle' hypr-binds.conf
#   ^ -F literal, -x whole-line; exit 0 == present.

# (b) the comment contains the EXACT source line the user pastes (G-SOURCE-ABS-PATH).
grep -F 'source = /home/dustin/projects/voice-typing/hypr-binds.conf' hypr-binds.conf

# (c) the bind exec target exists and is executable (G-VOICECTL-PATH).
test -x /home/dustin/projects/voice-typing/.venv/bin/voicectl && echo "voicectl: executable"

# (d) install.sh prints a source line whose path EQUALS this file's real path (G-INSTALL-SNIPPET-STABLE).
#     install.sh computes REPO=SCRIPT_DIR; assert its echo resolves to the absolute path in (b).
bash -c 'set -e; REPO="/home/dustin/projects/voice-typing"; line="  source = $REPO/hypr-binds.conf"; \
  grep -Fx "$line" install.sh; [ "$(realpath "$REPO/hypr-binds.conf")" = "$REPO/hypr-binds.conf" ]'
#   ^ confirms install.sh:137 is unchanged and its $REPO resolves to the repo root.

# (e) install.sh no longer carries the stale "(after P2.M1 …)" qualifier (Task 2 succeeded).
! grep -F 'after P2.M1 creates hypr-binds.conf' install.sh

# Expected: every grep/test exits 0; the `!`-prefixed grep exits non-zero (i.e. the stale text is gone).
```

### Level 2: Syntax & style (immediate)

```bash
cd /home/dustin/projects/voice-typing
# install.sh must still parse after the 1-line edit.
bash -n install.sh && echo "install.sh: bash -n ok"
# shellcheck if available (warn-only — do not fail the task on shellcheck absence).
command -v shellcheck >/dev/null && shellcheck install.sh || echo "shellcheck: not installed (skipped)"
# hypr-binds.conf has no trailing blank lines / CRLF (Hyprland tolerates, but keep it clean).
tail -c1 hypr-binds.conf | od -An -tx1 | grep -q '0a' && echo "hypr-binds.conf: ends with LF"
! grep -lU $'\r' hypr-binds.conf >/dev/null 2>&1 || echo "WARN: hypr-binds.conf has CRLF"

# Expected: bash -n ok; no CRLF; file ends with a single LF.
```

### Level 3: Manual end-to-end proof (the real integration test — run once, record the flip)

> Hyprland cannot auto-fire a synthetic SUPER+ALT+D from a script reliably (it is a real compositor
> keybind), so this level is a short **human** walkthrough. It is the proof that the bind works.

```bash
cd /home/dustin/projects/voice-typing

# 0) daemon is running + NOT listening (install.sh started it un-armed).
/home/dustin/projects/voice-typing/.venv/bin/voicectl status    # expect: listening: off

# 1) TEMPORARILY add the source line to the user's hyprland.conf (the implementer does this by hand;
#    the project never auto-edits it). Put it at the BOTTOM so it wins bind precedence.
#      echo 'source = /home/dustin/projects/voice-typing/hypr-binds.conf' >> ~/.config/hypr/hyprland.conf
#    (or add it via your editor; remove it again if you do not want the bind permanent.)

# 2) reload Hyprland and confirm the bind registered.
hyprctl reload
hyprctl binds | grep -A2 -i 'SUPER.*ALT.*D'   # expect a bind whose dispatcher is exec -> voicectl toggle

# 3) press SUPER+ALT+D, then check state flipped to listening.
#    (press the keys)
/home/dustin/projects/voice-typing/.venv/bin/voicectl status    # expect: listening: on
# 4) press SUPER+ALT+D again.
/home/dustin/projects/voice-typing/.venv/bin/voicectl status    # expect: listening: off

# Expected: each keypress flips listening on<->off (voicectl exit 0). If step 2 shows no bind or the
# key is inert, a later `bind =` in ~/.config/hypr/custom/keybinds.conf or hyprland/keybinds.conf is
# shadowing it -> move the source line to the very bottom, or rebind to SUPER ALT, V (see conf note).
```

### Level 4: Documentation / downstream-readiness

```bash
cd /home/dustin/projects/voice-typing
# The README (P2.M1.T2.S1) will lift these two strings verbatim — assert they are final + stable.
grep -F 'source = /home/dustin/projects/voice-typing/hypr-binds.conf' hypr-binds.conf
grep -Fx 'bind = SUPER ALT, D, exec, /home/dustin/projects/voice-typing/.venv/bin/voicectl toggle' hypr-binds.conf
# git status should show EXACTLY: new hypr-binds.conf + modified install.sh (nothing else).
git status --porcelain
# Expected: '?? hypr-binds.conf' (or 'A  hypr-binds.conf') and ' M install.sh', and NO other rows.
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 1 assertions pass: exact bind line present; exact source line in comment; voicectl
      executable; install.sh source line resolves to this file's path; stale qualifier gone.
- [ ] Level 2: `bash -n install.sh` clean; no CRLF; hypr-binds.conf ends with LF.
- [ ] Level 3 (manual): `hyprctl binds` shows the SUPER+ALT+D exec bind; pressing it flips
      `voicectl status` on→off→on.
- [ ] Level 4: `git status --porcelain` shows ONLY `hypr-binds.conf` (new) + `install.sh` (modified).

### Feature Validation

- [ ] hypr-binds.conf contains the PRD §4.10 bind line verbatim (G-BIND-VERBATIM).
- [ ] The conf comment contains the exact `source =` line and follows the Mode-A pattern (G-MODE-A-DOC).
- [ ] install.sh prints a source snippet whose path equals the file's real path; its lead-in no
      longer claims the file is missing (G-INSTALL-SNIPPET-STABLE).
- [ ] No auto-edit of `~/.config/hypr/hyprland.conf` (G-NO-AUTOEDIT-HYPRLAND) — only the manual
      Level-3 step touches it, by the implementer's hand.
- [ ] Precedence/conflict note present (G-BIND-PRECEDENCE) so an inert hotkey is debuggable.

### Code Quality Validation

- [ ] File placement matches the desired tree (repo root, beside `install.sh` / `PRD.md`).
- [ ] Naming `hypr-binds.conf` matches PRD §4.10 + install.sh's echo.
- [ ] The bind path matches the systemd unit / install.sh usage line (full `.venv/bin/voicectl`).
- [ ] install.sh edit is minimal (1 line); no collateral changes.

### Documentation & Deployment

- [ ] The conf's header comment IS the hotkey doc (Mode A); no separate doc file needed for the bind.
- [ ] The `source =` snippet is stable for the README (P2.M1.T2.S1) to copy verbatim.
- [ ] No new env vars / config keys / dependencies introduced.

---

## Anti-Patterns to Avoid

- ❌ Don't "normalize" `SUPER ALT` to `SUPER_ALT` — both are valid; the PRD's spelling is the contract.
- ❌ Don't auto-edit `~/.config/hypr/hyprland.conf` — PRD §4.10 forbids it; print the instruction only.
- ❌ Don't change install.sh's `source = $REPO/hypr-binds.conf` echo (line 137) — it is a stable
  surface the README copies; edit only the lead-in phrase on line 136.
- ❌ Don't add a README, a pytest, a submap, or `bindl`/`bindm` — out of scope for this item.
- ❌ Don't put hypr-binds.conf under `voice_typing/` or `config/` — PRD §4.10 + install.sh reference
  the repo root (`$REPO/hypr-binds.conf`).
- ❌ Don't rely on a bare `voicectl` (PATH) in the bind — use the full `.venv/bin/voicectl` path.
- ❌ Don't omit the precedence/conflict note — the user's config sources other keybind files that may
  already bind SUPER+ALT+D.

---

## Confidence Score

**9/10.** The deliverable is a single static config file with a verbatim-pinned bind line (PRD §4.10)
plus a one-line, old-text/new-text install.sh edit. Every load-bearing string is pinned in this PRP;
the Mode-A comment pattern is fixed by pointing at `voice_typing/status.sh`; the Hyprland syntax is
backed by the wiki; and all Level-1/2/4 validations are deterministic greps executable as written.
The only non-deterministic step (Level 3: a real keypress under Hyprland) is inherently manual for
any compositor keybind and is fully scripted as a short human walkthrough. Deducted 1 point for the
unavoidable manual step + the (documented) possibility of a pre-existing SUPER+ALT+D bind in the
user's own keybind files, which only the user can resolve.
