# PRP — P1.M1.T4.S1: Fix `toggle_lite` docstring "pressing F" → "pressing D" (3×) + TDD test

## Goal

**Feature Goal**: Fix bugfix **Issue 4** (Minor doc defect): the `toggle_lite()` docstring in
`voice_typing/daemon.py:1410-1411` says **"pressing F"** (3×) when describing the lite key's
behavior — but the lite keybind is **key D** (`hypr-binds.conf:44`:
`bind = SUPER ALT, D, exec, .../voicectl toggle-lite`; PRD §4.10), **never F**. This contradicts
PRD §4.10, `hypr-binds.conf`, `README.md`, AND the sibling `toggle()` docstring (daemon.py:1377-1378)
which all correctly use "pressing D". It's the same F-thinko as Issue 2 (config.toml, fixed in
P1.M1.T2.S1). Internal-only (a maintainer-facing docstring), but it actively misleads anyone reading
the toggle semantics. This subtask replaces the 3 "pressing F" with "pressing D" (mirroring `toggle()`)
and adds a **TDD red→green** test asserting `toggle_lite.__doc__` contains "pressing D" and NOT
"pressing F", so the drift cannot recur.

**Deliverable** (2 files edited, no new files):
1. `voice_typing/daemon.py` — 1 text edit (3 char swaps F→D across a 2-line span on lines 1410-1411;
   no behavior change). The `toggle_lite()` method BODY is byte-identical.
2. `tests/test_daemon.py` — one ADDITIVE test (`test_toggle_lite_docstring_says_pressing_d_not_f`)
   under a new banner section at the file's END: accesses `daemon.VoiceTypingDaemon.toggle_lite.__doc__`
   (no instantiation), asserts `"pressing D" in doc` and `"pressing F" not in doc`. RED before the
   daemon.py fix, GREEN after.

**Success Definition**:
- (a) `daemon.VoiceTypingDaemon.toggle_lite.__doc__` contains **"pressing D"** (count ≥ 1) and does
  **NOT** contain **"pressing F"** (count 0).
- (b) The new test is **RED before** the daemon.py edit (TDD) and **GREEN after**.
- (c) `toggle_lite()` BODY logic (`_load_host`/`_arm`/`_disarm`/`_request_stop`) is byte-identical —
  zero runtime behavior change. All 8 existing behavioral `toggle_lite` tests pass unmodified.
- (d) `toggle_lite.__doc__` now mirrors the sibling `toggle.__doc__` (both say "pressing D"), and
  agrees with `hypr-binds.conf:44` + `README.md` + PRD §4.10 (lite = `Alt+Super+D`, key **D**).

