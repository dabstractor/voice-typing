# PRP — P1.M1.T2.S1: Correct `SUPER+ALT+F` → `SUPER+ALT+D` in the `lite_model` comment

## Goal

**Feature Goal**: Fix bugfix **Issue 2** (Minor doc defect): `config.toml:34`'s user-facing `lite_model` comment names the **wrong** lite-mode keybind letter — `SUPER+ALT+F` (key **F**) — but **F is not bound anywhere**. The correct lite bind is `SUPER+ALT+D` (key **D**), per `hypr-binds.conf:6`/`:44` (`bind = SUPER ALT, D, exec, …/voicectl toggle-lite`) and PRD §4.10. A user reading `config.toml` to learn the lite hotkey would press F and nothing would happen. This subtask corrects the single letter and adds a TDD static-text test so the drift cannot recur (the existing value drift-guards parse via `tomllib`, which **drops comments**, so they never catch this).

**Deliverable** (two files edited, no new files):
1. `config.toml` line 34 — change `SUPER+ALT+F` → `SUPER+ALT+D` **inside the `lite_model` comment** (keep all surrounding comment text + the value `"small.en"` byte-identical).
2. `tests/test_config_repo_default.py` — add `test_repo_config_lite_model_comment_names_correct_keybind`: reads `config.toml` as **raw text**, finds the `lite_model` line, asserts it contains `SUPER+ALT+D` and NOT the stale `SUPER+ALT+F`.

**Success Definition**:
- (a) `grep -n 'SUPER+ALT' config.toml` returns exactly one match, on the `lite_model` line, reading `SUPER+ALT+D` (no `F`).
- (b) `config.toml` still parses as valid TOML; `VoiceTypingConfig.from_toml_file(_repo_config_path()) == VoiceTypingConfig()` still holds (the VALUE is unchanged — only a comment token changed).
- (c) The new test is **RED before** the config.toml edit (it currently has `SUPER+ALT+F`) and **GREEN after** (TDD red→green).
- (d) `.venv/bin/python -m pytest tests/test_config_repo_default.py -v` → 0 failures (the 2 existing drift-guards + the 1 new test).
- (e) `git diff --name-only` == `config.toml` + `tests/test_config_repo_default.py`.

## User Persona

**Target User**: The end user who opens `config.toml` to discover/tune the lite-mode hotkey (this file is *both* the runtime default *and* the user-facing config doc — Mode A). A wrong letter here sends them to a dead key.

**Use Case**: User scans the `[asr]` section, reads the `lite_model` comment to learn how to invoke lite mode, presses the named keybind. After the fix they press `SUPER+ALT+D` (the real bind) and lite mode arms.

**Pain Points Addressed**: Issue 2 — the comment's `SUPER+ALT+F` is a thinko (F is unbound); the real lite bind is `SUPER+ALT+D`. It actively misleads the user.

## Why

- **PRD §4.10 is the source of truth.** It pins the binds: `Ctrl+Alt+Super+D → toggle` (normal) and `Alt+Super+D → toggle-lite` (lite). `hypr-binds.conf:6`/`:44` implement exactly that (`SUPER ALT, D → toggle-lite`). The `config.toml` comment's `SUPER+ALT+F` contradicts both — F appears in no bind anywhere.
- **User-facing doc (Mode A).** `config.toml` is the file users edit to tune the daemon; its comments ARE the tuning docs. A wrong keybind letter here is not an internal typo — it sends a user to a dead key.
- **Why it slipped past tests.** The two existing drift-guards (`test_repo_config_toml_equals_defaults`, `test_repo_config_toml_has_no_extra_keys`) parse `config.toml` via `tomllib`, which **discards comments**. So a wrong keybind letter in a comment is invisible to them. The new test reads the **raw text** and asserts the comment substring, closing that gap permanently.
- **Scope discipline.** T2.S1 owns ONLY `config.toml` + `tests/test_config_repo_default.py`. It does NOT touch `hypr-binds.conf` (already correct), `install.sh` (P1.M1.T1.S1 owns the install-onboarding hint), `ctl.py` help text (P1.M1.T3), `daemon.py` `toggle_lite` docstring (P1.M1.T4), or README (P1.M1.T5). One letter + one test.

