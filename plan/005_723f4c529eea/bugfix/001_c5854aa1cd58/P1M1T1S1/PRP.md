# PRP — P1.M1.T1.S1: Correct install.sh usage line (7 commands) + fix the keybind hint

## Goal

**Feature Goal**: Fix the two defects in `install.sh`'s `[7/7]` onboarding output (lines 178-179) so that the first thing every user sees after install is accurate: (a) the usage line lists ALL 7 `voicectl` commands (including `toggle-lite`/`start-lite`), and (b) the inline keybind hint states the CORRECT binds — `Ctrl+Alt+Super+D → voicectl toggle` (normal) and `Alt+Super+D → voicectl toggle-lite` (lite) — instead of the factually-wrong `SUPER+ALT+D → voicectl toggle` (that bind is actually lite). Plus a TDD static-text test that pins both corrections so the drift can't recur.

**Deliverable**: Three edits across two files:
1. `install.sh` line 178 — append `|toggle-lite|start-lite` to the usage line (5 → 7 commands).
2. `install.sh` line 179 — replace the wrong single-bind hint with the correct two-bind hint.
3. `tests/test_systemd_unit.py` — add `test_install_sh_usage_lists_all_commands_and_correct_keybinds` (static `read_text` + substring asserts, following the existing `test_install_sh_offline_grep_and_summary` pattern).

**Success Definition**: (a) `install.sh` usage line contains `toggle-lite` and `start-lite`; (b) the bind hint contains `Ctrl+Alt+Super+D` and `Alt+Super+D -> voicectl toggle-lite`; (c) the wrong mapping `SUPER+ALT+D -> voicectl toggle` is GONE; (d) the new test is RED before the install.sh edit and GREEN after (TDD); (e) `bash -n install.sh` passes; (f) only `install.sh` + `tests/test_systemd_unit.py` change.

## User Persona

**Target User**: A user running `./install.sh` for the first time. The `[7/7]` block is the primary onboarding/usage quick-start (install.sh header lines 21-22).

**Use Case**: After install, the user reads the printed usage to learn the commands and the keybind hint to wire up (or recognize) their Hyprland bind.

**Pain Points Addressed**: (1) A user who binds/presses `SUPER+ALT+D` expecting normal (big-model) mode currently arms LITE mode (the wrong hint). (2) A user relying on the printed usage line never learns `toggle-lite`/`start-lite` exist. Both contradict the canonical `hypr-binds.conf` and PRD §4.8/§4.10.

## Why

- **Major doc defect (bugfix Issue 1):** the printed usage lists 5 of 7 commands and states a keybind→command mapping that is factually backwards. `hypr-binds.conf:5-6` (correct) and PRD §4.10 pin `CTRL+SUPER+ALT+D → toggle` / `SUPER+ALT+D → toggle-lite`; install.sh:179 says the opposite for the normal bind.
- **First-run surface:** this is the first thing every user sees after install. Wrong info here actively misleads.
- **Why it slipped past tests:** comments/help/usage strings are NOT covered by the config drift-guard (which only checks parsed VALUES) and no test asserted the help/usage strings. The new static-text test closes that gap permanently.
- **Lowest-risk fix:** two `echo` line edits + one deterministic test. No logic, no config values, no behavior change.

## What

Edit two `echo` lines in `install.sh`'s `[7/7]` block and add one static-text test that reads `install.sh` and asserts the corrected substrings (and the absence of the wrong mapping). No code logic, no config, no other doc surface (sibling tasks own config.toml/ctl.py/daemon.py/README).

### Success Criteria

- [ ] `install.sh:178` usage line includes `toggle-lite` and `start-lite` (7 commands total).
- [ ] `install.sh:179` bind hint includes `Ctrl+Alt+Super+D` (normal) and `Alt+Super+D -> voicectl toggle-lite` (lite).
- [ ] The wrong mapping `SUPER+ALT+D -> voicectl toggle` no longer appears in install.sh.
- [ ] New test `test_install_sh_usage_lists_all_commands_and_correct_keybinds` passes; it FAILED before the install.sh edit (TDD red→green).
- [ ] `bash -n install.sh` passes (valid bash).
- [ ] Only `install.sh` + `tests/test_systemd_unit.py` modified.

## All Needed Context

### Context Completeness Check

_Pass._ Both defective lines are quoted verbatim with line numbers; the canonical command set and keybinds are quoted verbatim from `ctl.py`/`hypr-binds.conf`; the exact test pattern to follow (`test_install_sh_offline_grep_and_summary`) is quoted; and the bash-syntax gate is confirmed working. An agent new to this codebase can apply the three edits from this PRP alone.

