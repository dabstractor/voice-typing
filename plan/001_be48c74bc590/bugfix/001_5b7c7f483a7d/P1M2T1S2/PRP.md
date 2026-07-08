# PRP — P1.M2.T1.S2: Harden `test_ctl_module_present_and_imports_pure` to be order-independent

## Goal

**Feature Goal**: Rewrite `tests/test_voicectl.py::test_ctl_module_present_and_imports_pure` so it tests `voice_typing.ctl`'s **own** import behavior in **isolation**, not the global `sys.modules` state of the pytest process. Today the test asserts `not [m for m in ("RealtimeSTT","torch","ctranslate2") if m in sys.modules]` — a **global** check that passes or fails depending on which tests ran *before* it (the bugfix Issue 4 order-dependence). Replace that assertion with a **child-process** probe: spawn a fresh interpreter that imports only `voice_typing.ctl` and asserts no heavy deps appear in *its* `sys.modules`. This is order-independent by construction — a fresh interpreter's `sys.modules` is unaffected by anything the parent pytest session imported.

**Deliverable** (test-only; 2 edits to ONE existing file, no new files):
1. `tests/test_voicectl.py` —
   - **Edit A**: add `import subprocess` to the stdlib import block (it is not currently imported).
   - **Edit B**: rewrite the body of `test_ctl_module_present_and_imports_pure` (lines 200-203) to spawn the subprocess probe instead of asserting on the parent's global `sys.modules`.

