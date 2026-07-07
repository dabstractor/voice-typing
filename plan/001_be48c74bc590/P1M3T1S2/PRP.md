# PRP — P1.M3.T1.S2: Unit tests for typing backends (`tests/test_typing_backends.py`, subprocess mocked)

## Goal

**Feature Goal**: Ship `tests/test_typing_backends.py` — the pure-Python unit-test
harness for `voice_typing/typing_backends.py` (P1.M3.T1.S1). `subprocess.run` is
monkeypatched for EVERY test, so it runs with **no display, no ydotoold, and NO real
keystrokes**. It pins the three PRD §4.3 command lists (wtype / ydotool `--key-delay 2`
/ tmux `send-keys -t -l --`) and the wtype→ydotool auto-fallback contract (PRD §4.3 +
§8 risk "wtype fails on some window"). This is the **test half** of milestone P1.M3.T1;
it consumes the implementation landed by P1.M3.T1.S1 and validates it before the daemon
(P1.M4.T1.S2) is wired.

**Deliverable** (ONE artifact — tests only):
1. `tests/test_typing_backends.py` — 26 pytest tests in 7 sections (see Implementation
   Blueprint → Task 2 for the verbatim source). Uses a `recorder` fixture that
   monkeypatches `subprocess.run` to capture `(argv, kwargs)` and never reach the OS.

**Success Definition**:
- (a) `tests/test_typing_backends.py` exists, `.venv/bin/python -m py_compile`-clean,
  and `.venv/bin/python -m pytest tests/test_typing_backends.py -v` → **26 passed** with
  NO real keystroke sent (every test uses the `recorder` fixture or installs its own).
- (b) The three backends are asserted to call the EXACT PRD §4.3 argv:
  `WtypeBackend` → `("wtype","--",text)`; `YdotoolBackend` →
  `("ydotool","type","--key-delay","2","--",text)`; `TmuxBackend(cfg)` →
  `("/usr/bin/tmux","send-keys","-t",cfg.tmux_target,"-l","--",text)` — each with
  `check=True` (load-bearing for the fallback).
- (c) `TypingBackend` is abstract (`TypingBackend()` raises `TypeError`); the three
  concretes are `TypingBackend` instances.
- (d) `make_backend`: `backend="wtype"` → `_WtypeWithFallback` wrapping a `WtypeBackend`
  primary + `YdotoolBackend` fallback; `"ydotool"` → `YdotoolBackend`; `"tmux"` →
  `TmuxBackend` carrying `cfg.tmux_target`; unknown → `ValueError`.
- (e) Auto-fallback (via `monkeypatch`ed `subprocess.run` that raises): wtype nonzero
  exit (`CalledProcessError`) → ydotool invoked; wtype missing binary
  (`FileNotFoundError`) → ydotool invoked; wtype `PermissionError` → ydotool invoked;
  success → fallback NOT invoked (exactly 1 call); both fail → second exception
  PROPAGATES (exactly 2 calls, no swallow); a `WARNING` is logged on fallback.
- (f) No out-of-scope files: NO edits to `voice_typing/typing_backends.py` (S1 owns it),
  no `tests/__init__.py` (pytest discovers without it), no edits to `config.py`/
  `textproc.py`/`config.toml`/`pyproject.toml`/`uv.lock`/`PRD.md`/`tasks.json`/
  `prd_snapshot.md`/`.gitignore`. stdlib + pytest + `OutputConfig` import only — no new
  dependencies (no `pytest-mock`, no `unittest.mock`).

## User Persona

**Target User**: None directly (test-only; item DOCS: "none"). Its "users" are the
maintainer running `pytest` and the orchestrator gating P1.M3.T1 complete.

**Use Case**: After `typing_backends.py` lands (S1), `pytest tests/test_typing_backends.py`
proves the command lists + fallback ordering deterministically, in CI/CPU contexts, with
no Wayland session, no `ydotoold`, and zero risk of typing into a focused window.

**User Journey**: `cd voice-typing && .venv/bin/python -m pytest tests/test_typing_backends.py -v`
→ 26 passed → P1.M3.T1 declared complete → daemon (P1.M4.T1.S2) wires `make_backend`.

**Pain Points Addressed**: (1) wtype/ydotool type into the FOCUSED window — running them
for real in unit tests would disrupt the user's session and is non-deterministic; mocking
`subprocess.run` makes the tests hermetic and safe. (2) The fallback ordering (wtype
then ydotool) and the "propagate, don't swallow" rule are easy to get wrong; the tests
pin them before the daemon depends on them.

## Why

- **Tests ride with the work (SOW §3).** This is the test harness for the typing backends
  — P1.M3.T1.S1 ships the impl; S2 (this) ships its tests. Together they close P1.M3.T1.
- **It is the validation gate before daemon wiring.** The daemon's `on_final`
  (P1.M4.T1.S2) calls `backend.type_text(...)`. If the fallback ordering or the command
  lists were wrong, the daemon would silently mistype or crash on wtype failure. These
  tests catch that BEFORE the daemon is built.
