# PRP — P1.M4.T4.S1: Audit hypr-binds.conf (both keybinds, correct commands, source instructions) vs PRD §4.10 + §4.2ter

## Goal

**Feature Goal**: Produce the authoritative **`hypr-binds.conf` Hyprland-keybind compliance audit** as a NEW
`gap_hypr_binds.md` report — verifying **ALL** work-item contract points (a)–(e) + the DOCS point against the
LIVE committed `hypr-binds.conf` (repo root, 3 KB) + its 3 cross-references (install.sh's printed source
instruction + launcher install, README.md's "Hotkey (Hyprland)" section = Acceptance #7, and the
`tests/test_systemd_unit.py` pinning tests), all tied to **PRD §4.10** ("create `hypr-binds.conf` …
`bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle` / `bind = SUPER ALT, D, exec,
$HOME/.local/bin/voicectl toggle-lite` … Print an instruction to `source` it from
`~/.config/hypr/hyprland.conf`. Do NOT modify the user's Hyprland config automatically") + **PRD §4.2ter**
("`Ctrl+Alt+Super+D` → `toggle` (big/normal model) and `Alt+Super+D` → `toggle-lite` (little/lite model)")
+ **Acceptance #7** ("README documents hotkey snippet").

The 5 contract points + the DOCS point:
- **(a)** `bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle` present (NORMAL / big model).
- **(b)** `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite` present (LITE / little model).
- **(c)** both binds invoke `$HOME/.local/bin/voicectl` — the STABLE launcher symlink `install.sh` maintains
  (`$HOME/.local/bin/voicectl → <repo>/.venv/bin/voicectl`, VT-003) — NOT a hardcoded `/home/<user>` repo path.
- **(d)** the file CONTAINS a source-instruction comment telling the user to add `source = <repo>/hypr-binds.conf`
  to `~/.config/hypr/hyprland.conf`.
- **(e)** the repo does NOT auto-modify the user's `hyprland.conf` (install.sh only PRINTS the instruction).
- **DOCS [Mode A]**: the `hypr-binds.conf` comment block explains BOTH the source instruction AND the two
  modes (normal vs lite) — verify it does.

**Deliverable** (ONE artifact — CREATE a new report file; do NOT append to an existing one):
- `plan/006_862ee9d6ef41/architecture/gap_hypr_binds.md` — a NEW self-contained `# Gap Report —
  P1.M4.T4.S1: …` file (there is NO existing `gap_hypr*` in `architecture/`; `ls architecture/` confirms —
  this subtask creates it). Format mirrors `gap_install.md` (P1.M4.T3.S1) / `gap_launch_daemon.md`
  (P1.M4.T2.S1) / `gap_systemd.md` — all read-only infra-layer audits of committed files. Verbatim content
  scaffold in the Implementation Blueprint → Task 3 (evidence pre-filled from verified `hypr-binds.conf`
  content + `install.sh:line` + `README.md:line` + the 3 pinning tests; the auditor re-confirms the line
  numbers + the test pass count LIVE).

> **VERIFIED VERDICT (this PRP's research): `hypr-binds.conf` is COMPLIANT** with PRD §4.10 + §4.2ter +
> the work-item contract + Acceptance #7 — **no fix needed**. All 5 contract points + the DOCS point pass:
> (a) `bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle` present; (b)
> `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite` present; (c) both use
> `$HOME/.local/bin/voicectl` (VT-003 launcher, install.sh:190 `ln -s "$REPO/.venv/bin/voicectl"
> "$LAUNCHER"`); (d) the comment block has the `source = <repo>/hypr-binds.conf` instruction +
> `hyprctl reload`; (e) install.sh only PRINTS (`:216`-`:217`), never edits the user's hyprland.conf; DOCS
> the comment block explains both modes (big=distil-large-v3+small.en, lite=small.en only) + the source
> instruction + VT-003 + precedence. Acceptance #7 PASSES: README.md:79-116 "Hotkey (Hyprland)" is a
> **3-way match** (README ↔ hypr-binds.conf ↔ install.sh:216-217). Test suite **15 passed in 0.01s**
> (re-verified LIVE this round).

> **The audit's value-add (HEADLINE NUANCE): the actual `bind =` MODS+key↔command MAPPING in
> hypr-binds.conf has NO direct test.** `test_hypr_binds_use_portable_home_launcher` (`:321`) pins ONLY the
> command PATH (`$HOME/.local/bin/voicectl` + no `/home/`), not which MODS+key maps to `toggle` vs
> `toggle-lite`; `test_install_sh_usage_lists_all_commands_and_correct_keybinds` (`:223`) pins the keybind
> hints in install.sh's usage STRING, not the bind= lines. ⇒ a swapped-binds regression (toggle-lite on
> `CTRL SUPER ALT`) would PASS the 15-test suite silently. **This audit IS the PRD §4.10 MODS↔command
> compliance check the suite cannot perform.**

**Success Definition**: `architecture/gap_hypr_binds.md` exists, is self-contained, records a per-contract-point
compliance table (5 points + DOCS) with `file:line` evidence re-verified LIVE, cites the 3 pinning tests +
their coverage limit, re-runs `tests/test_systemd_unit.py` (expect 15 passed), cross-reads README ↔
hypr-binds.conf ↔ install.sh for Acceptance #7, and states the headline coverage nuance. NO source file is
modified (read-only audit — consistent with every round-006 audit).

## Why

- **P1 is the "PRD Compliance Verification & Remediation" round.** P1.M4.T4 is the Hyprland-keybinds audit
  slice (PRD §4.10 Phase 2). This subtask (S1) is its ONLY leaf — the closed-form verification that the
  committed `hypr-binds.conf` matches the PRD's two-bind spec + the source-it-don't-edit-it contract.
- The binds are the USER-FACING entry point to both arming modes (normal via `toggle`, lite via
  `toggle-lite`, PRD §4.2ter). A swapped or mispathed bind is a silent UX regression the test suite cannot
  catch (§headline nuance) — so this read audit is the only gate.
- Feeds **P1.M5.T5.S1** (acceptance-criteria cross-check) the Acceptance-#7 evidence, and **P1.M6.T1.S1**
  (README completeness) the 3-way-match finding.

## What

A read-only audit producing one Markdown report. The auditor: (1) reads `hypr-binds.conf` in full;
(2) maps each of the 5 contract points + the DOCS point to `file:line` evidence via `grep -nE`;
(3) cross-reads install.sh (source-instruction print + launcher install) + README.md (Hotkey section) +
`tests/test_systemd_unit.py` (3 pinning tests); (4) re-runs the test suite LIVE; (5) writes the gap report
mirroring `gap_install.md`'s structure, with the headline coverage nuance as §5.

### Success Criteria

- [ ] `architecture/gap_hypr_binds.md` created (NEW file; did not exist before).
- [ ] Per-contract-point compliance table covers (a)–(e) + the DOCS point, each with `file:line` evidence
      re-verified LIVE this round (not copied from this PRP's numbers).
- [ ] Acceptance #7 verdict recorded with the 3-way-match evidence (README ↔ hypr-binds.conf ↔ install.sh).
- [ ] The 3 pinning tests named with their `tests/test_systemd_unit.py` line numbers + their coverage LIMIT
      (the headline nuance) explicitly stated.
- [ ] `tests/test_systemd_unit.py` re-run LIVE (expect **15 passed in ~0.01s**); actual count recorded.
- [ ] Verdict = COMPLIANT (no fix); the report states NO source was modified.

## All Needed Context

### Context Completeness Check

_Pass._ Someone who knows nothing about this codebase gets: the exact file to audit (`hypr-binds.conf`,
repo root), the exact contract (5 points + DOCS, each with the expected literal), the 3 cross-reference
files + their relevant line ranges, the authoritative Hyprland docs URLs (bind/source/precedence), the
test command + expected result, and a verbatim scaffold of the report to write. No inference required.

### Documentation & References

```yaml
# MUST READ — the audited artifact + its 3 cross-references
- file: hypr-binds.conf
  why: THE audited file — the two bind= lines (contract a+b), the $HOME launcher path (c), the source
        instruction comment (d), the never-edit promise (e), and the two-mode + VT-003 explanation (DOCS).
  pattern: a committed Hyprland config snippet with a Mode-A "USER INTEGRATION" comment block.
  gotcha: MODS field `CTRL SUPER ALT` (space) is the PRD's exact spelling — do NOT "normalize" to
          `CTRL_SUPER_ALT`; both parse but the PRD is the contract. The path is `$HOME/.local/bin/voicectl`
          (VT-003 launcher), NOT the older `.venv/bin/voicectl` absolute path.

- file: install.sh
  why: cross-ref for contract (c) [the launcher symlink the binds resolve to] + (d)/(e) [it PRINTS the
        source instruction, never applies it].
  section: ":174-:192" (VT-003 launcher install: LAUNCHER="$HOME/.local/bin/voicectl" :180,
            ln -s "$REPO/.venv/bin/voicectl" "$LAUNCHER" :190); ":209-:210" (usage + keybind hint);
            ":216-:217" (the PRINTED source = $REPO/hypr-binds.conf line).
  gotcha: install.sh was ALREADY audited wholesale by P1.M4.T3.S1 (gap_install.md) — DO NOT re-audit it;
          cite its :190/:216-:217 findings as the cross-reference only.

- file: README.md
  why: cross-ref for Acceptance #7 ("README documents hotkey snippet") — the "## Hotkey (Hyprland)" section.
  section: ":79-:116" — documents both keybinds, the source = …/hypr-binds.conf line, the never-edit
            promise, hyprctl reload, the $HOME launcher, the verbatim bind block, + precedence/troubleshooting.
  pattern: Mode-A doc that lifts the snippet verbatim from hypr-binds.conf + install.sh.

- file: tests/test_systemd_unit.py
  why: the audit's RUN COMMAND + the 3 tests that pin hypr-binds.conf (and their coverage LIMIT = the
        headline nuance). Pure-stdlib re/pathlib (parses the unit + wrapper + install + binds files; NO
        GPU/CUDA/daemon/mic).
  section: "_hypr_binds_path() :66-68; test_hypr_binds_use_portable_home_launcher :321-332 [pins PATH
            only]; test_install_sh_installs_stable_voicectl_launcher :306-318; test_install_sh_usage_lists_
            all_commands_and_correct_keybinds :223-254 [pins usage STRING, not bind= lines]."

# MUST READ — PRD contract (the merged PRD sections; also in plan/006_862ee9d6ef41/prd_snapshot.md)
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: §4.10 (the exact two binds + the source-it-don't-edit-it contract) + §4.2ter (which keybind maps to
        which mode: Ctrl+Alt+Super+D → toggle/big, Alt+Super+D → toggle-lite/little).
  section: "§4.10 Phase 2" + "§4.2ter Lite mode → Commands / keybind".

# MUST READ — the sibling gap reports to MIRROR (structure + tone + the "headline nuance" convention)
- file: plan/006_862ee9d6ef41/architecture/gap_install.md
  why: the closest sibling (infra-layer, install.sh source-instruction + launcher already audited as part
        of it) — MIRROR its structure: header (Date/Scope/Audited artifacts/Bottom line) → §1 Method +
        Commands run → §2 Per-contract-point Compliance Table → §3 (live probe if any) → §4 Test results →
        §5 Non-defect nuances (headline coverage gap) → §6 Conclusion.
- file: plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md
  why: the other infra sibling — its §5.1 "headline nuance = primary function has no test" is the EXACT
        pattern this audit's headline nuance follows.

# External — authoritative Hyprland facts (the "why the binds are correct" backbone; cite in DOCS section)
- url: https://wiki.hypr.land/Configuring/Basics/Binds/
  why: bind = MODS, key, dispatcher, params syntax; MODS splits on whitespace OR underscore (so
        `SUPER ALT` ≡ `SUPER_ALT`); the file's space spelling is valid + matches the PRD.
  critical: confirms contract (a)+(b) MODS spelling is correct; do not "fix" the space to an underscore.
- url: https://wiki.hypr.land/Configuring/Basics/Dispatchers/
  why: the `exec` dispatcher runs params as a shell command via /bin/sh -c — this is WHY `$HOME` in the
        bind expands at press time (user/repo-location-independent). The file's VT-003 comment states this.
  critical: confirms contract (c)'s `$HOME` expansion mechanism; a hardcoded /home/<user> would be a
            portability regression (VT-003) the launcher symlink + $HOME together prevent.
- url: https://wiki.hypr.land/Configuring/
  why: the `source = <path>` keyword (relative → ~/.config/hypr/; absolute works as-is); both `source=`
        and `source = ` parse. The file + install.sh use `source = …` (spaces).
  critical: confirms contract (d)'s `source = <repo>/hypr-binds.conf` is correct + the precedence caveat
            (last matching bind wins ⇒ source LAST) the file documents.

# Prior research (round-001) — the implementation note that created hypr-binds.conf
- file: plan/001_be48c74bc590/P2M1T1.S1/research/hyprland_bind_and_source.md
  why: the original implementation research — bind/source/precedence facts, the user's real hyprland.conf
        structure (sources custom/keybinds.conf + hyprland/keybinds.conf ⇒ precedence caveat), the Mode-A
        doc convention (mirror status.sh's USER INTEGRATION block).
  gotcha: that note referenced the OLDER `.venv/bin/voicectl` absolute path; the CURRENT committed file
          uses `$HOME/.local/bin/voicectl` (VT-003 launcher) — the file + PRD are the source of truth.
```

### Current Codebase tree (relevant slice)

```bash
hypr-binds.conf                       # THE audited file (repo root, 3 KB) — 2 binds + Mode-A comment block
install.sh                            # cross-ref: :174-192 launcher, :209-210 usage, :216-217 source print
README.md                             # cross-ref: :79-116 "## Hotkey (Hyprland)" = Acceptance #7
tests/test_systemd_unit.py            # RUN CMD + 3 pinning tests (:223, :306, :321)
systemd/voice-typing.service          # (out of scope — P1.M4.T1.S1 / gap_systemd.md)
voice_typing/launch_daemon.sh         # (out of scope — P1.M4.T2.S1 / gap_launch_daemon.md)
voice_typing/ctl.py / voicectl        # (out of scope — P1.M3.T2.S1/S2; the verbs the binds exec)
plan/006_862ee9d6ef41/architecture/   # OUTPUT location — gap_hypr_binds.md (NEW) joins 16 sibling gap_*.md
```

### Desired Codebase tree with files to be added

```bash
plan/006_862ee9d6ef41/architecture/gap_hypr_binds.md   # NEW — the audit report (the SOLE deliverable)
# (research note already exists: plan/006_862ee9d6ef41/P1M4T4S1/research/hypr_binds_audit_research.md)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL: this is a READ-ONLY audit. Do NOT edit hypr-binds.conf, install.sh, README.md, or any test.
#   Every round-006 audit is read-only + "no new tests" — the gap report IS the compliance check.
# CRITICAL: re-verify EVERY file:line + the test pass count LIVE (grep -nE + pytest re-run). Do NOT copy
#   this PRP's embedded numbers verbatim — the report must reflect the tree as the auditor reads it.
# CRITICAL (AGENTS.md): the pytest run is pure-stdlib + ~0.01s, but STILL wrap it in `timeout`:
#   `timeout 90 .venv/bin/python -m pytest tests/test_systemd_unit.py -q` (inner) + the bash tool `timeout`
#   above it (outer). test_systemd_unit.py is explicitly GPU/CUDA/daemon/mic-FREE (safe, fast).
# GOTCHA: hypr-binds.conf MODS uses SPACE (`CTRL SUPER ALT`), not underscore — both parse (Hyprland splits
#   MODS on whitespace OR underscore), but the PRD §4.10 spells it with spaces, so the file is correct.
#   Do NOT flag the space as a defect.
# GOTCHA: the bind path is `$HOME/.local/bin/voicectl` (VT-003 launcher symlink → <repo>/.venv/bin/voicectl),
#   NOT the .venv absolute path. $HOME expands because Hyprland runs `bind exec` via `/bin/sh -c`.
# GOTCHA: install.sh was ALREADY audited by P1.M4.T3.S1 (gap_install.md). Cite its :190/:216-:217 findings;
#   do NOT re-audit install.sh wholesale (scope = hypr-binds.conf + its 3 cross-refs, not the installer).
```

## Implementation Blueprint

### Data models and structure

N/A — this is a documentation/audit deliverable (one Markdown report). No code models.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RE-VERIFY the live state (read + grep) — the audit's evidence base
  - READ: hypr-binds.conf (full, ~50 lines) — confirm the 2 bind= lines + the Mode-A comment block.
  - GREP the 5 contract points + DOCS (file:line evidence); EXPECT all present:
      grep -nE 'bind = CTRL SUPER ALT, D, exec, \$HOME/\.local/bin/voicectl toggle'    hypr-binds.conf   # (a)
      grep -nE 'bind = SUPER ALT, D, exec, \$HOME/\.local/bin/voicectl toggle-lite'    hypr-binds.conf   # (b)
      grep -nE '\$HOME/\.local/bin/voicectl'                                          hypr-binds.conf   # (c) path
      grep -nE '/home/'                                                               hypr-binds.conf   # (c) expect: NO non-comment /home/ literal
      grep -nE 'source = .*hypr-binds\.conf|USER INTEGRATION|never edit'               hypr-binds.conf   # (d)+(e)+DOCS
      grep -nE 'CTRL\+?SUPER\+?ALT\+?D|SUPER\+?ALT\+?D|BIG model|LITTLE model|distil-large|small\.en' hypr-binds.conf  # DOCS two-mode
  - CROSS-GREP install.sh (contract c/d/e wiring — cite, don't re-audit):
      grep -nE 'LAUNCHER=.*\.local/bin/voicectl|ln -s .*voicectl'                      install.sh        # (c) launcher :180/:190
      grep -nE 'source = .*/hypr-binds\.conf|Hyprland — source'                        install.sh        # (d) print :216-217
      grep -nE '~/.config/hypr/hyprland\.conf'                                        install.sh        # (e) expect: PRINT/echo only, no sed/cp/append
  - CROSS-GREP README.md (Acceptance #7):
      grep -nE '## Hotkey|source = .*hypr-binds\.conf|Ctrl\+Alt\+Super\+D|Alt\+Super\+D|toggle-lite' README.md
  - NAMING/PLACEMENT: evidence recorded as `file:line` in the §2 compliance table.

Task 2: RE-RUN the pinning test suite LIVE (the audit's run command — two timeouts per AGENTS.md Rule 1)
  - RUN: timeout 90 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
    (set the bash tool `timeout` ABOVE 90, e.g. 120 — the outer backstop)
  - EXPECT: 15 passed in ~0.01s (pure-stdlib; no GPU/CUDA/daemon/mic).
  - IDENTIFY the 3 hypr-binds pinning tests + their coverage LIMIT:
      grep -nE 'def test_hypr_binds_use_portable_home_launcher|def test_install_sh_installs_stable_voicectl_launcher|def test_install_sh_usage_lists_all_commands_and_correct_keybinds' tests/test_systemd_unit.py
  - CONFIRM the coverage gap (the headline nuance §5): the bind= MODS↔command MAPPING has no direct test:
      grep -qE 'def test_.*(bind_mods|ctrl_super_alt|toggle_lite_bind|bind_mapping)' tests/test_systemd_unit.py && echo "a mapping test EXISTS (update §5)" || echo "no MODS↔command mapping test (headline nuance §5)"

Task 3: WRITE plan/006_862ee9d6ef41/architecture/gap_hypr_binds.md (the SOLE deliverable)
  - CREATE: a NEW `# Gap Report — P1.M4.T4.S1: hypr-binds.conf … vs PRD §4.10 + §4.2ter` file.
  - FOLLOW structure: gap_install.md (P1.M4.T3.S1) / gap_launch_daemon.md (P1.M4.T2.S1) VERBATIM:
      Header block (Date / Scope / Audited artifacts / **Bottom line: ✅ COMPLIANT, no fix**)
      §1 Method (+ Commands run, re-verification — the Task 1+2 greps + pytest)
      §2 Per-contract-point Compliance Table (a-e + DOCS | expected | actual file:line | pinning test | verdict)
      §3 (optional) the bind/source/precedence external facts (the Hyprland wiki URLs) — the "why correct"
      §4 Test results (15 passed in 0.01s; name the 3 pinning tests + lines)
      §5 Non-defect nuances — §5.1 HEADLINE: the MODS↔command mapping has NO test (the swapped-binds
           regression that would pass silently) + §5.2 the $HOME-expansion-via-/bin/sh-c mechanism +
           §5.3 the source-LAST precedence caveat + §5.4 the never-edit-is-a-promise-not-a-test point
      §6 Conclusion (PASS; Acceptance #7 met; scope = hypr-binds.conf + 3 cross-refs; no source modified)
  - NAMING: gap_hypr_binds.md (snake_case, matches the 16 sibling gap_*.md files).
  - PLACEMENT: plan/006_862ee9d6ef41/architecture/ (where every sibling gap report lives).
  - CONTENT: pre-fill the §2 table from this PRP's VERIFIED VERDICT + Task 1's LIVE grep output; cite
      gap_install.md for the install.sh :190/:216-:217 findings (do not re-derive).

Task 4: (NONE — no source modification, no test addition)
  - DO NOT edit hypr-binds.conf / install.sh / README.md / any test / PRD / tasks.json / prd_snapshot.md.
  - DO NOT add a test for the MODS↔command mapping (every round-006 audit is "read-only, no new tests";
      the gap report records the coverage gap; a future test-hardening pass may close it).
```

### Implementation Patterns & Key Details

```python
# The §2 compliance table row pattern (mirror gap_launch_daemon.md §2):
# | # | contract requirement | expected | actual (file:line) | pinning test | verdict |
# |---|---|---|---|---|---|
# | (a) | bind CTRL SUPER ALT,D -> voicectl toggle (normal) | `bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle` | hypr-binds.conf:<line> | (none — headline §5.1) | ✅ |
# | (b) | bind SUPER ALT,D -> voicectl toggle-lite (lite)   | `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite` | hypr-binds.conf:<line> | (none — headline §5.1) | ✅ |
# | (c) | uses $HOME/.local/bin/voicectl (VT-003 launcher)  | $HOME/.local/bin/voicectl, no /home/ literal | hypr-binds.conf:<line> + install.sh:190 | test_hypr_binds_use_portable_home_launcher :321 | ✅ |
# | (d) | source-instruction comment present                | `source = <repo>/hypr-binds.conf` + hyprctl reload in comment | hypr-binds.conf:<line> + install.sh:216-217 | (none — doc) | ✅ |
# | (e) | does NOT modify user's hyprland.conf              | install.sh PRINTS only (echo), no sed/cp/append on ~/.config/hypr/hyprland.conf | install.sh:216-217 | (none — behavior promise) | ✅ |
# | DOCS | comment explains source instr + BOTH modes        | USER INTEGRATION block + BIG/LITTLE model lines | hypr-binds.conf:<line> | (none — doc) | ✅ |

# The headline nuance §5.1 pattern (mirror gap_launch_daemon.md §5.1):
# "hypr-binds.conf's PRIMARY contract — the MODS+key↔command MAPPING (a/b) — has NO direct test.
#  test_hypr_binds_use_portable_home_launcher (:321) pins ONLY the command PATH; test_install_sh_usage_
#  lists_all_commands_and_correct_keybinds (:223) pins install.sh's usage STRING. NEITHER asserts which
#  MODS+key maps to toggle vs toggle-lite. ⇒ a swapped-binds regression passes the 15-test suite silently.
#  This audit IS the PRD §4.10 MODS↔command compliance check the suite cannot perform."
```

### Integration Points

```yaml
CONSUMES (read-only cross-references):
  - hypr-binds.conf (repo root)                          # THE audited file
  - install.sh :174-192, :209-210, :216-217              # launcher + source-instruction print (cite gap_install.md)
  - README.md :79-116                                    # Acceptance #7 hotkey doc
  - tests/test_systemd_unit.py :223, :306, :321          # the 3 pinning tests (+ their coverage limit)
  - plan/006_862ee9d6ef41/prd_snapshot.md §4.10 + §4.2ter # the contract

PRODUCES (the SOLE output):
  - plan/006_862ee9d6ef41/architecture/gap_hypr_binds.md # NEW report (joins 16 sibling gap_*.md)

FEEDS (downstream consumers):
  - P1.M5.T5.S1 (acceptance cross-check)                 # consumes the Acceptance-#7 PASS evidence here
  - P1.M6.T1.S1 (README completeness)                    # consumes the 3-way-match finding here
  - P1.M6.T1.S3 (commit readiness)                       # gap_hypr_binds.md is a committed plan artifact

PARALLEL-SAFE:
  - P1.M4.T3.S2 (prefetch.py audit, Implementing) = ZERO file overlap (prefetch.py/HF-cache vs hypr-binds).
    This PRP consumes nothing prefetch produces; both write distinct gap_*.md files to architecture/.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# The deliverable is a Markdown report — validate structure, not code.
# Confirm the report exists + has the required sections (mirror gap_install.md):
test -f plan/006_862ee9d6ef41/architecture/gap_hypr_binds.md && echo "EXISTS"
grep -c '^## ' plan/006_862ee9d6ef41/architecture/gap_hypr_binds.md   # expect ≥6 H2 sections (Method/Table/Test/nuances/Conclusion)
grep -q 'P1.M4.T4.S1' plan/006_862ee9d6ef41/architecture/gap_hypr_binds.md && echo "titled correctly"
grep -qi 'COMPLIANT' plan/006_862ee9d6ef41/architecture/gap_hypr_binds.md && echo "verdict present"
# Expected: EXISTS; ≥6 sections; title + COMPLIANT verdict present. NO code to lint/type-check.
```

### Level 2: Unit Tests (Component Validation)

```bash
# Re-run the pinning suite LIVE (the audit's run command — two timeouts per AGENTS.md Rule 1):
timeout 90 .venv/bin/python -m pytest tests/test_systemd_unit.py -q
# (set the bash tool `timeout` to 120 — the outer backstop above the inner 90.)
# Expected: 15 passed in ~0.01s. The 3 hypr-binds tests (:223, :306, :321) are among them.
# Record the ACTUAL count + timing in gap_hypr_binds.md §4 (do not copy this PRP's number verbatim).
```

### Level 3: Integration Testing (System Validation)

```bash
# Acceptance #7 3-way match (README ↔ hypr-binds.conf ↔ install.sh) — the cross-read proof:
grep -F 'bind = CTRL SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle'       hypr-binds.conf
grep -F 'bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite'       hypr-binds.conf
grep -F 'source = ' README.md | grep 'hypr-binds.conf'                            # README snippet
grep -nE 'source = .*/hypr-binds\.conf|source = \$REPO/hypr-binds\.conf'         install.sh      # install.sh print
# Expected: the two bind lines in hypr-binds.conf; the source= line in BOTH README + install.sh.
# (NO live daemon/hyprctl/wtype needed — this is a static-doc audit. Do NOT arm the mic or reload Hyprland.)
```

### Level 4: Creative & Domain-Specific Validation

```bash
# The "never edit the user's hyprland.conf" guarantee (contract e) — grep-provable across the repo:
grep -rnE 'sed.*hyprland\.conf|cp .*hyprland\.conf|>> ?.*hyprland\.conf|> ?.*hyprland\.conf' \
    --include='*.sh' --include='*.py' . 2>/dev/null | grep -v '.venv/' | grep -v 'plan/'
# Expected: NO hits (the repo only PRINTS the source= instruction; it never writes to the user's hyprland.conf).
# Record this proof in gap_hypr_binds.md §2 row (e) / §5.4.
```

## Final Validation Checklist

### Technical Validation

- [ ] `architecture/gap_hypr_binds.md` created (NEW; did not exist before — `ls architecture/gap_hypr*` was empty).
- [ ] §2 compliance table covers ALL 5 contract points (a)–(e) + the DOCS point, each with LIVE `file:line`.
- [ ] `tests/test_systemd_unit.py` re-run LIVE; actual pass count recorded (expect 15 passed in ~0.01s).
- [ ] The 3 pinning tests named with line numbers (:223, :306, :321).
- [ ] Headline coverage nuance (§5.1: MODS↔command mapping untested) explicitly stated.

### Feature Validation

- [ ] Acceptance #7 verdict recorded with 3-way-match evidence (README ↔ hypr-binds.conf ↔ install.sh).
- [ ] All success criteria from "What" section met.
- [ ] Verdict = COMPLIANT (no fix needed) — the report states NO source was modified.

### Code Quality Validation

- [ ] Report structure mirrors `gap_install.md` / `gap_launch_daemon.md` (header → §1 Method → §2 Table →
      §4 Test → §5 Nuances → §6 Conclusion).
- [ ] Every `file:line` re-verified LIVE (not copied from this PRP).
- [ ] Scope respected: hypr-binds.conf + 3 cross-refs ONLY (install.sh cited from gap_install.md, not re-audited).

### Documentation & Deployment

- [ ] Report is self-contained (an implementer/reviewer needs no other file to understand the verdict).
- [ ] External Hyprland wiki URLs cited (binds / dispatchers / source) in the "why correct" section.

---

## Anti-Patterns to Avoid

- ❌ Don't EDIT any source file — this is a read-only audit; the gap report is the only artifact.
- ❌ Don't ADD a test for the MODS↔command mapping — round-006 audits are "read-only, no new tests"; record
  the coverage gap in §5, do not close it here.
- ❌ Don't re-audit install.sh wholesale — it was audited by P1.M4.T3.S1 (gap_install.md); cite its findings.
- ❌ Don't copy this PRP's embedded line numbers / pass count into the report verbatim — re-verify LIVE.
- ❌ Don't flag the `CTRL SUPER ALT` space spelling as a defect — Hyprland splits MODS on whitespace OR
  underscore; the PRD §4.10 spells it with spaces, so the file is correct.
- ❌ Don't flag the `$HOME/.local/bin/voicectl` path as a defect vs the older `.venv/bin/voicectl` — the
  VT-003 launcher symlink (install.sh:190) + `$HOME` expansion via `/bin/sh -c` are the intended portability
  mechanism; the file + PRD agree.
- ❌ Don't run the daemon, arm the mic, or `hyprctl reload` — this is a static-doc audit; AGENTS.md forbids
  foregrounding the daemon, and no live Hyprland state is needed to verify committed text.

---

## Confidence Score

**9/10** — one-pass success likelihood. The audited file is ALREADY compliant (verified by this PRP's
research: both binds present + correct, $HOME launcher, source-instruction comment, never-edit promise,
two-mode DOCS, Acceptance #7 3-way match, 15 tests green). The deliverable is a single Markdown report
mirroring two existing sibling gap reports whose structure is fully spelled out above with a verbatim §2
table scaffold + the headline nuance text. The only residual risk is the auditor copying this PRP's line
numbers instead of re-grepping LIVE — mitigated by the explicit "re-verify LIVE" task instruction +
anti-pattern. (Not 10/10 only because a tired auditor could skip the live re-verification.)