## What

Edit one comment token on one line of `config.toml` + add one raw-text static test. No value change, no schema change, no behavior change.

### Success Criteria

- [ ] `config.toml:34` `lite_model` comment reads `… LITE mode (\`voicectl toggle-lite\` / SUPER+ALT+D) …` (D, not F).
- [ ] `config.toml:34` value is still `lite_model = "small.en"` (unchanged).
- [ ] No other `SUPER+ALT+F` occurrence anywhere in `config.toml` (`grep -c 'SUPER+ALT+F' config.toml` == 0).
- [ ] `config.toml` still parses; `from_toml_file(_repo_config_path()) == VoiceTypingConfig()` holds.
- [ ] New `test_repo_config_lite_model_comment_names_correct_keybind` passes; it is RED before the config.toml edit (TDD).
- [ ] `.venv/bin/python -m pytest tests/test_config_repo_default.py -v` → 0 failures.
- [ ] `git diff --name-only` == `config.toml` + `tests/test_config_repo_default.py`.

## All Needed Context

### Context Completeness Check

_Pass._ The exact defect line (verbatim), the exact replacement (one token: `F`→`D`), the source of truth (`hypr-binds.conf:6`/`:44` + PRD §4.10), the test-file path helper (`_repo_config_path`, already imported), the reason the existing drift-guards miss it (tomllib drops comments), and the no-conflict boundary with the parallel T1.S1 are all verified below with line citations. An agent new to this repo can apply the fix from this PRP alone.

### Documentation & References

```yaml
# THE DEFECT (verbatim) — the line under fix
- file: config.toml
  why: Line 34 (the lite_model line) comment contains 'SUPER+ALT+F'. Verbatim current text:
       'lite_model = "small.en"  # PRD §4.2ter: the SINGLE model loaded in LITE mode (`voicectl
       toggle-lite` / SUPER+ALT+F) — used for both partials AND finals …'. The F is the thinko.
  pattern: "Change the single token SUPER+ALT+F -> SUPER+ALT+D inside the comment. Do NOT touch the
            value ('small.en'), the comment's other text, or the em-dash/alignment."
  gotcha: "config.toml uses an em-dash (—, UTF-8). Edit ONLY the keybind token; preserve the rest of
           the line byte-for-byte so no alignment/encoding drifts."

# THE SOURCE OF TRUTH — the correct keybind
- file: hypr-binds.conf
  why: Line 6 'SUPER+ALT+D -> voicectl toggle-lite (LITE / "little" model)' + line 44
       'bind = SUPER ALT, D, exec, …/voicectl toggle-lite'. The lite bind is SUPER+ALT+D (key D, no
       Ctrl). PRD §4.10 pins the same. So config.toml's lite_model comment must say SUPER+ALT+D.
  critical: "The lite bind is SUPER+ALT+D (Super+Alt+D, NO Ctrl). The NORMAL bind is Ctrl+Super+Alt+D
            (with Ctrl). Do NOT write Ctrl+Super+Alt+D for the lite comment — that is the normal bind.
            SUPER+ALT+D matches the existing SUPER+ALT+F format with just F->D (the minimal change)."

# THE TEST FILE — path helper + the value-drift-guard patterns (the gap this test fills)
- file: tests/test_config_repo_default.py
  why: Imports `_repo_config_path` from voice_typing.config (line 14) — reuse it to locate config.toml.
       test_repo_config_toml_equals_defaults (L17) + test_repo_config_toml_has_no_extra_keys (L27)
       BOTH parse via tomllib, which DROPS comments — so neither catches a wrong keybind letter in a
       comment. The new test reads the RAW TEXT (not tomllib) to assert the comment substring.
  pattern: "Read _repo_config_path() as text; filter splitlines() for the line starting with
            'lite_model'; assert 'SUPER+ALT+D' in it AND 'SUPER+ALT+F' not in it. Mirror the file's
            existing open(_repo_config_path(), …) style (L40)."
  critical: "tomllib.load() CANNOT be used for this assertion — it discards comments. MUST read the
            file as TEXT and substring-match. Scope the assertion to the lite_model LINE (not the whole
            file) so a future SUPER+ALT+D elsewhere can't mask a regression on this line."

# THE MANDATE (the bug report)
- docfile: plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/prd_snapshot.md
  why: §Issue 2 documents the defect (config.toml:34 SUPER+ALT+F), the repro (grep), and the fix
       (SUPER+ALT+F -> SUPER+ALT+D). Cite in the test docstring.
  critical: "The fix is a single token; the regression guard is the new raw-text test (the value
            drift-guards cannot catch comment drift)."

# THE PARALLEL ITEM (no-conflict boundary)
- docfile: plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/P1M1T1S1/PRP.md
  why: T1.S1 (parallel) fixes install.sh's [7/7] onboarding hint (Ctrl+Alt+Super+D normal / Alt+Super+D
       lite) + adds a test in tests/test_systemd_unit.py. It explicitly states 'sibling tasks own
       config.toml/ctl.py/daemon.py/README.' T2.S1 owns config.toml + tests/test_config_repo_default.py.
  critical: "No file overlap. T1.S1 = install.sh + test_systemd_unit.py; T2.S1 = config.toml +
            test_config_repo_default.py. NOTE: T1.S1 asserts the WRONG mapping 'SUPER+ALT+D -> voicectl
            toggle' is GONE from install.sh (because SUPER+ALT+D is lite, not normal, in install.sh's
            context). In config.toml's lite_model comment, SUPER+ALT+D IS correct (it's the lite bind).
            These do NOT conflict — different files, different contexts."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── config.toml                       # ← EDIT line 34 (lite_model comment: SUPER+ALT+F -> SUPER+ALT+D).
│   #                                   Value + all other comment text unchanged.
├── hypr-binds.conf                   # READ-ONLY source of truth (line 6 + 44: SUPER+ALT+D = toggle-lite).
└── tests/
    └── test_config_repo_default.py   # ← EDIT (+1 raw-text test). _repo_config_path imported L14.
                                      #   Existing tests parse via tomllib (drop comments) — the gap.
```