- **Auto-fallback is a PRD §8 prescribed mitigation** ("wtype fails on some window →
  auto-fallback to ydotool"). These tests make that mitigation executable and regression-
  proof: a future change that narrows the catch to only `FileNotFoundError`, drops
  `check=True`, or swallows the fallback exception will turn a test red.
- **Small, bounded, GPU-free, no new deps.** Pure pytest + stdlib (`subprocess`,
  `logging`) + one `OutputConfig` import. Runs in any environment with the venv.

## What

One file `tests/test_typing_backends.py` (pytest, `from __future__ import annotations`)
that: monkeypatches `subprocess.run` via a reusable `recorder` fixture (captures argv +
kwargs, returns `CompletedProcess(returncode=0)` by default, configurable `raise_on`);
asserts the three exact PRD §4.3 argv + `check=True`; asserts `TypingBackend` abstractness
and the `make_backend` dispatch; and exercises the auto-fallback end-to-end through the
REAL backends (not injected fakes) by making the patched `subprocess.run` raise
`CalledProcessError` / `FileNotFoundError` / `PermissionError` for `wtype`. Verbatim
source in Implementation Blueprint → Task 2.

### Success Criteria

- [ ] `tests/test_typing_backends.py` exists; `.venv/bin/python -m py_compile tests/test_typing_backends.py` exits 0.
- [ ] `.venv/bin/python -m pytest tests/test_typing_backends.py -v` → **26 passed**, 0 failed, 0 skipped.
- [ ] `WtypeBackend().type_text("hello world")` records exactly `("wtype","--","hello world")` with `check=True`.
- [ ] `YdotoolBackend().type_text("hello")` records `("ydotool","type","--key-delay","2","--","hello")` with `check=True`.
- [ ] `TmuxBackend(OutputConfig(backend="tmux", tmux_target="voicetest:0.0")).type_text("Hello 123")` records `("/usr/bin/tmux","send-keys","-t","voicetest:0.0","-l","--","Hello 123")` with `check=True`.
- [ ] `TypingBackend()` raises `TypeError`; each concrete backend is a `TypingBackend` instance.
- [ ] `make_backend(OutputConfig(backend="wtype"))` is a `_WtypeWithFallback` whose `_primary` is `WtypeBackend` and `_fallback` is `YdotoolBackend`.
- [ ] `make_backend(OutputConfig(backend="ydotool"))` is a `YdotoolBackend`; `backend="tmux", tmux_target="s:0.1"` is a `TmuxBackend` with `_tmux_target == "s:0.1"`.
- [ ] `make_backend(OutputConfig(backend="bogus"))` raises `ValueError` whose message contains `"bogus"`.
- [ ] Auto-fallback (subprocess.run raising on `"wtype"`): nonzero exit (`CalledProcessError`) AND `FileNotFoundError` AND `PermissionError` each cause ydotool to be invoked; success → exactly 1 subprocess call (no fallback); both `wtype`+`ydotool` raising → `CalledProcessError` propagates AND exactly 2 subprocess calls; a `WARNING` record mentioning `"ydotool"` is emitted on fallback.
- [ ] NO real keystroke is sent: every test path is covered by the `recorder` fixture (or a manually installed `_Recorder`); no test reaches the OS.
- [ ] ONLY `tests/test_typing_backends.py` is created/modified. Nothing else changes.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge: the CONTRACT under test (S1's
`typing_backends.py` — class names, command lists, `_primary`/`_fallback`/`_tmux_target`
attribute names, the `_TMUX` constant, the fallback catch set + propagate semantics, the
`make_backend` dispatch + `ValueError` message) is pinned from `P1M3T1S1/PRP.md` and
mirrored in research §1. The monkeypatch mechanic + recorder design are pinned (research
§2). The established test style (module docstring, section dividers, `monkeypatch`
fixture, `pytest.raises`) is mirrored from `tests/test_config.py` + `tests/test_textproc.py`
(read at preflight). The verbatim test source is in Implementation Blueprint → Task 2.
Validation commands are executable as written (research §8: pytest 9.1.1 in venv; no
mypy; ruff optional at `~/.local/bin/ruff`; run via `.venv/bin/python`).

### Documentation & References

```yaml
# MUST READ — the authoritative behavior spec (what the tests pin)
- file: PRD.md
  why: "§4.3 is the verbatim spec for the three command lists + the auto-fallback rule
        ('daemon MUST auto-fall-back to ydotool if a wtype call fails (nonzero exit),
        logging a warning'). §8 lists the 'wtype fails on some window (rare)' risk with
        mitigation 'auto-fallback to ydotool (§4.3)'. §4.3 last paragraph: 'Never send
        Enter/newline unless the utterance-final text itself demands it'."
  critical: "Assert the THREE command lists EXACTLY (incl. the literal '/usr/bin/tmux'
             full path and the '--key-delay 2' SPACE form). The fallback triggers on
             NONZERO EXIT (CalledProcessError) OR missing/unusable binary (OSError family).
             NEVER assert that a newline/space is appended."

# MUST READ — the contract under test (S1's deliverable). READ to align names/behavior.
- file: plan/001_be48c74bc590/P1M3T1S1/PRP.md
  why: "Defines EXACTLY what typing_backends.py exports and how it behaves — this PRP's
        tests assert against that contract. §Implementation Blueprint → Task 2 SOURCE is
        the verbatim module: class/attr names (_primary, _fallback, _tmux_target, _TMUX),
        the exact argv, the fallback try/except + propagate, the make_backend dispatch,
        the ValueError message ('unknown output.backend: {backend!r}')."
  critical: "S1 is being implemented IN PARALLEL; assume it lands EXACTLY as specified.
             The tests import _WtypeWithFallback (module-private but S1 designed it for
             testability: 'Optional injection lets unit tests (P1.M3.T1.S2) swap in
             fakes'). Attribute names _primary/_fallback/_tmux_target are part of the
             S1 contract — S1's own L3 smoke accesses them."

# MUST READ — the established test STYLE to mirror (docstring + sections + monkeypatch)
- file: tests/test_config.py
  why: "The project's pytest STYLE TEMPLATE. Mirror its: module docstring (what it tests,
        PRD cross-ref, pure-Python note, run command, TDD note), `from __future__ import
        annotations`, section dividers (`# ----...`), `import pytest`, descriptive
        `test_X_Y` names, and ESPECIALLY its `monkeypatch.setattr(module, 'attr', fake)`
        pattern (e.g. test_search_order_xdg_wins_over_repo) — that is the exact mechanic
        used here to patch subprocess.run."
  critical: "Use the stdlib pytest `monkeypatch` fixture (NOT unittest.mock, NOT
             pytest-mock — neither is a dependency; dev=['pytest>=9.1.1'] only).
             monkeypatch auto-restores subprocess.run after each test (no leakage)."

# MUST READ — a second style reference (TDD module docstring + return-contract section)
- file: tests/test_textproc.py
  why: "Sibling test module (P1.M2.T2.S1). Mirror its TDD module-docstring wording
        ('Written FIRST (TDD) — it is RED until textproc.py lands') and its
        'Return-value contract' section style (grouping assertions about the contract)."
  critical: "Both test_config.py and test_textproc.py use `.venv/bin/python -m pytest`
             as the run command (zsh aliases python → uv run; ALWAYS .venv/bin/python)."

# MUST READ — the consumed config contract (OutputConfig constructor + defaults)
- file: voice_typing/config.py
  why: "OutputConfig(backend='wtype', tmux_target='', append_space=True) — the factory
        input. Tests construct OutputConfig(...) to drive make_backend and TmuxBackend.
        READ, do NOT edit."
  critical: "make_backend takes OutputConfig (the [output] sub-config), NOT
             VoiceTypingConfig. append_space is the DAEMON's concern — the tests must
             NOT assert any space/newline is appended by the backends."