### Verified Current State (re-verified — defects ARE present)

**`install.sh` lines 178-179 (verbatim, confirmed):**
```
178: echo "usage  : $REPO/.venv/bin/voicectl toggle|start|stop|status|quit"
179: echo "          (bind SUPER+ALT+D -> voicectl toggle; see the Hyprland note below)"
```
- Line 178: only 5 commands (`toggle|start|stop|status|quit`) — missing `toggle-lite`, `start-lite`.
- Line 179: `SUPER+ALT+D -> voicectl toggle` is WRONG (that bind is toggle-LITE).
- `grep -c 'SUPER+ALT+D -> voicectl toggle' install.sh` = **1** (the wrong hint is present → the negative assertion is RED now, GREEN after the fix = TDD proof).

**Canonical command set — `voice_typing/ctl.py:35`:**
```python
_COMMANDS: tuple[str, ...] = ("toggle", "start", "stop", "status", "quit", "toggle-lite", "start-lite")
```
→ 7 commands. install.sh must list all 7.

**Canonical keybinds — `hypr-binds.conf:5-6` (correct; do NOT edit):**
```
#     CTRL+SUPER+ALT+D -> voicectl toggle       (NORMAL / "big" model: distil-large-v3 + small.en)
#     SUPER+ALT+D      -> voicectl toggle-lite   (LITE / "little" model: small.en only)
```
→ Both binds use key **D** (never F). Normal = CTRL+SUPER+ALT+D; Lite = SUPER+ALT+D. install.sh's hint must match this.

**Test pattern — `tests/test_systemd_unit.py` `test_install_sh_offline_grep_and_summary` (line 200):**
```python
    text = _install_sh_path().read_text()
    assert "HTTP Request: GET https://huggingface.co" in text, ("...")
    assert "no network at runtime" in text, ("...")
```
`_install_sh_path()` (line 61-63) = `Path(__file__).resolve().parent.parent / "install.sh"`. The new test reuses this helper and this exact `read_text()` + substring-assert style.

### Documentation & References

```yaml
# THE DEFECT (authoritative)
- docfile: plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/prd_snapshot.md
  why: §h3.0 Issue 1 documents both defects (5-command usage line; wrong SUPER+ALT+D→toggle hint)
       with the verbatim bad output and the suggested fix.
  critical: "The wrong hint maps SUPER+ALT+D to normal toggle; canonical (hypr-binds.conf:5-6 +
            PRD §4.10) maps SUPER+ALT+D to toggle-LITE and CTRL+SUPER+ALT+D to normal toggle."

# THE FIX SITE
- file: install.sh
  why: The [7/7] onboarding block (lines 173-189). Line 178 = usage; line 179 = bind hint. Both are
        `echo "..."` lines. The block is the user-facing install/usage quick-start (header 21-22).
  pattern: "`echo \"<key>  : <value>\"` lines, aligned colons. Append the two lite commands to the
            existing usage line; rewrite the parenthetical to state BOTH binds."
  gotcha: "The new bind-hint wording's casing MUST match the test's positive assertion exactly —
           prescribe 'Ctrl+Alt+Super+D' (mixed case) and 'Alt+Super+D' in BOTH the edit and the test."

# THE CANONICAL COMMAND SET (source of truth for the 7 commands)
- file: voice_typing/ctl.py
  why: _COMMANDS (line 35) is the authoritative 7-tuple. The usage line must list exactly these.
  critical: "Do NOT edit ctl.py — its _COMMANDS is already correct (Issue 3, the ctl help-text fix,
            is a sibling task T3, not S1). S1 only mirrors the command set into install.sh."

# THE CANONICAL KEYBINDS (source of truth for the binds)
- file: hypr-binds.conf
  why: Lines 5-6 pin CTRL+SUPER+ALT+D->toggle, SUPER+ALT+D->toggle-lite. The hint must match.
  critical: "Do NOT edit hypr-binds.conf — it is CORRECT (the canonical source). S1 only fixes the
            install.sh hint to agree with it."

# THE TEST PATTERN TO FOLLOW
- file: tests/test_systemd_unit.py
  why: _install_sh_path() (61) + test_install_sh_offline_grep_and_summary (200) show the exact
        read_text()+substring-assert idiom and where install.sh static checks live. Add the new
        test right after test_install_sh_offline_grep_and_summary, reusing _install_sh_path().
  pattern: "text = _install_sh_path().read_text(); assert '<sub>' in text, ('<msg>'); and
            assert '<wrong>' not in text, ('<msg>')."
  critical: "The test is STATIC (reads install.sh as text) — no bash exec, no live systemd."