### Desired Codebase tree with files to be changed

```bash
config.toml                       # MODIFY: line 34 comment token SUPER+ALT+F -> SUPER+ALT+D. Value unchanged.
tests/test_config_repo_default.py # MODIFY: +test_repo_config_lite_model_comment_names_correct_keybind (raw-text assert).
# No hypr-binds.conf / install.sh / daemon.py / ctl.py / README changes (sibling subtasks / already correct).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — TOMLLIB DROPS COMMENTS. The two existing drift-guards parse config.toml via
# tomllib.load(), which discards ALL comments. So they CANNOT detect a wrong keybind letter in a
# comment. The new test MUST read the file as RAW TEXT (open().read() / splitlines) and substring-
# match — NOT tomllib. This is the entire reason the bug shipped undetected.

# CRITICAL #2 — SCOPE THE ASSERTION TO THE lite_model LINE. config.toml may gain other SUPER+ALT+D
# mentions later (e.g. another comment). Assert on the line whose lstrip() starts with 'lite_model'
# (filter splitlines), not the whole file — so the test pins THIS comment specifically. Also assert
# 'SUPER+ALT+F' is ABSENT from that line (the regression signal), not just that 'SUPER+ALT+D' is present.

# CRITICAL #3 — SUPER+ALT+D IS THE LITE BIND (no Ctrl); Ctrl+Super+Alt+D is NORMAL. Do NOT write
# Ctrl+Super+Alt+D in the lite_model comment — that is the normal/big-model bind (hypr-binds.conf:5).
# The minimal, correct change is F->D keeping the existing 'SUPER+ALT+D' format (matches hypr-binds.conf:6).
# (Contrast with the parallel T1.S1, which REMOVES a wrong 'SUPER+ALT+D -> toggle' from install.sh —
# different file, different context; no conflict.)

# CRITICAL #4 — PRESERVE THE REST OF THE LINE BYTE-FOR-BYTE. config.toml:34's comment has an em-dash
# (—, UTF-8) + careful alignment. Edit ONLY the single token 'SUPER+ALT+F' -> 'SUPER+ALT+D'. Do NOT
# reflow the comment, change the value, or touch the alignment — the value drift-guard
# (test_repo_config_toml_equals_defaults) must still pass (it does: only a comment token changed).

# GOTCHA #5 — REUSE _repo_config_path(). The test file already imports it (L14:
# 'from voice_typing.config import VoiceTypingConfig, _repo_config_path'). Use _repo_config_path() to
# locate config.toml — do NOT hardcode a path or re-derive the repo root. open(_repo_config_path()) in
# text mode reads the UTF-8 file (em-dash included) cleanly on Linux.

# GOTCHA #6 — TDD: TEST IS RED BEFORE THE FIX. The current config.toml has SUPER+ALT+F, so the new
# test's 'SUPER+ALT+D in line' assertion FAILS on the current tree (RED). Write the test FIRST, confirm
# RED, then apply the one-token config.toml fix -> GREEN. (The validation loop encodes this order.)

# GOTCHA #7 — DON'T TOUCH SIBLING SURFACES. hypr-binds.conf is already correct (source of truth).
# install.sh's hint is P1.M1.T1.S1's job; ctl.py help is P1.M1.T3; daemon.py toggle_lite docstring
# ('pressing F' -> 'pressing D', Issue 4) is P1.M1.T4; README is P1.M1.T5. T2.S1 = config.toml comment
# + its test ONLY.

# GOTCHA #8 — FULL PATHS. `.venv/bin/python -m pytest` (machine aliases python3 -> uv run). No
# ruff/mypy configured — don't invoke them.
```