# MUST READ — this task's research (monkeypatch mechanic + recorder design + test inventory)
- docfile: plan/001_be48c74bc590/P1M3T1S2/research/test_design_notes.md
  why: "§1 the S1 contract table (names/attrs/argv). §2 why monkeypatch subprocess.run
        + the recorder design. §3 check=True is load-bearing for the fallback. §4 the
        OSError family (FileNotFoundError + PermissionError both trigger fallback).
        §5 retry-once-then-propagate. §6 caplog WARNING assertion. §7 no-real-keystrokes
        safety guarantee. §8 tooling reality. §9 the 26-test inventory."
  section: "ALL sections load-bearing. §1 (contract), §2 (mechanic), §4 (OSError family),
            §5 (propagate), §9 (test list)."

# Background — machine facts (READ-ONLY context; full-path + zsh-alias tooling facts)
- file: plan/001_be48c74bc590/architecture/system_context.md
  why: "§1: /usr/bin/tmux (zsh aliases tmux — the TmuxBackend argv MUST use the full
        path, which the test asserts); shell aliases python/pip/tmux → ALWAYS
        .venv/bin/python for test runs. §3 data-flow: on_final → textproc.clean → type
        text (the backends are the typed-output link these tests cover)."
  critical: "Assert argv[0]=='/usr/bin/tmux' literally in the TmuxBackend tests (a bare
             'tmux' would be a regression). Run pytest via .venv/bin/python (never bare
             python/pytest)."

# Background — the plan (scope boundaries: do NOT touch S1's impl, do NOT add deps)
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M3.T1.S1 owns voice_typing/typing_backends.py (impl); P1.M3.T1.S2 (this) owns
        ONLY tests/test_typing_backends.py. P1.M4.T1.S2 (daemon) is the downstream
        consumer gated by these tests passing. P1.M7.T3.S1 (E2E) later exercises the REAL
        tmux backend end-to-end — this task mocks subprocess, it does NOT run real tools."
  critical: "Do NOT edit voice_typing/typing_backends.py (S1 owns it). Do NOT add
             pytest-mock/unittest-mock deps. Do NOT create tests/__init__.py."
```

### Current Codebase tree (state at P1.M3.T1.S2 start)

> P1.M3.T1.S1 is implemented IN PARALLEL and may not have landed yet. Assume it lands
> EXACTLY as `P1M3T1S1/PRP.md` specifies (its Task 2 SOURCE is verbatim). This task's
> tests will be RED until S1 lands — that is expected (TDD).

```bash
/home/dustin/projects/voice-typing/
├── .git/                       # git repo, branch main
├── .gitignore                  # DO NOT touch
├── .venv/                      # Python 3.12.10; pytest 9.1.1 (dev group)
├── PRD.md                      # READ-ONLY
├── config.toml                 # P1.M2.T1.S2 output. DO NOT touch.
├── pyproject.toml              # dev=["pytest>=9.1.1"]. DO NOT touch (no new deps).
├── uv.lock                     # DO NOT touch
├── voice_typing/
│   ├── __init__.py
│   ├── cuda_check.py           # P1.M1.T2.S2 (unrelated)
│   ├── launch_daemon.sh        # P1.M1.T2.S1 (unrelated)
│   ├── prefetch.py             # P1.M1.T3.S1 (unrelated)
│   ├── config.py               # P1.M2.T1.S1 (OutputConfig lives HERE). READ only.
│   ├── textproc.py             # P1.M2.T2.S1 (style template). READ only.
│   └── typing_backends.py      # ← P1.M3.T1.S1 output (the CONTRACT under test). READ only.
└── tests/
    ├── test_config.py                # P1.M2.T1.S1. STYLE TEMPLATE. DO NOT EDIT.
    ├── test_config_repo_default.py   # P1.M2.T1.S2. DO NOT EDIT.
    └── test_textproc.py              # P1.M2.T2.S1. STYLE TEMPLATE. DO NOT EDIT.
# NO tests/test_typing_backends.py yet — Task 2 creates it (the ONLY new file).
# NO tests/__init__.py (pytest discovers test_*.py without it; do NOT add one).
```

### Desired Codebase tree with files to be added

```bash
/home/dustin/projects/voice-typing/
└── tests/
    └── test_typing_backends.py   # ← CREATE (Task 2): 26 tests, subprocess.run mocked via `recorder` fixture
# NOTHING ELSE. No edits to voice_typing/typing_backends.py (S1 owns it). No tests/__init__.py.
# No new deps. No other test files.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — MONKEYPATCH subprocess.run, NOT unittest.mock / pytest-mock. The project
#   uses the stdlib pytest `monkeypatch` fixture exclusively (see tests/test_config.py:
#   monkeypatch.setattr(cfgmod, "_xdg_config_path", ...)). typing_backends does
#   `import subprocess` then `subprocess.run(...)`, so patching the `run` ATTRIBUTE on
#   the `subprocess` module is what every backend sees. Form:
#       monkeypatch.setattr(subprocess, "run", fake_run)
#   monkeypatch auto-restores after each test (no leakage). Do NOT add pytest-mock to
#   pyproject (dev=["pytest>=9.1.1"] only — no new deps). (Research §2.)

# CRITICAL #2 — check=True IS LOAD-BEARING FOR THE FALLBACK TEST. PRD §4.3 lists commands
#   as `subprocess.run([...])`; S1 adds `check=True` so a NONZERO EXIT raises
#   CalledProcessError (otherwise run returns CompletedProcess(returncode!=0) silently and
#   the fallback never fires). "subprocess returns nonzero" (item wording) = RAISE
#   CalledProcessError(1, [...]) in the mock. The tests assert kwargs["check"] is True for
#   all three backends (documents that the fallback is ARMED). (Research §3; S1 Gotcha #1.)

# CRITICAL #3 — THE OSError FAMILY ALL TRIGGERS THE FALLBACK. S1 catches
#   (CalledProcessError, OSError). FileNotFoundError (binary missing) AND PermissionError
#   (binary not executable) are BOTH OSError subclasses. Test BOTH raise on wtype and
#   assert ydotool is invoked — this guards the S1 contract and catches a common bug
#   (narrowing the catch to only FileNotFoundError). (Research §4; S1 Gotcha #3.)

# CRITICAL #4 — RETRY ONCE, THEN PROPAGATE (do NOT assert the exception is swallowed).
#   If wtype raises AND ydotool raises, the exception PROPAGATES (S1 does not wrap it in a
#   bare `except Exception`). Test: both raise → pytest.raises(CalledProcessError) AND
#   exactly 2 subprocess calls (one each, never a loop). Asserting it is swallowed would
#   be wrong and would hide a real failure from the daemon. (Research §5; S1 Critical #4.)

# CRITICAL #5 — NEVER ASSERT A NEWLINE/SPACE IS APPENDED. PRD §4.3 last paragraph: backends
#   type EXACTLY the text given; textproc stripped trailing newlines; the DAEMON appends a
#   trailing space when cfg.output.append_space (not the backend). Tests assert the text
#   appears verbatim as argv[-1] (e.g. "Hello", not "Hello\n"). (S1 Critical #5.)