# PRD CONTEXT
- docfile: plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/prd_snapshot.md
  why: §4.8 (7 commands) and §4.10 (CTRL+SUPER+ALT,D / SUPER,ALT,D keybinds) are the spec basis.
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── install.sh                       # [7/7] block @173; usage @178; bind hint @179  ← EDIT (2 lines)
├── voice_typing/ctl.py              # _COMMANDS @35 (7 cmds)  ← READ ONLY (correct; T3 owns help text)
├── hypr-binds.conf                  # binds @5-6 (CTRL+SUPER+ALT+D / SUPER+ALT+D)  ← READ ONLY (correct)
└── tests/test_systemd_unit.py       # _install_sh_path @61; test_install_sh_offline_grep_and_summary @200  ← ADD test
```

### Desired Codebase tree with files to be changed

```bash
install.sh                       # MODIFY: usage line (178) + bind hint (179)
tests/test_systemd_unit.py       # MODIFY: +1 test fn (test_install_sh_usage_lists_all_commands_and_correct_keybinds)
# NO other files. config.toml (T2), ctl.py (T3), daemon.py (T4), README (T5), hypr-binds.conf (correct, leave alone).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — CASING MUST AGREE BETWEEN EDIT AND TEST. The test asserts "Ctrl+Alt+Super+D"
# (mixed case) is present. The install.sh edit MUST use that EXACT casing. hypr-binds.conf uses
# all-caps "CTRL+SUPER+ALT+D"; the PRD/contract suggest mixed-case "Ctrl+Alt+Super+D" for the
# human-readable hint. Pick "Ctrl+Alt+Super+D" (contract wording) and use it in BOTH places.

# CRITICAL #2 — THE NEGATIVE ASSERTION TARGETS THE EXACT WRONG SUBSTRING. Assert
# "SUPER+ALT+D -> voicectl toggle" is ABSENT — NOT that "SUPER+ALT+D" is absent. The corrected
# line legitimately contains "Alt+Super+D -> voicectl toggle-lite" (the LITE bind), so a naive
# "SUPER+ALT+D not in text" or "Super+D not in text" would FALSE-FAIL on the correct lite bind.
# The exact wrong hint is "SUPER+ALT+D -> voicectl toggle" (all caps, maps to plain toggle).

# CRITICAL #3 — hypr-binds.conf IS CORRECT; DO NOT EDIT IT. It is the canonical keybind source.
# Same for ctl.py _COMMANDS (correct). S1 fixes only the install.sh hint to AGREE with them.

# CRITICAL #4 — TDD ORDER. The contract says write the test FIRST, watch it FAIL against the
# unfixed install.sh (proves it catches the bug), THEN edit install.sh and watch it go GREEN.
# The negative assertion is RED right now (grep -c = 1); after the edit it's GREEN.

# GOTCHA #5 — SCOPE. S1 = install.sh + the new test ONLY. Sibling tasks: T2 (config.toml
# lite_model comment SUPER+ALT+F→D), T3 (ctl.py --help lists 7 cmds), T4 (daemon.py toggle_lite
# docstring "F"→"D"), T5 (README sync). Don't pre-empt them.

# GOTCHA #6 — DON'T touch the usage line's "$REPO/.venv/bin/voicectl" prefix or the "|" separators
# beyond appending the two commands. Keep it: toggle|start|stop|status|quit|toggle-lite|start-lite.