> **VERIFIED DEFECT (this PRP's research):** live run confirms `toggle_lite.__doc__` has
> `'pressing F' in doc == True` (count **3**) and `'pressing D' in doc == False`. The implementing
> agent applies the single verbatim 2-line edit below; the new test goes red→green.

## User Persona

**Target User**: the maintainer / contributor reading `toggle_lite()` to understand the lite-mode
toggle semantics (mode-specific arming, cross-mode switching) before changing it.
**Use Case**: a contributor opens `daemon.py` to understand what `toggle_lite` does, reads the
docstring's "So: pressing F while idle arms in lite...", and is misled into thinking the lite
hotkey is F (it is D). After the fix, the docstring consistently says "pressing D", matching
`hypr-binds.conf`, `README`, and the sibling `toggle()` docstring.
**Pain Points Addressed**: Issue 4 — the toggle_lite docstring references the wrong key letter,
contradicting the actual keybind (D) and every other surface that documents it.

## Why

- **PRD §4.10 + `hypr-binds.conf` are the source of truth.** The lite bind is `SUPER ALT, D`
  (key **D**, PRD §4.10; `hypr-binds.conf:44`). "F" is bound to nothing. The docstring must agree.
- **Internal consistency.** The sibling `toggle()` docstring (daemon.py:1377-1378) already correctly
  says "pressing D" (3×). `toggle_lite()` saying "pressing F" (3×) is a self-contradiction within
  the same ~30-line span of the same class — the two toggle docstrings describe the SAME two
  hotkeys (one with CTRL = normal, one without = lite) and must use the SAME key letter.
- **Why it slipped past tests.** The suite has 8 behavioral `toggle_lite` tests (instantiating the
  daemon with fakes — test_daemon.py:2831, 3551, 3563, 3574, 3645, ...), but **NO test asserts the
  docstring text**. A docstring is a string literal that can drift silently. The new TDD test reads
  `toggle_lite.__doc__` as text and asserts the correct key letter — closing the gap permanently.
  (system_context.md: "NO test asserts the ... docstring".)
- **Scope discipline.** T4.S1 owns ONLY `voice_typing/daemon.py` (1 text edit) +
  `tests/test_daemon.py` (1 test). It does NOT touch the toggle_lite BODY (behavior unchanged),
  the `toggle()` docstring (already correct), `config.toml` (P1.M1.T2.S1-complete), `ctl.py`
  (P1.M1.T3.S1), `install.sh` (P1.M1.T1.S1-complete), `README` (P1.M1.T5.S1), or `hypr-binds.conf`
  (correct). Pure Mode-A doc fix + a hermetic regression test.

## What

Apply 1 verbatim text edit to `voice_typing/daemon.py` (lines 1410-1411) replacing the 3 "pressing F"
with "pressing D", then add one TDD test to `tests/test_daemon.py` asserting `toggle_lite.__doc__`
contains "pressing D" and not "pressing F". No value/schema/behavior change.

### Success Criteria

- [ ] daemon.py:1410 reads `...arms in lite. So: pressing D while idle` (was `pressing F`).
- [ ] daemon.py:1411 reads `arms in lite; pressing D while armed-in-lite disarms; pressing D while armed-in NORMAL` (was `pressing F` ×2).
- [ ] `toggle_lite.__doc__.count("pressing F") == 0` and `toggle_lite.__doc__.count("pressing D") == 3`.
- [ ] `toggle_lite()` BODY (`_load_host`/`_arm`/`_disarm`/`_request_stop`/`_lock`) UNCHANGED (only the docstring text changes).
- [ ] `toggle()` docstring (lines 1377-1378) UNCHANGED (it is already correct).
- [ ] New `test_toggle_lite_docstring_says_pressing_d_not_f` passes; it is RED before the daemon.py edit (TDD).
- [ ] `.venv/bin/python -m pytest tests/test_daemon.py -v` → 0 failures (all existing + the 1 new).
- [ ] `git diff --name-only` == `voice_typing/daemon.py` + `tests/test_daemon.py`.

## All Needed Context

### Context Completeness Check

_Pass._ The exact defect is empirically confirmed (live run: `pressing F`=True ×3, `pressing D`=False).
The fix is given as one verbatim 2-line old→new edit against current lines 1410-1411 (verified), the
correct reference pattern (`toggle()` docstring @1377-1378, "pressing D") + the keybind truth
(`hypr-binds.conf:44`, key D) are cited, the TDD test design + placement (new banner section at the
END of test_daemon.py; `daemon.VoiceTypingDaemon.toggle_lite.__doc__` accessed without instantiation
→ hermetic) are specified, and the no-conflict boundary with the parallel T3.S1 (disjoint files) is
established. An agent new to this repo can apply the fix from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the verified defect + the verbatim old→new edit + the TDD test design (this task's research)
- docfile: plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/P1M1T4S1/research/toggle_lite_docstring_pressing_d.md
  why: "§0 confirms the defect empirically (live: pressing F=3×, pressing D=0×) + proves __doc__ is
        reachable without instantiation. §1 is the verbatim 2-line old→new edit with exact line
        numbers. §2 cites the keybind truth (hypr-binds.conf:44 = SUPER ALT, D; both binds use D,
        never F). §3 is the TDD test design + placement (banner at END of test_daemon.py; pure
        __doc__ text assertion; no instance/GPU/socket) + the red→green proof. §4 parallel
        no-conflict (disjoint files). §5 scope discipline (touch ONLY the docstring text; behavior
        untouched). §6 validation tooling (pytest only; full paths)."
  critical: "§1 (the verbatim 2-line edit) and §3 (the test) are load-bearing. The 'do NOT touch the
            toggle_lite BODY or the toggle() docstring' note (§5) prevents out-of-scope edits."

# THE FILE UNDER FIX — voice_typing/daemon.py (the docstring span)
- file: voice_typing/daemon.py
  why: "toggle_lite() @1407; the buggy docstring lines @1410-1411 (3× 'pressing F'). The SIBLING
        toggle() @1374 has the CORRECT reference docstring @1377-1378 ('pressing D' ×3) — mirror it.
        VoiceTypingDaemon is the class @542; toggle_lite is a method so its __doc__ is reachable as
        VoiceTypingDaemon.toggle_lite.__doc__ WITHOUT instantiation (pure class-attribute access)."
  pattern: "The fix is ONE edit replacing the contiguous 2-line span @1410-1411 (the 3 'pressing F'
            all sit on those 2 lines). Preserve the line-continuation wrapping exactly — only the
            letter changes (F→D ×3). Do NOT reflow/reformat the docstring; do NOT touch the 3rd line
            ('switches to lite ...') or the method body."
  gotcha: "Do NOT edit toggle_lite() BODY (_load_host/_arm/_disarm/_request_stop) — it is correct
           (8 behavioral tests pass). Do NOT edit toggle() docstring — it is already 'pressing D'.
           Issue 4 is a DOCSTRING-TEXT-ONLY defect."

# THE TEST FILE — tests/test_daemon.py (where the new test goes)
- file: tests/test_daemon.py
  why: "Imports `from voice_typing import daemon` @23 (no new import needed). Module docstring @1
        confirms hermetic: 'NO real RealtimeSTT / NO model load / NO CUDA'. Each subtask appends its
        own BANNER SECTION (the current last banner is '# P1.M1.T2.S1 — toggle/toggle_lite
        mode-specific arming' @3537; its tail tests are the file EOF today). 8 behavioral toggle_lite
        tests exist (@2831, 3551, 3563, 3574, 3645, ...) — ALL instantiate the daemon; NONE assert
        __doc__. That is the coverage gap this test closes."
  pattern: "ADD a new section at the END under a 'P1.M1.T4.S1 — toggle_lite docstring references key D'
            banner. The test accesses daemon.VoiceTypingDaemon.toggle_lite.__doc__ (NO instance),
            asserts 'pressing D' in doc and 'pressing F' not in doc. No fixture, no monkeypatch,
            no daemon instance — pure __doc__ text (hermetic)."
  critical: "Access __doc__ as a CLASS attribute (VoiceTypingDaemon.toggle_lite.__doc__), NOT via an
            instance — instantiation would require fakes + a recorder (unneeded here). The
            load-bearing assertions are BOTH: 'pressing D' present (the fix) AND 'pressing F' absent
            (guards regression — do NOT drop the 'not in' assertion)."

# THE MANDATE — PRD §4.10 (the lite keybind = Alt+Super+D, key D) + Issue 4 definition
- docfile: plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/prd_snapshot.md
  why: "§4.10 pins the lite bind: 'Alt+Super+D → toggle-lite'. Issue 4 (Minor) is the source: the
        toggle_lite docstring references 'pressing F' (should be 'pressing D'); Suggested Fix:
        'Replace the three occurrences of pressing F with pressing D ... mirror the correct pressing D
        already used in the sibling toggle docstring.'"
  critical: "This subtask IS that fix + the test that closes the 'no test asserts the docstring' gap."

# THE KEYBIND TRUTH + THE REFERENCE PATTERN (correct-on-D sources)
- file: hypr-binds.conf
  why: ":44 = 'bind = SUPER ALT, D, exec, .../voicectl toggle-lite' (lite = key D). :42 = 'bind = CTRL
        SUPER ALT, D, ... toggle' (normal = key D). BOTH binds use key D, never F. This is the
        authoritative keybind source (system_context.md)."
  pattern: "Do NOT edit hypr-binds.conf (it is correct). Use it as the proof that the docstring's 'F'
            is wrong and 'D' is right."
- file: voice_typing/daemon.py
  why: "toggle() docstring @1377-1378 is the in-file correct reference ('pressing D' ×3). toggle_lite()
        @1410-1411 must mirror it exactly (same key letter D)."
  critical: "After the fix, toggle() and toggle_lite() docstrings use the SAME key letter (D) — the
            internal contradiction is gone."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── daemon.py            # VoiceTypingDaemon @542; toggle() @1374 (doc @1377-1378 = CORRECT 'pressing D');
│   │                          toggle_lite() @1407 (doc @1410-1411 = BUGGY 'pressing F' ×3).  ← EDIT (1 docstring span)
│   │                          NOTE: T3.S1 (parallel) edits voice_typing/ctl.py — DISJOINT.
└── tests/
    └── test_daemon.py       # imports `from voice_typing import daemon` @23; 8 behavioral toggle_lite     ← EDIT (additive banner + 1 test)
                               # tests (all instantiate); NONE assert __doc__. New test appends at END.
# NOTE: the fix is 1 docstring edit (F→D ×3) + 1 additive hermetic test. No behavior change. No GPU/socket/daemon instance.
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py       # EDIT: 1 docstring span @1410-1411 ('pressing F' → 'pressing D' ×3).
#                            toggle_lite() BODY UNCHANGED. toggle() docstring UNCHANGED. No new imports.
tests/test_daemon.py         # ADD: one banner section + test_toggle_lite_docstring_says_pressing_d_not_f (additive;
#                            no existing test changed). No new imports (uses daemon.VoiceTypingDaemon.toggle_lite.__doc__).
# No new files. No config.toml / ctl.py / install.sh / README / hypr-binds.conf changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DOCSTRING-TEXT-ONLY EDIT. The 3 'pressing F' all sit on the contiguous lines 1410-1411.
# Replace that ONE 2-line span (F→D ×3), preserving the line-continuation wrapping exactly. Do NOT
# reflow/reformat the docstring, do NOT touch the 3rd line ('switches to lite ...'), and do NOT edit
# the toggle_lite() BODY. (research §1, §5.)

# CRITICAL #2 — TDD RED→GREEN. The new test MUST fail BEFORE the daemon.py edit and pass AFTER. Verify
# by running it once against the unedited daemon.py (expect RED: 'pressing D' absent from __doc__),
# then apply the edit and re-run (expect GREEN). PROVEN empirically: before the fix
# toggle_lite.__doc__ has 'pressing F'=True ×3, 'pressing D'=False. (research §0, §3; Gotcha #6.)

# CRITICAL #3 — DO NOT EDIT THE toggle_lite() BODY OR THE toggle() DOCSTRING. The toggle_lite BODY
# (_load_host/_arm/_disarm/_request_stop/_lock) is correct (8 behavioral tests pass). The toggle()
# docstring (@1377-1378) is ALREADY 'pressing D'. Issue 4 is a toggle_lite-DOCSTRING-TEXT-ONLY defect.
# Editing anything else is out of scope and would break existing tests. (research §5.)

# GOTCHA #4 — ACCESS __doc__ AS A CLASS ATTRIBUTE (no instantiation). daemon.VoiceTypingDaemon.toggle_lite.__doc__
# reads the method's docstring via the underlying function object's class attribute — NO instance, NO
# __init__, NO recorder, NO GPU, NO socket. Instantiating would require _FakeFeedback/_FakeRecorder
# fakes (unneeded here). The test is fully hermetic. (research §3.)

# GOTCHA #5 — BOTH ASSERTIONS ARE LOAD-BEARING. Assert BOTH 'pressing D' in doc (the fix) AND
# 'pressing F' not in doc (the regression guard). Dropping the 'not in' assertion would let a future
# edit add 'pressing D' while LEAVING a stray 'pressing F' — the test would still pass. The 'not in'
# assertion is the discrimination that pins the defect closed. (research §3.)

# GOTCHA #6 — THIS PROJECT USES pytest (NO ruff/mypy in pyproject). Validation = py_compile + pytest.
# Do NOT invent ruff/mypy commands (the PRP template's ruff/mypy L1 lines are N/A here). (research §6.)

# GOTCHA #7 — USE FULL PATHS. This machine aliases python3→uv run, pip→alias, tmux→zsh plugin. Invoke
# .venv/bin/python explicitly. Never bare python/pytest/uv. (system_context.md; research §6.)

# GOTCHA #8 — NO SOCKET / DAEMON / GPU / RECORDER in the new test. toggle_lite.__doc__ is a pure
# stdlib string operation. Importing voice_typing.daemon is hermetic (test_daemon.py module docstring
# confirms: NO real RealtimeSTT / NO model load / NO CUDA). (research §3, §6.)

# GOTCHA #9 — DO NOT touch config.toml (T2.S1-complete), ctl.py/test_voicectl.py (T3.S1, parallel),
# install.sh (T1.S1-complete), README (T5.S1), or hypr-binds.conf (correct). Only voice_typing/daemon.py
# + tests/test_daemon.py. Editing other files risks a conflict with the parallel/later siblings
# (disjoint files = clean merges). (research §4.)

# GOTCHA #10 — test_daemon.py APPEND IS SAFE (no concurrent appender). T3.S1 (the only parallel
# implementation) owns test_voicectl.py, NOT test_daemon.py. So appending a banner to test_daemon.py's
# EOF has no merge contention. If a future sibling ever appends to test_daemon.py concurrently, re-read
# the file's current tail before inserting (banner blocks are independent; ordering is irrelevant).
```

## Implementation Blueprint

### Data models and structure

None. This subtask adds no code, no types, no config, no behavior. The only "data" is 3 char swaps
(F→D) in a docstring + one additive test function. `toggle_lite()` is unchanged source logic.

### Implementation Tasks (ordered by dependencies — TDD: test FIRST, then the fix)

```yaml
Task 1: ADD the failing test FIRST (TDD red) — tests/test_daemon.py
  - PLACE: a new banner section at the END of tests/test_daemon.py (the file's convention — each
    subtask appends its own banner section; the current last banner is '# P1.M1.T2.S1 —
    toggle/toggle_lite mode-specific arming' @3537 whose tail tests are the EOF today).
  - ADD (verbatim; `daemon` is already imported at the top: `from voice_typing import daemon` @23):
        # ===========================================================================
        # P1.M1.T4.S1 — toggle_lite docstring references the correct key D (bugfix Issue 4)
        # (the lite keybind is Alt+Super+D — key D, never F (hypr-binds.conf:44 / PRD §4.10). The
        #  toggle_lite docstring previously said "pressing F" 3×; this pins it at "pressing D",
        #  mirroring the sibling toggle() docstring. Pure static-text assertion on __doc__ — no
        #  instantiation, no GPU/socket/recorder.)
        # ===========================================================================
        def test_toggle_lite_docstring_says_pressing_d_not_f():
            """toggle_lite.__doc__ references key D (the lite bind is Alt+Super+D), never F (Issue 4).

            The lite keybind is SUPER ALT, D (hypr-binds.conf:44 / PRD §4.10) — key D, not F. The
            docstring must mirror the sibling toggle() docstring, which correctly says "pressing D".
            Before the fix this was RED: "pressing F" present (3×), "pressing D" absent.
            """
            doc = daemon.VoiceTypingDaemon.toggle_lite.__doc__
            assert doc is not None, "toggle_lite is missing its docstring"
            assert "pressing D" in doc, "toggle_lite docstring must say 'pressing D' (lite bind = Alt+Super+D)"
            assert "pressing F" not in doc, "toggle_lite docstring must NOT reference key F (it is D)"
  - RUN (confirm RED before the fix — TDD):
      cd /home/dustin/projects/voice-typing
      .venv/bin/python -m pytest tests/test_daemon.py::test_toggle_lite_docstring_says_pressing_d_not_f -v
  - EXPECTED: the test FAILS (RED) with "toggle_lite docstring must say 'pressing D' ...". This
    proves the defect is real and the test discriminates. (If it PASSES, the assertions are wrong —
    re-check; Gotcha #2/#5.) This RED run is the TDD baseline.

Task 2: EDIT voice_typing/daemon.py — the toggle_lite docstring span (the fix)
  - FIND daemon.py:1410-1411 (the 3 'pressing F' live on these 2 contiguous lines). Current:
        Disarms ONLY if currently armed in LITE; otherwise arms in lite. So: pressing F while idle
        arms in lite; pressing F while armed-in-lite disarms; pressing F while armed-in NORMAL
  - EDIT (oldText → newText — 3 char swaps F→D; preserve the line-continuation wrapping exactly):
      OLD:
        Disarms ONLY if currently armed in LITE; otherwise arms in lite. So: pressing F while idle
        arms in lite; pressing F while armed-in-lite disarms; pressing F while armed-in NORMAL
      NEW:
        Disarms ONLY if currently armed in LITE; otherwise arms in lite. So: pressing D while idle
        arms in lite; pressing D while armed-in-lite disarms; pressing D while armed-in NORMAL
  - DO NOT: edit the toggle_lite() BODY, the toggle() docstring, or any other line (Gotcha #1/#3).

Task 3: VERIFY — TDD green + the empirical __doc__ counts + full test_daemon.py suite
  - RUN (the test from Task 1 must now be GREEN):
      cd /home/dustin/projects/voice-typing
      .venv/bin/python -m pytest tests/test_daemon.py::test_toggle_lite_docstring_says_pressing_d_not_f -v
  - EXPECTED: PASS (GREEN). (Task 2 made __doc__ contain 'pressing D' and not 'pressing F'.)
  - RUN (empirical confirmation — __doc__ counts are now D=3, F=0):
      .venv/bin/python -c "from voice_typing import daemon; d=daemon.VoiceTypingDaemon.toggle_lite.__doc__; print('pressing D count:', d.count('pressing D')); print('pressing F count:', d.count('pressing F'))"
      .venv/bin/python -c "from voice_typing import daemon; print(daemon.VoiceTypingDaemon.toggle_lite.__doc__)"
  - EXPECTED: 'pressing D count: 3', 'pressing F count: 0'; the printed docstring says 'pressing D'
    on both lines (mirrors the sibling toggle() docstring @1377-1378).
  - RUN (full test_daemon.py — no regression to the 8 behavioral toggle_lite tests):
      .venv/bin/python -m pytest tests/test_daemon.py -v 2>&1 | tail -8
  - EXPECTED: 0 failures (all existing + the 1 new). See Validation L2.
  - DO NOT: edit the toggle_lite() BODY / toggle() docstring; touch config.toml/ctl.py/README/install.sh/hypr-binds.conf.

Task 4: VALIDATE — run the Validation Loop L1–L4 below. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M1.T4.S1: toggle_lite docstring now says 'pressing D' (was 'pressing F' ×3),
  matching hypr-binds.conf + the sibling toggle() docstring; docstring assertion test added (TDD red→green)."
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — a docstring is a string literal that can drift silently. The fix swaps F→D in place;
# the TDD test reads toggle_lite.__doc__ AS TEXT and asserts the correct key letter, so any future
# reintroduction of 'pressing F' turns the test RED. (Gotcha #5.)
doc = daemon.VoiceTypingDaemon.toggle_lite.__doc__   # class-attribute access (no instance)
assert "pressing D" in doc                             # the fix
assert "pressing F" not in doc                          # the regression guard (load-bearing)

# PATTERN 2 — mirror the in-file reference. toggle() @1377-1378 is ALREADY correct ('pressing D').
# After the fix, toggle() and toggle_lite() docstrings use the SAME key letter (D) — the internal
# contradiction (one said D, the other F) is gone, and both agree with hypr-binds.conf + README.
```

### Integration Points

```yaml
DELTA ACCEPTANCE (bugfix Issue 4 / PRD §4.10):
  - This subtask fixes Issue 4 (the toggle_lite docstring typo) + adds the regression test that the
    issue's analysis + system_context.md flagged as missing ("no test asserts the docstring"). PRD
    §4.10's keybind (Alt+Super+D = key D) is now consistent across hypr-binds.conf, README, the
    toggle() docstring, AND the toggle_lite() docstring.

PARALLEL — P1.M1.T3.S1 (voicectl help text, in flight):
  - T3.S1 edits voice_typing/ctl.py + tests/test_voicectl.py. T4.S1 edits voice_typing/daemon.py +
    tests/test_daemon.py. DISJOINT files — no line-level conflict. Both are Mode-A doc fixes with a
    TDD static-text test. Clean merge. (research §4.)

SIBLINGS (also disjoint):
  - T1.S1 (complete) owned install.sh; T2.S1 (complete) owned config.toml/test_config_repo_default.py;
    T5.S1 (later) verifies README/overview consistency. None touch daemon.py/test_daemon.py.

NO INTERFACE / BEHAVIOR CHANGES:
  - toggle_lite() BODY (_load_host/_arm/_disarm/_request_stop/_lock), toggle(), start/stop/quit,
    the control socket protocol, exit codes, model-load paths: ALL UNCHANGED. Only the docstring
    text changes. The 8 existing behavioral toggle_lite tests pass unmodified.
```

## Validation Loop

> Full paths in every command (zsh aliases shadow python3/pip on this machine). Run from the repo
> root `/home/dustin/projects/voice-typing`. This project uses pytest (NO ruff/mypy — Gotcha #6).
> All gates are pure/hermetic (no GPU/socket/daemon/recorder — Gotcha #8).

### Level 1: The docstring edit is in place (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- toggle_lite docstring now says 'pressing D' (was 'pressing F') ---"
sed -n '1407,1416p' voice_typing/daemon.py
echo "--- 'pressing F' is GONE from the whole file (should print nothing) ---"
grep -n "pressing F" voice_typing/daemon.py || echo "L1 PASS: no 'pressing F' remains in daemon.py"
echo "--- 'pressing D' present in BOTH toggle() and toggle_lite() docstrings ---"
grep -n "pressing D" voice_typing/daemon.py
echo "--- py_compile sanity (the edit didn't break syntax) ---"
.venv/bin/python -m py_compile voice_typing/daemon.py && echo "L1 PASS: daemon.py compiles"
# Expected: the @1410-1411 span reads 'pressing D' (×3); grep 'pressing F' finds nothing;
# 'pressing D' appears in both the toggle() (@1377-1378) and toggle_lite() (@1410-1411) docstrings;
# py_compile succeeds. NO ruff/mypy (this project doesn't use them — Gotcha #6).
```

### Level 2: TDD red→green + full test_daemon.py suite (the deliverable)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
echo "--- the new test PASSES (GREEN after Task 2) ---"
"$PY" -m pytest tests/test_daemon.py::test_toggle_lite_docstring_says_pressing_d_not_f -v
echo "--- full test_daemon.py — no regression (all existing + the 1 new) ---"
"$PY" -m pytest tests/test_daemon.py -v 2>&1 | tail -8
# Expected: the new test PASSES; the full suite is GREEN (0 failures) — including the 8 behavioral
# toggle_lite tests (they instantiate the daemon with fakes; the docstring edit doesn't touch them).
# (If you ran the new test BEFORE the daemon.py edit per Task 1, it was RED — the TDD baseline, now
# resolved by Task 2.)
```

### Level 3: Empirical __doc__ counts + internal consistency (the user-facing fix)

```bash
cd /home/dustin/projects/voice-typing
echo "--- toggle_lite.__doc__ counts: pressing D = 3, pressing F = 0 ---"
.venv/bin/python -c "from voice_typing import daemon; d=daemon.VoiceTypingDaemon.toggle_lite.__doc__; print('pressing D:', d.count('pressing D'), '| pressing F:', d.count('pressing F'))"
echo "--- toggle_lite + toggle docstrings now AGREE on key letter D ---"
.venv/bin/python -c "from voice_typing import daemon; lt=daemon.VoiceTypingDaemon.toggle_lite.__doc__; tn=daemon.VoiceTypingDaemon.toggle.__doc__; print('toggle_lite pressing D:', lt.count('pressing D'), '| toggle pressing D:', tn.count('pressing D'))"
echo "--- the toggle_lite docstring (full) ---"
.venv/bin/python -c "from voice_typing import daemon; print(daemon.VoiceTypingDaemon.toggle_lite.__doc__)"
# Expected: 'pressing D: 3 | pressing F: 0'; both toggle docstrings have pressing D ≥ 3; the printed
# docstring says 'pressing D' on both @1410-1411 lines (mirrors toggle() @1377-1378).
```

### Level 4: Scope guards — only daemon.py + test_daemon.py changed; behavior unchanged

```bash
cd /home/dustin/projects/voice-typing
echo "--- only the 2 in-scope files changed ---"
git diff --name-only
echo "--- the toggle_lite BODY + toggle() docstring UNCHANGED (only the 1410-1411 span moved) ---"
git diff voice_typing/daemon.py | grep -E '^[+-]' | grep -vE '^[+-]{3}|pressing [FD] while|pressing [FD] while armed-in' || echo "L4 PASS: only the 'pressing F'→'pressing D' tokens changed in daemon.py"
echo "--- read-only / sibling files UNCHANGED ---"
git diff --exit-code -- config.toml voice_typing/ctl.py install.sh README.md hypr-binds.conf PRD.md plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/tasks.json plan/005_723f4c529eea/bugfix/001_c5854aa1cd58/prd_snapshot.md .gitignore && echo "L4 PASS: no config/ctl/install/README/read-only changes" || echo "L4 NOTE: tasks.json may show orchestrator bookkeeping (M) — not this subtask"
# Expected: git diff --name-only == voice_typing/daemon.py + tests/test_daemon.py; the daemon.py
# behavior-filter shows ONLY the 'pressing F'→'pressing D' line changes; config.toml/ctl.py/install.sh/
# README/hypr-binds.conf untouched.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: the @1410-1411 docstring span reads "pressing D" (×3); `grep "pressing F" daemon.py` finds nothing; `py_compile` passes; no ruff/mypy invented.
- [ ] L2: new `test_toggle_lite_docstring_says_pressing_d_not_f` GREEN (was RED before the edit per Task 1); full `tests/test_daemon.py` green (incl. the 8 behavioral toggle_lite tests).
- [ ] L3: empirical `toggle_lite.__doc__` counts = `pressing D: 3 | pressing F: 0`; toggle() and toggle_lite() docstrings agree on key letter D.
- [ ] L4: only `voice_typing/daemon.py` + `tests/test_daemon.py` changed; toggle_lite() BODY + toggle() docstring untouched; sibling/read-only files unchanged.

### Feature Validation
- [ ] `toggle_lite.__doc__` contains "pressing D" and does NOT contain "pressing F" (both assertions — Gotcha #5).
- [ ] `toggle_lite()` docstring now mirrors the sibling `toggle()` docstring (both "pressing D") and agrees with `hypr-binds.conf:44` (lite = `Alt+Super+D`, key D) + `README.md` + PRD §4.10.
- [ ] The 8 existing behavioral `toggle_lite` tests still pass (the docstring edit changed no behavior).

### Code Quality / Scope Validation
- [ ] 1 docstring-text edit only (F→D ×3) — no reflow/reformat, no body change (Gotcha #1/#3).
- [ ] New test is ADDITIVE (banner section at END; no existing test changed); pure `__doc__` text (no instance/GPU/socket/recorder — Gotcha #4/#8).
- [ ] Both assertions present (`"pressing D" in doc` AND `"pressing F" not in doc` — Gotcha #5).
- [ ] No conflict with parallel T3.S1 (disjoint files); no edit to config.toml/ctl.py/install.sh/README/hypr-binds.conf.

### Documentation & Deployment
- [ ] [Mode A] the daemon.py docstring is the maintainer-facing doc — the fix IS the doc update (no separate docs subtask).
- [ ] No user-facing/config/API BEHAVIOR change (toggle_lite logic, control socket, model-load paths all byte-identical).

---

## Anti-Patterns to Avoid

- ❌ Don't edit the `toggle_lite()` BODY (`_load_host`/`_arm`/`_disarm`/`_request_stop`/`_lock`) — it is correct (8 behavioral tests pass); Issue 4 is a DOCSTRING-TEXT-ONLY defect. (Gotcha #3.)
- ❌ Don't edit the `toggle()` docstring — it is ALREADY correct ("pressing D"). Use it as the reference to mirror, not a target to change. (Gotcha #3.)
- ❌ Don't reflow/reformat the docstring or touch lines outside the 1410-1411 span — replace the 2-line span in place (F→D ×3), preserving the line-continuation wrapping exactly. (Gotcha #1.)
- ❌ Don't skip the TDD red step (Task 1) — run the new test AGAINST THE UNEDITED daemon.py first to confirm it FAILS (proves the defect + that the test discriminates). PROVEN RED empirically: `pressing F`=True ×3, `pressing D`=False. (Gotcha #2.)
- ❌ Don't drop the `"pressing F" not in doc` assertion — it is the regression guard. Asserting only `"pressing D" in doc` would let a future edit leave a stray "pressing F". (Gotcha #5.)
- ❌ Don't instantiate `VoiceTypingDaemon` in the test — access `toggle_lite.__doc__` as a class attribute (`daemon.VoiceTypingDaemon.toggle_lite.__doc__`); instantiation needs fakes + a recorder and is unnecessary. (Gotcha #4/#8.)
- ❌ Don't touch config.toml (T2.S1-complete), ctl.py/test_voicectl.py (T3.S1, parallel), install.sh (T1.S1-complete), README (T5.S1), or hypr-binds.conf (correct) — only `voice_typing/daemon.py` + `tests/test_daemon.py`. (Gotcha #9.)
- ❌ Don't use bare `python`/`pytest`/`uv` (zsh aliases shadow them) — use `.venv/bin/python`. (Gotcha #7.)
- ❌ Don't invent ruff/mypy gates — this project uses pytest only. (Gotcha #6.)
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, or `.gitignore` (read-only / owned by others).

---

## Confidence Score

**9.5/10** for one-pass implementation success. The defect is empirically confirmed (live: `pressing F`=True ×3, `pressing D`=False; `count("pressing F")`=3), the fix is given as one verbatim 2-line old→new edit against exact current lines (1410-1411 — verified), the TDD test design + placement mirror the file's existing banner-section convention and use the verified hermetic `VoiceTypingDaemon.toggle_lite.__doc__` seam (no instance/GPU/socket), and the parallel T3.S1 edits disjoint files (ctl.py/test_voicectl.py). The −0.5 residual is the small chance of a copy-paste slip in the 2-line span (e.g., missing one of the 3 F→D swaps) — which the L1 grep (`grep "pressing F"` finds nothing) + the L2 test (asserts both `"pressing D" in` and `"pressing F" not in`) catch immediately. No GPU, socket, daemon instance, or network is required.
