# Gap Report — P1.M1.T3.S1: typing_backends.py vs PRD §4.3

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/typing_backends.py` against PRD §4.3's five typing-backend contract
points — (a) the `type_text` interface, (b) wtype→ydotool auto-fallback (WARNING + retry on nonzero
exit / `FileNotFoundError`), (c) tmux using `/usr/bin/tmux` (not the bare aliased `tmux`),
(d) ydotool `--key-delay 2`, (e) never sending Enter/newline — and re-run the pure-Python unit
suite (`tests/test_typing_backends.py`, `subprocess.run` mocked). Subtask **P1.M1.T3.S1** of
verification round `006_862ee9d6ef41`.
**Audited artifacts (all read-only):**
- `voice_typing/typing_backends.py` — `TypingBackend` ABC (`:60-61`) + `WtypeBackend` (`:75`) +
  `YdotoolBackend` (`:86`) + `TmuxBackend` (`:103`) + `_WtypeWithFallback` (`:110`, `:129`) +
  `make_backend` factory (`:142`); `_TMUX` constant (`:54`); module docstring (`:25`).
- `tests/test_typing_backends.py` — the 27-test suite (the contract's run command); `subprocess.run`
  MOCKED via the `recorder` fixture (no display / `ydotoold` / keystrokes).
- `plan/006_862ee9d6ef41/prd_snapshot.md` — §4.3 (the 5-point spec), §8 (the "wtype fails on some
  window → auto-fallback to ydotool" risk row that point (b) mitigates).

**Bottom line:** ✅ `typing_backends.py` is **COMPLIANT** with PRD §4.3 — all 5 contract points
hold, each mapped to a `typing_backends.py` file:line, and the 27-test suite is green
(`subprocess.run` mocked). **No source files were modified** — the backends faithfully implement the
spec, including the `/usr/bin/tmux` full-path guard against the zsh-`tmux`-alias trap. The two
non-blocking observations (the `(CalledProcessError, OSError)` *tested superset*; the absent-but-
correct-by-construction fallback-fail-propagates test) are recorded in §4 so they are not mistaken
for defects.

---

## 1. Method

Each of the five PRD §4.3 points was mapped 1:1 to its `typing_backends.py` implementation by
`grep -n` (the file:line evidence), and the no-bare-`tmux` invariant was checked directly. The full
`tests/test_typing_backends.py` suite was then **re-run live** to record the actual pass count and
timing. Nothing was assumed from the PRP's embedded numbers — every figure below was re-verified
this round (pure stdlib: `subprocess`/`logging`/`abc`; no GPU/daemon/display/`ydotoold` required).

### Commands run (re-verification)

```bash
# (a) Line-number map of the 5 audit points (grep -n)
grep -nE '@abstractmethod|def type_text\(self, text: str\) -> None' voice_typing/typing_backends.py
grep -nE 'except \(subprocess.CalledProcessError, OSError\)|logger.warning|_fallback.type_text\(text\)' voice_typing/typing_backends.py
grep -nE '_TMUX = "/usr/bin/tmux"|\[_TMUX, "send-keys"' voice_typing/typing_backends.py
grep -nE '"--key-delay", "2"' voice_typing/typing_backends.py
grep -nE '"-l", "--"|NEVER EMIT ENTER' voice_typing/typing_backends.py
grep -nE 'subprocess.run\(\["tmux"' voice_typing/typing_backends.py   # the bare-tmux defect check → CLEAN

