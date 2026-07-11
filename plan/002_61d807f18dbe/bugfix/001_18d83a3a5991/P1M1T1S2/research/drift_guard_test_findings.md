# Research Note: drift-guard test for launch_daemon.sh offline exports (P1.M1.T1.S2)

**Status:** EMPIRICALLY VERIFIED against the live repo (voice_typing/launch_daemon.sh, tests/test_systemd_unit.py) on July 11 2026.
**Purpose:** Pin down the exact pattern + the one critical trap for the new pytest drift-guard test that asserts `launch_daemon.sh` exports the offline env vars.

---

## §1. Current state of launch_daemon.sh (S1 ALREADY APPLIED)

`voice_typing/launch_daemon.sh` (74 lines, `#!/usr/bin/env bash`). Relevant tail (verified via `cat -n` + `grep -n`):

```
60  # HF offline guarantee (PRD §1 ... bugfix Issue 1). Models are ...
...
71  export HF_HUB_OFFLINE=1
72  export TRANSFORMERS_OFFLINE=1
73
74  exec "$PY" -m voice_typing.daemon "$@"
```

- The two offline exports are present, **verbatim** (`export HF_HUB_OFFLINE=1`, `export TRANSFORMERS_OFFLINE=1`), at lines 71-72.
- They precede the final `exec "$PY" -m voice_typing.daemon "$@"` at line 74. (Ordering is load-bearing — env vars read at `execve(2)`.)
- The pre-existing `export LD_LIBRARY_PATH=...` is at line 53. Total `^export ` lines = 3.
- → The S1 contract is satisfied in the live file. The new S2 test is expected to PASS on first run.

---

## §2. THE FALSE-PASS TRAP (the single most important detail)

The WHY comment block at lines 60-70 mentions `HF_HUB_OFFLINE=1` **in prose**, e.g.:

```
62  # daemon loads them from cache with ZERO network. HF_HUB_OFFLINE=1 makes huggingface_hub
```

**Consequence:** a naive `assert "HF_HUB_OFFLINE=1" in launch_daemon_sh_text` would PASS even if the real `export HF_HUB_OFFLINE=1` directive (line 71) were **deleted**, because the comment prose still contains the substring. That would make the drift-guard useless — it would not catch the exact regression it exists to catch (someone removing the export). This is the same class of circular-proof / masking failure that let bugfix Issue 1 ship (the test_idle_and_gpu.sh G-OFFLINE masking, scout §6).

**FIX — mandatory design rule:** the presence assertion MUST match the real directive only, by anchoring to a line that STARTS WITH `export `. Use a line-by-line regex:

```python
import re
hf_re = re.compile(r'^export\s+HF_HUB_OFFLINE=(?:1|"1"|\'1\')\s*$')
# iterates file lines; matches ONLY a real `export HF_HUB_OFFLINE=1` (or quoted variants),
# never the comment prose (comments start with '#', not 'export').
```

The ordering assertion (exports before `exec`) is naturally line-based too, so the whole test should be line-oriented, not substring-oriented. This is the difference between a guard that works and one that is theatre.

---

## §3. Existing test pattern in tests/test_systemd_unit.py (mirror it)

`tests/test_systemd_unit.py` (95 lines). Established conventions to follow EXACTLY:

- **Module docstring** explains the drift-guard philosophy (repo unit file IS what runs; static checks avoid needing live systemd; each test's docstring cites the PRD/issue rationale + the regression it prevents).
- **Path helper**: `_unit_path()` → `Path(__file__).resolve().parent.parent / "systemd" / "voice-typing.service"`.
- **Text helper**: `_unit_lines()` → `read_text().splitlines()`, filters out blank + `#`-comment lines, returns `list[str]` of real directives.
- **3 existing tests**, each with a multi-line docstring: `test_execstart_points_at_launch_daemon_wrapper`, `test_execstartpre_imports_wayland_and_display_env`, `test_restart_on_failure`.
- Style: `from __future__ import annotations`; `from pathlib import Path`; descriptive assertion messages.

For the new test, add a **sibling path helper** (do NOT overload `_unit_path`, which is semantically the systemd unit):

```python
def _launch_daemon_path() -> Path:
    return Path(__file__).resolve().parent.parent / "voice_typing" / "launch_daemon.sh"
```

(repo root = parent of `tests/`; `voice_typing/launch_daemon.sh` sits there. Same `parent.parent` idiom as `_unit_path`.)

---

## §4. Quote-variant requirement (from the contract)

The contract says accept all of: `export HF_HUB_OFFLINE=1`, `export HF_HUB_OFFLINE="1"`, `export HF_HUB_OFFLINE='1'`. The regex alternation `(?:1|"1"|\'1\')` covers all three. The live file uses the bare `=1` form today; the test tolerates future quoting without weakening the guard. Same for `TRANSFORMERS_OFFLINE`.

---

## §5. pytest invocation + config (verified)

- pytest **9.1.1** is installed in `.venv/bin/pytest` (declared in `pyproject.toml`: `pytest>=9.1.1`).
- There is **no** `[tool.pytest.ini_options]`, no `pytest.ini`, no `setup.cfg`, no `conftest.py` / `tests/conftest.py`. Tests are plain functions; collection is automatic from `tests/`.
- Run command (full path — machine aliases `python3`→`uv run`):
  ```
  .venv/bin/python -m pytest tests/test_systemd_unit.py -v
  ```
- The file currently collects 3 tests; after S2 it should collect 4, all passing.

---

## §6. Ordering-check mechanics (why line-indices, not regex global)

Env vars are read by the kernel at `execve(2)` when `exec "$PY" ...` replaces the process, so the exports MUST appear on an earlier source line than the `exec "$PY"` line. The test computes `enumerate(lines)` indices for: first `^export HF_HUB_OFFLINE=...` match, first `^export TRANSFORMERS_OFFLINE=...` match, and the first line matching `^exec\s+"\$PY"\s+-m voice_typing\.daemon`. Then asserts `hf_idx < exec_idx` and `tf_idx < exec_idx` (with 1-based line numbers in the failure message for debuggability).

The `exec` line in the file is literally `exec "$PY" -m voice_typing.daemon "$@"` (note: `$PY` is literal bash, 4 characters `$`,`P`,`Y` — in a Python string `'exec "$PY"'` is correct). A regex `r'^exec\s+"\$PY"\s+-m\s+voice_typing\.daemon'` is precise and avoids matching any commented-out exec.

---

## SUMMARY (what S2 can rely on)

1. ✅ S1 is already applied: exports at L71-72, exec at L74 — the new test PASSES on first run.
2. ⚠️ **MANDATORY**: use line-anchored `^export ...` regex, NOT a substring `in text` check — the comment block mentions the var name in prose and would cause a false pass (§2).
3. ✅ Mirror the existing `test_systemd_unit.py` conventions: sibling `_launch_daemon_path()` helper, descriptive docstring citing PRD §1/§7.8 + bugfix Issue 1.
4. ✅ Accept quote variants `=1` / `="1"` / `='1'` for both vars.
5. ✅ Assert both exports appear before `exec "$PY"` (line-index check; env read at execve).
6. ✅ pytest 9.1.1, no special config; run `.venv/bin/python -m pytest tests/test_systemd_unit.py -v` → expect 4 passed.
7. ✅ The guard's *effectiveness* MUST be validated by a temporary mutation: delete an export line → test fails → restore via `git checkout`.