# GOTCHA #7 — FULL-PATH DISCIPLINE. Machine aliases python3->uv run. Use .venv/bin/python for the
# pytest gate. `bash -n`/`grep` are fine as-is. No ruff/mypy in this project.
```

## Implementation Blueprint

### Data models and structure

None. This is a two-line `echo` edit in a bash script plus a static-text pytest. No data models, no logic, no config values.

### Implementation Tasks (ordered — TDD: test first, then fix)

```yaml
Task 1: ADD the static-text test (TDD — write first; it is RED against unfixed install.sh).
  - IN tests/test_systemd_unit.py, immediately AFTER test_install_sh_offline_grep_and_summary
    (~line 218), add this function (reuses _install_sh_path(); matches the existing idiom):
        def test_install_sh_usage_lists_all_commands_and_correct_keybinds():
            """install.sh [7/7] onboarding lists ALL 7 commands (PRD §4.8) + the CORRECT keybinds
            (PRD §4.10 / hypr-binds.conf: Ctrl+Alt+Super+D -> toggle [normal], Alt+Super+D ->
            toggle-lite). bugfix Issue 1 (P1.M1.T1.S1). Static read_text check (same pattern as
            test_install_sh_offline_grep_and_summary) — closes the gap that let the wrong hint ship
            (the config drift-guard checks only parsed VALUES, not usage/help strings).
            """
            text = _install_sh_path().read_text()
            # (a) usage line lists all 7 commands (PRD §4.8; ctl.py _COMMANDS).
            assert "toggle-lite" in text, (
                "install.sh usage line omits 'toggle-lite' (PRD §4.8 lists 7 commands)."
            )
            assert "start-lite" in text, (
                "install.sh usage line omits 'start-lite' (PRD §4.8 lists 7 commands)."
            )
            # (b) correct NORMAL keybind is stated (hypr-binds.conf:5; PRD §4.10).
            assert "Ctrl+Alt+Super+D" in text, (
                "install.sh bind hint is missing the correct normal bind 'Ctrl+Alt+Super+D' "
                "(PRD §4.10: CTRL+SUPER+ALT+D -> voicectl toggle)."
            )
            # (c) correct LITE keybind is stated and mapped to toggle-lite.
            assert "Alt+Super+D -> voicectl toggle-lite" in text, (
                "install.sh bind hint is missing the correct lite bind "
                "'Alt+Super+D -> voicectl toggle-lite' (hypr-binds.conf:6)."
            )
            # (d) the WRONG mapping is gone. 'SUPER+ALT+D -> voicectl toggle' claimed the LITE bind
            #     (SUPER+ALT+D) maps to normal toggle — backwards. Exact-substring check so the
            #     legitimate 'Alt+Super+D -> voicectl toggle-lite' does NOT trip it.
            assert "SUPER+ALT+D -> voicectl toggle" not in text, (
                "install.sh still claims 'SUPER+ALT+D -> voicectl toggle' — WRONG: SUPER+ALT+D is "
                "the LITE bind (toggle-lite); normal toggle is Ctrl+Alt+Super+D (PRD §4.10)."
            )
  - RUN it against the UNFIXED install.sh and confirm it FAILS (TDD red):
        .venv/bin/python -m pytest tests/test_systemd_unit.py -v -k install_sh_usage
    # Expected before Task 2: FAIL on the 'toggle-lite'/'Ctrl+Alt+Super+D'/wrong-mapping asserts.

Task 2: EDIT install.sh line 178 — usage line lists all 7 commands.
  - FIND:
        echo "usage  : $REPO/.venv/bin/voicectl toggle|start|stop|status|quit"
  - REPLACE WITH (append |toggle-lite|start-lite; keep the prefix + separators intact):
        echo "usage  : $REPO/.venv/bin/voicectl toggle|start|stop|status|quit|toggle-lite|start-lite"

