# Gap Report — P1.M4.T4.S1: hypr-binds.conf (keybinds, commands, source instruction) vs PRD §4.10 + §4.2ter

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `hypr-binds.conf` — the committed Hyprland keybind snippet (PRD §4.10 Phase 2 "create
`hypr-binds.conf` … `bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle` /
`bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite` … Print an instruction to `source` it
from `~/.config/hypr/hyprland.conf`. Do NOT modify the user's Hyprland config automatically" + PRD §4.2ter
"`Ctrl+Alt+Super+D` → `toggle` (big/normal model) and `Alt+Super+D` → `toggle-lite` (little/lite model)")
— against ALL work-item contract points: (a) `bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl
toggle` present (NORMAL / big model); (b) `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl
toggle-lite` present (LITE / little model); (c) both binds invoke `$HOME/.local/bin/voicectl` — the STABLE
launcher symlink `install.sh` maintains (VT-003), NOT a hardcoded `/home/<user>` repo path; (d) the file
CONTAINS a source-instruction comment (`source = <repo>/hypr-binds.conf`); (e) the repo does NOT
auto-modify the user's `hyprland.conf` (install.sh only PRINTS the instruction); **+ the DOCS point**: the
comment block explains BOTH the source instruction AND the two modes (normal vs lite). Re-verified live via
grep + a 3-way cross-read (hypr-binds.conf ↔ install.sh ↔ README.md = Acceptance #7) + the pure-Python
`tests/test_systemd_unit.py` re-run. Subtask **P1.M4.T4.S1** of verification round `006_862ee9d6ef41`.
Satisfies **Acceptance #7** ("README documents hotkey snippet").
**Audited artifacts (all read-only):**
- `hypr-binds.conf` — the 52-line committed Hyprland snippet. Header WHAT-THIS-IS (`:1`-`7`) naming both
  binds + both model sets; USER INTEGRATION block (`:10`-`33`) with the `source = <repo>/hypr-binds.conf`
  instruction (`:16`) + `hyprctl reload` (`:19`) + the VT-003 launcher explanation (`:21`-`28`, incl. the
  `/bin/sh -c` expansion mechanism + the `readlink -f` fallback); the two-mode explanation (`:29`-`33`);
  PRECEDENCE/CONFLICTS (`:35`-`43`, "source LAST"); MODS SYNTAX (`:45`-`47`). The two binds:
  `bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle` (`:50`, big/normal) +
  `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite` (`:52`, lite/little).
- `install.sh` — cross-ref for (c) [the VT-003 launcher the binds resolve to] + (d)/(e) [it PRINTS the
  source instruction, never applies it]. `LAUNCHER="$HOME/.local/bin/voicectl"` (`:180`);
  `ln -s "$REPO/.venv/bin/voicectl" "$LAUNCHER"` (`:190`); the usage keybind hint
  (`:211`, `Ctrl+Alt+Super+D -> voicectl toggle; Alt+Super+D -> voicectl toggle-lite`); the PRINTED
  `source = $REPO/hypr-binds.conf` line (`:216`-`217`, `echo` only). (install.sh was audited wholesale by
  P1.M4.T3.S1 / `gap_install.md` — cited here, NOT re-audited.)
- `README.md` — cross-ref for Acceptance #7. The `## Hotkey (Hyprland)` section (`:79`-`116`): both keybind
  names (`:81`), the never-edit promise (`:83`), `source = /home/<you>/projects/voice-typing/hypr-binds.conf`
  (`:87`, `<you>` = placeholder), `hyprctl reload` (`:92`), the `$HOME/.local/bin/voicectl` launcher note
  (`:98`-`100`), BOTH bind lines verbatim (`:101`-`102`), the two-mode explanation (`:105`-`110`),
  precedence/source-LAST (`:112`-`116`).
- `tests/test_systemd_unit.py` — the 15-test suite (the contract's run command); pure-stdlib re+pathlib
  (parses the unit + wrapper + install + binds files; NO GPU/CUDA/daemon/mic). The 3 hypr-binds pinning
  tests: `_hypr_binds_path()` (`:66`-`68`), `test_install_sh_usage_lists_all_commands_and_correct_keybinds`
  (`:223`), `test_install_sh_installs_stable_voicectl_launcher` (`:306`),
  `test_hypr_binds_use_portable_home_launcher` (`:321`).
- `plan/006_862ee9d6ef41/prd_snapshot.md` / `PRD.md` — §4.10 (the exact two binds + the
  source-it-don't-edit-it contract) + §4.2ter (which keybind maps to which mode).

**Bottom line:** ✅ `hypr-binds.conf` is **COMPLIANT** with PRD §4.10 + §4.2ter + the work-item contract +
Acceptance #7 — all 5 contract points (a)–(e) + the DOCS point PASS, the 3-way cross-read
(README ↔ hypr-binds.conf ↔ install.sh) is a MATCH, and the suite is green (**15 passed in 0.01s**,
re-run live). **No source files were modified** — the file faithfully implements the spec. The audit's
value-add = the **headline nuance (§5.1)**: the `bind =` MODS+key↔command MAPPING in hypr-binds.conf has
NO direct test — `test_hypr_binds_use_portable_home_launcher` (`:321`) pins ONLY the command PATH
(`$HOME/.local/bin/voicectl` + no `/home/`), and `test_install_sh_usage_lists_all_commands_and_correct_
keybinds` (`:223`) pins the keybind hints in install.sh's usage STRING, not the bind= lines — so a
swapped-binds regression IN hypr-binds.conf (e.g. `toggle-lite` on `CTRL SUPER ALT`) would PASS the 15-test
suite silently. **This audit IS the PRD §4.10 MODS↔command compliance check the suite cannot perform.**

---

## 1. Method

Each of the 5 work-item contract points + the DOCS point was mapped 1:1 to its `hypr-binds.conf`
implementation by `grep -nE` (the file:line evidence), the USER INTEGRATION comment block explaining the
non-obvious parts (the VT-003 `$HOME`-via-`/bin/sh -c` expansion mechanism; the source-LAST precedence
caveat; the MODS-whitespace-or-underscore syntax) was read directly, and Acceptance #7 was verified by a
**3-way cross-read** (hypr-binds.conf's bind= lines + source instruction ↔ install.sh's printed `source =`
line + launcher symlink ↔ README.md's `## Hotkey (Hyprland)` section). The "never edit the user's
hyprland.conf" promise (contract point (e)) was verified **repo-wide** by a grep for any `sed`/`cp`/`>>`/`>`
write to `hyprland.conf` across `*.sh` + `*.py` (§3). The full `tests/test_systemd_unit.py` suite was then
**re-run live** to record the actual pass count + timing. Nothing was assumed from the PRP's embedded
numbers — every line number + the pass count below was re-verified this round (the suite is pure-stdlib
`re`/`pathlib`; no GPU/CUDA/daemon/mic/model-load required).

### Commands run (re-verification)

```bash
# (a)-(b): the two bind= lines (line-numbered)
grep -nE 'bind = CTRL SUPER ALT, D, exec, \$HOME/\.local/bin/voicectl toggle'    hypr-binds.conf   # (a) normal/big
grep -nE 'bind = SUPER ALT, D, exec, \$HOME/\.local/bin/voicectl toggle-lite'    hypr-binds.conf   # (b) lite/little
# (c): the $HOME launcher path + the absence of a non-comment /home/ literal
grep -nE '\$HOME/\.local/bin/voicectl'   hypr-binds.conf                                          # (c) path
grep -nE '/home/'                        hypr-binds.conf                                          # (c) expect: comment-only
# (d)+(e)+DOCS: the source instruction + USER INTEGRATION block + never-edit promise
grep -nE 'source = .*hypr-binds\.conf|USER INTEGRATION|never edit'               hypr-binds.conf
# DOCS two-mode explanation (BIG vs LITTLE model sets)
grep -nE 'CTRL\+SUPER\+ALT\+D|SUPER\+ALT\+D|BIG model|LITTLE model|distil-large|small\.en' hypr-binds.conf
# CROSS-GREP install.sh (cite gap_install.md, don't re-audit): launcher + source-print + never-edit
grep -nE 'LAUNCHER=.*\.local/bin/voicectl|ln -s .*voicectl'                      install.sh         # (c) :180/:190
grep -nE 'source = .*/hypr-binds\.conf|Hyprland — source'                        install.sh         # (d) :216-217
grep -nE '~/.config/hypr/hyprland\.conf'                                        install.sh         # (e) echo/PRINT only
# CROSS-GREP README.md (Acceptance #7): hotkey heading + source line + both binds + never-edit
grep -nE '## Hotkey|source = .*hypr-binds\.conf|Ctrl\+Alt\+Super\+D|Alt\+Super\+D|toggle-lite|never (edit|modify)' README.md
grep -nE 'bind = CTRL SUPER ALT, D, exec, \$HOME/\.local/bin/voicectl toggle'    README.md          # verbatim bind
grep -nE 'bind = SUPER ALT, D, exec, \$HOME/\.local/bin/voicectl toggle-lite'    README.md          # verbatim bind
# the 3 hypr-binds pinning tests + the coverage-gap check
grep -nE 'def test_hypr_binds_use_portable_home_launcher|def test_install_sh_installs_stable_voicectl_launcher|def test_install_sh_usage_lists_all_commands_and_correct_keybinds' tests/test_systemd_unit.py
grep -qE 'def test_.*(bind_mods|ctrl_super_alt|toggle_lite_bind|bind_mapping)' tests/test_systemd_unit.py && echo "a mapping test EXISTS" || echo "no MODS<->command mapping test (headline nuance §5.1)"
# the never-edit guarantee, repo-wide (Level 4)
grep -rnE 'sed.*hyprland\.conf|cp .*hyprland\.conf|>> ?.*hyprland\.conf|> ?.*hyprland\.conf' --include='*.sh' --include='*.py' . 2>/dev/null | grep -v '.venv/' | grep -v 'plan/'
# the contract's run command (two timeouts per AGENTS.md Rule 1)
timeout 90 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
```

### Observed output (re-verified against the live tree this round)

```
bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle       hypr-binds.conf:50   (a)
bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite       hypr-binds.conf:52   (b)
$HOME/.local/bin/voicectl                                              hypr-binds.conf:21,22,50,52   (c) path
/home/                                                                 hypr-binds.conf:25   (c) COMMENT only — the "removes the hardcoded /home/<user>" explainer
source = <repo>/hypr-binds.conf                                        hypr-binds.conf:16   (d)
USER INTEGRATION                                                       hypr-binds.conf:11   (d)+(e)+DOCS block)
we never edit                                                          hypr-binds.conf:13   (e) the never-edit promise, in-file
CTRL+SUPER+ALT+D -> voicectl toggle  (NORMAL / "big" model)            hypr-binds.conf:5    (DOCS)
SUPER+ALT+D      -> voicectl toggle-lite (LITE / "little" model)        hypr-binds.conf:6    (DOCS)
CTRL+SUPER+ALT+D = the BIG model (distil-large-v3 + small.en)          hypr-binds.conf:29,49   (DOCS)
SUPER+ALT+D      = the LITTLE/lite model (small.en only)               hypr-binds.conf:30,51   (DOCS)
LAUNCHER="$HOME/.local/bin/voicectl"                                   install.sh:180       (c) launcher var
ln -s "$REPO/.venv/bin/voicectl" "$LAUNCHER"                           install.sh:190       (c) VT-003 symlink
echo "Hyprland — source … from ~/.config/hypr/hyprland.conf (add this line):"  install.sh:216   (d)+(e) PRINT
echo "  source = $REPO/hypr-binds.conf"                                install.sh:217       (d) printed source line
## Hotkey (Hyprland)                                                   README.md:79        (Acceptance #7)
source = /home/<you>/projects/voice-typing/hypr-binds.conf             README.md:87        (Acceptance #7, <you>=placeholder)
the repo never edits your hyprland.conf                                README.md:83        (Acceptance #7, never-edit)
bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle       README.md:101       (Acceptance #7, verbatim)
bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite       README.md:102       (Acceptance #7, verbatim)
(no MODS<->command mapping test — headline nuance §5.1)
(NO hits on the repo-wide never-edit grep — no sed/cp/>>/> on hyprland.conf anywhere)
15 passed in 0.01s
```

---

## 2. Per-contract-point Compliance Table (work-item contract / PRD §4.10 + §4.2ter vs `hypr-binds.conf`)

| # | contract requirement | expected | actual (file:line) | pinning test (`tests/test_systemd_unit.py`) | verdict |
|---|---|---|---|---|---|
| (a) | `bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle` (NORMAL / big model; PRD §4.10 + §4.2ter) | the exact literal, MODS spelled with spaces | `bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle` (`hypr-binds.conf:50`, commented "BIG model (normal mode): distil-large-v3 + small.en" `:49`) | **none direct** — `test_hypr_binds_use_portable_home_launcher` (`:321`) pins only the PATH, not the MODS+key↔command mapping (**coverage gap §5.1**) | ✅ |
| (b) | `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite` (LITE / little model; PRD §4.10 + §4.2ter) | the exact literal, MODS spelled with spaces | `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite` (`hypr-binds.conf:52`, commented "LITTLE model (lite mode, PRD §4.2ter): small.en only" `:51`) | **none direct** — same as (a); the usage-hint mapping is pinned in install.sh (`:223`), NOT in hypr-binds.conf's bind= lines (**coverage gap §5.1**) | ✅ |
| (c) | both binds invoke `$HOME/.local/bin/voicectl` (VT-003 launcher), NOT a hardcoded `/home/<user>` repo path | `$HOME/.local/bin/voicectl` on both bind= lines; no non-comment `/home/` literal | both binds use `$HOME/.local/bin/voicectl` (`:50`, `:52`); the ONLY `/home/` hit is `:25`, a COMMENT ("This removes the hardcoded `/home/<user>` repo path…") describing the VT-003 mechanism — never a path in a bind. Launcher: `LAUNCHER="$HOME/.local/bin/voicectl"` (`install.sh:180`) + `ln -s "$REPO/.venv/bin/voicectl" "$LAUNCHER"` (`install.sh:190`) | `test_hypr_binds_use_portable_home_launcher` (`:321`) — asserts `$HOME/.local/bin/voicectl` present + no `/home/` on EVERY bind line; `test_install_sh_installs_stable_voicectl_launcher` (`:306`) — asserts the launcher symlink install | ✅ |
| (d) | the file CONTAINS a source-instruction comment (`source = <repo>/hypr-binds.conf`) | a comment telling the user to add `source = <repo>/hypr-binds.conf` to `~/.config/hypr/hyprland.conf` | USER INTEGRATION block (`:10`-`33`): "Add ONE line to `~/.config/hypr/hyprland.conf`" (`:13`) + `source = <repo>/hypr-binds.conf` (`:16`) + `hyprctl reload` (`:19`); install.sh PRINTS the realized line `source = $REPO/hypr-binds.conf` (`install.sh:216`-`217`) | none — doc (install.sh's print is behavior-tested indirectly via `:223`) | ✅ |
| (e) | the repo does NOT auto-modify the user's `hyprland.conf` (install.sh only PRINTS the instruction) | install.sh `echo`s the instruction; NO `sed`/`cp`/`>>`/`>` write to `hyprland.conf` anywhere in the repo | install.sh PRINTS only: `echo "Hyprland — source … (add this line):"` (`:216`) + `echo "  source = $REPO/hypr-binds.conf"` (`:217`); the in-file promise "we never edit your hyprland.conf" (`hypr-binds.conf:13`) + README "the repo never edits your hyprland.conf" (`README.md:83`); **repo-wide grep for `sed`/`cp`/`>>`/`>` on `hyprland.conf` across `*.sh`+`*.py` = ZERO hits** (§3) | none — behavior promise (provable by grep, §3) | ✅ |
| DOCS | the comment block explains BOTH the source instruction AND the two modes (normal vs lite) | a Mode-A USER INTEGRATION block: source instr + BIG/LITTLE model sets + VT-003 + precedence | USER INTEGRATION block (`:10`-`33`): source instruction (`:13`-`19`); VT-003 launcher + `/bin/sh -c` expansion + `readlink -f` fallback (`:21`-`28`); two-mode explanation — `CTRL+SUPER+ALT+D = the BIG model (distil-large-v3 + small.en)` (`:29`) + `SUPER+ALT+D = the LITTLE/lite model (small.en only)` (`:30`); PRECEDENCE "source LAST" (`:35`-`43`); MODS SYNTAX (`:45`-`47`) | none — doc | ✅ |

> All 5 contract points + the DOCS point **PASS**. The file:line numbers above are `grep -n`-verified
> against the live tree this round. The 4 points with no direct test (a), (b), (d), (e)+DOCS are confirmed
> correct by direct read + the repo-wide grep (§3); the gap is recorded as a non-blocking coverage
> observation in §5.1.

### Robustness extras (compliant, beyond the 5 contract points — recorded so they are not "simplified" away)

| extra | actual (file:line) | why it matters | tested? |
|---|---|---|---|
| WHAT-THIS-IS header names both binds + both model sets | `hypr-binds.conf:1`-`7` | a reader sees the contract in the first 7 lines without scanning to the binds | no |
| VT-003 `/bin/sh -c` expansion explanation | `hypr-binds.conf:21`-`28` | documents WHY `$HOME` works in a bind (Hyprland's `exec` dispatcher shells out) + cites the Hyprland source line; offers a `readlink -f` absolute-path fallback | no |
| `readlink -f ~/.local/bin/voicectl` fallback hint | `hypr-binds.conf:28` | a user who prefers the absolute path can resolve it themselves | no |
| PRECEDENCE / source-LAST caveat | `hypr-binds.conf:35`-`43` | Hyprland uses the LAST matching bind for a MODS+key — sourcing this file last makes its binds win; lists the user's real conflict files to check | no |
| MODS SYNTAX note (`CTRL SUPER ALT` ≡ `CTRL_SUPER_ALT`) | `hypr-binds.conf:45`-`47` | pre-empts a "fix" that normalizes the space to an underscore (both parse; the PRD spells it with spaces) | no |

---

## 3. The "never edit the user's hyprland.conf" guarantee (contract point (e), repo-wide proof)

The item's contract point (e) + PRD §4.10 ("Do NOT modify the user's Hyprland config automatically") is the
strongest guarantee in this slice. It is grep-provable across the WHOLE repo (not just install.sh):

```bash
$ grep -rnE 'sed.*hyprland\.conf|cp .*hyprland\.conf|>> ?.*hyprland\.conf|> ?.*hyprland\.conf' \
      --include='*.sh' --include='*.py' . 2>/dev/null | grep -v '.venv/' | grep -v 'plan/'
(NO hits)
```

→ The repo NEVER writes to the user's `~/.config/hypr/hyprland.conf`. The ONLY references to that path are
**PRINTED instructions** (install.sh:216 `echo "Hyprland — source … from ~/.config/hypr/hyprland.conf
(add this line):"` + the README:83 prose "the repo never edits your hyprland.conf" + the in-file
hypr-binds.conf:13 promise "we never edit your hyprland.conf for you"). This is exactly the PRD §4.10
contract: "Print an instruction to `source` it … Do NOT modify the user's Hyprland config automatically."
✅

### External Hyprland facts (the "why the binds are correct" backbone)

| fact | URL | confirms |
|---|---|---|
| `bind = MODS, key, dispatcher, params` syntax; MODS splits on whitespace OR underscore | https://wiki.hypr.land/Configuring/Basics/Binds/ | contract (a)+(b): the `CTRL SUPER ALT` space spelling is valid + matches the PRD — do NOT "fix" it to `CTRL_SUPER_ALT` |
| the `exec` dispatcher runs params via `/bin/sh -c` | https://wiki.hypr.land/Configuring/Basics/Dispatchers/ | contract (c): `$HOME` expands at press time (user/repo-location-independent); a hardcoded `/home/<user>` would be a portability regression the launcher symlink + `$HOME` together prevent |
| the `source = <path>` keyword (relative → `~/.config/hypr/`; absolute works as-is) | https://wiki.hypr.land/Configuring/ | contract (d): `source = <repo>/hypr-binds.conf` is correct; the last-matching-bind precedence ⇒ source LAST (the file's `:35`-`43` caveat) |

---

## 4. Test results (the contract's run command, LIVE)

```
$ timeout 90 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
...............                                                          [100%]
15 passed in 0.01s
```

The suite (15 tests) is pure-stdlib `re`/`pathlib`: it parses `systemd/voice-typing.service` +
`voice_typing/launch_daemon.sh` + `install.sh` + `hypr-binds.conf` — no GPU/CUDA/daemon/mic. **3 tests pin
hypr-binds.conf-related concerns** (all VT-003 / Mode-A-docs / usage-hint): `test_hypr_binds_use_portable_
home_launcher` (`:321`, contract point (c) — asserts `$HOME/.local/bin/voicectl` + no `/home/` on EVERY
bind line), `test_install_sh_installs_stable_voicectl_launcher` (`:306`, VT-003 launcher-presence — bare
`ln -s` + the never-clobber-foreign guard), `test_install_sh_usage_lists_all_commands_and_correct_keybinds`
(`:223`, the 7-command usage list + the CORRECT keybind hints in install.sh's usage STRING — asserts both
`Ctrl+Alt+Super+D` and `Alt+Super+D -> voicectl toggle-lite` are present AND the WRONG mapping
`SUPER+ALT+D -> voicectl toggle` is absent). **Coverage gap**: NO test asserts the MODS+key↔command mapping
on hypr-binds.conf's `bind =` lines themselves (§5.1) — the headline nuance.

---

## 5. Non-defect nuances (so they are not mistaken for gaps)

### 5.1 THE HEADLINE — the `bind =` MODS+key↔command MAPPING in hypr-binds.conf has NO direct test (coverage gap, NOT a code defect)
hypr-binds.conf's PRIMARY contract — which MODS+key maps to `toggle` vs `toggle-lite` (contract points
(a)+(b), PRD §4.10 + §4.2ter) — has NO direct test. The two relevant tests pin only ADJACENT concerns:

- `test_hypr_binds_use_portable_home_launcher` (`:321`) reads `_hypr_binds_path()` (`:66`), collects every
  `bind =` line, and asserts EACH contains `$HOME/.local/bin/voicectl` + no `/home/`. It does NOT check
  which MODS+key prefixes the line, nor which `toggle`/`toggle-lite` verb follows — it would pass a file
  where the two binds were swapped (`CTRL SUPER ALT → toggle-lite`, `SUPER ALT → toggle`).
- `test_install_sh_usage_lists_all_commands_and_correct_keybinds` (`:223`) reads `install.sh` (NOT
  hypr-binds.conf) and asserts the usage STRING contains `Ctrl+Alt+Super+D` +
  `Alt+Super+D -> voicectl toggle-lite` + the absence of the wrong `SUPER+ALT+D -> voicectl toggle`. This
  DOES pin the mapping — but only in install.sh's **printed hint text**, not in hypr-binds.conf's actual
  `bind =` lines. A swapped-binds regression in hypr-binds.conf (with install.sh's hint left correct) would
  pass the 15-test suite silently.

So the mapping is pinned in the WRONG file (install.sh's usage string) relative to the file that actually
executes at key-press time (hypr-binds.conf's `bind =` lines). **This is a coverage gap, not a code
defect**: the code is correct (verified by read §1 + §2). This audit IS the PRD §4.10 MODS↔command
compliance check the suite cannot perform — exactly the role `gap_launch_daemon.md`'s §5.1 (the cuBLAS/
cuDNN discovery has no test) + `gap_install.md`'s §5.4 (the core install flow has no test) play for their
slices. A future test-hardening pass COULD add a `test_hypr_binds_mods_map_to_correct_command` (parse the
`bind =` lines + assert `CTRL SUPER ALT, D` → ends with `toggle` and `SUPER ALT, D` → ends with
`toggle-lite`) — **out of scope for this read-only audit** (do NOT add a test here; consistent with every
round-006 audit's "read-only, no new tests" discipline). ✅

### 5.2 `$HOME` expansion works because Hyprland runs `bind exec` via `/bin/sh -c` (contract point (c))
The binds use `$HOME/.local/bin/voicectl` rather than an absolute `/home/<user>/…` path. This is NOT a
shell-variable that Hyprland fails to expand — Hyprland's `exec` dispatcher passes the params to
`/bin/sh -c "<cmd>"`, so `$HOME` expands at press time under the pressing user's environment. The file
documents this precisely (`hypr-binds.conf:21`-`28`, citing the Hyprland source `Executor.cpp` `execl("/bin/sh",
"/bin/sh", "-c", …)`). Combined with the VT-003 launcher symlink (`install.sh:190`, `$HOME/.local/bin/voicectl
→ $REPO/.venv/bin/voicectl`), this makes the binds work regardless of which user runs them or where the repo
was cloned — the intended portability mechanism. A hardcoded `/home/<user>` would be a regression (the
older `.venv/bin/voicectl` absolute path was replaced by this for exactly that reason). Do NOT flag the
`$HOME` as a defect. ✅

### 5.3 The source-LAST precedence caveat (contract point (d) + DOCS)
Hyprland uses the LAST matching bind for a given MODS+key (so two binds on the same combo → the later one
wins). The file's PRECEDENCE block (`:35`-`43`) tells the user to `source` it LAST (at the bottom of
`~/.config/hypr/hyprland.conf`) so its binds win, and lists the user's real conflict files to check
(`~/.config/hypr/custom/keybinds.conf`, `~/.config/hypr/hyprland/keybinds.conf` — from the round-001
research note `plan/001_be48c74bc590/P2M1T1.S1/research/hyprland_bind_and_source.md`). This is correct +
matches the Hyprland wiki (https://wiki.hypr.land/Configuring/). The `source = <repo>/hypr-binds.conf`
instruction (`:16`) + `hyprctl reload` (`:19`) are the realization. ✅

### 5.4 The "never edit" promise is a PROMISE, not a test (contract point (e))
Contract point (e) — "Do NOT modify the user's Hyprland config automatically" (PRD §4.10) — is an ABSENCE
guarantee: the repo must NOT do something. It cannot be pinned by a positive unit test (you cannot assert a
negative by parsing a file that might add the write elsewhere). The repo-wide grep in §3 is the strongest
static proof (ZERO `sed`/`cp`/`>>`/`>` hits on `hyprland.conf` across all `*.sh`+`*.py`), backed by the
triple in-source promise (hypr-binds.conf:13 + install.sh:216 "add this line" + README:83). This audit
records the proof; it does not (and cannot) add a test that the repo will never grow such a write — that is
a code-review concern, satisfied by the grep here + the convention it establishes. ✅

### 5.5 MODS spelled with SPACES (`CTRL SUPER ALT`), not underscores — correct, do NOT "normalize" (contracts (a)+(b))
The binds spell the MODS field as `CTRL SUPER ALT, D` (whitespace-separated). Hyprland's bind parser splits
MODS on whitespace OR underscore (https://wiki.hypr.land/Configuring/Basics/Binds/), so `CTRL SUPER ALT` ≡
`CTRL_SUPER_ALT` — both valid. The PRD §4.10 spells it with spaces, so the file matches the contract
verbatim. A well-meaning "normalization" to `CTRL_SUPER_ALT` would be a no-op functionally but a drift from
the PRD's literal. Do NOT flag the space spelling as a defect. ✅

---

## 6. Conclusion

**PASS.** `hypr-binds.conf` fully complies with PRD §4.10 + §4.2ter + the work-item contract + Acceptance
#7: all 5 contract points (a)–(e) + the DOCS point are present + correct (file:line-evidenced), the 3-way
cross-read (README ↔ hypr-binds.conf ↔ install.sh) is a MATCH (both bind= lines verbatim in all three, the
`source =` instruction in all three, the never-edit promise in all three), the VT-003 launcher path
(`$HOME/.local/bin/voicectl`) is used on both binds with NO non-comment `/home/` literal, the repo-wide grep
confirms the repo NEVER writes to the user's `hyprland.conf`, and the suite is green (**15 passed in 0.01s**).
**No source files were modified** (read-only audit); the sole artifact is this report. The audit's value-add
= the headline §5.1 coverage gap (the `bind =` MODS+key↔command mapping in hypr-binds.conf is verified by
read + the 3-way cross-read, NOT by any test — the mapping is pinned only in install.sh's usage STRING,
`test_install_sh_usage_lists_all_commands_and_correct_keybinds` `:223`, so a swapped-binds regression in
hypr-binds.conf would pass silently). Ties to PRD §4.10 (the two binds + the source-it-don't-edit-it
contract), §4.2ter (which keybind maps to which mode), and Acceptance #7 (README documents the hotkey
snippet). Acceptance #7 is MET. Scope is `hypr-binds.conf` + its 3 cross-references ONLY — `install.sh` is
P1.M4.T3.S1 (`gap_install.md`, cited not re-audited), `launch_daemon.sh` is P1.M4.T2.S1
(`gap_launch_daemon.md`), the systemd unit is P1.M4.T1.S1 (`gap_systemd.md`), and the `voicectl` verbs the
binds exec are P1.M3.T2.S1/S2.