# CRITICAL #6 — /usr/bin/tmux LITERAL in the TmuxBackend argv (assert argv[0] == exactly
#   that). zsh aliases `tmux` to a plugin wrapper; S1 pins the full path as `_TMUX =
#   "/usr/bin/tmux"`. A test that accepts a bare "tmux" would miss a regression to the
#   alias. (Research §1; system_context.md §1; S1 Critical #2.)

# CRITICAL #7 — caplog WARNING via getMessage(), not r.message. S1 logs on fallback:
#   logger.warning("wtype typing failed (%s); retrying once via ydotool", exc) under
#   logger = logging.getLogger("voice_typing.typing_backends"). Use:
#       with caplog.at_level(logging.WARNING, logger="voice_typing.typing_backends"):
#           ...
#       assert any(r.levelno == logging.WARNING and "ydotool" in r.getMessage() for r in caplog.records)
#   getMessage() reliably applies the % args; r.message may be unset until formatting.
#   (Research §6.)

# CRITICAL #8 — RUN VIA .venv/bin/python, never bare python/pytest. zsh aliases python →
#   `uv run`. Always: `.venv/bin/python -m pytest ...` and `.venv/bin/python -m
#   py_compile ...`. (system_context.md §1; tests/test_config.py run command.)

# CRITICAL #9 — mypy is NOT installed (import mypy → ModuleNotFoundError). Do NOT list it
#   as a validation gate. The gates are py_compile + pytest. ruff is available at
#   /home/dustin/.local/bin/ruff (a uv tool, NOT in .venv) — `ruff format --check` and
#   `ruff check` are OPTIONAL lints (run if present; do not let a missing/empty config
#   block). (Research §8; S1 Gotcha #13.)

# CRITICAL #10 — DO NOT CREATE tests/__init__.py. pytest discovers test_*.py without it
#   (43 tests currently collect: config + config_repo_default + textproc). Adding
#   __init__.py changes import semantics and is unnecessary. (Research §8.)

# CRITICAL #11 — DO NOT EDIT voice_typing/typing_backends.py (S1 owns it, in parallel).
#   If a test reveals an S1 bug, the fix is S1's responsibility — raise it, do not patch
#   the impl here. This task writes ONLY tests/test_typing_backends.py. (tasks.json scope.)

# GOTCHA #12 — _WtypeWithFallback is module-private (leading underscore) but S1 designed
#   it for testability ('Optional injection lets unit tests (P1.M3.T1.S2) swap in fakes').
#   Importing it and asserting isinstance + its _primary/_fallback attrs is part of the
#   intended contract (S1's own L3a smoke does the same). (Research §1; S1 Gotcha #14.)

# GOTCHA #13 — TmuxBackend NEEDS an OutputConfig at construction (it reads cfg.tmux_target
#   into self._tmux_target). Construct with OutputConfig(backend="tmux", tmux_target=...).
#   The default OutputConfig() has tmux_target="" (assert the empty-target path too).
#   (Research §1; config.py OutputConfig.)

# GOTCHA #14 — CompletedProcess(args=argv, returncode=0) is the success return under
#   check=True. The recorder returns this by default; raise_on(cmd0, exc) overrides per
#   command name (argv[0]). The first argv element selects behavior: "wtype" vs "ydotool"
#   vs "/usr/bin/tmux". (Research §2.)
```

## Implementation Blueprint

### Data models and structure

No new data model. The test module imports `OutputConfig` from `voice_typing/config.py`
(P1.M2.T1.S1) and the backend classes/factory from `voice_typing/typing_backends.py`
(P1.M3.T1.S1). The only new structure is the `_Recorder` helper class + the `recorder`
pytest fixture (monkeypatches `subprocess.run`).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm inputs/contract present and target absent (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/config.py && echo "ok: config.py exists (OutputConfig source)" || echo "PREFLIGHT FAIL"
      test -f tests/test_config.py && echo "ok: test_config.py exists (style template)" || echo "PREFLIGHT FAIL"
      test -f tests/test_textproc.py && echo "ok: test_textproc.py exists (style template)" || echo "PREFLIGHT FAIL"
      test ! -e tests/test_typing_backends.py && echo "ok: target absent (will create)" || echo "PREFLIGHT FAIL: target exists"
      test ! -e tests/__init__.py && echo "ok: no tests/__init__.py (pytest discovers without it)" || echo "PREFLIGHT NOTE: tests/__init__.py exists"
      .venv/bin/python -c "from voice_typing.config import OutputConfig; print('OutputConfig OK', OutputConfig().backend, repr(OutputConfig().tmux_target))" || echo "PREFLIGHT FAIL: OutputConfig import"
      .venv/bin/python -c "import subprocess; from subprocess import CalledProcessError, CompletedProcess; print('subprocess OK')" || echo "PREFLIGHT FAIL"
      .venv/bin/python -m pytest --version || echo "PREFLIGHT FAIL: pytest not runnable"
  - CONDITIONAL (S1 may not have landed yet — TDD allows RED until it does):
      .venv/bin/python -c "from voice_typing.typing_backends import TypingBackend, WtypeBackend, YdotoolBackend, TmuxBackend, _WtypeWithFallback, make_backend; print('typing_backends OK')" 2>/dev/null \
        && echo "ok: S1 (typing_backends.py) present — tests should go GREEN" \
        || echo "note: S1 (typing_backends.py) not yet present — tests will be RED (expected for TDD; they turn GREEN when S1 lands)"
  - EXPECTED: config.py + test_config.py + test_textproc.py present; target absent; OutputConfig OK
    prints `wtype ''`; subprocess OK; pytest --version prints 9.1.x; typing_backends either
    present (GREEN) or absent (RED-until-S1, expected).
  - DO NOT: create the test file yet, edit typing_backends.py/config.py, run uv sync/add,
    or touch any other file.

Task 2: CREATE tests/test_typing_backends.py — use the `write` tool with EXACTLY the
        content in "Task 2 SOURCE" below (verbatim).
  - FILE: tests/test_typing_backends.py
  - CONTENT: module docstring + `from __future__ import annotations` + imports (logging,
    subprocess, pytest, OutputConfig, the 6 names from typing_backends) + _Recorder class
    + recorder fixture + 7 test sections (26 tests).
  - DO NOT: import unittest.mock or pytest-mock (Critical #1); edit typing_backends.py
    (Critical #11); create tests/__init__.py (Critical #10); add new deps; assert a
    newline/space is appended (Critical #5); use r.message instead of getMessage() for
    caplog (Critical #7); run pytest via bare `python`/`pytest` (Critical #8).

Task 3: VALIDATE — run the Validation Loop L1 (py_compile) + L2 (pytest, the primary
        gate). Iterate until 26 passed. If S1 has NOT landed, the tests will error on
        import — that is expected (RED); once S1 lands they go GREEN. L3/L4 are scope
        guards. No git commit unless the orchestrator directs it. If asked: message
        "P1.M3.T1.S2: tests/test_typing_backends.py (26 tests, subprocess.run mocked)".
```

