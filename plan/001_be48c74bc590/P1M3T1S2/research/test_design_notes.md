# P1.M3.T1.S2 — Test Design Notes (typing_backends unit tests)

**Goal:** `tests/test_typing_backends.py` — pure-Python, subprocess MOCKED, no real
keystrokes. Pins the three PRD §4.3 command lists + the wtype→ydotool auto-fallback.
Written FIRST (TDD); RED until `voice_typing/typing_backends.py` (P1.M3.T1.S1) lands.

---

## 1. What S1 produces (the CONTRACT under test — from P1M3T1S1/PRP.md, verbatim source)

`voice_typing/typing_backends.py` exports:

| Name | Kind | Behavior under test |
|---|---|---|
| `TypingBackend` | ABC | `@abstractmethod type_text`; `TypingBackend()` → `TypeError` |
| `WtypeBackend` | class | `subprocess.run(["wtype","--",text], check=True)` |
| `YdotoolBackend` | class | `subprocess.run(["ydotool","type","--key-delay","2","--",text], check=True)` |
| `TmuxBackend(cfg)` | class | stores `cfg.tmux_target` (attr `_tmux_target`); `subprocess.run(["/usr/bin/tmux","send-keys","-t",target,"-l","--",text], check=True)` |
| `_WtypeWithFallback` | private class | `__init__(primary=None, fallback=None)`; attrs `_primary`/`_fallback`; catches `(CalledProcessError, OSError)`, logs WARNING, retries ONCE via fallback, PROPAGATES if fallback also raises |
| `make_backend(cfg)` | factory | `cfg.backend=="wtype"`→`_WtypeWithFallback()`; `"ydotool"`→`YdotoolBackend()`; `"tmux"`→`TmuxBackend(cfg)`; else `ValueError(f"unknown output.backend: {backend!r}")` |
| `_TMUX` | constant | `"/usr/bin/tmux"` (zsh aliases tmux — full path mandatory) |

`make_backend` takes `OutputConfig` (NOT `VoiceTypingConfig`). `append_space` is the
daemon's concern — backends type exactly the text given (no newline/space appended).

---

## 2. Why monkeypatch `subprocess.run` (the item's required approach)

The item says: *"monkeypatch subprocess.run to simulate failure"* and *"No real
keystrokes must be sent during tests (mock everything)."*

**Mechanic:** `typing_backends.py` does `import subprocess` then `subprocess.run(...)`.
So patching the `run` ATTRIBUTE on the `subprocess` module object is what every backend
sees (it is the same module object regardless of who imports it). The idiomatic pytest
fixture form (proven in `tests/test_config.py`, which uses `monkeypatch.setattr(cfgmod,
"_xdg_config_path", ...)` on module attributes) is:

```python
monkeypatch.setattr(subprocess, "run", fake_run)
```

`monkeypatch` auto-restores the real `subprocess.run` after each test — no leakage
between tests, no global state. Do NOT use `unittest.mock.patch` (the project uses the
stdlib pytest `monkeypatch` fixture exclusively — keep one pattern). Do NOT use
`pytest-mock`/`mocker` (not a dependency; `dev = ["pytest>=9.1.1"]` only).

**Recorder design:** capture `(argv_tuple, kwargs_dict)` per call. Default outcome =
`subprocess.CompletedProcess(args=argv, returncode=0)` (success under `check=True`).
Per-test failure simulation via `raise_on(argv[0], exc)` keyed on the command name
(`"wtype"` vs `"ydotool"` vs `"/usr/bin/tmux"`). See PRP → Implementation Blueprint for
the verbatim `_Recorder` class + `recorder` fixture.

---

## 3. `check=True` is load-bearing for the fallback test

PRD §4.3 lists commands as plain `subprocess.run([...])`; S1 adds `check=True` so a
**nonzero exit** raises `subprocess.CalledProcessError` (otherwise `run` returns a
`CompletedProcess` with `returncode != 0` and the fallback never fires). Therefore:

- "subprocess returns nonzero" (item wording) = `raise CalledProcessError(1, [...])` in
  the mock. The test asserts that the wrapper catches it and runs ydotool.
- Tests assert `kwargs.get("check") is True` for all three backends — this documents
  that the fallback mechanism is ARMED (a regression dropping `check=True` would be caught).

---

## 4. The OSError family — all trigger the fallback