# (b) The unit suite (the contract's run command), LIVE
.venv/bin/python -m pytest tests/test_typing_backends.py -q
```

### Observed output (abridged)

```
(a) 60:@abstractmethod  61:def type_text(self, text: str) -> None   (+ impls @75, 86, 103, 129)
(b) 132:except (subprocess.CalledProcessError, OSError) as exc:  136:logger.warning(  139:_fallback.type_text(text)
(c) 54:_TMUX = "/usr/bin/tmux"   105:[_TMUX, "send-keys", ...]
(d) 90:["ydotool", "type", "--key-delay", "2", "--", text], check=True
(e) 25:NEVER EMIT ENTER/NEWLINE ...   105:[_TMUX, "send-keys", "-t", ..., "-l", "--", text]
(e-clean) no bare "tmux" in any subprocess.run argv → CLEAN
...........................                                              [100%]
27 passed in 0.01s
```

---

## 2. Per-point Compliance Table (PRD §4.3 vs `typing_backends.py`)

| # | PRD §4.3 requirement | Expected (spec) | `typing_backends.py` actual | file:line | Pinning tests (`tests/test_typing_backends.py`) | Verdict |
|---|---|---|---|---|---|---|
| **(a)** | `type_text(text: str) -> None` interface on a backend selected by `output.backend` | `TypingBackend` ABC + concrete impls + `make_backend(cfg)` factory returning a `TypingBackend` | `TypingBackend` ABC declares `@abstractmethod def type_text(self, text: str) -> None`; 4 concrete backends implement it (`WtypeBackend`, `YdotoolBackend`, `TmuxBackend`, `_WtypeWithFallback`); `make_backend(cfg)` dispatches on `cfg.backend` and returns a `TypingBackend` | ABC `:60-61`; impls `:75`, `:86`, `:103`, `:129`; `make_backend` `:142` | `test_typing_backend_is_abstract` `:201`; `test_concrete_backends_are_typing_backends` `:206` | ✅ |
| **(b)** | wtype auto-fallback: WARNING log + retry via ydotool on nonzero exit OR missing binary | "daemon MUST auto-fall-back to ydotool if a wtype call fails (nonzero exit), logging a warning" (§4.3 + §8 risk row) | `_WtypeWithFallback.type_text()` tries the wtype primary (`check=True` → nonzero exit raises `CalledProcessError`), catches `(subprocess.CalledProcessError, OSError)`, logs a WARNING, and calls the ydotool fallback **once** | `except (subprocess.CalledProcessError, OSError) as exc:` `:132`; `logger.warning(...)` `:136`; `self._fallback.type_text(text)` `:139`; `make_backend` returns `_WtypeWithFallback()` for `backend=="wtype"` (`:158-159`) | `test_wtype_success_does_not_invoke_fallback` `:248`; `test_wtype_nonzero_exit_falls_back_to_ydotool` `:254`; `test_wtype_missing_binary_falls_back_to_ydotool` `:269`; `test_wtype_permission_error_also_falls_back` `:279` (the superset proof) | ✅ |
| **(c)** | tmux uses `/usr/bin/tmux` (NOT bare `tmux`) | `["/usr/bin/tmux", "send-keys", ...]` (full path; zsh aliases `tmux`) | `_TMUX = "/usr/bin/tmux"` constant; `TmuxBackend.type_text()` uses `[_TMUX, "send-keys", ...]` as argv[0]; `grep` confirms **no** `subprocess.run(["tmux", ...])` anywhere — every `"tmux"` token is a docstring or the `backend == "tmux"` config-string comparison | `_TMUX = "/usr/bin/tmux"` `:54`; TmuxBackend argv `:105` | `test_tmux_uses_full_bin_path` `:144` (asserts `argv[0] == "/usr/bin/tmux"`) | ✅ |
| **(d)** | ydotool `--key-delay 2` | `["ydotool", "type", "--key-delay", "2", "--", text]` | `YdotoolBackend.type_text()` runs `["ydotool", "type", "--key-delay", "2", "--", text]` with `check=True` | `:90` | `test_ydotool_uses_key_delay_2` `:117` (asserts `argv[:4] == ("ydotool", "type", "--key-delay", "2")`) | ✅ |
| **(e)** | Never send Enter/newline | "Never send Enter/newline ... strip trailing newlines in textproc"; backends type exactly what they're given (no ADDED newline) | WtypeBackend `["wtype", "--", text]` (`:80`); YdotoolBackend `["ydotool", "type", "--key-delay", "2", "--", text]` (`:90`); TmuxBackend uses the literal `-l` flag + `--` separator (`[_TMUX, "send-keys", "-t", ..., "-l", "--", text]`, `:105`) so `send-keys` treats the argument as LITERAL text (no key-name interpretation, no trailing Enter). Module docstring documents it explicitly | docstring `:25`; tmux `-l` + `--` `:105` | `test_wtype_never_appends_newline_or_space` `:106`; `test_tmux_send_keys_with_dash_l` `:150` | ✅ |

> All five points **PASS**. The file:line numbers above are `grep -n`-verified against the live tree
> this round. The bare-`tmux` defect check (`grep -nE 'subprocess.run\(\["tmux"'`) returned **CLEAN**
> — confirming point (c) holds literally, not just by the `_TMUX` constant's existence.

---

## 3. Test Results

```
.venv/bin/python -m pytest tests/test_typing_backends.py -q
...........................                                              [100%]
27 passed in 0.01s
```

**27 passed, 0 failed, 0 errors.** This matches the PRP's verified baseline exactly. The suite
mocks `subprocess.run` via the `recorder` fixture for the whole test (no real `wtype`/`ydotool`/
`tmux` keystroke is ever sent — Gotcha #7 holds). Coverage by concern:

- **Interface / ABC (a):** `test_typing_backend_is_abstract` `:201` (instantiating the ABC raises);
  `test_concrete_backends_are_typing_backends` `:206` (all concrete backends are `TypingBackend`).
- **wtype argv (e):** `test_wtype_never_appends_newline_or_space` `:106` (exact argv incl. `--` +
  no trailing newline/space); plus `check=True` + dash-literal assertions.
- **ydotool argv (d):** `test_ydotool_uses_key_delay_2` `:117` (`argv[:4]`); plus the full-argv +
  `check=True` assertions.
- **tmux argv (c, e):** `test_tmux_uses_full_bin_path` `:144` (`argv[0] == "/usr/bin/tmux"` — THE
  full-path pin); `test_tmux_send_keys_with_dash_l` `:150` (the `-l` literal flag); plus exact
  argv + empty-target-when-unset + `check=True`.
- **make_backend factory:** wtype→`_WtypeWithFallback` wrapper, ydotool, tmux-carries-target,
  unknown-backend→`ValueError`.
- **auto-fallback (b):** `test_wtype_success_does_not_invoke_fallback` `:248` (happy path);
  `test_wtype_nonzero_exit_falls_back_to_ydotool` `:254` (`CalledProcessError` → ydotool);
  `test_wtype_missing_binary_falls_back_to_ydotool` `:269` (`FileNotFoundError` → ydotool);
  `test_wtype_permission_error_also_falls_back` `:279` (`PermissionError` → ydotool — the superset
  proof).

---

## 4. Mismatches / Drift / Notes

**None — `typing_backends.py` is fully PRD §4.3-compliant.** All 5 points map 1:1 to the spec with
file:line evidence (§2); the 27-test suite is green (§3); no source files were modified.

Two **non-blocking observations** are recorded here so a future reader does not mistake them for
defects (neither is a §4.3 violation; neither warrants a code change):

### 4.1 (b) The fallback `except` is a TESTED SUPERSET — compliant, not over-broad

PRD §4.3 names the auto-fallback trigger as "nonzero exit or `FileNotFoundError`." The code catches
**(`subprocess.CalledProcessError`, `OSError`)** (`typing_backends.py:132`), which is a **superset**:

```
OSError
├── FileNotFoundError      (binary missing — the §4.3 named case)
├── PermissionError        (binary present but not executable)
└── ... (other OSError subclasses)
```

`CalledProcessError` covers the nonzero-exit case (the `check=True` on `WtypeBackend` converts a
nonzero return code into the exception). This is **intentionally MORE robust** than the contract's
literal wording: a `PermissionError` (e.g. a non-executable `wtype` binary) would otherwise be
swallowed instead of triggering the ydotool retry. It is **explicitly tested** by
`test_wtype_permission_error_also_falls_back` (`tests/test_typing_backends.py:279`).

> **Do NOT "narrow" this to `(CalledProcessError, FileNotFoundError)`.** That would re-introduce the
> swallowed-`PermissionError` risk the superset guards against. It is recorded here precisely so a
> well-meaning future tightening does not become a regression. This mirrors the "compliant-by-design"
> recording convention used for the VT-006 blocklist decision in `gap_config.md` (§3).

### 4.2 (b) No explicit "fallback-fail-propagates" test — correct-by-construction

The `_WtypeWithFallback` docstring states that if the ydotool fallback *also* raises, the exception
propagates (it is "never silently swallowed"). The behavior is **correct-by-construction**: the
fallback call (`self._fallback.type_text(text)`, `typing_backends.py:139`) is **not** wrapped in a
`try/except`, so any exception it raises naturally propagates to the caller. There is no *explicit*
test asserting fallback-failure propagation, but §4.3 does not require one — this is a non-blocking
"nice-to-have" coverage observation, not a gap.

---

## 5. Conclusion

**PASS — no fix required.** `voice_typing/typing_backends.py` faithfully implements PRD §4.3 on all
five contract points: (a) the `type_text(text: str) -> None` interface via the `TypingBackend` ABC
(`:60-61`) + 4 concrete backends + the `make_backend` factory (`:142`); (b) the wtype→ydotool
auto-fallback with a WARNING log + single retry on `(CalledProcessError, OSError)` (`:132`/`:136`/
`:139`) — a *tested superset* of the spec's "nonzero exit or `FileNotFoundError`"; (c) tmux using
the full `/usr/bin/tmux` path (`_TMUX` `:54`, argv `:105`) — with **no** bare `tmux` anywhere in a
`subprocess.run` argv, guarding against the zsh-`tmux`-alias trap; (d) ydotool `--key-delay 2`
(`:90`); (e) never sending Enter/newline — the tmux `-l` literal flag + `--` separators (`:105`),
the wtype/ydotool `--` separators, and the module docstring (`:25`). The 27-test suite
(`tests/test_typing_backends.py`, `subprocess.run` mocked) pins every point including the
permission-error fallback (the superset proof) and the `/usr/bin/tmux` full-path assertion.

**No code changes were required and none were made.** `voice_typing/typing_backends.py` and
`tests/test_typing_backends.py` are **unchanged**. The two non-blocking observations
(§4 — the OSError superset; the absent fallback-fail-propagates test) are recorded so they are not
mistaken for defects or "fixed" into regressions.

This closes **P1.M1.T3.S1**. Downstream **P1.M2.T1** (main-loop audit) can rely on this report's
per-point table as the reference for the `make_backend(cfg.output).type_text(...)` contract the
daemon's `on_final` depends on; **P1.M7.T3** (E2E test) can rely on point (c)'s `/usr/bin/tmux` +
`send-keys -l` argv for its `backend="tmux"` text capture. The §4.3 trailing-newline *strip* is
textproc's job (audited in `gap_textproc.md`, P1.M1.T2.S1) — the backends only guarantee they type
exactly what they're given and never ADD a newline (point (e)).