#### Task 2 SOURCE — `tests/test_typing_backends.py` (write verbatim)

```python
"""Unit tests for voice_typing.typing_backends (PRD §4.3 — typing-backend test harness).

Pure-Python, subprocess.run MOCKED: no display, no ydotoold, NO real keystrokes. Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_typing_backends.py -v

subprocess.run is monkeypatched for every test via the `recorder` fixture, so each call
is captured (argv + kwargs) and never reaches the OS. This is the test harness for
typing_backends.py (P1.M3.T1.S1): it pins the three PRD §4.3 command lists (wtype /
ydotool --key-delay 2 / tmux send-keys -t -l --) and the wtype->ydotool auto-fallback
contract (PRD §4.3 + §8 risk "wtype fails on some window") before the daemon
(P1.M4.T1.S2) is wired.

Written FIRST (TDD) — RED until voice_typing/typing_backends.py (P1.M3.T1.S1) lands.
"""
from __future__ import annotations

import logging
import subprocess

import pytest

from voice_typing.config import OutputConfig
from voice_typing.typing_backends import (
    TmuxBackend,
    TypingBackend,
    WtypeBackend,
    YdotoolBackend,
    _WtypeWithFallback,
    make_backend,
)


# ---------------------------------------------------------------------------
# subprocess.run recorder — captures EVERY call; never sends real keystrokes.
#
# typing_backends does `import subprocess` and calls `subprocess.run(...)`, so
# patching the `run` attribute on the `subprocess` module is what every backend
# sees (same module object regardless of importer). monkeypatch restores the real
# subprocess.run after each test — no leakage between tests.
# ---------------------------------------------------------------------------


class _Recorder:
    """Records subprocess.run(argv, **kwargs) calls and never touches the OS.

    By default each call returns CompletedProcess(returncode=0) (success under
    check=True). Configure failures with raise_on(argv[0], exc): the first element
    of argv selects the behavior ("wtype" / "ydotool" / "/usr/bin/tmux").
    """

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
        self._raises: dict[str, BaseException] = {}

    def raise_on(self, cmd0: str, exc: BaseException) -> None:
        """Make every call whose argv[0] == cmd0 raise `exc`."""
        self._raises[cmd0] = exc

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(argv, **kwargs):
            self.calls.append((tuple(argv), dict(kwargs)))
            exc = self._raises.get(argv[0])
            if exc is not None:
                raise exc
            return subprocess.CompletedProcess(args=list(argv), returncode=0)

        monkeypatch.setattr(subprocess, "run", fake_run)

    @property
    def argvs(self) -> list[tuple[str, ...]]:
        """Just the argv tuples, in call order."""
        return [argv for argv, _kw in self.calls]


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    """subprocess.run is mocked for the WHOLE test; no real keystroke is ever sent."""
    rec = _Recorder()
    rec.install(monkeypatch)
    return rec


# ---------------------------------------------------------------------------
# WtypeBackend — exact argv ["wtype","--",text] (PRD §4.3)
# ---------------------------------------------------------------------------


def test_wtype_invokes_exact_argv(recorder):
    WtypeBackend().type_text("hello world")
    assert recorder.argvs == [("wtype", "--", "hello world")]


def test_wtype_passes_check_true(recorder):
    # check=True turns nonzero exit into CalledProcessError -> the fallback can catch it.
    WtypeBackend().type_text("hi")
    assert recorder.calls[0][1].get("check") is True


def test_wtype_text_starting_with_dash_stays_literal(recorder):
    # `--` keeps "-5 degrees" positional (not parsed as an option) — PRD §4.3.
    WtypeBackend().type_text("-5 degrees")
    assert recorder.argvs == [("wtype", "--", "-5 degrees")]


def test_wtype_never_appends_newline_or_space(recorder):
    # Backends type EXACTLY `text`; the trailing space is the daemon's job.
    WtypeBackend().type_text("Hello")
    assert recorder.argvs[0][-1] == "Hello"  # no "\n", no extra " "


# ---------------------------------------------------------------------------
# YdotoolBackend — argv includes ["type","--key-delay","2","--",text] (PRD §4.3)
# ---------------------------------------------------------------------------


def test_ydotool_uses_key_delay_2(recorder):
    YdotoolBackend().type_text("hi")
    assert recorder.argvs[0][:4] == ("ydotool", "type", "--key-delay", "2")


def test_ydotool_invokes_exact_argv(recorder):
    YdotoolBackend().type_text("hello")
    assert recorder.argvs[0] == (
        "ydotool",
        "type",
        "--key-delay",
        "2",
        "--",
        "hello",
    )


def test_ydotool_passes_check_true(recorder):
    YdotoolBackend().type_text("hi")
    assert recorder.calls[0][1].get("check") is True


# ---------------------------------------------------------------------------
# TmuxBackend — /usr/bin/tmux send-keys -t <target> -l -- text (PRD §4.3)
# ---------------------------------------------------------------------------


def test_tmux_uses_full_bin_path(recorder):
    # zsh aliases `tmux`; the FULL path is mandatory (system_context.md §1).
    TmuxBackend(OutputConfig(backend="tmux", tmux_target="s:0.0")).type_text("hi")
    assert recorder.argvs[0][0] == "/usr/bin/tmux"


def test_tmux_send_keys_with_dash_l(recorder):
    # `-l` = literal text (no key-name interpretation, no trailing Enter).
    TmuxBackend(OutputConfig(backend="tmux", tmux_target="s:0.0")).type_text("a;b")
    assert recorder.argvs[0][:5] == (
        "/usr/bin/tmux",
        "send-keys",
        "-t",
        "s:0.0",
        "-l",
    )


def test_tmux_invokes_exact_argv(recorder):
    TmuxBackend(OutputConfig(backend="tmux", tmux_target="voicetest:0.0")).type_text(
        "Hello 123"
    )
    assert recorder.argvs[0] == (
        "/usr/bin/tmux",
        "send-keys",
        "-t",
        "voicetest:0.0",
        "-l",
        "--",
        "Hello 123",
    )


def test_tmux_uses_empty_target_when_unset(recorder):
    # OutputConfig().tmux_target defaults to "" (active pane / explicit default).
    TmuxBackend(OutputConfig(backend="tmux")).type_text("hi")
    assert recorder.argvs[0] == (
        "/usr/bin/tmux",
        "send-keys",
        "-t",
        "",
        "-l",
        "--",
        "hi",
    )


def test_tmux_passes_check_true(recorder):
    TmuxBackend(OutputConfig(backend="tmux")).type_text("hi")
    assert recorder.calls[0][1].get("check") is True


# ---------------------------------------------------------------------------
# TypingBackend ABC — abstract, uninstantiable (PRD §4.3 interface)
# ---------------------------------------------------------------------------


def test_typing_backend_is_abstract():
    with pytest.raises(TypeError):
        TypingBackend()


def test_concrete_backends_are_typing_backends():
    assert isinstance(WtypeBackend(), TypingBackend)
    assert isinstance(YdotoolBackend(), TypingBackend)
    assert isinstance(TmuxBackend(OutputConfig(backend="tmux")), TypingBackend)


# ---------------------------------------------------------------------------
# make_backend — factory dispatch on cfg.backend (PRD §4.3)
# ---------------------------------------------------------------------------


def test_make_backend_wtype_returns_fallback_wrapper():
    b = make_backend(OutputConfig(backend="wtype"))
    assert isinstance(b, _WtypeWithFallback)
    # S1 designed _primary/_fallback as testable injection points.
    assert isinstance(b._primary, WtypeBackend)
    assert isinstance(b._fallback, YdotoolBackend)


def test_make_backend_ydotool():
    b = make_backend(OutputConfig(backend="ydotool"))
    assert isinstance(b, YdotoolBackend)


def test_make_backend_tmux_carries_target():
    b = make_backend(OutputConfig(backend="tmux", tmux_target="s:0.1"))
    assert isinstance(b, TmuxBackend)
    assert b._tmux_target == "s:0.1"


def test_make_backend_unknown_raises_value_error():
    with pytest.raises(ValueError, match="bogus"):
        make_backend(OutputConfig(backend="bogus"))


# ---------------------------------------------------------------------------
# Auto-fallback — wtype -> ydotool on failure (PRD §4.3 + §8 risk).
# Monkeypatch subprocess.run to simulate failure (the item's required approach).
# These exercise the REAL backends end-to-end (not injected fakes).
# ---------------------------------------------------------------------------


def test_wtype_success_does_not_invoke_fallback(recorder):
    make_backend(OutputConfig(backend="wtype")).type_text("hi")
    assert len(recorder.calls) == 1
    assert recorder.argvs[0][0] == "wtype"


def test_wtype_nonzero_exit_falls_back_to_ydotool(recorder):
    # check=True converts a nonzero returncode into CalledProcessError -> caught -> fallback.
    recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
    make_backend(OutputConfig(backend="wtype")).type_text("hi")
    assert recorder.argvs[0] == ("wtype", "--", "hi")
    assert recorder.argvs[1] == (
        "ydotool",
        "type",
        "--key-delay",
        "2",
        "--",
        "hi",
    )


def test_wtype_missing_binary_falls_back_to_ydotool(recorder):
    # FileNotFoundError (binary not installed) is an OSError -> caught -> fallback.
    recorder.raise_on(
        "wtype", FileNotFoundError(2, "No such file or directory", "wtype")
    )
    make_backend(OutputConfig(backend="wtype")).type_text("hi")
    assert recorder.argvs[0][0] == "wtype"
    assert recorder.argvs[1][0] == "ydotool"


def test_wtype_permission_error_also_falls_back(recorder):
    # PermissionError (binary not executable) is an OSError too -> must fall back.
    recorder.raise_on("wtype", PermissionError("wtype not executable"))
    make_backend(OutputConfig(backend="wtype")).type_text("hi")
    assert recorder.argvs[1][0] == "ydotool"


def test_fallback_fails_too_propagates(recorder):
    # If ydotool ALSO fails, the exception propagates (retry ONCE; no silent swallow).
    recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
    recorder.raise_on("ydotool", subprocess.CalledProcessError(1, ["ydotool"]))
    with pytest.raises(subprocess.CalledProcessError):
        make_backend(OutputConfig(backend="wtype")).type_text("hi")
    # Exactly 2 subprocess calls: primary once, fallback once.
    assert len(recorder.calls) == 2


def test_fallback_retries_exactly_once(recorder):
    # Must NOT loop / retry repeatedly on consecutive failures.
    recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
    recorder.raise_on("ydotool", subprocess.CalledProcessError(1, ["ydotool"]))
    with pytest.raises(subprocess.CalledProcessError):
        make_backend(OutputConfig(backend="wtype")).type_text("hi")
    assert len(recorder.calls) == 2  # never more than primary + one fallback


def test_fallback_logs_warning(recorder, caplog):
    recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))
    with caplog.at_level(logging.WARNING, logger="voice_typing.typing_backends"):
        make_backend(OutputConfig(backend="wtype")).type_text("hi")
    assert any(
        r.levelno == logging.WARNING and "ydotool" in r.getMessage()
        for r in caplog.records
    )


# ---------------------------------------------------------------------------
# No real keystrokes — the recorder guarantees subprocess.run never runs for real.
# ---------------------------------------------------------------------------


def test_no_real_subprocess_run_during_tests(monkeypatch):
    # Sanity guard: the monkeypatch mechanism itself replaces `subprocess.run`, so a
    # stray call records instead of executing (it would otherwise type into the user's
    # FOCUSED window — a real safety hazard). Every other test uses the `recorder`
    # fixture; this one asserts the mechanism directly.
    rec = _Recorder()
    rec.install(monkeypatch)
    result = subprocess.run(["wtype", "--", "x"], check=True)
    assert result.returncode == 0
    assert rec.argvs == [("wtype", "--", "x")]
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — monkeypatch subprocess.run (NOT unittest.mock / pytest-mock). The project
# uses the stdlib pytest `monkeypatch` fixture exclusively (tests/test_config.py). Since
# typing_backends does `import subprocess` then `subprocess.run(...)`, patching the `run`
# attribute on the module is what every backend sees.
monkeypatch.setattr(subprocess, "run", fake_run)   # auto-restored after the test

# PATTERN 2 — recorder captures argv + kwargs; returns success by default; raises per cmd.
class _Recorder:
    def install(self, monkeypatch):
        def fake_run(argv, **kwargs):
            self.calls.append((tuple(argv), dict(kwargs)))
            if argv[0] in self._raises:
                raise self._raises[argv[0]]
            return subprocess.CompletedProcess(args=list(argv), returncode=0)
        monkeypatch.setattr(subprocess, "run", fake_run)

# PATTERN 3 — assert the EXACT PRD §4.3 argv (tuple equality) + check=True separately.
assert recorder.argvs == [("wtype", "--", "hello")]
assert recorder.calls[0][1].get("check") is True

# PATTERN 4 — fallback via subprocess.run raising (the item's required approach). Exercise
# the REAL backends (make_backend + type_text), not injected fakes, so the command lists
# AND the fallback ordering are both validated end-to-end.
recorder.raise_on("wtype", subprocess.CalledProcessError(1, ["wtype"]))   # nonzero exit
recorder.raise_on("wtype", FileNotFoundError(2, "no such file", "wtype"))  # missing binary
recorder.raise_on("wtype", PermissionError("not executable"))              # OSError family
# success -> exactly 1 call; both fail -> propagate + exactly 2 calls.

# PATTERN 5 — caplog WARNING via getMessage() (applies %-args reliably).
with caplog.at_level(logging.WARNING, logger="voice_typing.typing_backends"):
    ...
assert any(r.levelno == logging.WARNING and "ydotool" in r.getMessage() for r in caplog.records)
```

