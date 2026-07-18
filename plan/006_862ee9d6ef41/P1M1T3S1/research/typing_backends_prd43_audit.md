# Research: typing_backends PRD §4.3 compliance audit (VERIFIED)

**Status:** VERIFIED against the live `voice_typing/typing_backends.py` + `tests/test_typing_backends.py`
on this machine. This note is the load-bearing evidence the implementing agent transcribes into
`plan/006_862ee9d6ef41/architecture/gap_typing.md`.
**Task:** P1.M1.T3.S1 — "Audit typing backends interface, auto-fallback & tmux path & run tests" (PRD §4.3).

---

## 0. VERDICT — COMPLIANT, no fix needed

`typing_backends.py` satisfies ALL FIVE PRD §4.3 requirements the contract names. The unit suite is
**27 passed in 0.01s** (subprocess.run mocked — no real keystrokes/display/ydotoold). The expected
`gap_typing.md` outcome is **all-pass / no source changes** (mirrors the sibling gap_textproc.md /
gap_config.md "compliant, no fix" pattern). The implementing agent re-verifies (the greps + pytest
below) and transcribes the findings; code changes happen ONLY if a real defect surfaces (none does).

---

## 1. THE 5 REQUIREMENTS — per-point evidence (file:line)

### (a) `type_text` interface matches PRD §4.3 — PASS
PRD §4.3: "Interface: `type_text(text: str) -> None`."
- `TypingBackend` ABC: `@abstractmethod def type_text(self, text: str) -> None:` (typing_backends.py:60-61).
- All concrete backends implement it: `WtypeBackend` (75), `YdotoolBackend` (86), `TmuxBackend` (103),
  `_WtypeWithFallback` (129).
- `make_backend(cfg)` returns a `TypingBackend` (factory dispatch on `cfg.backend`; line 141+).
- Tests: `test_typing_backend_is_abstract` (instantiating the ABC raises), `test_concrete_backends_are_typing_backends`.

### (b) wtype auto-fallback: WARNING + retry via ydotool on nonzero exit / FileNotFoundError — PASS
PRD §4.3 + §8 risk "wtype fails on some window": "daemon MUST auto-fall-back to ydotool if a wtype
call fails (nonzero exit), logging a warning."
- `_WtypeWithFallback.type_text()` (line 129+):
  ```python
  try:
      self._primary.type_text(text)                       # wtype (check=True)
  except (subprocess.CalledProcessError, OSError) as exc: # line 132
      logger.warning("wtype typing failed (%s); retrying once via ydotool", exc)  # line 136 — WARNING
      self._fallback.type_text(text)                      # line 139 — retry via ydotool (one retry only)
  ```
  - `CalledProcessError` = nonzero exit (the `check=True` on WtypeBackend converts it). ✓
  - `OSError` ⊇ `FileNotFoundError` (binary missing) AND `PermissionError` (not executable). ✓
- `make_backend(OutputConfig(backend="wtype"))` returns `_WtypeWithFallback()` (the wrapper) — verified
  by `test_make_backend_wtype_returns_fallback_wrapper`.
- **NOTE (compliant superset, not a defect):** the contract names "nonzero exit or FileNotFoundError",
  but the code catches `(CalledProcessError, OSError)` — a SUPERSET that also covers PermissionError.
  This is MORE robust than required, and it is EXPLICITLY TESTED:
  - `test_wtype_success_does_not_invoke_fallback` (line 248) — happy path, no fallback.
  - `test_wtype_nonzero_exit_falls_back_to_ydotool` (254) — CalledProcessError → ydotool.
  - `test_wtype_missing_binary_falls_back_to_ydotool` (269) — FileNotFoundError → ydotool.
  - `test_wtype_permission_error_also_falls_back` (279) — PermissionError → ydotool (the superset proof).
- **Optional coverage observation (NOT a §4.3 gap):** the docstring claims "If the fallback also raises,
  the exception propagates ... never silently swallowed." That behavior is correct-by-construction (the
  `self._fallback.type_text(text)` call is NOT wrapped in a try/except, so any exception naturally
  propagates), but there is no EXPLICIT test asserting fallback-failure propagation. §4.3 does not
  require that test; record it as a non-blocking "nice-to-have" in the report's mismatches/notes section.

### (c) tmux uses /usr/bin/tmux (not bare tmux) — PASS
PRD §4.3: `subprocess.run(["/usr/bin/tmux", "send-keys", ...])`. system_context.md §1: zsh aliases `tmux`.
- `_TMUX = "/usr/bin/tmux"` (line 54).
- `TmuxBackend.type_text()`: `subprocess.run([_TMUX, "send-keys", "-t", self._tmux_target, "-l", "--", text], check=True)` (line 105).
- grep confirms NO bare `"tmux"` token appears in ANY subprocess argv list — every `"tmux"` string
  occurrence is in a docstring or the `backend == "tmux"` config-string comparison, never in the call.
- Tests: `test_tmux_uses_full_bin_path` (144) asserts `argv[0] == "/usr/bin/tmux"`.

### (d) ydotool uses --key-delay 2 — PASS
PRD §4.3 verbatim: `subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text])`.
- `YdotoolBackend.type_text()` (line 86-91):
  ```python
  subprocess.run(["ydotool", "type", "--key-delay", "2", "--", text], check=True)
  ```