S1 catches `(subprocess.CalledProcessError, OSError)`. `OSError` is the parent of:
- `FileNotFoundError` (binary not installed) — the PRD §8 risk case.
- `PermissionError` (binary not executable) — rarer, but must also fall back (narrowing
  to only `FileNotFoundError` would be a bug; S1 Gotcha #3 forbids it).

Tests cover BOTH `FileNotFoundError` and `PermissionError` raising on wtype, asserting
ydotool is invoked in each. This guards the S1 contract and a common implementation
mistake (catching only `FileNotFoundError`).

---

## 5. "Retry ONCE, then propagate" — the swallow-guard

S1 retry semantics: if the PRIMARY (wtype) raises, the FALLBACK (ydotool) runs ONCE. If
the fallback ALSO raises, the exception PROPAGATES (never silently swallowed — the daemon
logs/handles it). Tests:
- both `wtype` AND `ydotool` raise → `pytest.raises(CalledProcessError)` + exactly 2
  subprocess calls (one each, never a loop).
- success path → exactly 1 call (fallback NOT invoked).

---

## 6. WARNING log assertion (caplog)

S1 logs `logger = logging.getLogger(__name__)` → name `"voice_typing.typing_backends"`;
on fallback: `logger.warning("wtype typing failed (%s); retrying once via ydotool", exc)`.
Test uses `caplog.at_level(logging.WARNING, logger="voice_typing.typing_backends")` and
asserts a WARNING record whose `getMessage()` contains `"ydotool"`. Use `getMessage()`
(not `r.message`) — it always applies `%`-args reliably.

---

## 7. No real keystrokes — the safety guarantee

The `recorder` fixture replaces `subprocess.run` for the ENTIRE test, so no test can
reach the OS. A stray `subprocess.run` without the fixture would type into the user's
FOCUSED window (wtype/ydotool) — a real safety hazard. The guard test
`test_no_real_subprocess_run_during_tests` makes the mechanism explicit: it instantiates
`_Recorder`, installs it manually, and asserts a direct `subprocess.run(["wtype",...])`
returns a CompletedProcess and records (never execs). No test calls the real binary.

**Note:** real wtype/ydotool execution is deferred to the E2E test (P1.M7.T3.S1, which
uses `backend="tmux"` anyway) and manual daemon usage (P1.M4). This task is UNIT tests
only — mock everything.

---

## 8. Tooling reality (confirmed live, 2026-07-06)

- **Run:** `.venv/bin/python -m pytest tests/test_typing_backends.py -v` (zsh aliases
  `python`→`uv run`; ALWAYS use `.venv/bin/python`).
- **pytest 9.1.1** installed (dev group). 43 tests currently collect (config +
  config_repo_default + textproc).
- **No `tests/__init__.py`** — pytest discovers `test_*.py` without it. Do NOT add one.
- **mypy NOT installed** (`import mypy` → ModuleNotFoundError). Do NOT list it as a gate.
- **ruff** available at `/home/dustin/.local/bin/ruff` (a uv tool, NOT in `.venv`). Prior
  tasks treated `py_compile` + `pytest` as the authoritative gates; `ruff format --check`
  is an OPTIONAL lint (run it if present, but a missing/empty config must not block).
- The full suite gate after this task: `.venv/bin/python -m pytest -v` (all tests pass).

---

## 9. Test inventory (26 tests, 7 sections)

| Section | Tests | Key assertions |
|---|---|---|
| WtypeBackend | 4 | exact argv `("wtype","--",text)`; `check=True`; `-`-prefix literal via `--`; no newline appended |
| YdotoolBackend | 3 | argv starts `("ydotool","type","--key-delay","2",...)`; exact argv; `check=True` |
| TmuxBackend | 5 | argv[0]==`"/usr/bin/tmux"`; `-l` present; exact argv incl `-t <target>`; empty target; `check=True` |
| TypingBackend ABC | 2 | `TypingBackend()`→TypeError; concretes are `TypingBackend` instances |
| make_backend | 4 | wtype→`_WtypeWithFallback` (w/ `_primary`/`_fallback`); ydotool→YdotoolBackend; tmux→TmuxBackend(carries `_tmux_target`); bogus→`ValueError` |
| Auto-fallback | 7 | success→1 call; nonzero→ydotool; FileNotFoundError→ydotool; PermissionError→ydotool; both-fail→propagate; WARNING logged; retry exactly once |
| No real keystrokes | 1 | recorder mechanism replaces `subprocess.run`; direct call records, never execs |
