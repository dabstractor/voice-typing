# Research — P1.M1.T4.S1: Fix `toggle_lite` docstring "pressing F" → "pressing D"

> Issue 4 (Minor, PRD §4.10). The `toggle_lite()` docstring in `voice_typing/daemon.py:1410-1411`
> says "pressing F" (3×); the lite keybind is key **D** (`hypr-binds.conf:44`:
> `bind = SUPER ALT, D, exec, .../voicectl toggle-lite`), never F. Mirror the sibling `toggle()`
> docstring (lines 1377-1378) which correctly says "pressing D". Mode-A maintainer-facing doc fix
> + a TDD static-text regression test.

## §0 — The defect, empirically confirmed (load-bearing)

The toggle_lite docstring at daemon.py:1407-1416 currently reads:

```python
def toggle_lite(self) -> None:
    """LITE-mode toggle (PRD §4.2ter / delta §3.4): mode-specific arming.

    Disarms ONLY if currently armed in LITE; otherwise arms in lite. So: pressing F while idle
    arms in lite; pressing F while armed-in-lite disarms; pressing F while armed-in NORMAL
    switches to lite (one bounded reload — the same mode-switch _load_host uses). Each key only
    ever toggles its own mode on/off; the cross-mode press switches (one reload).
    """
```

Lines **1410-1411** carry the 3 occurrences of "pressing F":

- `...arms in lite. So: pressing F while idle`
- `arms in lite; pressing F while armed-in-lite disarms; pressing F while armed-in NORMAL`

**PROOF (live run):**

```
$ .venv/bin/python -c "from voice_typing import daemon; d=daemon.VoiceTypingDaemon.toggle_lite.__doc__; print('pressing F' in d, 'pressing D' in d)"
True False
$ .venv/bin/python -c "from voice_typing import daemon; print(daemon.VoiceTypingDaemon.toggle_lite.__doc__.count('pressing F'))"
3
```

So: `pressing F` is **present** (3×), `pressing D` is **absent**. This is the exact state that makes
the TDD test RED before the fix.

## §1 — The verbatim fix (single 2-line span; old → new)

The 3 "pressing F" all live on the contiguous lines 1410-1411. The cleanest edit is ONE
replacement of that 2-line span (preserves the line-continuation wrapping exactly; the 3rd line
`switches to lite ...` is untouched):

```
OLD (daemon.py:1410-1411):
        Disarms ONLY if currently armed in LITE; otherwise arms in lite. So: pressing F while idle
        arms in lite; pressing F while armed-in-lite disarms; pressing F while armed-in NORMAL
NEW:
        Disarms ONLY if currently armed in LITE; otherwise arms in lite. So: pressing D while idle
        arms in lite; pressing D while armed-in-lite disarms; pressing D while armed-in NORMAL
```

Equivalently: replace the substring `pressing F` → `pressing D` (3×) within the docstring. Either
way the resulting docstring has `pressing F` count 0 and `pressing D` count 3.

**Reference pattern (the correct sibling):** `toggle()` docstring, lines 1377-1378:

```
        Disarms ONLY if currently armed in NORMAL; otherwise arms in normal. So: pressing D while
        idle arms in normal; pressing D while armed-in-normal disarms; pressing D while armed-in
```

`toggle()` already says "pressing D" (3×) — `toggle_lite()` must mirror it (both binds use key D,
just different modifier sets).

## §2 — The keybind truth (why it's D, not F)

`hypr-binds.conf` is the canonical keybind source of truth (system_context.md):

```
:42  bind = CTRL SUPER ALT, D, exec, .../voicectl toggle        # NORMAL (big model)  — key D
:44  bind = SUPER ALT, D,      exec, .../voicectl toggle-lite    # LITE  (small model) — key D
```

- Normal toggle: `Ctrl+Alt+Super+D` (key **D**, has CTRL)
- Lite toggle:   `Alt+Super+D`      (key **D**, NO CTRL)