**Success Definition**:
- (a) `test_ctl_module_present_and_imports_pure` passes whether run **alone**, **first**, or **after a test that deliberately pollutes `sys.modules`** with `RealtimeSTT`/`torch`/`ctranslate2`. (The defining property of this fix.)
- (b) The test still **bites**: if `voice_typing.ctl` (or a transitive import) ever pulls in a heavy dep, the test fails loudly (negative control verified — see Validation L2).
- (c) `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → **0 failed** (currently green via S1; this task must not regress it).
- (d) No source files (`ctl.py`, `daemon.py`, `cuda_check.py`, …) are touched; `test_daemon.py` is NOT touched (S1 owns it); no new tests/fixtures/files/imports beyond the one `import subprocess`.

## User Persona

Not applicable (test-only change; no user-facing/config/API/doc surface — item DOCS: "none"). The beneficiary is the **maintainer/CI**: a test that no longer flips red/green based on collection order, so `pytest tests/` is trustworthy.

## Why

- **The documented fast suite must stay green regardless of order.** PRD §6/§7.1 acceptance and every test module's docstring point users at `pytest tests/`. A purity test that fails when a *different* module runs first is a false alarm that trains maintainers to ignore red suites. (bugfix Issue 4.)
- **Defense-in-depth with the sibling fix.** P1.M2.T1.S1 removes the pollution at its source (monkeypatches the resolver in the 4 offending `test_daemon.py` tests). That is necessary but **not sufficient**: any *future* test that imports a heavy dep — or a contributor who hasn't applied S1-style hermeticity — re-breaks the global assertion. This task makes the purity test **robust by design** so it cannot be re-broken by anything outside `test_voicectl.py`. The two tasks are complementary (different files, no overlap).
- **Assert the real invariant, not a proxy.** The test's NAME and docstring claim "importing `voice_typing.ctl` is pure." The global assertion does not actually check that — it checks "the whole process is currently clean," which is a weaker, environment-dependent proxy. The subprocess probe checks the claimed invariant directly: "a fresh interpreter that imports `voice_typing.ctl` stays clean."
- **Small, surgical, GPU-free.** One test function rewritten + one stdlib import. No subprocess cost concern (one ~50–100 ms spawn in a ~4 s / 246-test suite). Validated entirely with pytest + a one-liner proof.

## What

Make two edits to `tests/test_voicectl.py` (verbatim in Implementation Blueprint):

**Edit A** — add `import subprocess` to the stdlib import group (alphabetical: `importlib.util`, `subprocess`, `sys`).

**Edit B** — replace the global-`sys.modules` assertion in `test_ctl_module_present_and_imports_pure` with a `subprocess.run([sys.executable, "-c", probe], ...)` that imports `voice_typing.ctl` in a fresh child and asserts the child's `sys.modules` contains none of `RealtimeSTT`/`torch`/`ctranslate2`. Keep the cheap `importlib.util.find_spec("voice_typing.ctl")` precondition (it documents the "module present" half of the test name and has no heavy import side-effect). On failure, the assertion message includes the child's returncode + stdout + stderr for fast diagnosis.

### Success Criteria

- [ ] `tests/test_voicectl.py` has `import subprocess` in its top stdlib import block.
- [ ] `test_ctl_module_present_and_imports_pure` uses `subprocess.run([sys.executable, "-c", ...])` and asserts `result.returncode == 0`; it no longer references the parent's `sys.modules` for the purity check.
- [ ] The test passes run **alone**: `.venv/bin/python -m pytest tests/test_voicectl.py::test_ctl_module_present_and_imports_pure -q`.
- [ ] The test passes run **after deliberate pollution** of the parent `sys.modules` (order-independence proof — Validation L2).
- [ ] The test **bites**: a probe that imports a heavy dep fails with nonzero returncode (negative control — Validation L2).
- [ ] `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → `0 failed`.
- [ ] `git status --short` shows ONLY `tests/test_voicectl.py` modified. No source file, no `test_daemon.py`, no `pyproject.toml`/`uv.lock`/`.gitignore`/`PRD.md`/`tasks.json`/`prd_snapshot.md` change.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement it from this PRP + the referenced research. The defect is explained (global vs isolated `sys.modules`), the **wrong** fix (in-process snapshot) is ruled out with a concrete reason (it is a tautology here — see Gotcha #1), the correct fix (subprocess) is given verbatim and was verified live (child import is pure; the test bites on pollution; CWD/editable-install robust), and both edits are exact `oldText→newText` against the current file. The one-liner order-independence proof is in Validation L2.

### Documentation & References

```yaml
# MUST READ — the defect, the tautology trap, the verified subprocess fix (load-bearing)
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T1S2/research/order_independent_purity_test.md
  why: "§1 the defect (global sys.modules assertion). §2 ctl.py IS genuinely pure (the real invariant).
        §3 WHY the in-process snapshot is a tautology here (ctl is already imported at test-module load ->
        'added' is always empty -> false green) -> do NOT use it. §4 the subprocess approach, verified live
        (pure from repo root AND /tmp; bites on RealtimeSTT; -c not a temp file; cost/flakiness). §5 exact edit
        sites. §6 scope boundaries vs S1."
  section: "ALL load-bearing. §3 (tautology) and §4 (subprocess proof) are the core."

# MUST READ — the test being rewritten (exact current text + line numbers)
- file: tests/test_voicectl.py
  why: "Lines 13-14 are the stdlib import block (Edit A inserts 'import subprocess'). Lines 200-203 are
        test_ctl_module_present_and_imports_pure (Edit B target). Line 22 'from voice_typing import ctl,
        daemon' is WHY ctl is already cached at test time (the tautology root cause). The module docstring
        documents the three test layers; this test is in the 'argparse / structural' group."
  critical: "Match Edit B's oldText EXACTLY (4 lines: def + comment + 2 asserts). The file is imported by
             pytest collection; do not change any OTHER test. importlib.util is STILL used after the rewrite
             (the find_spec precondition stays) so its import is retained."

# MUST READ — the sibling fix (no overlap; complementary defense-in-depth)
- file: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T1S1/PRP.md
  why: "S1 edits tests/test_daemon.py (monkeypatches cuda_check.resolve_device_and_models in 4 polluting
        tests). It explicitly leaves test_voicectl.py to THIS task (S2). Together: no pollution source AND an
        order-independent purity test. Confirm S1's contract: it does NOT touch test_voicectl.py, so no edit
        conflict."
  critical: "Do NOT edit test_daemon.py (S1 owns it). The two tasks touch DIFFERENT files; there is no
             merge conflict. S1's success (fast suite green) is the baseline this task must preserve."

# THE MODULE UNDER TEST — confirms it is genuinely pure (the invariant the test asserts)
- file: voice_typing/ctl.py
  why: "Top imports: argparse, json, socket, sys + 'from voice_typing.daemon import _default_control_socket_path'.
        grep for RealtimeSTT|torch|ctranslate2 -> NONE. daemon.py has no MODULE-LEVEL heavy imports (lazy). So
        'import voice_typing.ctl' in a fresh process leaves sys.modules clean — the subprocess probe passes."
  critical: "If ctl.py (or a future change to it) ever adds a module-level heavy import, this test WILL
             correctly fail (that is the point). Do NOT weaken the probe to mask a real future regression."

# THE POLLUTION SOURCE (context only — NOT edited here)
- file: voice_typing/cuda_check.py
  why: "resolve_device_and_models() -> is_cuda_available() -> _cuda_device_count() does 'import ctranslate2'
        (-> torch). That is what test_daemon.py imported (pre-S1) and what this test guards against as a
        transitive import of ctl. ctl does NOT import cuda_check, so ctl stays pure."
  critical: "This file is OUT OF SCOPE. S1 handles the daemon tests' use of it. This task only rewrites the
             purity assertion."

# THE DEFECT (Issue 4) + the option-(b) decision this task implements
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/prd_snapshot.md
  why: "§2.3 Issue 4 suggested fix (b): 'make test_ctl_module_present_and_imports_pure robust by checking that
        importing voice_typing.ctl does not add heavy modules (snapshot sys.modules before/after the import,
        rather than asserting global absence).' This PRP implements (b) via the MORE ROBUST subprocess form
        (the snapshot form is a tautology here — research §3)."
  critical: "The PRD text literally says 'snapshot sys.modules before/after'. That wording is the IN-PROCESS
             form, which is a tautology because ctl is pre-imported. The item description itself flags the
             subprocess approach as 'the most robust' — implement the subprocess form, NOT the literal snapshot."
```

### Current Codebase tree (relevant slice — the only file this task edits)

```bash
/home/dustin/projects/voice-typing/
├── tests/
│   ├── test_voicectl.py   # EDIT (Edit A: +import subprocess; Edit B: rewrite test_ctl_module_present_and_imports_pure).
│   └── test_daemon.py     # OUT OF SCOPE (P1.M2.T1.S1). Do NOT edit.
└── voice_typing/
    ├── ctl.py             # UNCHANGED. Stdlib-only; the pure module under test.
    ├── daemon.py          # UNCHANGED. ctl imports only _default_control_socket_path from it; no module-level heavy imports.
    └── cuda_check.py      # UNCHANGED. The historical polluter (ctranslate2); NOT imported by ctl.
# No new files. No source edits. No pyproject/uv.lock/.gitignore changes.
```

### Desired Codebase tree with files to be changed

```bash
tests/test_voicectl.py     # EDIT ONLY — +1 stdlib import (subprocess), 1 test body rewritten.
# NOTHING ELSE. (test_daemon.py = S1; ctl.py/daemon.py/cuda_check.py = source; all out of scope.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DO NOT USE THE IN-PROCESS sys.modules SNAPSHOT. It is a TAUTOLOGY here.
#   tests/test_voicectl.py line 22 does `from voice_typing import ctl, daemon` at MODULE LOAD. So by the time
#   ANY test function runs, `voice_typing.ctl` is ALREADY cached in sys.modules. An in-process
#   `before=set(sys.modules); import voice_typing.ctl; after=set(sys.modules); added=after-before` would make
#   `added` ALWAYS EMPTY (the import is a no-op cache hit) -> the assertion ALWAYS passes, even if ctl.py were
#   changed to `import torch` at module top. That is a FALSE GREEN, strictly worse than today. Use the
#   SUBPROCESS approach (a fresh interpreter has its own sys.modules). (research §3.)

# CRITICAL #2 — THE TEST MUST STILL BITE. The probe asserts `not leaked` IN THE CHILD. Verified live: a probe
#   that does `import RealtimeSTT` first -> child returncode 1, AssertionError 'leaked: [RealtimeSTT]'. So if
#   ctl.py (or a transitive import) ever pulls a heavy dep, this test fails. Do NOT weaken it (e.g. do NOT
#   assert only on a subset of names, do NOT swallow nonzero returncode). (research §4.2 #3.)

# CRITICAL #3 — `sys.executable` IS THE VENV PYTHON. Under pytest it is
#   /home/dustin/projects/voice-typing/.venv/bin/python (never None). The child inherits the venv + env, so
#   `voice_typing` resolves via the EDITABLE INSTALL (verified: probe passes from /tmp too). Do NOT hardcode a
#   python path; do NOT add `-S` (site-packages / editable .pth may be needed in other setups; plain `-c` is
#   correct and matches how the daemon/pytest actually run). (research §4.2 #2.)

# CRITICAL #4 — KEEP `import importlib.util` AND the find_spec LINE. The rewrite still calls
#   `importlib.util.find_spec("voice_typing.ctl")` as a cheap precondition (pure; no heavy import side-effect;
#   documents the "module present" half of the test name). So Edit A ADDS `import subprocess`; it does NOT
#   remove anything. `import sys` is already present (used by [sys.executable, ...] and other tests). (research §5.)

# CRITICAL #5 — THE CHILD PROBE IS A SINGLE -c STRING, not a temp file. `python -c "<probe>"` avoids temp-file
#   cleanup and path juggling. Build it as a Python string concatenation (see Implementation Blueprint) so the
#   f-string asserts the right thing. Use `capture_output=True, text=True, timeout=30` (timeout guards an
#   unforeseen hang; real import is <1 s). (research §4.3.)

# CRITICAL #6 — DO NOT EDIT test_daemon.py. S1 (P1.M2.T1.S1) owns it. This task edits ONLY test_voicectl.py.
#   The two tasks are complementary (S1 = remove pollution source; S2 = order-independent assertion) and touch
#   different files -> no conflict. (research §6.)

# CRITICAL #7 — DO NOT ADD conftest.py / autouse fixtures / new test files. One function rewritten + one
#   import. Adding an autouse fixture would over-reach (change other tests' behavior) and is unnecessary: the
#   subprocess isolation is per-test, self-contained. (research §6.)

# GOTCHA #8 — FULL PATHS in every bash command. This machine aliases python3->uv run, pip->alias, tmux->zsh
#   plugin. Invoke .venv/bin/python and .venv/bin/python -m pytest explicitly. Never bare python/pytest/uv.
#   (system_context.md §1; S1 PRP Gotcha #9.)

# GOTCHA #9 — THIS PROJECT USES pytest, NOT ruff/mypy. pyproject has [dependency-groups] dev=["pytest>=9.1.1"]
#   and NO [tool.ruff]/[tool.mypy]. Do NOT invent ruff/mypy validation commands. Validation = pytest + the L2
#   one-liner proof. (S1 PRP Gotcha #10.)

# GOTCHA #10 — subprocess.run INHERITS the parent CWD. pytest runs from the repo root, so the child CWD is the
#   repo root too. But the probe does NOT rely on that (verified from /tmp via the editable install) — belt-
#   and-suspenders you MAY pass cwd=<repo root>, but it is unnecessary and adds a voice_typing.__file__
#   computation. Prefer the simplest form: no cwd kwarg. (research §4.2 #2.)
```

## Implementation Blueprint

### Data models and structure

None. No schema/config/types change. This is a 1-import-add + 1-test-body-rewrite to a test file, using stdlib `subprocess`/`sys`/`importlib.util`.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT tests/test_voicectl.py — 2 edits in ONE edit call (Edit A: add import; Edit B: rewrite the test)
  - Apply these 2 exact oldText -> newText edits (each oldText is unique in the file):

    EDIT A — add `import subprocess` to the stdlib import block:
      OLD:
        import importlib.util
        import sys
      NEW:
        import importlib.util
        import subprocess
        import sys

    EDIT B — rewrite test_ctl_module_present_and_imports_pure (currently lines 200-203) to use a subprocess:
      OLD:
        def test_ctl_module_present_and_imports_pure():
            # Import purity: importing voice_typing.ctl must NOT pull in RealtimeSTT/torch/ctranslate2.
            assert importlib.util.find_spec("voice_typing.ctl") is not None
            assert not [m for m in ("RealtimeSTT", "torch", "ctranslate2") if m in sys.modules]
      NEW:
        def test_ctl_module_present_and_imports_pure():
            # Import purity, ORDER-INDEPENDENT: a FRESH interpreter importing only voice_typing.ctl
            # must NOT pull in RealtimeSTT/torch/ctranslate2. Asserting in a child process means the
            # result reflects ONLY what ctl itself imports — never what earlier tests left in this
            # process's sys.modules (PRD bugfix Issue 4; defense-in-depth with P1.M2.T1.S1).
            assert importlib.util.find_spec("voice_typing.ctl") is not None
            probe = (
                "import sys, voice_typing.ctl; "
                "leaked = [m for m in ('RealtimeSTT', 'torch', 'ctranslate2') if m in sys.modules]; "
                "assert not leaked, f'voice_typing.ctl transitively imports heavy deps: {leaked}'"
            )
            result = subprocess.run(
                [sys.executable, "-c", probe],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, (
                "fresh interpreter importing voice_typing.ctl leaked heavy deps or failed to import:\n"
                f"--- returncode {result.returncode}\n--- stdout:\n{result.stdout}\n--- stderr:\n{result.stderr}"
            )

  - WHY subprocess (not an in-process snapshot): test_voicectl.py line 22 (`from voice_typing import ctl,
    daemon`) imports ctl at MODULE LOAD, so `voice_typing.ctl` is ALREADY cached when any test runs. An
    in-process `before/after` diff would be empty by definition -> a tautology (false green). The subprocess
    has its OWN sys.modules, so it tests the real invariant regardless of parent state. (research §3-4;
    Gotcha #1.)
  - WHY keep find_spec: cheap, pure (no heavy import), documents the "module present" half of the test name;
    `importlib.util` stays imported. (Gotcha #4.)
  - WHY these subprocess args: capture_output+text capture failure diagnostics; timeout=30 guards a hang;
    sys.executable is the venv python (child resolves voice_typing via the editable install, CWD-independent).
    (Gotchas #3, #5, #10.)
  - DO NOT: use the in-process snapshot form (Gotcha #1); weaken the probe or swallow nonzero returncode
    (Gotcha #2); add `-S` or hardcode a python path (Gotcha #3); edit test_daemon.py (Gotcha #6); add
    conftest/fixtures/new files (Gotcha #7); use bare python/pytest (Gotcha #8); invent ruff/mypy (Gotcha #9).

Task 2: VALIDATE — run the Validation Loop L1-L4 below; fix until all green. No git commit unless the
  orchestrator directs it. If asked, message:
  "P1.M2.T1.S2: harden test_ctl_module_present_and_imports_pure to a subprocess child-process probe (order-independent purity assertion, bugfix Issue 4 defense-in-depth)".
```

### Implementation Patterns & Key Details

```python
# PATTERN — child-process isolation for an import-purity assertion. The PARENT's sys.modules is irrelevant;
# the CHILD imports only the module under test and asserts its OWN sys.modules. Order-independent by construction.
def test_ctl_module_present_and_imports_pure():
    assert importlib.util.find_spec("voice_typing.ctl") is not None   # cheap "module present" precondition
    probe = (
        "import sys, voice_typing.ctl; "                              # the ONLY import under test
        "leaked = [m for m in ('RealtimeSTT', 'torch', 'ctranslate2') if m in sys.modules]; "
        "assert not leaked, f'... {leaked}'"                          # child-side assertion
    )
    result = subprocess.run([sys.executable, "-c", probe],            # fresh interpreter, own sys.modules
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, f"... stderr:\n{result.stderr}"    # child's assertion failure -> nonzero

# ANTI-PATTERN (do NOT use) — the in-process before/after snapshot is a TAUTOLOGY in this file, because
# `from voice_typing import ctl, daemon` (line 22) pre-caches ctl at module load. `added = after - before`
# is always empty -> the test can never fail even if ctl imports torch. (research §3.)
before = set(sys.modules); import voice_typing.ctl; after = set(sys.modules)   # WRONG: added always empty
```

### Integration Points

```yaml
SIBLING — P1.M2.T1.S1 (remove pollution source): COMPLEMENTARY, no overlap.
  - S1 edits tests/test_daemon.py (monkeypatches cuda_check.resolve_device_and_models in 4 tests). This task
    edits tests/test_voicectl.py (the purity assertion). Different files -> no conflict. Together: no pollution
    AND an order-independent purity test. Do NOT touch test_daemon.py here.

UNCHANGED (source):
  - ctl.py (the pure module under test — stdlib + one daemon helper import), daemon.py (no module-level heavy
    imports), cuda_check.py (the historical polluter; not imported by ctl), config.py, typing_backends.py,
    feedback.py, control-socket, install.sh, systemd, launch_daemon.sh, pyproject.toml, uv.lock, .gitignore.

BUILD ARTIFACTS:
  - This task creates NO new files, NO dist/, NO pyproject/uv.lock/.venv changes, NO new deps (subprocess is
    stdlib). Validation = pytest + the L2 one-liner proof. No `uv sync`/`uv build`.
```

## Validation Loop

> Full paths in every command (zsh aliases — Gotcha #8). Run from the repo root `/home/dustin/projects/voice-typing`.
> This project uses pytest (NO ruff/mypy — Gotcha #9). All gates are fast/unit (no real CUDA/model load).

### Level 1: the 2 edits are in place (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- Edit A: 'import subprocess' present in the stdlib import block ---"
grep -nE '^import (importlib\.util|subprocess|sys)$' tests/test_voicectl.py
echo "--- Edit B: the test now uses subprocess + asserts returncode (no parent-sys.modules purity assert) ---"
grep -nE 'def test_ctl_module_present_and_imports_pure' tests/test_voicectl.py
sed -n "/def test_ctl_module_present_and_imports_pure/,/^def /p" tests/test_voicectl.py | head -22
# Expected: the import block lists importlib.util, subprocess, sys; the test body contains
# `subprocess.run([sys.executable, "-c", probe]` and `assert result.returncode == 0`, and does NOT contain
# the old `assert not [m for m in ("RealtimeSTT", "torch", "ctranslate2") if m in sys.modules]` line.
```

### Level 2: ORDER-INDEPENDENCE PROOF + the test bites (the whole point of this fix)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# (a) The test passes run ALONE:
"$PY" -m pytest tests/test_voicectl.py::test_ctl_module_present_and_imports_pure -q
# (b) ORDER-INDEPENDENCE PROOF: fake-pollute the PARENT sys.modules, then show the OLD logic fails but the
#     NEW (subprocess) logic still passes. This does not depend on S1 or any test collection order:
"$PY" - <<'PYEOF'
import subprocess, sys
sys.modules["torch"] = type(sys)("torch")            # simulate a prior test having imported torch
sys.modules["ctranslate2"] = type(sys)("ctranslate2")
old_ok = not [m for m in ("RealtimeSTT", "torch", "ctranslate2") if m in sys.modules]   # OLD global assertion
probe = ("import sys, voice_typing.ctl; "
         "leaked=[m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules]; "
         "assert not leaked, f'leaked: {leaked}'")
r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=30)
print("OLD global-assertion passes under pollution? ", old_ok, "(expect False)")
print("NEW subprocess returncode under pollution?    ", r.returncode, "(expect 0)")
assert old_ok is False and r.returncode == 0, "ORDER-INDEPENDENCE PROOF FAILED"
print("L2b PROOF PASS: old logic is order-dependent; new logic is order-independent")
PYEOF
# (c) THE TEST BITES (negative control): a probe that DOES import a heavy dep must exit nonzero:
"$PY" - <<'PYEOF'
import subprocess, sys
bad = ("import RealtimeSTT; import sys; "
       "leaked=[m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules]; "
       "assert not leaked, f'leaked: {leaked}'")
r = subprocess.run([sys.executable, "-c", bad], capture_output=True, text=True, timeout=30)
print("negative-control returncode (expect nonzero):", r.returncode)
print("  stderr tail:", (r.stderr.strip().splitlines() or [''])[-1])
assert r.returncode != 0, "negative control should have FAILED (the test must bite)"
print("L2c PASS: the assertion bites when a heavy dep is present")
PYEOF
# Expected: (a) 1 passed; (b) OLD False / NEW 0 -> PROOF PASS; (c) nonzero returncode with 'leaked: [...]' ->
# the test correctly fails if ctl ever imports a heavy dep.
```

### Level 3: the full fast suite is green (no regression; PRD §6/§7.1 documented sweep)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# The real alphabetical order (test_daemon.py before test_voicectl.py) — must be 0 failed:
"$PY" -m pytest tests/test_daemon.py tests/test_voicectl.py -q
# The whole fast suite (test_feed_audio.py is the heavy GPU/offline suite, intentionally ignored on a fast sweep):
"$PY" -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed for both. (Collection is ~246 tests; assert by pass/fail, not a hard count, since S1 /
# other work may shift the total. test_feed_audio.py needs CUDA + audio assets — out of scope for this sweep.)
```

### Level 4: scope guard — only test_voicectl.py changed

```bash
cd /home/dustin/projects/voice-typing
# Only test_voicectl.py modified; nothing else:
git status --short
# Belt-and-suspenders: the historical bug-trigger (polluting test THEN purity test, one session) now passes
# regardless of S1 (subprocess isolation makes the purity test immune to the parent's sys.modules):
.venv/bin/python -m pytest \
  "tests/test_daemon.py::test_cfg_to_kwargs_keys_are_exactly_the_non_callback_set" \
  "tests/test_voicectl.py::test_ctl_module_present_and_imports_pure" -q
# Expected: git status shows ONLY tests/test_voicectl.py; the 2-test trigger -> 2 passed (would pass even if
# the daemon test still polluted, because the purity test now runs in a child process).
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `import subprocess` added; `test_ctl_module_present_and_imports_pure` rewritten to `subprocess.run` + `assert result.returncode == 0`; no parent-`sys.modules` purity assert remains.
- [ ] L2: test passes alone; ORDER-INDEPENDENCE PROOF (old logic fails under pollution, new logic passes); NEGATIVE CONTROL (probe importing a heavy dep exits nonzero — the test bites).
- [ ] L3: `pytest tests/test_daemon.py tests/test_voicectl.py -q` → 0 failed; `pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
- [ ] L4: `git status` shows ONLY `tests/test_voicectl.py`; the historical 2-test trigger → 2 passed.

### Feature Validation
- [ ] The purity test passes in **any** collection order (alone / first / after a polluting test).
- [ ] The test still **bites** (a real heavy import in ctl → failure).
- [ ] No new tests/fixtures/files; one stdlib import added; one function rewritten.

### Code Quality Validation
- [ ] Uses `sys.executable` (venv python), not a hardcoded path; no `-S`.
- [ ] `capture_output=True, text=True, timeout=30` on `subprocess.run`; failure message includes stdout+stderr.
- [ ] `importlib.util` import retained (find_spec precondition kept); `import sys` retained.
- [ ] Full paths in every bash command (`.venv/bin/python`, no bare python/pytest/uv).

### Scope Boundary Validation
- [ ] No source files touched (`ctl.py`, `daemon.py`, `cuda_check.py`, `config.py`, …).
- [ ] `test_daemon.py` NOT edited (P1.M2.T1.S1 owns it).
- [ ] No `pyproject.toml`/`uv.lock`/`.gitignore`/`PRD.md`/`tasks.json`/`prd_snapshot.md` changes; no new files.

---

## Anti-Patterns to Avoid

- ❌ Don't use the **in-process `sys.modules` before/after snapshot** — it is a **tautology** here: `from voice_typing import ctl, daemon` (line 22) pre-caches `voice_typing.ctl` at module load, so `added = after - before` is always empty and the test can never fail. Use the **subprocess** (child-process) probe. (research §3; Gotcha #1.)
- ❌ Don't weaken the probe (subset of names, swallowed returncode) — the test must **bite** if ctl ever imports a heavy dep. (Gotcha #2.)
- ❌ Don't hardcode a python path or add `-S` — use `sys.executable` with plain `-c`; the child resolves `voice_typing` via the editable install. (Gotcha #3.)
- ❌ Don't remove `import importlib.util` or the `find_spec` line — it's the kept precondition; only ADD `import subprocess`. (Gotcha #4.)
- ❌ Don't edit `test_daemon.py` (S1 owns it) or any source file — this task touches ONLY `test_voicectl.py`. (Gotchas #6.)
- ❌ Don't add `conftest.py`, autouse fixtures, or new test files — one function + one import; subprocess isolation is self-contained. (Gotcha #7.)
- ❌ Don't use a temp `.py` file for the probe — `python -c "<probe>"` avoids cleanup/path juggling. (Gotcha #5.)
- ❌ Don't invent ruff/mypy commands — this project uses pytest only. (Gotcha #9.)
- ❌ Don't use bare `python`/`pytest`/`uv` (zsh aliases) — use `.venv/bin/python -m pytest`. (Gotcha #8.)
- ❌ Don't edit `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`.

---

## Confidence Score

**9/10** for one-pass implementation success. The defect is precisely characterized (global vs isolated `sys.modules`); the **wrong** fix (in-process snapshot) is ruled out with a concrete, verified reason (ctl is pre-imported at module load → tautology); the **correct** fix (subprocess) is given verbatim and was proven live in three ways (child import is pure from both repo root and `/tmp`; the assertion bites on a real heavy import; the order-independence proof shows old-logic-fails / new-logic-passes under pollution). Both edits are exact `oldText→newText` against the current file, and the change is stdlib-only with no new deps/files. The residual uncertainty (−1) is environmental: the subprocess relies on `sys.executable` being the venv python and on `voice_typing` being importable in the child — both verified live, but a future non-venv or non-editable run could in principle differ; the L2 proof and the `find_spec` precondition surface such a mismatch as a clear failure rather than a silent pass.