### Integration Points

```yaml
IMPORTS:
  - add to: tests/test_typing_backends.py (NEW)
  - pattern: |
      import logging, subprocess
      import pytest
      from voice_typing.config import OutputConfig
      from voice_typing.typing_backends import (
          TmuxBackend, TypingBackend, WtypeBackend, YdotoolBackend,
          _WtypeWithFallback, make_backend,
      )

FIXTURES:
  - new: "recorder (monkeypatches subprocess.run for the whole test) — local to this file"
  - reused: "monkeypatch, caplog, pytest.raises (stdlib pytest — no new deps)"

CONFIG: none — tests construct OutputConfig(...) directly; no config.toml reads.

DEPENDENCIES: none new. dev=["pytest>=9.1.1"] already satisfies everything. Do NOT add
  pytest-mock / unittest.mock / pytest-cov (not declared; not needed).
```

## Validation Loop

> All commands use FULL PATHS (zsh aliases — system_context.md §1). Run from
> `/home/dustin/projects/voice-typing`. L1 is instant. L2 (pytest) is the PRIMARY gate.
> L3 is a no-real-keystrokes guard. L4 is the scope guard.

### Level 1: Syntax (no deps needed beyond the venv)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
test -f tests/test_typing_backends.py && echo "L1 file present" || echo "L1 FAIL: file missing"
"$PY" -m py_compile tests/test_typing_backends.py && echo "L1 py_compile OK" || echo "L1 FAIL: syntax error"
"$PY" -c "import ast; ast.parse(open('tests/test_typing_backends.py').read()); print('L1 ast.parse OK')"
# Expected: file present; py_compile OK; ast.parse OK (proves the file parses standalone).
```

### Level 2: Unit Tests (the PRIMARY gate — 26 passed)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python

# 2a — collect first (does the file import + are 26 tests discovered?).
"$PY" -m pytest tests/test_typing_backends.py --collect-only -q
# Expected: "26 tests collected" (and NO collection errors). If S1 (typing_backends.py)
#   has NOT landed yet, collection ERRORS on the `from voice_typing.typing_backends import
#   ...` line — that is expected for TDD (RED-until-S1); re-run once S1 lands.

