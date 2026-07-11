# PRP — P1.M1.T1.S2: Add static drift-guard test asserting launch_daemon.sh exports offline vars

## Goal

**Feature Goal**: Add a fast, static pytest drift-guard test to `tests/test_systemd_unit.py` that fails the moment someone removes the `export HF_HUB_OFFLINE=1` / `export TRANSFORMERS_OFFLINE=1` lines from `voice_typing/launch_daemon.sh`. This permanently closes the "circular-proof" gap that let bugfix **Issue 1** (production daemon phoning home to huggingface.co on every startup) ship in the first place — by asserting the offline guarantee lives in the **production launch wrapper**, not in a test harness that pre-sets the variable.

**Deliverable**: One new test function (`test_launch_daemon_exports_offline_vars`) + one sibling path helper (`_launch_daemon_path`), appended to `tests/test_systemd_unit.py` (currently 95 lines, 3 tests → becomes 4 tests). No other file is touched. This is a **test-only** subtask: no CUDA, no models, no network, no live systemd needed — it `read_text()`s the wrapper and runs in milliseconds.

**Success Definition**:
- (a) `.venv/bin/python -m pytest tests/test_systemd_unit.py -v` collects **4 tests** (the 3 existing + the 1 new) and **all pass** against the current `launch_daemon.sh` (which S1 has already populated with the exports).
- (b) The new test asserts BOTH `export HF_HUB_OFFLINE=1` and `export TRANSFORMERS_OFFLINE=1` are present as real directives (accepting `=1` / `="1"` / `='1'`).
- (c) The new test asserts BOTH exports appear on an earlier source line than `exec "$PY" -m voice_typing.daemon` (env vars read at `execve(2)`).
- (d) **The guard actually guards**: temporarily deleting an export line turns the new test RED (verified, then restored). Critically, the test does NOT false-pass via the comment block (which mentions the var name in prose) — it uses a line-anchored `^export …` match.
- (e) `git diff` touches ONLY `tests/test_systemd_unit.py`.

## User Persona

**Target User**: The maintainer (human or AI agent) of the voice-typing daemon — the person who will edit `launch_daemon.sh` in future changesets and must not silently regress the "100% local" guarantee (PRD §1, acceptance §7.8).

**Use Case**: A future refactor of the launch wrapper (e.g. reorganizing the CUDA-libs block, or "cleaning up" what looks like redundant env vars). The drift-guard test runs in the normal pytest suite and fails the build before such a change can ship, forcing the author to consciously remove the offline guarantee (and explain why) rather than doing it by accident.

**Pain Points Addressed**: bugfix Issue 1 shipped precisely because no static assertion guarded the production launch path's env — the only "offline" test (`test_idle_and_gpu.sh:206`) *itself* supplied `HF_HUB_OFFLINE=1`, masking the production defect. This test removes that blind spot for the launch-wrapper layer.

## Why