## Implementation Blueprint

### Data models and structure

None. No ORM/pydantic/dataclass/TOML-value change. The only "structure" is one comment token (`F`→`D`) and one raw-text pytest assertion.

### Implementation Tasks (ordered by dependencies — TDD: test first, then fix)

```yaml
Task 1: ADD tests/test_config_repo_default.py — the raw-text regression test (write FIRST; it is RED now)
  - PLACE: after test_repo_config_toml_has_no_extra_keys (ends ~L53), the natural home for config.toml
    text assertions.
  - ADD EXACTLY this test (reuses the file's existing _repo_config_path import; no new imports needed):
        def test_repo_config_lite_model_comment_names_correct_keybind():
            """The lite_model comment must name SUPER+ALT+D (the real lite bind), not the stale SUPER+ALT+F.

            config.toml is user-facing config DOC (Mode A); a wrong keybind letter sends users to a dead
            key (F is unbound). tomllib DROPS comments, so the value drift-guards above don't catch this —
            assert on the RAW text. Source of truth: hypr-binds.conf `bind = SUPER ALT, D, ... toggle-lite`
            (PRD §4.10). (bugfix Issue 2.)
            """
            with open(_repo_config_path()) as fh:
                text = fh.read()
            lite_lines = [ln for ln in text.splitlines() if ln.lstrip().startswith("lite_model")]
            assert lite_lines, "no lite_model line in config.toml"
            line = lite_lines[0]
            assert "SUPER+ALT+D" in line, (
                "config.toml lite_model comment must reference SUPER+ALT+D (the lite keybind, PRD §4.10 / "
                "hypr-binds.conf), not a stale letter (Issue 2)."
            )
            assert "SUPER+ALT+F" not in line, "config.toml lite_model comment still has the stale SUPER+ALT+F"
  - CONSTRAINTS:
      * Read via open(_repo_config_path()) in TEXT mode (CRITICAL #1 — NOT tomllib; comments must survive).
      * Scope to the lite_model line (CRITICAL #2 — filter splitlines by lstrip().startswith).
      * Assert BOTH 'SUPER+ALT+D' in line AND 'SUPER+ALT+F' not in line.
      * Reuse _repo_config_path (L14 import); no new imports.
  - EXPECTED ON CURRENT TREE: the test FAILS (RED) — config.toml:34 currently has SUPER+ALT+F, so the
    'SUPER+ALT+D in line' assert fails. This is the TDD red state; Task 2 turns it green.

Task 2: MODIFY config.toml — change SUPER+ALT+F -> SUPER+ALT+D in the lite_model comment (line 34)
  - FIND line 34 (the lite_model line). Its comment currently contains the substring:
        `LITE mode (\`voicectl toggle-lite\` / SUPER+ALT+F) —`
  - EDIT: change ONLY that token:
        `LITE mode (\`voicectl toggle-lite\` / SUPER+ALT+D) —`
  - The full line after the edit (value + all other comment text unchanged):
        lite_model                   = "small.en"          # PRD §4.2ter: the SINGLE model loaded in LITE mode (`voicectl toggle-lite` / SUPER+ALT+D) — used for both partials AND finals, so the large model never loads. ~half the VRAM + faster finals, lower accuracy. Good for short quips/prompts where the big model's latency isn't worth it.
  - WHY: SUPER+ALT+D is the lite bind (hypr-binds.conf:6/:44; PRD §4.10). F is unbound. (CRITICAL #3/#4.)
  - DO NOT: change the value, reflow the comment, touch the em-dash/alignment, or edit any other line.

Task 3: VALIDATE — run the Validation Loop L1–L3 (TDD red->green + no regression + scope). No git commit
  unless the orchestrator directs it. If asked, message:
  "P1.M1.T2.S1: correct config.toml lite_model keybind comment SUPER+ALT+F -> SUPER+ALT+D (Issue 2)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — raw-text assertion (the gap-filler). The value drift-guards use tomllib, which DROPS
# comments. To assert on a COMMENT substring, read the file as TEXT and substring-match:
with open(_repo_config_path()) as fh:          # text mode (UTF-8; em-dash survives)
    text = fh.read()
lite_lines = [ln for ln in text.splitlines() if ln.lstrip().startswith("lite_model")]
line = lite_lines[0]
assert "SUPER+ALT+D" in line and "SUPER+ALT+F" not in line

# PATTERN 2 — minimal token edit. The fix is one token (F->D) inside an existing comment, preserving
# the line's value, alignment, em-dash, and all other text. The value drift-guard
# (from_toml_file == VoiceTypingConfig()) stays green because only a COMMENT changed.
```

### Integration Points

```yaml
TEST SUITE:
  - The new test joins the 2 existing in tests/test_config_repo_default.py. Run:
    `.venv/bin/python -m pytest tests/test_config_repo_default.py -v` -> 0 failures (3 tests).
    T2.S1 only ADDS a test + edits a comment, so no existing test can regress (the value drift-guards
    parse values, untouched by a comment-token change).

SOURCE OF TRUTH (do NOT edit here):
  - hypr-binds.conf:6/:44 — SUPER+ALT+D = toggle-lite (the canonical lite bind). READ-ONLY.
  - PRD §4.10 — pins both binds. READ-ONLY.

NO INTERFACE / BEHAVIOR CHANGES:
  - config.toml VALUE unchanged (only a comment token). The daemon loads identically before/after.
  - No daemon.py / ctl.py / recorder_host.py / systemd / install.sh changes.

SIBLING BOUNDARY (no conflict):
  - P1.M1.T1.S1 (parallel) = install.sh + tests/test_systemd_unit.py (the onboarding hint).
  - P1.M1.T3 = ctl.py help text. P1.M1.T4 = daemon.py toggle_lite docstring. P1.M1.T5 = README.
  - T2.S1 = config.toml comment + tests/test_config_repo_default.py. Distinct files; no overlap.
```

## Validation Loop

> Full paths (machine aliases python3→uv run). All gates are FAST + hermetic — no GPU/models/daemon/network.
> No ruff/mypy configured. Run from `/home/dustin/projects/voice-typing`.

### Level 1: TDD red — the new test FAILS on the current (unfixed) tree

```bash
cd /home/dustin/projects/voice-typing
echo "--- L1a: the new test is discovered ---"
.venv/bin/python -m pytest tests/test_config_repo_default.py --collect-only -q | grep -q test_repo_config_lite_model_comment_names_correct_keybind \
  && echo "L1a PASS: test collected" || echo "L1a FAIL: test missing"
echo "--- L1b: confirm the defect is still present (RED prerequisite) ---"
grep -q 'SUPER+ALT+F' config.toml && echo "L1b: config.toml still has SUPER+ALT+F (expected RED state)" || echo "L1b NOTE: config.toml already fixed — Task 2 may have run"
echo "--- L1c: run the new test ALONE on the current tree (expect FAIL if Task 2 not yet done) ---"
.venv/bin/python -m pytest tests/test_config_repo_default.py::test_repo_config_lite_model_comment_names_correct_keybind -v 2>&1 | tail -6
# Expected (TDD red, BEFORE Task 2): the test FAILS — 'assert "SUPER+ALT+D" in line' fails because the
# line still has SUPER+ALT+F. This confirms the test ACTUALLY guards (not vacuous). If it PASSES before
# the fix, config.toml was already corrected — re-check the assertion logic (CRITICAL #1/#2).
```

### Level 2: TDD green — after the config.toml fix, the new test PASSES + the value drift-guards hold

```bash
cd /home/dustin/projects/voice-typing
echo "--- L2a: the fix landed (SUPER+ALT+F gone, SUPER+ALT+D present on the lite_model line) ---"
grep -c 'SUPER+ALT+F' config.toml | grep -qx '0' && echo "L2a PASS: no SUPER+ALT+F anywhere" || echo "L2a FAIL: SUPER+ALT+F remains"
lite_line=$(grep -n 'lite_model' config.toml | head -1)
echo "$lite_line" | grep -q 'SUPER+ALT+D' && echo "L2b PASS: lite_model line has SUPER+ALT+D" || echo "L2b FAIL"
echo "--- L2c: the new test is now GREEN ---"
.venv/bin/python -m pytest tests/test_config_repo_default.py::test_repo_config_lite_model_comment_names_correct_keybind -v 2>&1 | tail -4
echo "--- L2d: config.toml still parses + value drift-guard holds (only a comment changed) ---"
.venv/bin/python -c "from voice_typing.config import VoiceTypingConfig, _repo_config_path; assert VoiceTypingConfig.from_toml_file(_repo_config_path()) == VoiceTypingConfig(); print('L2d PASS: config.toml parses == defaults')"
# Expected: 0 SUPER+ALT+F; lite_model line has SUPER+ALT+D; new test PASSES; config.toml == defaults.
```

### Level 3: No regression + scope clean

```bash
cd /home/dustin/projects/voice-typing
echo "--- L3a: full repo-default suite green ---"
.venv/bin/python -m pytest tests/test_config_repo_default.py -v 2>&1 | tail -6
echo "--- L3b: broader sanity (config suite) green ---"
.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q 2>&1 | tail -3
echo "--- L3c: scope — ONLY config.toml + test_config_repo_default.py changed ---"
git diff --name-only | grep -vxE 'config.toml|tests/test_config_repo_default.py' && echo "L3c FAIL: out-of-scope file changed" || echo "L3c PASS: only config.toml + test_config_repo_default.py"
git diff --quiet hypr-binds.conf install.sh voice_typing/daemon.py voice_typing/ctl.py README.md \
  && echo "L3c PASS: sibling/source files unchanged" || echo "L3c FAIL: a sibling file was modified"
# Expected: repo-default suite 0 failures; config suite green; diff = config.toml + test_config_repo_default.py;
# hypr-binds.conf/install.sh/daemon.py/ctl.py/README.md unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: new test collected; defect still present (RED prerequisite); new test FAILS on the unfixed tree (TDD red — proves it guards).
- [ ] L2: 0 `SUPER+ALT+F` in config.toml; lite_model line has `SUPER+ALT+D`; new test PASSES (green); config.toml parses == defaults (value drift-guard holds).
- [ ] L3: repo-default suite + config suite green; diff = `config.toml` + `tests/test_config_repo_default.py`; sibling/source files unchanged.

### Feature Validation
- [ ] `config.toml:34` `lite_model` comment names `SUPER+ALT+D` (the lite bind), not `SUPER+ALT+F`.
- [ ] The value `lite_model = "small.en"` is unchanged; the rest of the comment is byte-identical.
- [ ] The new test reads RAW TEXT (not tomllib) + is scoped to the lite_model line.
- [ ] The test is RED before the fix and GREEN after (TDD).

### Code Quality Validation
- [ ] New test reuses `_repo_config_path` (no hardcoded path, no new imports).
- [ ] New test asserts BOTH presence of `SUPER+ALT+D` AND absence of `SUPER+ALT+F`.
- [ ] New test docstring cites Issue 2 + PRD §4.10 + hypr-binds.conf as the source of truth.
- [ ] Only one comment token changed in config.toml (value/alignment/em-dash preserved).

### Scope Boundary Validation
- [ ] `hypr-binds.conf` unmodified (source of truth; already correct).
- [ ] `install.sh` unmodified (P1.M1.T1.S1 owns it).
- [ ] `voice_typing/daemon.py` (`toggle_lite` docstring, Issue 4) unmodified (P1.M1.T4).
- [ ] `voice_typing/ctl.py` (help text, Issue 3) unmodified (P1.M1.T3).
- [ ] `README.md` unmodified (P1.M1.T5).
- [ ] PRD.md, tasks.json, prd_snapshot.md, .gitignore NOT modified.

### Documentation & Deployment
- [ ] Mode A: the corrected `config.toml` comment IS the doc update (config.toml is user-facing config doc). No separate docs subtask.
- [ ] If asked to commit: message references Issue 2 + the SUPER+ALT+F→D correction for traceability.

---

## Anti-Patterns to Avoid

- ❌ Don't use `tomllib` for the test assertion — it **drops comments**, so it cannot see the keybind letter (that's why the bug shipped). Read the file as **raw text** (CRITICAL #1).
- ❌ Don't assert on the whole file — scope to the `lite_model` line (filter `splitlines` by `lstrip().startswith("lite_model")`) so a future `SUPER+ALT+D` elsewhere can't mask a regression here (CRITICAL #2). Assert both presence of `D` AND absence of `F`.
- ❌ Don't write `Ctrl+Super+Alt+D` in the lite comment — that's the NORMAL bind. The lite bind is `SUPER+ALT+D` (no Ctrl). The minimal correct change is `F`→`D` keeping the existing format (CRITICAL #3).
- ❌ Don't reflow the comment, change the value, or touch the em-dash/alignment — edit ONLY the `SUPER+ALT+F`→`SUPER+ALT+D` token so the value drift-guard stays green (CRITICAL #4).
- ❌ Don't edit `hypr-binds.conf` (it's the correct source of truth), `install.sh` (P1.M1.T1.S1), `daemon.py` (P1.M1.T4), `ctl.py` (P1.M1.T3), or `README.md` (P1.M1.T5) — T2.S1 is config.toml + its test ONLY (Gotcha #7).
- ❌ Don't conflate this with T1.S1's install.sh fix — T1.S1 REMOVES a wrong `SUPER+ALT+D -> toggle` from install.sh (because there SUPER+ALT+D was mislabeled as normal). In config.toml's lite comment, `SUPER+ALT+D` IS correct (lite bind). Different files, different contexts; no conflict (CRITICAL #3).
- ❌ Don't skip the TDD red step — run the new test on the unfixed tree FIRST and confirm it FAILS; a test that passes before the fix is vacuous (Gotcha #6).
- ❌ Don't hardcode the config.toml path — reuse `_repo_config_path` (already imported in the test file, L14) (Gotcha #5).
- ❌ Don't use bare `python`/`pytest` or invoke ruff/mypy (not configured). Use `.venv/bin/python -m pytest` (Gotcha #8).

---

## Confidence Score

**9.5/10** for one-pass implementation success. This is a one-token comment fix + one raw-text static test — the smallest possible change — and every load-bearing fact is verified against the live repo: the verbatim defect line (config.toml:34, `SUPER+ALT+F`), the source of truth (hypr-binds.conf:6/:44 `SUPER+ALT+D = toggle-lite`; PRD §4.10), the reason the existing guards miss it (tomllib drops comments), the reusable path helper (`_repo_config_path`, imported at test_config_repo_default.py:14), and the no-conflict boundary with the parallel T1.S1 (install.sh + test_systemd_unit.py vs config.toml + test_config_repo_default.py). The TDD red→green loop (L1 red on the current tree → L2 green after the one-token edit) proves the test actually guards rather than vacuously passing. The −0.5 is solely the small risk of an edit accident touching the comment's em-dash/alignment (mitigated by CRITICAL #4's "edit ONLY the token" + L2d's value drift-guard check that confirms the value still parses == defaults).