# 2b — run the file (the gate).
"$PY" -m pytest tests/test_typing_backends.py -v
# Expected: 26 passed, 0 failed, 0 skipped, 0 errors. Each test name listed with PASSED.
#   If any FAIL: READ the assertion message (it prints expected vs actual argv/kwargs),
#   reconcile against S1's typing_backends.py, and fix the TEST (not S1 — S1 owns the impl;
#   raise the discrepancy if the impl diverges from P1M3T1S1/PRP.md).

# 2c — full suite regression (nothing else broke).
"$PY" -m pytest -v
# Expected: all previously-passing tests still pass + the 26 new ones = (43 + 26) = 69 passed
#   (assuming S1 + config/textproc tests are all GREEN).
```

### Level 3: No-real-keystrokes guard (subprocess.run is fully mocked)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python

# 3a — prove NO test reaches the real subprocess.run: every test is covered by the
# `recorder` fixture (or installs its own _Recorder). A negative proof: grep the test
# file for any subprocess.run call NOT inside a fake_run defined under monkeypatch.
grep -nE 'subprocess\.run' tests/test_typing_backends.py
# Expected: the ONLY occurrences are (a) inside `_Recorder.install`'s `fake_run` body is
#   NOT a real call (it's the patched attribute assignment target — actually `monkeypatch.
#   setattr(subprocess, "run", fake_run)`), and (b) the ONE direct call in
#   `test_no_real_subprocess_run_during_tests`, which is GUARDED by `rec.install(monkeypatch)`
#   on the line above it. There must be NO unguarded `subprocess.run(...)` that could type
#   into the focused window.

# 3b — run with -p no:cacheprovider for a clean run (no stale cache) — optional sanity.
"$PY" -m pytest tests/test_typing_backends.py -v -p no:cacheprovider
# Expected: 26 passed again (hermetic; no dependence on prior state).
```

### Level 4: Creative & Domain-Specific Validation

```bash
cd /home/dustin/projects/voice-typing

# 4a — SCOPE GUARD: confirm ONLY tests/test_typing_backends.py was created.
test -f tests/test_typing_backends.py && echo "L4 ok: test file present" || echo "L4 FAIL"
test ! -e tests/__init__.py && echo "L4 ok: no tests/__init__.py added" || echo "L4 FAIL: __init__.py created (out of scope)"
git status --porcelain
# Expected: git status shows ONLY: ?? tests/test_typing_backends.py   (one new untracked file).
#   Any modification to voice_typing/typing_backends.py, config.py, textproc.py, config.toml,
#   pyproject.toml, uv.lock, PRD.md, tasks.json is a SCOPE VIOLATION.

# 4b — OPTIONAL lint (ruff is a uv tool at ~/.local/bin/ruff, NOT in .venv; do NOT block
#   on a missing/empty config). py_compile + pytest (L1/L2) are the authoritative gates.
command -v ruff >/dev/null 2>&1 && ruff format --check tests/test_typing_backends.py || echo "L4 note: ruff absent or no config — skipped (not a gate)"

