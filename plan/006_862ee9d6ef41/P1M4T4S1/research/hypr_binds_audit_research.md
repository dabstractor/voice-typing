# Research note — P1.M4.T4.S1 (audit hypr-binds.conf vs PRD §4.10 + §4.2ter)

**Task type:** READ-ONLY compliance audit (P1 = "PRD Compliance Verification & Remediation").
**Deliverable:** a NEW `plan/006_862ee9d6ef41/architecture/gap_hypr_binds.md` report (no existing gap_hypr* —
`ls architecture/` confirms; this subtask creates it). Format mirrors `gap_install.md` (P1.M4.T3.S1) /
`gap_launch_daemon.md` (P1.M4.T2.S1) — both infra-layer, both read-only audits of committed files.
**Scope:** `hypr-binds.conf` (repo root) + its 3 cross-references (install.sh source instruction, README
hotkey doc = Acceptance #7, tests/test_systemd_unit.py pinning tests). NO source modification.

---

## 1. The audited file — LIVE state of `hypr-binds.conf` (3 KB, repo root)

Read in full. It is ALREADY the committed, documented artifact (created by round-001 P2.M1.T1.S1). The
two load-bearing `bind =` lines (the contract's points (a)+(b)) are byte-for-byte:

```
bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle       # BIG/normal model
bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite       # LITTLE/lite model
```

These match PRD §4.10 VERBATIM:
> `bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle`
> `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite`

(NOTE: PRD §4.10's prose says `$HOME/.local/bin/voicectl`; the round-001 P2M1.T1.S1 research note
referenced the older `.venv/bin/voicectl` absolute path, but the CURRENT committed file + PRD + the VT-003
launcher all use `$HOME/.local/bin/voicectl`. The file is the contract source of truth — it is correct.)

The comment block (the contract's point (d) + the DOCS point) contains, verbatim:
- Header: `# hypr-binds.conf — voice-typing Hyprland keybindings (PRD §4.10 + §4.2ter; P2.M1.T1.S1).`
- A WHAT THIS IS block naming BOTH binds + BOTH modes (`toggle` = NORMAL/big model distil-large-v3+small.en;
  `toggle-lite` = LITE/little model small.en only).
- A **`USER INTEGRATION (item DOCS: Mode A — this comment IS the hotkey doc)`** block with the exact
  `source = <repo>/hypr-binds.conf` line to paste into `~/.config/hypr/hyprland.conf`, the explicit
  promise **"install.sh prints it; we never edit your hyprland.conf for you"** (contract point (e)), and
  the `hyprctl reload` step.
- A **VT-003** block explaining the binds invoke `$HOME/.local/bin/voicectl` (the STABLE launcher symlink
  install.sh maintains → `<repo>/.venv/bin/voicectl`), why `$HOME` expands (Hyprland runs `bind exec`
  through `/bin/sh -c`), and the precedence/source-LAST caveat.
- A **PRECEDENCE / CONFLICTS** block (last-matching-bind-wins; source LAST; conflict check files).
- A **MODS SYNTAX** block (`CTRL SUPER ALT` == `CTRL_SUPER_ALT`; both valid) + the Binds wiki URL.

→ Contract points (a), (b), (c), (d), (e) + the DOCS point are ALL present in the committed file. This is a
**COMPLIANT, no-fix audit** — same verdict shape as `gap_launch_daemon.md` / `gap_install.md`.

---

## 2. The 3 cross-references (the DOCS + Acceptance-#7 + test-pinning surface)

### 2a. install.sh — prints the source instruction; installs the launcher; never edits hyprland.conf
- `:174`-`:192` — the `# --- (6b) install the stable voicectl launcher (VT-003) ---` block.
  `LAUNCHER="$HOME/.local/bin/voicectl"` (`:180`); `mkdir -p "$HOME/.local/bin"` (`:181`); the if-exists
  foreign-check (`:182`-`:189`); `ln -s "$REPO/.venv/bin/voicectl" "$LAUNCHER"` (`:190`). This is the symlink
  the binds' `$HOME/.local/bin/voicectl` resolves to at press time → contract point (c) is WIRED.
- `:209`-`:210` — the usage line `voicectl toggle|start|stop|status|quit|toggle-lite|start-lite` + the keybind
  hint `(bind Ctrl+Alt+Super+D -> voicectl toggle;  Alt+Super+D -> voicectl toggle-lite; see the Hyprland
  note below)`.
- `:216`-`:217` — **the source instruction, PRINTED (never applied)**:
  `echo "Hyprland — source the repo's hypr-binds.conf from ~/.config/hypr/hyprland.conf (add this line):"`
  `echo "  source = $REPO/hypr-binds.conf"` → contract points (d) +(e) WIRED (print-only; no sed/cp/append
  on the user's hyprland.conf anywhere in install.sh — grep-confirmed).

### 2b. README.md — "Hotkey (Hyprland)" section = Acceptance #7 ("README documents hotkey snippet")
- `:79`-`:116` — the `## Hotkey (Hyprland)` section. Documents: the two keybinds
  (`Ctrl+Alt+Super+D` big/normal; `Alt+Super+D` lite), the one-line `source = /home/<you>/projects/voice-
  typing/hypr-binds.conf` to add to `hyprland.conf`, the "install.sh prints it; the repo never edits your
  hyprland.conf" promise, the `hyprctl reload` step, the `$HOME/.local/bin/voicectl` launcher explanation,
  the verbatim bind block (matches hypr-binds.conf), and the precedence/troubleshooting note.
  → **Acceptance #7 PASSES** (3-way match: README ↔ hypr-binds.conf ↔ install.sh:216-217 all agree on the
  `source = …/hypr-binds.conf` line + the two binds + the two modes).

### 2c. tests/test_systemd_unit.py — what pins hypr-binds.conf (pure-stdlib re/pathlib; the audit's run cmd)
- `_hypr_binds_path()` (`:66`-`:68`) — resolves `hypr-binds.conf` at repo root (parent of tests/).
- `test_hypr_binds_use_portable_home_launcher` (`:321`-`:332`) — VT-003: asserts every `bind =` line contains
  `$HOME/.local/bin/voicectl` AND contains no `/home/` literal. → pins contract point **(c)** (the path).
- `test_install_sh_installs_stable_voicectl_launcher` (`:306`-`:318`) — VT-003: asserts install.sh installs
  `$HOME/.local/bin/voicectl` via `ln -s` + never clobbers a foreign file. → pins the launcher the binds need.
- `test_install_sh_usage_lists_all_commands_and_correct_keybinds` (`:223`-`:254`) — asserts install.sh's usage
  STRING states `Ctrl+Alt+Super+D` + `Alt+Super+D -> voicectl toggle-lite` + the WRONG mapping
  (`SUPER+ALT+D -> voicectl toggle`) is gone. → pins the keybind hints in install.sh (NOT the bind= lines).
- **Re-verified LIVE this round:** `timeout 90 .venv/bin/python -m pytest tests/test_systemd_unit.py -q`
  → **15 passed in 0.01s** (pure-stdlib; no GPU/CUDA/daemon/mic/model-load).

---

## 3. Hyprland bind / source / precedence — authoritative facts (external, with URLs)

(Re-confirmed via web search this round; stable across Hyprland versions.)

- **Bind syntax** — Hyprland Wiki, *Configuring/Basics/Binds*:
  https://wiki.hypr.land/Configuring/Basics/Binds/
  > `bind = MODS, key, dispatcher, params` — e.g. `bind = SUPER_SHIFT, Q, exec, firefox`.
  - MODS accepts multiple modifiers; the parser splits MODS on **whitespace OR underscore** →
    `SUPER ALT` (PRD §4.10's exact spelling) ≡ `SUPER_ALT`. The PRD is the contract ⇒ the file keeps
    `SUPER ALT` (space) verbatim. Both forms are valid; the file is correct.
- **`exec` dispatcher** — Hyprland Wiki, *Configuring/Basics/Dispatchers*:
  https://wiki.hypr.land/Configuring/Basics/Dispatchers/
  > `exec` executes the remainder of `params` as a shell command line. Hyprland spawns it via
  > `execl("/bin/sh", "/bin/sh", "-c", ...)` (Hyprland source: `src/config/supplementary/.../Executor.cpp`).
  → This is WHY `$HOME` in the bind expands at press time (the `/bin/sh -c` invocation expands it), making
  the binds user/repo-location-independent. The file's VT-003 comment documents exactly this. Correct.
- **`source` keyword** — Hyprland Wiki, *Configuring* (Variables / config file):
  https://wiki.hypr.land/Configuring/
  > `source = <path>` reads another config file inline. Relative paths resolve against `~/.config/hypr/`;
  > absolute paths work as-is. Both `source=...` (no space) and `source = ...` (spaces) parse.
  → `source = <repo>/hypr-binds.conf` (absolute) is correct; install.sh prints the absolute `$REPO/...` form.
- **Bind precedence** — Hyprland uses the **LAST** matching `bind =` for a given MODS+key.
  → The file's PRECEDENCE comment ("source this file LAST … so its binds win") is correct + necessary,
  because the user's real `~/.config/hypr/hyprland.conf` already sources `custom/keybinds.conf` +
  `hyprland/keybinds.conf` (verified round-001) which could shadow a same-MODS+key bind.

These external facts are the "why the binds are correct" backbone the gap report cites in its DOCS/nuance
sections. No deeper external research is needed — the file is compliant and the syntax is stable.

---

## 4. The HEADLINE NUANCE (the audit's value-add — coverage gap, NOT a code defect)

Mirroring every sibling gap report's "headline nuance" section (e.g. `gap_launch_daemon.md` §5.1: the
wrapper's primary function has no test; `gap_install.md` §5.4: the core install flow has no named test):

**The actual `bind =` MODS+key↔command MAPPING in hypr-binds.conf has NO direct test.**
- `test_hypr_binds_use_portable_home_launcher` (`:321`) pins ONLY the PATH (`$HOME/.local/bin/voicectl` +
  no `/home/`) — it iterates `bind =` lines but asserts on the command PATH, NOT which MODS+key maps to
  `toggle` vs `toggle-lite`.
- `test_install_sh_usage_lists_all_commands_and_correct_keybinds` (`:223`) pins the keybind hints in
  install.sh's usage STRING (`Ctrl+Alt+Super+D` / `Alt+Super+D -> voicectl toggle-lite`), NOT the actual
  `bind =` lines in hypr-binds.conf.

⇒ A **swapped-binds regression** in hypr-binds.conf (e.g. `CTRL SUPER ALT, D → toggle-lite` +
`SUPER ALT, D → toggle`) would PASS the 15-test suite silently — the path check still passes (both lines
still use `$HOME/.local/bin/voicectl`), and the usage-string check only reads install.sh. **This audit IS
the PRD §4.10 MODS↔command compliance check the suite cannot perform** — recording it so a swapped-bind
regression cannot ship silently. (Consistent with every round-006 audit's "read-only, no new tests"
discipline — do NOT add a test here.)

Secondary untested points (standard for doc/behavior guarantees, verifiable only by read):
- (d) the source-instruction comment's presence/correctness — no test parses the comment block.
- (e) the "never edit the user's hyprland.conf" guarantee — a behavioral promise, grep-provable (no
  sed/cp/append targets `~/.config/hypr/hyprland.conf` anywhere in the repo), not unit-testable.

---

## 5. Scope boundaries (no conflicts with parallel/adjacent work)

- **Parallel item P1.M4.T3.S2** (Implementing) = the `prefetch.py` download-logic audit → `gap_prefetch.md`.
  **ZERO file overlap** with hypr-binds.conf (prefetch.py / HF cache vs hypr-binds.conf / install.sh source
  line). Safe to land in parallel; this PRP consumes nothing prefetch produces.
- **P1.M4.T3.S1** (`gap_install.md`, COMPLETE) already audited install.sh's `:216`-`:217` source-instruction
  print + `:190` launcher symlink as PART of its install-flow audit. This audit (S1) is the COMPLEMENT: it
  audits the FILE that line sources (`hypr-binds.conf`) + the README hotkey doc + the bind correctness.
  Cross-reference `gap_install.md`'s install.sh findings; do NOT re-audit install.sh wholesale.
- **README (P1.M6.T1.S1, Planned)** will verify README completeness against PRD §7 #7 — this audit's
  README §2b finding (Acceptance #7 PASSES: 3-way match) is the input P1.M6.T1.S1 consumes.
- **voicectl toggle / toggle-lite** (P1.M3.T2.S1/S2, COMPLETE) — the commands the binds exec are audited
  there (`gap_voicectl.md` / `gap_socket.md`). This audit trusts those verbs exist + behave; it audits the
  BIND WIRING to them, not the verbs' internals.

## 6. Verdict (this PRP's pre-audit finding)

**hypr-binds.conf is COMPLIANT** with PRD §4.10 + §4.2ter + the work-item contract on ALL 5 points + the
DOCS point; Acceptance #7 PASSES (README hotkey doc is a 3-way match). No fix needed. The audit re-confirms
live (line numbers + test pass count) and records the headline coverage nuance (§4). Output = a NEW
`architecture/gap_hypr_binds.md` mirroring `gap_install.md` / `gap_launch_daemon.md`.