- **Closes the masking gap at the cheapest possible layer.** A static text-grep test is deterministic, sub-second, dependency-free (no GPU/models/network/systemd), and runs on every commit. It cannot prove the daemon makes zero network calls at runtime (that is S3's job on `test_idle_and_gpu.sh`), but it DOES prove the *configurational precondition* — the offline exports are present in the production wrapper — which is the root cause S1 fixed.
- **Mirrors an established, trusted pattern.** `tests/test_systemd_unit.py` already does exactly this for `systemd/voice-typing.service` (3 static drift-guards: ExecStart→wrapper, ExecStartPre Wayland import, Restart=on-failure). Extending it to `launch_daemon.sh` is the natural, low-friction home — same file, same conventions, same reviewer mental model.
- **Codifies the design decision.** S1 deliberately put the offline vars in the wrapper (not the systemd `Environment=`, not `daemon.py`'s `os.environ`) because (a) the unit is environment-free by design (line 29 "DO NOT add Environment=…") and (b) `huggingface_hub` latches `HF_HUB_OFFLINE` at import time. This test pins that decision: if someone later "tidies up" by moving the vars elsewhere, the test forces a conscious decision + a corresponding test update.
- **Scope discipline.** S2 only adds the static drift-guard. It does NOT touch `launch_daemon.sh` (S1 owns it), does NOT close the `test_idle_and_gpu.sh` circular-proof gap (S3 owns it), and does NOT edit `install.sh` (T2) or README/ACCEPTANCE (M3).

## What

Append to `tests/test_systemd_unit.py`: (1) a sibling path helper `_launch_daemon_path()` and (2) a test `test_launch_daemon_exports_offline_vars()` that reads `voice_typing/launch_daemon.sh` as text, splits into lines, and asserts via line-anchored regex that both offline exports are present as real directives and precede the `exec "$PY"` line. No runtime behavior change, no config, no API.

### Success Criteria

- [ ] `tests/test_systemd_unit.py` contains a new `_launch_daemon_path()` helper resolving to `Path(__file__).resolve().parent.parent / "voice_typing" / "launch_daemon.sh"`.
- [ ] `tests/test_systemd_unit.py` contains `test_launch_daemon_exports_offline_vars` with a docstring citing PRD §1 + acceptance §7.8 + bugfix Issue 1 and explaining why this is a *static* check and what regression it prevents.
- [ ] The test passes when the exports exist (current state) and **fails** when either export is removed (mutation-verified).
- [ ] The test does NOT false-pass on the comment prose (line-anchored `^export …` match).
- [ ] Both `=1` and the quoted variants (`="1"`, `='1'`) are accepted.
- [ ] Both exports are asserted to precede `exec "$PY" -m voice_typing.daemon` (line-index check).
- [ ] `.venv/bin/python -m pytest tests/test_systemd_unit.py -v` → 4 passed (3 existing + 1 new).
- [ ] `git diff --name-only` == `tests/test_systemd_unit.py` only.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement S2 from this PRP alone: the exact target file, the exact pattern to mirror (with the existing helpers shown), the exact regex logic, the false-pass trap, and the deterministic validation commands are all specified. The reference implementation in the Implementation Blueprint is copy-ready. No prior knowledge required.

### Documentation & References

```yaml
# THE INPUT CONTRACT — what launch_daemon.sh MUST contain (S1's deliverable)
- file: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/P1M1T1S1/PRP.md
  why: Defines the verbatim strings S1 produced: `export HF_HUB_OFFLINE=1` and
       `export TRANSFORMERS_OFFLINE=1`, positioned before `exec "$PY" -m voice_typing.daemon "$@"`.
       S1's "REGRESSION GUARDS" section explicitly says S2 will grep for these verbatim strings.
  critical: "S1 is ALREADY APPLIED in the live file (exports at L71-72, exec at L74). So the new
       test is expected to PASS on first run. Treat the S1 PRP as the source of truth for the
       exact export strings the test greps for."

# THE FILE UNDER TEST
- file: voice_typing/launch_daemon.sh
  why: 74-line bash wrapper. Offline exports at L71-72; `exec "$PY" -m voice_typing.daemon "$@"`
       at L74. The WHY comment block at L60-70 mentions `HF_HUB_OFFLINE=1` IN PROSE (e.g. L62).
  pattern: "Real directives begin with `export `; comment prose begins with `#`. The drift-guard
           MUST distinguish them (see Gotcha #1 — the false-pass trap)."
  gotcha: "L62/L66 contain `HF_HUB_OFFLINE=1` inside `#` comments. A substring `in text` check
           would pass even with the real export deleted. Use a line-anchored `^export …` regex."

# THE FILE BEING EDITED — the exact pattern to mirror
- file: tests/test_systemd_unit.py
  why: 95-line drift-guard module. `_unit_path()` (path helper), `_unit_lines()` (text→directive
       lines), 3 existing tests each with a rationale docstring. The new test + helper follow this
       style verbatim.
  pattern: "`from __future__ import annotations`; `from pathlib import Path`; path helper returns
           `Path(__file__).resolve().parent.parent / <subdir> / <file>`; each test docstring cites
           the PRD/issue + the regression it prevents + why it is static."
  gotcha: "Do NOT overload `_unit_path()` (it is semantically the systemd unit). Add a SIBLING
           helper `_launch_daemon_path()` for the wrapper."

# SCOUT RESEARCH — the recommended new-test opportunity (§5)
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/architecture/scout_launch_status_install.md
  why: §5 documents the existing test_systemd_unit.py pattern and recommends exactly this new test:
       "`read_text()` on launch_daemon.sh, assert it contains `export HF_HUB_OFFLINE=1` and
       `export TRANSFORMERS_OFFLINE=1`." §6 documents the S3 masking (test_idle_and_gpu.sh:206).
  section: "§5 (drift-guard test pattern) is the load-bearing section for S2."

# THIS SUBTASK'S OWN RESEARCH NOTE — the false-pass trap + verified line numbers
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/P1M1T1S2/research/drift_guard_test_findings.md
  why: Empirically verifies the live line numbers (exports L71-72, exec L74), the comment-prose
       false-pass trap, the quote-variant requirement, pytest 9.1.1 + no-special-config, and the
       mutation-test procedure that proves the guard works.
  section: "§2 (false-pass trap) and §6 (ordering mechanics) are load-bearing."

# PRD CONTEXT (READ-ONLY) — the requirement this guard protects
- file: PRD.md
  why: §1 ("100% local. No network calls at runtime") + §7 acceptance criterion 8 ("No network
       access needed at runtime, models cached by install"). The test docstring cites these.
  critical: "The drift-guard protects a definition-of-done criterion. Cite §1 + §7.8 in the
            docstring so a future reader understands WHY the export strings are load-bearing."

# SCOPE-BOUNDARY references (owned by SIBLING subtasks — do NOT touch)
- file: tests/test_idle_and_gpu.sh
  why: Line 206 `export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` is the G-OFFLINE masking that hid
       Issue 1. S3 (P1.M1.T1.S3) closes that circular-proof gap. S2 does NOT touch this file.
- file: voice_typing/launch_daemon.sh
  why: Owned by S1. S2 only READS it (read_text). Do NOT edit it. (The mutation-test in Validation
       L3 temporarily edits + restores via git checkout — that is a transient validation step, not
       a committed change.)
```

### Current Codebase tree (relevant slice — S1 already applied)

```bash
/home/dustin/projects/voice-typing/
├── tests/
│   └── test_systemd_unit.py     # 95 lines, 3 tests — the ONLY file S2 edits (append helper + test)
├── voice_typing/
│   └── launch_daemon.sh         # READ-ONLY for S2. S1 applied: exports at L71-72, exec at L74.
├── systemd/voice-typing.service # untouched
└── .venv/bin/pytest             # pytest 9.1.1 (declared pyproject: pytest>=9.1.1)
```

### Desired Codebase tree with files to be changed

```bash
tests/test_systemd_unit.py   # MODIFY: +_launch_daemon_path() helper +test_launch_daemon_exports_offline_vars
                             #          (+ optional 1-line module-docstring touch-up to mention the wrapper).
# NOTHING ELSE. No new files. No edits to launch_daemon.sh / the unit / daemon.py / install.sh / README.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE FALSE-PASS TRAP. The WHY comment block in launch_daemon.sh (lines 60-70)
# mentions `HF_HUB_OFFLINE=1` in PROSE, e.g. line 62:
#     "# daemon loads them from cache with ZERO network. HF_HUB_OFFLINE=1 makes huggingface_hub"
# A naive `assert "HF_HUB_OFFLINE=1" in text` would PASS even if the real `export HF_HUB_OFFLINE=1`
# directive (L71) were DELETED — because the comment still contains the substring. That makes the
# drift-guard useless (it would not catch the regression it exists for). This is the SAME class of
# masking failure that let bugfix Issue 1 ship.
# FIX: the presence assertion MUST be a line-by-line match anchored to `^export ` so it matches
# ONLY a real directive (comments start with `#`, never `export`). See Implementation Blueprint.
# VALIDATE the trap is avoided: Validation L3 (mutation test) — delete an export, confirm RED.

# CRITICAL #2 — ORDERING IS LOAD-BEARING. Env vars are read by the kernel at execve(2) when
# `exec "$PY" -m voice_typing.daemon "$@"` replaces the process. An export placed AFTER exec runs
# in the wrong (replaced) process and never reaches python/huggingface_hub. The test MUST assert
# both export lines precede the exec line (line-index check). (Same reason S1's L2 gate exists.)

# CRITICAL #3 — `exec "$PY"` IS LITERAL BASH. The file literally contains the 4 chars `$PY`
# (a bash variable reference), not an expansion. In a Python string, `'exec "$PY"'` is correct
# (no escaping needed — `$` is ordinary in a Python string literal). A regex needs `\$` to mean
# a literal dollar. Do not "fix" the dollar.

# GOTCHA #4 — ACCEPT QUOTE VARIANTS. The contract requires accepting `=1`, `="1"`, and `='1'`
# for BOTH vars. The live file uses bare `=1`; tolerate future quoting via regex alternation
# `(?:1|"1"|\'1\')`. Do NOT over-tighten to bare `=1` only or the test breaks on a harmless
# future reformat.

# GOTCHA #5 — SIBLING HELPER, NOT OVERLOAD. `_unit_path()` is semantically the systemd UNIT.
# Add a NEW `_launch_daemon_path()` helper (same `Path(__file__).resolve().parent.parent / …`
# idiom) for the wrapper. Reusing/overloading `_unit_path` would mislead future readers.

# GOTCHA #6 — pytest HAS NO SPECIAL CONFIG. There is no [tool.pytest.ini_options], no pytest.ini,
# no conftest.py. Tests are plain module-level functions; collection is automatic. Run with the
# FULL PATH `.venv/bin/python -m pytest tests/test_systemd_unit.py -v` (machine aliases python3→uv run).

# GOTCHA #7 — DO NOT TOUCH launch_daemon.sh AS A COMMITTED CHANGE. S1 owns it. S2 only reads it.
# The Validation L3 mutation step temporarily edits it to prove the guard works, then RESTORES via
# `git checkout voice_typing/launch_daemon.sh`. The final git diff must show ONLY the test file.

# GOTCHA #8 — DON'T DUPLICATE S3's WORK. The circular-proof gap in test_idle_and_gpu.sh:206 (the
# G-OFFLINE pre-set) is S3's to close. S2 is the STATIC wrapper-content guard only. Keep them
# separate so each guard is independently auditable.

# GOTCHA #9 — full-path discipline. `.venv/bin/python -m pytest …`; never bare `python`/`pytest`
# (zsh aliases python3→uv run on this machine). `bash`, `grep`, `git` are fine as-is.
```

## Implementation Blueprint

### Data models and structure

None. This is a pure-test subtask: one helper function + one test function (both module-level, no classes, no fixtures). The only "structure" is the regex contract:

```python
import re
# Real directive only (line-anchored); tolerates bare/quoted value. Never matches comment prose.
_HF_RE  = re.compile(r'^export\s+HF_HUB_OFFLINE=(?:1|"1"|\'1\')\s*$')
_TF_RE  = re.compile(r'^export\s+TRANSFORMERS_OFFLINE=(?:1|"1"|\'1\')\s*$')
_EXEC_RE = re.compile(r'^exec\s+"\$PY"\s+-m\s+voice_typing\.daemon')   # literal "$PY" in the file
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: ADD the sibling path helper to tests/test_systemd_unit.py
  - PLACE: directly under the existing `_unit_lines()` definition (keeps the path/text helpers
    grouped, before the test functions).
  - CODE (verbatim):
        def _launch_daemon_path() -> Path:
            # voice_typing/launch_daemon.sh — repo root is the parent of tests/.
            return Path(__file__).resolve().parent.parent / "voice_typing" / "launch_daemon.sh"
  - WHY a sibling (not an overload of _unit_path): _unit_path is semantically the systemd unit;
    a dedicated helper keeps the two drift-guard targets self-documenting.

Task 2: ADD the test function test_launch_daemon_exports_offline_vars
  - PLACE: after the existing `test_restart_on_failure` function (append at end of file).
  - CODE (reference implementation — copy-ready; the docstring + regex are the load-bearing parts):
        def test_launch_daemon_exports_offline_vars():
            """launch_daemon.sh must export HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1 BEFORE exec.

            Static drift guard for bugfix Issue 1 (PRD §1 "100% local" + acceptance §7.8). The
            production daemon phones home to https://huggingface.co on every startup unless
            HF_HUB_OFFLINE=1 is in the process environment before python starts (huggingface_hub
            latches the flag at import time). S1 put both exports in launch_daemon.sh — the
            sanctioned single source for the daemon env (same place LD_LIBRARY_PATH lives), inherited
            by both `systemctl` starts and manual launches. This test FAILS if either export is
            removed or moved after `exec`, so the "100% local" guarantee cannot silently regress.

            This is a STATIC check (read_text + line regex), not a live-systemd or runtime test:
            it is fast, needs no GPU/models/network, and runs on every commit. It guards the
            configurational precondition; the runtime no-network proof is test_idle_and_gpu.sh
            (S3 removes its pre-set masking so it exercises the real production path).

            Accepts bare `=1` and the quoted variants `="1"` / `='1'` so a harmless future reformat
            does not break the guard. Line-anchored on `^export ` so the WHY comment block (which
            mentions HF_HUB_OFFLINE=1 in prose) cannot cause a false pass.
            """
            lines = _launch_daemon_path().read_text().splitlines()

            hf_idx = next((i for i, ln in enumerate(lines) if _HF_RE.match(ln)), None)
            tf_idx = next((i for i, ln in enumerate(lines) if _TF_RE.match(ln)), None)
            assert hf_idx is not None, (
                "launch_daemon.sh is missing `export HF_HUB_OFFLINE=1` — the offline guarantee "
                "(bugfix Issue 1; PRD §1/§7.8) must be exported before exec."
            )
            assert tf_idx is not None, (
                "launch_daemon.sh is missing `export TRANSFORMERS_OFFLINE=1` — belt-and-suspenders "
                "offline var (bugfix Issue 1); both vars are required."
            )

            exec_idx = next((i for i, ln in enumerate(lines) if _EXEC_RE.match(ln)), None)
            assert exec_idx is not None, (
                "launch_daemon.sh has no `exec \"$PY\" -m voice_typing.daemon` line — cannot verify "
                "export ordering."
            )
            # Env vars are read at execve(2); exports MUST precede exec or they never reach python.
            assert hf_idx < exec_idx, (
                f"`export HF_HUB_OFFLINE=1` (line {hf_idx + 1}) must precede "
                f"`exec \"$PY\" …` (line {exec_idx + 1})."
            )
            assert tf_idx < exec_idx, (
                f"`export TRANSFORMERS_OFFLINE=1` (line {tf_idx + 1}) must precede "
                f"`exec \"$PY\" …` (line {exec_idx + 1})."
            )
  - CONSTRAINTS:
      * Define the module-level `_HF_RE`, `_TF_RE`, `_EXEC_RE` regexes near the top of the file
        (after the `from pathlib import Path` import; add `import re`). OR compile them inline in
        the test — either is acceptable; module-level constants match the file's clean style.
      * Do NOT use a substring `in text` assertion (Gotcha #1 — false-pass trap).
      * Do NOT overload `_unit_path()` (Gotcha #5).
      * Keep the 3 existing tests byte-identical.

Task 3: (OPTIONAL, recommended) TOUCH UP the module docstring
  - The module docstring currently says "Drift guard for systemd/voice-typing.service …". After
    adding a launch_daemon.sh test, append one sentence so the docstring stays accurate, e.g.:
    "Also drift-guards voice_typing/launch_daemon.sh's offline env exports (bugfix Issue 1)."
  - This is polish, not required for the success criteria; skip if it risks scope creep.

Task 4: VALIDATE — run the Validation Loop L1–L4 below. No git commit unless the orchestrator
  directs it. If asked to commit, message:
  "P1.M1.T1.S2: add static drift-guard test for launch_daemon.sh offline exports (Issue 1)".
```

### Implementation Patterns & Key Details

```python
# The single most important design decision: the presence check is LINE-ANCHORED, not substring.
# This is what makes the guard real instead of theatre.

# WRONG (false-pass trap — the comment block at L60-70 contains "HF_HUB_OFFLINE=1" in prose):
#   text = _launch_daemon_path().read_text()
#   assert "HF_HUB_OFFLINE=1" in text          # passes even with the real export DELETED

# RIGHT (matches only a real directive; comment prose starts with '#'):
import re
_HF_RE = re.compile(r'^export\s+HF_HUB_OFFLINE=(?:1|"1"|\'1\')\s*$')
lines = _launch_daemon_path().read_text().splitlines()
hf_idx = next((i for i, ln in enumerate(lines) if _HF_RE.match(ln)), None)
assert hf_idx is not None, "missing real `export HF_HUB_OFFLINE=1` directive"

# Ordering: env read at execve(2), so exports must precede the exec line by source-line index.
_EXEC_RE = re.compile(r'^exec\s+"\$PY"\s+-m\s+voice_typing\.daemon')
exec_idx = next((i for i, ln in enumerate(lines) if _EXEC_RE.match(ln)), None)
assert exec_idx is not None and hf_idx < exec_idx, "export must precede exec"
# (1-based line numbers in the assertion message aid debugging: f"line {hf_idx + 1}".)
```

### Integration Points

```yaml
TEST SUITE:
  - The new test joins the existing 3 in tests/test_systemd_unit.py. Collection is automatic (no
    conftest/pytest config). `pytest tests/test_systemd_unit.py -v` → 4 passed. The full suite
    (`pytest tests/ -v` excluding the shell-based .sh scripts) must remain green — S2 only ADDS a
    test, so no existing test can regress.

DEPENDS ON (S1 — P1.M1.T1.S1):
  - S2's test PASSES only because S1 put the verbatim export strings in launch_daemon.sh. S1 is
    already applied (exports at L71-72). If a future change reverts S1, S2's test goes RED — which
    is exactly the intended behavior. The two subtasks form a fix+guard pair.

DOWNSTREAM (S3 — P1.M1.T1.S3):
  - S2 is the STATIC configurational guard (exports present in the wrapper). S3 is the RUNTIME
    guard (production-path journal grep for 'HTTP Request: GET https://huggingface.co' after a real
    launch, without pre-setting the vars). Together they close the circular-proof gap end-to-end.
    S2 does not depend on S3 and vice versa; they are independently auditable.

FILES NOT TOUCHED (scope boundary):
  - voice_typing/launch_daemon.sh (S1 owns; S2 reads only).
  - tests/test_idle_and_gpu.sh (S3 owns).
  - systemd/voice-typing.service, voice_typing/daemon.py, install.sh, README.md, ACCEPTANCE.md
    (later subtasks / milestones).
```

## Validation Loop

> All commands use FULL PATHS (machine aliases python3→uv run). Run from
> `/home/dustin/projects/voice-typing`. All gates are fast/static (no GPU/models/network).

### Level 1: Syntax + collection (the new test is well-formed and discovered)

```bash
cd /home/dustin/projects/voice-typing
echo "--- Python parses the edited file ---"
.venv/bin/python -c "import ast; ast.parse(open('tests/test_systemd_unit.py').read()); print('L1a PASS: parses')"
echo "--- pytest discovers exactly 4 tests (3 existing + 1 new) ---"
.venv/bin/python -m pytest tests/test_systemd_unit.py --collect-only -q | tail -5
grep -q 'test_launch_daemon_exports_offline_vars' <(.venv/bin/python -m pytest tests/test_systemd_unit.py --collect-only -q) \
  && echo "L1b PASS: new test collected" || echo "L1b FAIL: new test not collected"
# Expected: L1a parses; collection lists 4 items including test_launch_daemon_exports_offline_vars.
```

### Level 2: The new test PASSES against the current (S1-applied) launch_daemon.sh

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_systemd_unit.py -v
echo "exit: $?"
# Expected: 4 passed (incl. test_launch_daemon_exports_offline_vars PASSED). exit 0.
# If the new test FAILS here, S1's exports are absent or mis-ordered — re-check launch_daemon.sh
# (should have `export HF_HUB_OFFLINE=1` + `export TRANSFORMERS_OFFLINE=1` before the exec line).
```

### Level 3: The guard ACTUALLY guards (mutation test — the load-bearing proof)

> This proves the test catches the regression AND is not a false-pass trap. It temporarily edits
> `launch_daemon.sh` (owned by S1) and RESTORES it afterward — the final diff must be clean.

```bash
cd /home/dustin/projects/voice-typing
cp voice_typing/launch_daemon.sh /tmp/launch_daemon.sh.bak   # safety backup

echo "--- 3a: delete the HF_HUB_OFFLINE export (keep the comment block) → test must FAIL ---"
# Remove only the real directive line; leave the WHY comment block (which mentions the var in prose).
sed -i '/^export HF_HUB_OFFLINE=1$/d' voice_typing/launch_daemon.sh
.venv/bin/python -m pytest tests/test_systemd_unit.py::test_launch_daemon_exports_offline_vars -v
echo "exit after HF removal: $? (expect NON-zero / failed)"
# Expected: test FAILS. If it still PASSES, the test is a false-pass trap (Gotcha #1) — fix the regex
# to be line-anchored `^export …` before proceeding.

echo "--- 3b: restore, then delete the TRANSFORMERS_OFFLINE export → test must FAIL ---"
cp /tmp/launch_daemon.sh.bak voice_typing/launch_daemon.sh
sed -i '/^export TRANSFORMERS_OFFLINE=1$/d' voice_typing/launch_daemon.sh
.venv/bin/python -m pytest tests/test_systemd_unit.py::test_launch_daemon_exports_offline_vars -v
echo "exit after TF removal: $? (expect NON-zero / failed)"
# Expected: test FAILS.

echo "--- 3c (optional): restore, move an export AFTER exec → test must FAIL (ordering guard) ---"
cp /tmp/launch_daemon.sh.bak voice_typing/launch_daemon.sh
# (Construct an after-exec variant only if trivial; otherwise rely on 3a/3b as sufficient proof.)

echo "--- 3d: RESTORE launch_daemon.sh to S1 state and confirm GREEN ---"
cp /tmp/launch_daemon.sh.bak voice_typing/launch_daemon.sh
git diff --quiet voice_typing/launch_daemon.sh && echo "L3d PASS: launch_daemon.sh restored to S1 state" || echo "L3d FAIL: launch_daemon.sh differs from git — run 'git checkout voice_typing/launch_daemon.sh'"
.venv/bin/python -m pytest tests/test_systemd_unit.py -v
# Expected: 4 passed; launch_daemon.sh byte-identical to git (S1 state). The mutation left no trace.
rm -f /tmp/launch_daemon.sh.bak
```

### Level 4: Scope + suite integrity (only the test file changed; nothing else regressed)

```bash
cd /home/dustin/projects/voice-typing
echo "--- git diff touches ONLY tests/test_systemd_unit.py ---"
git diff --name-only | grep -vxE 'tests/test_systemd_unit.py' && echo "L4 FAIL: out-of-scope file changed" || echo "L4 PASS: only tests/test_systemd_unit.py changed"
echo "--- confirm sibling-scope files are UNTOUCHED ---"
git diff --quiet voice_typing/launch_daemon.sh systemd/voice-typing.service tests/test_idle_and_gpu.sh install.sh \
  && echo "L4 PASS: launch_daemon.sh/unit/test_idle_and_gpu.sh/install.sh unchanged" \
  || echo "L4 FAIL: a sibling-scope file was modified"
echo "--- broader suite still green (python tests; the .sh scripts are run separately) ---"
.venv/bin/python -m pytest tests/test_systemd_unit.py tests/test_textproc.py tests/test_config.py -q
# Expected: all pass. (Run the full tests/ suite per project convention if desired; S2 is additive.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: edited `tests/test_systemd_unit.py` parses; pytest collects 4 tests incl. `test_launch_daemon_exports_offline_vars`.
- [ ] L2: `pytest tests/test_systemd_unit.py -v` → 4 passed (new test green against S1-applied wrapper).
- [ ] L3: mutation test — deleting either export turns the new test RED; deleting HF does NOT false-pass via the comment prose; wrapper restored to S1 state (clean git diff).
- [ ] L4: `git diff --name-only` == `tests/test_systemd_unit.py`; sibling-scope files unchanged.

### Feature Validation
- [ ] The new test asserts BOTH `export HF_HUB_OFFLINE=1` and `export TRANSFORMERS_OFFLINE=1` as real directives (line-anchored regex).
- [ ] Both `=1` and quoted variants (`="1"`, `='1'`) accepted.
- [ ] Both exports asserted to precede `exec "$PY" -m voice_typing.daemon` (line-index check; env read at execve).
- [ ] The test's docstring cites PRD §1 + acceptance §7.8 + bugfix Issue 1 and explains why it is a *static* check + the regression it prevents.

### Code Quality Validation
- [ ] New `_launch_daemon_path()` sibling helper follows the `_unit_path()` idiom (does NOT overload it).
- [ ] Follows existing file conventions: `from __future__ import annotations`, `from pathlib import Path`, descriptive assertion messages.
- [ ] No substring `in text` false-pass trap (Gotcha #1 verified absent via L3 mutation).
- [ ] The 3 existing tests are byte-identical (append-only change).

### Scope Boundary Validation
- [ ] `voice_typing/launch_daemon.sh` unmodified as a committed change (read-only; L3 mutation restored).
- [ ] `tests/test_idle_and_gpu.sh` unmodified (S3 owns the circular-proof-gap fix).
- [ ] `systemd/voice-typing.service`, `voice_typing/daemon.py`, `install.sh`, `README.md`, `ACCEPTANCE.md` unmodified.
- [ ] No bare `python`/`pytest` in any command (full-pathed `.venv/bin/python -m pytest`).

### Documentation & Deployment
- [ ] (No user-facing docs — test-only subtask.) The test docstring is the durable explanation.
- [ ] If asked to commit: message references bugfix Issue 1 for traceability.

---

## Anti-Patterns to Avoid

- ❌ Don't use a substring `in text` presence check — the comment block mentions `HF_HUB_OFFLINE=1` in prose and would cause a **false pass** even with the real export deleted (the exact masking failure that let Issue 1 ship). Use a line-anchored `^export …` regex. (Gotcha #1; verified by L3.)
- ❌ Don't skip the ordering assertion — env vars are read at `execve(2)`, so an export after `exec` never reaches python/huggingface_hub. The line-index check (`hf_idx < exec_idx`, `tf_idx < exec_idx`) is load-bearing.
- ❌ Don't overload `_unit_path()` — it is semantically the systemd unit. Add a sibling `_launch_daemon_path()`.
- ❌ Don't over-tighten the value match to bare `=1` only — the contract requires accepting `="1"` and `='1'` too (a harmless future reformat must not break the guard).
- ❌ Don't "fix" the `$PY` in the exec-line regex — it is literal bash (`$` ordinary in a Python string, `\$` in regex). `'exec "$PY"'` is correct.
- ❌ Don't edit `launch_daemon.sh` as a committed change — S1 owns it. The L3 mutation is a transient validation step, restored via `cp`/`git checkout`.
- ❌ Don't touch `tests/test_idle_and_gpu.sh` — closing its G-OFFLINE circular-proof gap is S3's job. S2 is the static wrapper-content guard only.
- ❌ Don't add runtime/live-systemd/network assertions to this test — it is deliberately a fast static check. The runtime proof belongs to S3.
- ❌ Don't use bare `python`/`pytest` (zsh aliases python3→uv run); use `.venv/bin/python -m pytest`.
- ❌ Don't modify `install.sh` (T2), `README.md`/`ACCEPTANCE.md` (M3), the systemd unit, or `daemon.py`.

---

## Confidence Score

**9.5/10** for one-pass implementation success. This is a small, fully-specified test addition with a copy-ready reference implementation. Every load-bearing fact is empirically verified against the live repo: S1's exports are already present (L71-72, exec L74), the existing `test_systemd_unit.py` pattern is read in full, the false-pass trap is concretely demonstrated (comment block mentions the var in prose), pytest 9.1.1 + no-special-config is confirmed, and the exact regex/line-index logic is given. The deterministic L1+L2 gates prove the test is well-formed and green; the L3 mutation test proves it actually catches the regression (and is not a false-pass trap) — which is the whole point of a drift guard. The −0.5 is solely that L3's mutation step temporarily edits a sibling-owned file (launch_daemon.sh) and must be meticulously restored; a careless restoration would leave a stray diff (mitigated by the explicit `cp` backup + `git diff --quiet` check in L3d/L4).