# DOMAIN NOTE — real wtype/ydotool/tmux execution is intentionally NOT exercised here:
#   this task is UNIT tests only (subprocess mocked). Real execution is validated by the
#   E2E test (P1.M7.T3.S1, which uses backend="tmux" against a throwaway pane) and by
#   manual daemon usage (P1.M4). ydotoold state is install.sh's (P1.M6) concern.
```

## Final Validation Checklist

### Technical Validation

- [ ] `.venv/bin/python -m py_compile tests/test_typing_backends.py` → exit 0.
- [ ] `.venv/bin/python -m pytest tests/test_typing_backends.py --collect-only -q` → "26 tests collected", no errors.
- [ ] `.venv/bin/python -m pytest tests/test_typing_backends.py -v` → **26 passed**.
- [ ] `.venv/bin/python -m pytest -v` → full suite green (new tests + all prior tests pass).
- [ ] L3 no-real-keystrokes guard: every `subprocess.run` in the file is under the `recorder` fixture / a manually installed `_Recorder` (grep confirms no unguarded call).
- [ ] L4 scope guard: ONLY `tests/test_typing_backends.py` created; no `tests/__init__.py`; no edits to `typing_backends.py`/`config.py`/`textproc.py`/`config.toml`/`pyproject.toml`/`uv.lock`.

### Feature Validation

- [ ] WtypeBackend asserts exact argv `("wtype","--",text)` + `check=True`; text with a leading `-` stays literal; no newline/space appended.
- [ ] YdotoolBackend asserts argv starts `("ydotool","type","--key-delay","2",...)`, full argv match, + `check=True`.
- [ ] TmuxBackend asserts `argv[0]=="/usr/bin/tmux"`, `-l` present, exact argv incl `-t <target>`, the empty-target path, + `check=True`.
- [ ] `TypingBackend()` raises `TypeError`; concretes are `TypingBackend` instances.
- [ ] `make_backend`: wtype→`_WtypeWithFallback` (`_primary` WtypeBackend / `_fallback` YdotoolBackend); ydotool→`YdotoolBackend`; tmux→`TmuxBackend` (`_tmux_target`); bogus→`ValueError(match="bogus")`.
- [ ] Auto-fallback: success→1 call; `CalledProcessError`/`FileNotFoundError`/`PermissionError` on wtype→ydotool invoked; both fail→`CalledProcessError` propagates + exactly 2 calls; WARNING logged mentioning "ydotool".
- [ ] No real keystrokes sent (the recorder fixture covers every test).

### Code Quality Validation

- [ ] Module docstring mirrors `tests/test_config.py`/`test_textproc.py` (what it tests, PRD §4.3 cross-ref, pure-Python/subprocess-mocked note, run command, TDD note).
- [ ] `from __future__ import annotations`; imports limited to `logging`, `subprocess`, `pytest`, `OutputConfig`, + the 6 names from `typing_backends`.
- [ ] Section dividers (`# ----`) group tests by concern, matching the established style.
- [ ] Descriptive `test_X_Y` names; assertion messages explain expected vs actual where non-obvious.
- [ ] No `unittest.mock`, no `pytest-mock`, no new deps; only the stdlib `monkeypatch`/`caplog` fixtures.

### Documentation & Deployment

- [ ] Module docstring documents: the mock strategy, the PRD §4.3 + §8 contract being pinned, the run command, and the TDD/RED-until-S1 note.
- [ ] No new env vars, no config keys, no user-facing surface (item DOCS: "none — test-only").

---

## Anti-Patterns to Avoid

- ❌ Don't use `unittest.mock.patch` or `pytest-mock` — the project uses the stdlib pytest `monkeypatch` fixture exclusively (see `tests/test_config.py`); adding a mock lib is a new dep and a style break.
- ❌ Don't run the REAL `wtype`/`ydotool`/`tmux` — they type into the focused window (a safety hazard) and are non-deterministic; mock `subprocess.run` for every test.
- ❌ Don't forget to assert `check=True` — it is load-bearing for the fallback (without it, nonzero exit is undetectable and the fallback never fires).
- ❌ Don't only test `FileNotFoundError` for the fallback — `PermissionError` and other `OSError`s must also fall back; S1 catches `(CalledProcessError, OSError)`.
- ❌ Don't assert the fallback exception is swallowed — it PROPAGATES (retry once, then surface to the daemon); assert `pytest.raises` + exactly 2 calls.
- ❌ Don't assert a newline/space is appended — backends type exactly `text`; the daemon owns `append_space`; textproc owns trailing-newline stripping.
- ❌ Don't accept a bare `"tmux"` in the TmuxBackend argv — assert `"/usr/bin/tmux"` literally (zsh aliases tmux; a regression to the alias must be caught).
- ❌ Don't use `r.message` for the caplog assertion — use `r.getMessage()` (applies %-args reliably).
- ❌ Don't edit `voice_typing/typing_backends.py` — S1 owns it (parallel task); if a test reveals an impl bug, raise it, don't patch the impl here.
- ❌ Don't create `tests/__init__.py` — pytest discovers `test_*.py` without it (43 tests already collect); adding it changes import semantics.
- ❌ Don't run `mypy` — it is not installed; `py_compile` + `pytest` are the gates. Don't block on `ruff` if absent/uncconfigured.
- ❌ Don't run pytest via bare `python`/`pytest` — zsh aliases `python`→`uv run`; always `.venv/bin/python -m pytest`.

---

## Confidence Score

**9/10** for one-pass implementation success.

Rationale: the test file is ~190 lines of straightforward pytest + one `_Recorder` helper.
The CONTRACT under test (S1's `typing_backends.py`) is pinned verbatim from
`P1M3T1S1/PRP.md` (class/attribute names, the three exact argv, the fallback catch set +
propagate semantics, the `make_backend` dispatch + `ValueError` message) and mirrored in
the research table. The monkeypatch mechanic is proven in `tests/test_config.py`
(`monkeypatch.setattr(module, "attr", fake)`), and the recorder/`caplog`/`pytest.raises`
patterns are stdlib pytest. Every assertion is aligned with S1's verbatim source.

The −1 reserves: (a) S1 is implemented IN PARALLEL — if its actual landed code diverges
from its PRP (e.g. renames `_primary`→`primary`, or the warning message wording), the
isinstance/internal-attr + caplog tests would need a one-line tweak; the BEHAVIORAL
fallback tests (via `subprocess.run` mock) are robust to such renames and would still
pass. (b) `test_make_backend_wtype_returns_fallback_wrapper` relies on the module-private
`_WtypeWithFallback` + `_primary`/`_fallback` attributes — S1 explicitly designed these
for S2 testability (its own L3a smoke accesses them), so the dependency is intended, but
it is the one place a private-attr rename would surface. Both are bounded, one-line fixes
gated by the L2 pytest output, not architectural risks.
