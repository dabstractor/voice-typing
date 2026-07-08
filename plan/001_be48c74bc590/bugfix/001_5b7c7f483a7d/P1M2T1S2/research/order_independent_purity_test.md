# Research — P1.M2.T1.S2: Harden `test_ctl_module_present_and_imports_pure` to be order-independent

> Purpose: nail down (a) WHY the current test is order-dependent, (b) why the
> in-process `sys.modules` snapshot is a *tautology* here (so it is NOT a valid
> fix), (c) the subprocess (child-process) approach as the correct fix — verified
> live, and (d) the exact edit sites. This is a 1-function test rewrite + 1
> import; research is correspondingly tight. All facts below were verified on the
> live tree (Python 3.12.10, venv `.venv/bin/python`, editable-installed
> `voice_typing`).

## 1. The defect (current test)

`tests/test_voicectl.py:200-203`:

```python
def test_ctl_module_present_and_imports_pure():
    # Import purity: importing voice_typing.ctl must NOT pull in RealtimeSTT/torch/ctranslate2.
    assert importlib.util.find_spec("voice_typing.ctl") is not None
    assert not [m for m in ("RealtimeSTT", "torch", "ctranslate2") if m in sys.modules]
```

The second assertion checks the **GLOBAL process** `sys.modules`, i.e. "no test
that ran before me imported these." It does NOT test "importing `voice_typing.ctl`
does not import these." So it is **order-dependent**: it fails whenever an earlier
test in the same pytest session imported `ctranslate2`/`torch` — historically
`tests/test_daemon.py` (alphabetically first) via the real
`cuda_check.resolve_device_and_models()` → `import ctranslate2` → torch.

Status today: the sibling **P1.M2.T1.S1** monkeypatches that resolver in the 4
polluting `test_daemon.py` tests, so the global `sys.modules` is clean again and
the fast suite is green (`246 passed`). **But the assertion is still fragile**:
any future test that imports a heavy dep (or a contributor running
`pytest tests/test_daemon.py tests/` before S1-style hermeticity is applied)
re-breaks it. This task (S2) is **defense-in-depth**: make the assertion test
`voice_typing.ctl`'s OWN import behavior, independent of every other test.

## 2. The target module is genuinely pure (the invariant the test SHOULD assert)

`voice_typing/ctl.py` imports ONLY stdlib + one helper from the daemon:

```
import argparse, json, socket, sys
from voice_typing.daemon import _default_control_socket_path
```

`grep` for `RealtimeSTT|torch|ctranslate2` in `ctl.py` → **none**. And
`voice_typing/daemon.py` has **no module-level heavy imports** (it lazy-imports
them inside functions). Verified empirically in a FRESH interpreter:

```
$ .venv/bin/python -c 'import sys; import voice_typing.ctl; \
    print([m for m in ("RealtimeSTT","torch","ctranslate2") if m in sys.modules])'
[]
```

So the invariant "importing `voice_typing.ctl` does not pull in heavy deps" is
**TRUE**, and a correct test should assert exactly that — in isolation.

## 3. Why the in-process `sys.modules` snapshot is a TAUTOLOGY (NOT a valid fix)

The item description offers two approaches. Approach (1), the in-process
before/after snapshot:

```python
before = set(sys.modules.keys())
import voice_typing.ctl
after = set(sys.modules.keys())
added = after - before
assert not any(m in added for m in ("RealtimeSTT","torch","ctranslate2"))
```

**This tests nothing in this file's context.** `tests/test_voicectl.py` line 22
already executes `from voice_typing import ctl, daemon` at **module load** (when
pytest imports the test module). By the time ANY test function runs,
`voice_typing.ctl` is **already cached in `sys.modules`**. So
`import voice_typing.ctl` inside the test is a no-op cache hit → `added` is
**always empty** → the assertion **always passes**, even if `ctl.py` were changed
to `import torch` at module top tomorrow. That is a false-green test: strictly
worse than today's order-dependent test, because it can never catch a regression.

To make an in-process snapshot meaningful you would have to forcibly evict
`voice_typing.ctl` (+ `voice_typing.daemon` + every transitive submodule) from
`sys.modules`, snapshot, then re-import. That is (a) fragile — you must enumerate
the exact eviction set or leave stale state; (b) destructive — other tests in the
file hold references to the OLD module objects, and re-importing creates NEW ones,
risking subtle identity mismatches; (c) more code than the subprocess fix. **Do
not use the in-process snapshot approach here.**