Task 3: EDIT install.sh line 179 — correct two-bind hint.
  - FIND:
        echo "          (bind SUPER+ALT+D -> voicectl toggle; see the Hyprland note below)"
  - REPLACE WITH (BOTH binds, CORRECT mapping; casing 'Ctrl+Alt+Super+D' / 'Alt+Super+D' MUST match
    the test's assertions — Gotcha #1):
        echo "          (bind Ctrl+Alt+Super+D -> voicectl toggle;  Alt+Super+D -> voicectl toggle-lite; see the Hyprland note below)"

Task 4: VALIDATE — re-run the test (now GREEN), bash -n, and the full test_systemd_unit.py (no
  regressions). No git commit unless the orchestrator directs it. If asked, message:
  "P1.M1.T1.S1: fix install.sh usage (7 cmds) + keybind hint (Ctrl+Alt+Super+D / Alt+Super+D) + test".
```

### Implementation Patterns & Key Details

```bash
# The whole task is two echo-line edits + one static-text test. Correctness rests on ONE invariant:
# the bind-hint wording in install.sh and the substring asserts in the test use IDENTICAL casing.
#
# Canonical sources (do NOT edit, just agree with):
#   ctl.py:35          _COMMANDS = (toggle, start, stop, status, quit, toggle-lite, start-lite)  # 7
#   hypr-binds.conf:5  CTRL+SUPER+ALT+D -> voicectl toggle        # NORMAL
#   hypr-binds.conf:6  SUPER+ALT+D      -> voicectl toggle-lite   # LITE
#
# Why the negative assert is "SUPER+ALT+D -> voicectl toggle" (exact) and not "SUPER+ALT+D":
# the corrected line legitimately contains "Alt+Super+D -> voicectl toggle-lite". The exact wrong
# substring is "SUPER+ALT+D -> voicectl toggle" (all caps, plain toggle) — absent after the fix.
#
# TDD proof: grep -c 'SUPER+ALT+D -> voicectl toggle' install.sh is 1 NOW (red), 0 AFTER (green).
```

### Integration Points

```yaml
INSTALL.SH ONBOARDING ([7/7] block):
  - The usage line (178) and bind hint (179) are the user's first post-install reference. With the
    fix they agree with ctl.py _COMMANDS (7) and hypr-binds.conf (correct binds). The later
    `source = .../hypr-binds.conf` instruction (install.sh line ~186) was already correct and is
    unchanged.

CANONICAL SOURCES (read-only — S1 makes install.sh agree with them):
  - voice_typing/ctl.py:35 _COMMANDS — 7 commands. (ctl.py's OWN --help text omitting lite cmds is
    Issue 3 / sibling task T3, NOT S1.)
  - hypr-binds.conf:5-6 — correct binds. (config.toml's lite_model comment saying SUPER+ALT+F is
    Issue 2 / sibling task T2, NOT S1.)

TEST SUITE:
  - The new test joins the install.sh static-check group in tests/test_systemd_unit.py alongside
    test_install_sh_offline_grep_and_summary. It is a pure read_text() check — no bash exec, no
    live systemd, fast (<0.1s). It permanently guards the usage-line command set + the bind hint.
```

## Validation Loop

> Full paths for python (machine aliases python3->uv run). No ruff/mypy. The new test (L2) is the
> load-bearing gate; run it once BEFORE the install.sh edit to confirm RED (TDD), then after to
> confirm GREEN.

### Level 1: The two install.sh edits landed correctly (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- usage line lists 7 commands ---"
grep -c 'toggle|start|stop|status|quit|toggle-lite|start-lite' install.sh | grep -q '^1$' && echo "L1a PASS" || echo "L1a FAIL"
echo "--- correct binds present ---"
grep -q 'Ctrl+Alt+Super+D -> voicectl toggle' install.sh && echo "L1b PASS (normal bind)" || echo "L1b FAIL"
grep -q 'Alt+Super+D -> voicectl toggle-lite' install.sh && echo "L1c PASS (lite bind)" || echo "L1c FAIL"
echo "--- WRONG mapping gone ---"
grep -q 'SUPER+ALT+D -> voicectl toggle' install.sh && echo "L1d FAIL: wrong hint still present" || echo "L1d PASS (wrong hint removed)"
echo "--- bash syntax OK ---"
bash -n install.sh && echo "L1e PASS (bash -n)" || echo "L1e FAIL"
# Expected: L1a–L1e PASS. (L1d: grep -q finds nothing → the && branch is skipped → the || prints PASS.)
```

### Level 2: The new test passes (and was RED before the fix — TDD)

```bash
cd /home/dustin/projects/voice-typing
echo "--- (TDD red, BEFORE the install.sh edit) the test should have FAILED pre-fix ---"
echo "--- (now, AFTER Tasks 2-3) it must PASS ---"
.venv/bin/python -m pytest tests/test_systemd_unit.py -v -k "install_sh_usage" 2>&1 | tail -6
# Expected: 1 passed: test_install_sh_usage_lists_all_commands_and_correct_keybinds.
# (To confirm TDD red→green: `git stash` the install.sh edit only, re-run → FAIL; `git stash pop` → PASS.)
```

### Level 3: No regression in the install.sh/systemd static-check group

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_systemd_unit.py -v 2>&1 | tail -20
# Expected: all PASS (the existing install.sh + launch_daemon.sh + unit tests stay green; the new
# test is an addition). If test_install_sh_offline_grep_and_summary or any unit test fails, the
# install.sh edit accidentally touched the wrong line — re-read the diff.
```

### Level 4: Scope — only install.sh + tests/test_systemd_unit.py changed

```bash
cd /home/dustin/projects/voice-typing
echo "--- git diff touches ONLY install.sh + tests/test_systemd_unit.py ---"
git diff --name-only
git diff --name-only | grep -vE 'install\.sh|tests/test_systemd_unit\.py' | grep -E '\.sh$|\.py$|\.toml$|\.conf$|\.md$' && echo "L4 FAIL: out-of-scope file" || echo "L4 PASS: only install.sh + test_systemd_unit.py"
echo "--- confirm canonical sources UNTOUCHED (they were already correct) ---"
git diff --name-only | grep -E 'hypr-binds\.conf|voice_typing/ctl\.py|config\.toml|voice_typing/daemon\.py' && echo "L4 FAIL: canonical source edited" || echo "L4 PASS: canonical sources untouched"
# Expected: "only install.sh + test_systemd_unit.py" + "canonical sources untouched".
```

## Final Validation Checklist

### Technical Validation
- [ ] L1a: usage line lists all 7 commands (`toggle|start|stop|status|quit|toggle-lite|start-lite`).
- [ ] L1b/L1c: correct normal bind (`Ctrl+Alt+Super+D -> voicectl toggle`) + lite bind (`Alt+Super+D -> voicectl toggle-lite`) present.
- [ ] L1d: wrong mapping `SUPER+ALT+D -> voicectl toggle` absent.
- [ ] L1e: `bash -n install.sh` passes.
- [ ] L2: new test PASSES (and was RED before the install.sh edit — TDD).
- [ ] L3: full `tests/test_systemd_unit.py` green (no regression).
- [ ] L4: only `install.sh` + `tests/test_systemd_unit.py` changed; canonical sources untouched.

### Feature Validation
- [ ] install.sh `[7/7]` onboarding lists all 7 commands and states both correct keybinds.
- [ ] The printed hint no longer mis-maps `SUPER+ALT+D` to normal toggle.
- [ ] The usage line + bind hint now agree with `ctl.py _COMMANDS` and `hypr-binds.conf`.

### Code Quality Validation
- [ ] Casing in the install.sh edit (`Ctrl+Alt+Super+D`/`Alt+Super+D`) exactly matches the test's asserts.
- [ ] New test follows the existing `test_install_sh_offline_grep_and_summary` idiom (`read_text` + substring asserts with messages).
- [ ] Usage-line prefix (`$REPO/.venv/bin/voicectl`) and separators (`|`) preserved.

### Scope Boundary Validation
- [ ] `hypr-binds.conf` unmodified (correct canonical source).
- [ ] `voice_typing/ctl.py` unmodified (T3 owns its help text).
- [ ] `config.toml` unmodified (T2 owns the lite_model keybind comment).
- [ ] `voice_typing/daemon.py` unmodified (T4 owns the toggle_lite docstring).
- [ ] `README.md` unmodified (T5 owns the README sync).

---

## Anti-Patterns to Avoid

- ❌ Don't use a naive `assert "SUPER+ALT+D" not in text` — the corrected line legitimately contains "Alt+Super+D -> voicectl toggle-lite". Assert the EXACT wrong substring `"SUPER+ALT+D -> voicectl toggle"` is absent.
- ❌ Don't mismatch casing between the install.sh edit and the test — both must use `Ctrl+Alt+Super+D` (mixed case) verbatim, or the positive assert false-fails.
- ❌ Don't edit `hypr-binds.conf` or `ctl.py _COMMANDS` — both are already correct; S1 only makes install.sh agree with them.
- ❌ Don't fix the sibling defects here — config.toml's `SUPER+ALT+F` (T2), ctl.py's `--help` (T3), daemon.py's "pressing F" docstring (T4), README (T5) are separate subtasks.
- ❌ Don't restructure the `[7/7]` block or "align" other echo lines — two line edits only; keep the diff minimal.
- ❌ Don't skip the TDD red step — run the new test against the UNFIXED install.sh first to prove it catches the bug (the negative assert is red right now, count=1).
- ❌ Don't invoke ruff/mypy — not configured; the gates are `bash -n` + pytest.

---

## Confidence Score

**9.5/10** for one-pass implementation success. The change is two `echo`-line edits at verified lines (178-179) plus one static-text test following a verified existing pattern (`test_install_sh_offline_grep_and_summary` + `_install_sh_path()`). The TDD red→green is concretely demonstrable (`grep -c 'SUPER+ALT+D -> voicectl toggle' install.sh` is 1 now, 0 after). The canonical sources (ctl.py:35, hypr-binds.conf:5-6) are quoted verbatim, and `bash -n` is confirmed working. The −0.5 is the casing-alignment caveat (edit and test must use identical casing) — mitigated by Gotcha #1 prescribing the exact wording in both places.