- Tests: `test_ydotool_uses_key_delay_2` (117) asserts `argv[:4] == ("ydotool","type","--key-delay","2")`;
  `test_ydotool_invokes_exact_argv` (122) asserts the full argv incl. `--` + text.

### (e) no Enter/newline sent (PRD §4.3 'Never send Enter/newline') — PASS
PRD §4.3: "Never send Enter/newline unless the utterance-final text itself demands it ... strip trailing
newlines in textproc."
- WtypeBackend: `["wtype", "--", text]` — `--` ends options so text is literal; no newline appended. ✓
- YdotoolBackend: `["ydotool", "type", "--key-delay", "2", "--", text]` — `--` literal; no newline. ✓
- TmuxBackend: `[_TMUX, "send-keys", "-t", ..., "-l", "--", text]` — the `-l` flag makes send-keys treat
  the argument as LITERAL text (no key-name interpretation, no trailing Enter). ✓ (Without `-l`, send-keys
  could mis-read punctuation as key names; the `-l` is the correctness flag.)
- Module docstring documents it explicitly: "NEVER EMIT ENTER/NEWLINE: the backends type EXACTLY the text
  passed (no trailing newline). textproc.clean() already stripped trailing newlines/whitespace; the daemon
  appends a single trailing space when output.append_space (not the backend)." (line 25-31.)
- Test: `test_wtype_never_appends_newline_or_space` (106).

---

## 2. TEST SUITE — 27 passed (the contract's run command)

```
.venv/bin/python -m pytest tests/test_typing_backends.py -q
→ 27 passed in 0.01s
```

Coverage by backend (all subprocess.run MOCKED via the `recorder` fixture — no display/ydotoold/keystrokes):
- **wtype** (4): exact argv, check=True, dash-literal, never-appends-newline/space.
- **ydotool** (3): --key-delay 2, exact argv, check=True.
- **tmux** (5): /usr/bin/tmux full path, send-keys -l, exact argv, empty-target-when-unset, check=True.
- **ABC / typing** (2): abstract base not instantiable; concrete backends are TypingBackend subclasses.
- **make_backend factory** (4): wtype→fallback-wrapper, ydotool, tmux-carries-target, unknown→ValueError.
- **auto-fallback** (4): success-no-fallback, nonzero-exit→ydotool, missing-binary→ydotool, permission-error→ydotool.
- (+ a couple structural/shared) = 27 total.

The `recorder` fixture monkeypatches `subprocess.run` for the WHOLE test (no real keystroke is ever sent);
it returns `CompletedProcess(returncode=0)` by default and can be tuned per-argv to simulate failures.

---

## 3. PARALLEL-TASK AWARENESS (no conflict)

- **P1.M1.T2.S1** (textproc audit, in parallel): produces `plan/006_862ee9d6ef41/architecture/gap_textproc.md`
  + audits `voice_typing/textproc.py` / runs `tests/test_textproc.py`. T3.S1 audits
  `voice_typing/typing_backends.py` / runs `tests/test_typing_backends.py` / produces `gap_typing.md`.
  **DISJOINT files** — no overlap, no merge conflict. Both are verification tasks with a gap-report
  deliverable; both follow the `gap_<module>.md` convention established by P1.M1.T1.S1 (`gap_config.md`).
- The gap-report convention location: `plan/006_862ee9d6ef41/architecture/` (confirmed: `gap_config.md`
  + `gap_textproc.md` already exist there). T3.S1 writes `gap_typing.md` to the SAME directory.

---

## 4. THE gap_typing.md REPORT STRUCTURE (mirror the sibling convention)

`gap_typing.md` should contain (mirror gap_textproc.md / gap_config.md):
1. **Header + verdict** — "typing_backends.py PRD §4.3 compliance audit" + the COMPLIANT verdict.
2. **Per-requirement compliance table** — the 5 points (a-e) with PRD §4.3 expected vs code actual (file:line) + PASS/FAIL. (All PASS.)
3. **Test-suite result** — `27 passed in 0.01s` (the contract's run command).
4. **Mismatches / drift / notes** — none (fully compliant); record the two OBSERVATIONS:
   - (b-superset) the fallback catches `(CalledProcessError, OSError)` — a tested SUPERSET of "nonzero
     exit or FileNotFoundError" (also covers PermissionError); MORE robust than required, not a defect.
   - (b-optional) no explicit "fallback-fail-propagates" test, but the behavior is correct-by-construction
     (the fallback call is unwrapped); §4.3 does not require that test — non-blocking nice-to-have.
5. **Conclusion** — COMPLIANT; no source changes; the typing backends faithfully implement PRD §4.3.

---

## 5. SCOPE DISCIPLINE (the contract's negative constraints)

- T3.S1 audits `voice_typing/typing_backends.py` + runs `tests/test_typing_backends.py` + writes
  `gap_typing.md`. That is its ENTIRE scope.
- DO NOT modify source unless a REAL defect is found (none is — the verdict is COMPLIANT). If the
  re-verification somehow surfaces a defect, fix it in `typing_backends.py` and record the fix in the
  report; otherwise record "no source changes — fully §4.3-compliant per audit."
- DO NOT re-audit textproc (T2.S1), config (T1.S1/S2/S3), or the daemon `on_final` wiring (P1.M2.T1).
- DO NOT touch config.toml (Mode A backend-selection docs are already correct — verified: `[output]`
  documents wtype/ydotool/tmux + the auto-fallback). DOCS: none for this subtask.
- DO NOT modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`, or any test file.