## 4. The subprocess (child-process) approach — verified, the correct fix

Approach (2): spawn a FRESH interpreter that imports only `voice_typing.ctl` and
asserts no heavy deps are in *its* `sys.modules`. The child's `sys.modules` is
unaffected by anything the parent pytest process imported, so the result is
**order-independent by construction**.

### 4.1 The probe (what the child runs)

```python
"import sys, voice_typing.ctl; "
"leaked = [m for m in ('RealtimeSTT', 'torch', 'ctranslate2') if m in sys.modules]; "
"assert not leaked, f'voice_typing.ctl transitively imports heavy deps: {leaked}'"
```

### 4.2 Live verification (all PASSED during this research)

1. **The invariant holds** (child import is pure), run from repo root:
   `subprocess.run([sys.executable, "-c", probe])` → **returncode 0, no stderr**.
2. **CWD-independent / editable-install robust** — the same probe run from `/tmp`
   (CWD with no `voice_typing/` subdir) still → **returncode 0**. So the test does
   NOT rely on pytest's CWD being the repo root; the editable install of
   `voice_typing` makes it importable anywhere. `sys.executable` is the venv python
   (`/home/dustin/projects/voice-typing/.venv/bin/python`), inherited by the child.
3. **The test BITES (negative control)** — a probe that does `import RealtimeSTT`
   first → **returncode 1**, stderr `AssertionError: leaked: ['RealtimeSTT']`.
   So this is not a tautology: if `ctl.py` (or a transitive import) ever pulls in a
   heavy dep, the test fails loudly. (This is the property the in-process snapshot
   lacks.)
4. **Order-independence proof (the whole point)** — fake-polluting the PARENT's
   `sys.modules` (e.g. `sys.modules['torch'] = ...`) and re-running: the OLD global
   assertion fails, but the subprocess assertion still passes (child is fresh). See
   the PRP Validation Level 2 for the exact one-liner.

### 4.3 Why `-c` (not a temp .py file, not `-m`)

`python -c "<probe>"` needs no temp file (nothing to clean up, no path juggling)
and keeps the change to a single test function + one import. `subprocess.run`
inherits the parent env + venv `sys.executable`, so `voice_typing` resolves via the
editable install. `capture_output=True, text=True` captures any failure for the
assertion message. `timeout=30` guards against an unforeseen hang (the real import
is <1 s).

### 4.4 Cost / flakiness

One subprocess spawn (~50–100 ms) added to a 246-test suite that runs in ~4 s:
negligible. No I/O wait, no network, no GPU → not flaky. `sys.executable` is set by
CPython itself (never `None` under pytest), so there is no environment-variable
dependency.

## 5. Edit sites (exact, current tree)

Only `tests/test_voicectl.py` changes. Two edits:

**(A) Add the `subprocess` import** to the stdlib import block (lines 13-14):

```python
# before:
import importlib.util
import sys
# after:
import importlib.util
import subprocess
import sys
```

(`importlib.util`, `subprocess`, `sys` — alphabetical, stdlib group.)

**(B) Rewrite the test** (lines 200-203). oldText → newText given verbatim in the
PRP's Implementation Blueprint. The new body: keep the cheap `find_spec`
precondition (pure; documents the "module present" half of the test name), replace
the global `sys.modules` assertion with the subprocess probe + `returncode == 0`
assertion that prints stdout/stderr on failure.

Nothing else changes. `importlib.util` is still used (the `find_spec` line stays),
so its import is retained. `import sys` stays (used by the `[sys.executable, ...]`
list and by other tests). No source files (`ctl.py`, `daemon.py`, …) are touched.
`test_daemon.py` is NOT touched (S1 owns it). No new files.

## 6. Scope boundaries (no conflict with parallel/sibling work)

- **P1.M2.T1.S1 (sibling, "Implementing")**: edits `tests/test_daemon.py`
  (monkeypatches the resolver in 4 polluting tests). This task edits
  `tests/test_voicectl.py` (the purity assertion). **No file overlap.** Together
  they are defense-in-depth: S1 removes the pollution at the source; S2 makes the
  purity test order-independent so it cannot be re-broken by any future test.
- **Source**: `ctl.py`, `daemon.py`, `cuda_check.py`, `config.py`, … — all
  untouched. This is a test-only change (item OUTPUT: "test-only change").
- **No new tests / fixtures / files / deps**. One function rewritten, one import
  added.
- `pytest` is the only runner (no ruff/mypy configured; do not invent them).