**Both binds use key D — never F.** The "F" is a thinko (Issue 2 made the same mistake in
config.toml's `lite_model` comment; it was the F→D fix in P1.M1.T2.S1, complete). The toggle_lite
docstring is the third surviving instance of the same typo. `README.md`, `hypr-binds.conf`, and the
`toggle()` docstring are all already correct on D.

## §3 — The TDD test design + placement (RED → GREEN)

**Why a test at all (and why now):** Issue 4's analysis + system_context.md both flag that no test
asserts the docstring text, which is exactly why this typo survived. A static-text assertion on
`toggle_lite.__doc__` closes that gap permanently: any future reintroduction of "pressing F" turns
the test RED. (This mirrors the P1.M1.T3.S1 help-text assertion pattern — a Mode-A doc fix + a
regression test on the rendered/stored text.)

**The seam — `__doc__` is accessible WITHOUT instantiation (hermetic):**

```python
from voice_typing import daemon
doc = daemon.VoiceTypingDaemon.toggle_lite.__doc__   # class-attribute access on the function object
```

A Python method's `__doc__` is an attribute of the underlying function object, reachable as
`ClassName.method.__doc__` — **no instance, no `__init__`, no GPU, no socket, no RealtimeSTT**.
Importing `voice_typing.daemon` is pure (it imports config/typing-backends, all hermetic; the
test_daemon.py module docstring confirms "NO real RealtimeSTT / NO model load / NO CUDA"). So the
test is fully hermetic.

**The test (verbatim):**

```python
# ===========================================================================
# P1.M1.T4.S1 — toggle_lite docstring references the correct key D (bugfix Issue 4)
# (the lite keybind is Alt+Super+D — key D, never F (hypr-binds.conf:44). The toggle_lite
#  docstring previously said "pressing F" 3×; this pins it at "pressing D", mirroring the
#  sibling toggle() docstring. Pure static-text assertion on __doc__ — no instantiation.)
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
```

**Placement:** add a new banner section at the **END** of `tests/test_daemon.py`. That file's
convention is that each subtask appends its own banner section (the current last banner is the
`# P1.M1.T2.S1 — toggle/toggle_lite mode-specific arming` section whose tail tests are the
file's EOF today). `daemon` is already imported at the top (`from voice_typing import daemon`,
line 23) — NO new import. No fixture, no monkeypatch, no daemon instance: pure `__doc__` text.

**RED→GREEN proof:**
- BEFORE the daemon.py edit: `"pressing D" in doc` is **False** → assertion fails (RED).
  (Verified live in §0: `pressing F`=True, `pressing D`=False.)
- AFTER the edit (§1): `"pressing D" in doc` becomes **True**, `"pressing F" not in doc` becomes
  **True** → test PASSES (GREEN).

## §4 — Parallel no-conflict (disjoint files; safe to merge)

This subtask (T4.S1) edits **only** `voice_typing/daemon.py` + `tests/test_daemon.py`.

| Subtask (status)           | Files it owns                            | Conflict w/ T4.S1? |
|----------------------------|------------------------------------------|--------------------|
| T1.S1 (complete)           | install.sh                               | NO (disjoint)      |
| T2.S1 (complete)           | config.toml, tests/test_config_repo_default.py | NO (disjoint) |
| T3.S1 (implementing, parallel) | voice_typing/ctl.py, tests/test_voicectl.py | NO (disjoint) |
| T5.S1 (planned, later)     | README.md / overview docs (verify only)  | NO (disjoint)      |
| **T4.S1 (this)**           | **voice_typing/daemon.py, tests/test_daemon.py** | —              |

No file overlap with any sibling → clean line-level merge. The only concurrent edit risk is if
T3.S1 also appended a banner to test_daemon.py — it does NOT (T3.S1 owns test_voicectl.py, per its
PRP). So appending to test_daemon.py's EOF is safe.

> NOTE on test_daemon.py EOF contention: IF the orchestrator ever schedules two test_daemon.py
> appends concurrently, the second must re-read the file's current tail before inserting (banner
> blocks are independent, so ordering is irrelevant). Today only T4.S1 touches test_daemon.py.

## §5 — Scope discipline (Mode A = doc fix + regression test; nothing else)

**IN scope (the entire delta):**
1. `voice_typing/daemon.py:1410-1411` — replace "pressing F" → "pressing D" (3×). The ONLY source edit.
2. `tests/test_daemon.py` — add 1 banner section + 1 additive test (`test_toggle_lite_docstring_says_pressing_d_not_f`).

**OUT of scope (do NOT touch):**
- `_load_host`, `_arm`, `_disarm`, `_request_stop`, `toggle()` — the toggle_lite BODY logic is
  correct (all 8 behavioral toggle_lite tests pass today; the typo is ONLY in the docstring text).
  Editing behavior would break those tests + is unrelated to Issue 4.
- `toggle()` docstring — it is ALREADY correct ("pressing D"). No edit.
- `config.toml` (T2.S1), `ctl.py`/`test_voicectl.py` (T3.S1), `install.sh` (T1.S1-complete),
  `README.md` (T5.S1), `hypr-binds.conf` (correct), `PRD.md`/`tasks.json`/`prd_snapshot.md`
  (read-only), `.gitignore` (never).

**No behavior / config / API change.** The fix is 3 characters (F→D ×3) in a docstring. No exit
code, socket, model-load, or control-protocol change. Mode A: the docstring IS the maintainer-facing
doc update — no separate docs subtask.

## §6 — Validation tooling & machine gotchas (carry into the PRP)

- **pytest ONLY.** This project has NO ruff/mypy (pyproject does not declare them). Validation =
  `py_compile` + `pytest`. Do NOT invent `ruff`/`mypy` gates (the PRP template's L1 ruff/mypy lines
  are N/A here — replace with py_compile + the grep/grep-based L1 checks).
- **Use full paths.** This machine aliases `python3`→`uv run`, `pip`→alias, `tmux`→zsh plugin.
  Invoke `.venv/bin/python` explicitly. Never bare `python`/`pytest`/`uv`.
- **Hermetic test.** `daemon.VoiceTypingDaemon.toggle_lite.__doc__` needs no instantiation — no
  GPU, no socket, no RealtimeSTT. The whole validation loop is offline.
- **Run from repo root** `/home/dustin/projects/voice-typing`.
