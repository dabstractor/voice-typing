# PRP — P1.M1.T3.S1: Audit typing backends interface, auto-fallback & tmux path & run tests

## Goal

**Feature Goal**: Produce an authoritative **gap report** (`plan/006_862ee9d6ef41/architecture/gap_typing.md`) cross-checking `voice_typing/typing_backends.py` against **PRD §4.3** on the five contract points — (a) the `type_text` interface, (b) wtype→ydotool auto-fallback (WARNING + retry on nonzero exit / FileNotFoundError), (c) tmux using `/usr/bin/tmux` (not the aliased bare `tmux`), (d) ydotool `--key-delay 2`, (e) never sending Enter/newline — and run the pure-Python unit suite (`tests/test_typing_backends.py`, subprocess mocked). This is a **verification/audit** subtask: the deliverable is the report; code changes happen ONLY if a real defect is found (none is expected — the audit finds `typing_backends.py` fully PRD §4.3-compliant).

**Deliverable**: One report at `plan/006_862ee9d6ef41/architecture/gap_typing.md` (mirroring the `gap_config.md` / `gap_textproc.md` convention) containing: (a) a per-point compliance table (PRD §4.3 expected vs `typing_backends.py` actual, with file:line); (b) the unit-test pass/fail count; (c) a mismatches/drift/notes section; (d) a conclusion. **This PRP's author has already performed the audit** (findings embedded below + in the research note) — the implementing agent re-verifies and transcribes, then writes the report.

**Success Definition**:
- (a) `plan/006_862ee9d6ef41/architecture/gap_typing.md` exists with the 4 sections above.
- (b) The recorded findings match the live re-verification: all 5 PRD §4.3 points are **compliant** (each with `typing_backends.py` file:line).
- (c) `.venv/bin/python -m pytest tests/test_typing_backends.py -q` → all pass (record the count; verified baseline: **27 passed**).
- (d) **No source files are modified** (because no defect exists — `typing_backends.py` is fully PRD §4.3-compliant per audit). If — and only if — the re-verification surfaces a REAL defect, fix it in `typing_backends.py` and record the fix; otherwise record "none — `typing_backends.py` is PRD §4.3-compliant per audit."
- (e) The report notes the two non-blocking observations (the `(CalledProcessError, OSError)` superset that also covers PermissionError; the absent-but-correct-by-construction fallback-fail-propagates test) so they aren't mistaken for defects.

> **VERIFIED VERDICT (this PRP's research): `typing_backends.py` is PRD §4.3-COMPLIANT — no fix needed.** All 5 points pass statically (file:line below); `tests/test_typing_backends.py` = **27 passed in 0.01s**.

## User Persona

**Target User**: the maintainer (human or AI agent) who needs to trust that the typing backends faithfully implement PRD §4.3 before the daemon ships typed text through them. Also the downstream P1.M2.T1 (main-loop audit) + P1.M7.T3 (E2E test) which depend on `make_backend(cfg.output).type_text(...)` and the tmux backend respectively.
**Use Case**: A future change to `typing_backends.py` (e.g. dropping the `-l` flag, swapping the fallback exception set, or using a bare `tmux`). The gap report + the unit tests are the reference that proves the change keeps (or breaks) PRD §4.3 compliance.
**Pain Points Addressed**: Closes the "do the backends actually (a) expose `type_text`, (b) auto-fall-back to ydotool on a wtype failure, (c) use `/usr/bin/tmux`, (d) pass `--key-delay 2`, and (e) never emit Enter/newline?" question with recorded, re-runnable evidence — not an assumption. (The §8 risk "wtype fails on some window" is mitigated by (b); the zsh-`tmux`-alias trap is mitigated by (c).)

## Why

- **PRD §4.3 is the spec; §8 names the auto-fallback as a prescribed mitigation.** The typing backends are the LAST hop before text leaves the daemon into the user's focused window — a wrong argv (bare `tmux`, missing `-l`, a swallowed failure) directly degrades or breaks the product. This audit confirms the implementation matches the spec before the heavier E2E (P1.M7.T3) + acceptance gates rely on it.
- **Catch silent drift the unit tests might not pin to the PRD.** The unit tests pin BEHAVIOR (exact argv, check=True, fallback ordering) but do not explicitly map each assertion to "PRD §4.3 point (a)-(e)." A future refactor could pass the tests yet drift from the PRD's wording (e.g. catch only `CalledProcessError` and silently drop the FileNotFoundError path). This audit is the human/agent check that closes that mapping gap, recorded durably in `gap_typing.md`.
- **Document the one robust design choice that is a SUPERSET of the contract** so it isn't "fixed" into a regression. The fallback catches `(CalledProcessError, OSError)` — broader than the contract's literal "nonzero exit or FileNotFoundError" — and there's an explicit PermissionError test. Recording this prevents a well-meaning future narrowing that would re-introduce the swallowed-failure risk.
- **Lowest-risk outcome.** The live verification (this PRP's author) finds `typing_backends.py` fully §4.3-compliant → no code changes → zero regression risk. The deliverable is the recorded evidence.
- **Scope discipline.** T3.S1 owns ONLY `typing_backends.py` audit + `gap_typing.md`. It does NOT re-audit textproc (P1.M1.T2 — the trailing-newline strip is textproc's job per §4.3), config (P1.M1.T1), or the daemon `on_final` wiring (P1.M2.T1), and does NOT modify source unless a real defect is found.

## What

Re-verify `typing_backends.py` against PRD §4.3's five points, run `tests/test_typing_backends.py`, and write `gap_typing.md`. No code change expected.

### The 5 audit points (the authority — PRD §4.3 + the contract)

| # | PRD §4.3 requirement | how to verify |
|---|---|---|
| (a) | Interface `type_text(text: str) -> None` on a backend selected by `output.backend` | `TypingBackend` ABC + 4 concrete impls + `make_backend` factory |
| (b) | wtype auto-fallback: WARNING log + retry via ydotool on nonzero exit OR missing binary | `_WtypeWithFallback` `except (CalledProcessError, OSError)` + `logger.warning` + fallback call |
| (c) | tmux uses `/usr/bin/tmux` (NOT bare `tmux`) | `_TMUX = "/usr/bin/tmux"` constant + TmuxBackend argv[0] |
| (d) | ydotool `--key-delay 2` | `YdotoolBackend` argv |
| (e) | Never send Enter/newline | no newline in any argv; tmux `-l` literal flag; `--` literal separator |

### Success Criteria

- [ ] `gap_typing.md` records: (a) ✅, (b) ✅, (c) ✅, (d) ✅, (e) ✅ (each with `typing_backends.py` file:line).
- [ ] `.venv/bin/python -m pytest tests/test_typing_backends.py -q` → `<N> passed` (baseline **27**), 0 failed.
- [ ] The report's notes section records the two non-blocking observations (the OSError superset; the absent fallback-fail-propagates test) — neither is a §4.3 defect.
- [ ] **No source files modified** unless the re-verification surfaces a REAL defect (none expected). If a defect IS found, fix `typing_backends.py` + record it; otherwise "no source changes — compliant per audit."
- [ ] `git diff --name-only` (excluding `plan/`) is EMPTY on the no-defect path (the report lives under `plan/.../architecture/`).

## All Needed Context

### Context Completeness Check

_Pass._ The verbatim current `typing_backends.py` source (with file:line for every load-bearing statement), every relevant unit test (with file:line), the contract's 5 points mapped to specific code + tests, the parallel-sibling no-conflict analysis, the gap-report convention (`gap_<module>.md` under `architecture/`), and the verified pytest baseline (27 passed) are all below. An agent new to this repo can re-verify + transcribe from this PRP alone. No CUDA/daemon/audio/display needed — `typing_backends.py` is pure stdlib (`subprocess`/`logging`/`abc`); tests mock `subprocess.run`.

### Documentation & References

```yaml
# MUST READ — the verified audit findings + the report structure (this task's own research)
- docfile: plan/006_862ee9d6ef41/P1M1T3S1/research/typing_backends_prd43_audit.md
  why: "§0 is the VERIFIED VERDICT (COMPLIANT, no fix). §1 is the per-point evidence table with file:line
        for all 5 requirements + the 4 fallback tests (success/no-fallback, nonzero-exit, missing-binary,
        permission-error). §2 is the test-suite result (27 passed). §3 is the parallel no-conflict + the
        gap-report convention location. §4 is the gap_typing.md structure to mirror. §5 is scope discipline."
  critical: "§1 (b) is load-bearing: the code catches (CalledProcessError, OSError) — a SUPERSET of the
            contract's 'nonzero exit or FileNotFoundError' (OSError also covers PermissionError). This is
            MORE robust than required + explicitly tested — record it as a compliant superset, NOT a defect.
            Also note (§1 b-optional) there is no explicit fallback-fail-propagates test, but the behavior
            is correct-by-construction (the fallback call is unwrapped) — non-blocking."

# THE FILE UNDER AUDIT — voice_typing/typing_backends.py
- file: voice_typing/typing_backends.py
  why: "The 5 audit points map to: (a) TypingBackend ABC @60-61 + impls @75/86/103/129 + make_backend @141+;
        (b) _WtypeWithFallback except (CalledProcessError, OSError) @132 + logger.warning @136 + fallback
        call @139; (c) _TMUX='/usr/bin/tmux' @54 + TmuxBackend argv @105; (d) YdotoolBackend argv @90
        ('--key-delay','2'); (e) '-l' literal flag @105 + '--' separators + the NEVER EMIT ENTER/NEWLINE
        docstring @25. All verified present."
  pattern: "Pure stdlib (subprocess/logging/abc + OutputConfig). check=True on every subprocess.run converts
            nonzero exit → CalledProcessError (the fallback's trigger). make_backend() returns a TypingBackend;
            backend=='wtype' → _WtypeWithFallback (the wrapped pair)."
  gotcha: "The fallback's except is (CalledProcessError, OSError), NOT just (CalledProcessError, 
           FileNotFoundError). OSError ⊇ FileNotFoundError ⊇ ... AND PermissionError. This is intentional
           (more robust) + tested — do NOT flag it as over-broad. A bare 'tmux' never appears in any argv."

# THE TEST SUITE — tests/test_typing_backends.py (the contract's run command)
- file: tests/test_typing_backends.py
  why: "27 tests, subprocess.run MOCKED via the `recorder` fixture (no display/ydotoold/keystrokes). The
        load-bearing assertions: test_typing_backend_is_abstract, test_concrete_backends_are_typing_backends
        (a); test_wtype_success_does_not_invoke_fallback @248, test_wtype_nonzero_exit_falls_back_to_ydotool
        @254, test_wtype_missing_binary_falls_back_to_ydotool @269, test_wtype_permission_error_also_falls_back
        @279 (b); test_tmux_uses_full_bin_path @144 (c); test_ydotool_uses_key_delay_2 @117 (d);
        test_wtype_never_appends_newline_or_space @106 + test_tmux_send_keys_with_dash_l @150 (e)."
  pattern: "The `recorder` fixture monkeypatches subprocess.run for the whole test; returns
            CompletedProcess(returncode=0) by default and can be tuned per-argv to simulate failures. Use
            `pytest tests/test_typing_backends.py -q` (the contract command) and record the count."

# THE GAP-REPORT CONVENTION — mirror the siblings
- file: plan/006_862ee9d6ef41/architecture/gap_config.md
  why: "P1.M1.T1.S1 established the gap-report convention: gap_<module>.md under plan/.../architecture/,
        with a per-point compliance table (PRD expected vs code actual + file:line), a test result, a
        mismatches/drift section, and a conclusion. gap_textproc.md (sibling T2.S1) mirrors it. gap_typing.md
        MUST follow the same shape so the reports are consistent + greppable."
  critical: "Write gap_typing.md to plan/006_862ee9d6ef41/architecture/gap_typing.md (NOT under P1M1T3S1/ —
             the architecture/ dir is the reports home). Do NOT append to gap_config.md or gap_textproc.md."

# THE SPEC — PRD §4.3 (the authority)
- file: PRD.md
  why: "§4.3 pins: type_text(text)->None interface; wtype ['wtype','--',text] default; ydotool ['ydotool',
        'type','--key-delay','2','--',text] fallback with 'daemon MUST auto-fall-back ... logging a warning';
        tmux ['/usr/bin/tmux','send-keys','-t',target,'-l','--',text]; 'Never send Enter/newline ... strip
        trailing newlines in textproc.' §8 risk row 'wtype fails on some window' → 'auto-fallback to ydotool'."
  critical: "§4.3 is the spec; the audit maps each line to typing_backends.py code. The trailing-newline
             STRIP lives in textproc (§4.3 says so) — T2.S1's scope, NOT a typing_backends concern; the
             backends merely type exactly what they're given (no added newline)."

# THE SIBLING (parallel) — confirms no overlap
- docfile: plan/006_862ee9d6ef41/P1M1T2S1/PRP.md
  why: "T2.S1 audits voice_typing/textproc.py + runs tests/test_textproc.py + writes gap_textproc.md. T3.S1
        audits voice_typing/typing_backends.py + runs tests/test_typing_backends.py + writes gap_typing.md.
        DISJOINT files — no merge conflict. Both are verification tasks; both follow gap_<module>.md."
  critical: "Do NOT re-audit textproc or config here. The §4.3 'strip trailing newlines' is textproc's job
             (T2.S1); the backends only guarantee they don't ADD a newline (point (e))."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── typing_backends.py     # THE FILE UNDER AUDIT. 5 points @54,60-61,75,86,90,103,105,129,132,136,139,141.
│   │                            Pure stdlib (subprocess/logging/abc + OutputConfig). check=True everywhere.
└── tests/
    └── test_typing_backends.py # 27 tests; subprocess.run MOCKED via `recorder` fixture. The contract's run target.
plan/006_862ee9d6ef41/architecture/
├── gap_config.md              # P1.M1.T1.S1's report — the convention to MIRROR.
├── gap_textproc.md            # sibling T2.S1's report (parallel) — also a mirror.
└── gap_typing.md              # ← CREATE (this task's deliverable; same dir + shape as the siblings).
# NOTE: this task is read-only verification. The only new file is gap_typing.md (under architecture/).
# No source change is expected (typing_backends.py is §4.3-compliant per audit).
```

### Desired Codebase tree with files to be added/changed

```bash
plan/006_862ee9d6ef41/architecture/gap_typing.md   # ← CREATE (the audit report; mirror gap_config.md/gap_textproc.md).
# (EXPECTED: NO source changes) — voice_typing/typing_backends.py + tests/test_typing_backends.py UNCHANGED.
# (CATCH-ALL, only if a REAL defect is found — none expected): a fix in typing_backends.py + a record in the report.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — THE FALLBACK except IS A SUPERSET, NOT A DEFECT. _WtypeWithFallback catches
# (subprocess.CalledProcessError, OSError) — broader than the contract's literal "nonzero exit or
# FileNotFoundError". OSError ⊇ FileNotFoundError AND PermissionError (binary not executable). This is
# INTENTIONAL (more robust) + EXPLICITLY TESTED (test_wtype_permission_error_also_falls_back @279). Record
# it as a compliant superset in the report — do NOT "narrow" it to (CalledProcessError, FileNotFoundError);
# that would re-introduce the swallowed-PermissionError risk. (research §1 (b).)

# CRITICAL #2 — gap_typing.md GOES UNDER architecture/, NOT P1M1T3S1/. The gap-report convention (from
# P1.M1.T1.S1's gap_config.md + sibling gap_textproc.md) puts reports at plan/006_862ee9d6ef41/architecture/
# gap_<module>.md. Write gap_typing.md THERE. Do NOT put it under P1M1T3S1/ (that's the PRP/research home)
# and do NOT append to gap_config.md or gap_textproc.md (each module gets its own report). (research §3.)

# CRITICAL #3 — THE EXPECTED VERDICT IS "COMPLIANT, NO FIX". This PRP's research CONFIRMS all 5 points pass
# + 27 tests pass. The implementing agent re-verifies (the greps + pytest below) and transcribes into
# gap_typing.md. Do NOT invent a defect to "fix"; a no-change verdict is the correct outcome. A source edit
# is warranted ONLY if the re-verification surfaces a REAL §4.3 violation (it won't). (research §0.)

# CRITICAL #4 — THE §4.3 TRAILING-NEWLINE STRIP IS TEXTPROC'S JOB, NOT THE BACKENDS'. PRD §4.3: "strip
# trailing newlines in textproc." The backends only guarantee they type EXACTLY what they're given (no ADDED
# newline — point (e), via the tmux `-l` flag + the `--` separators). The actual stripping is audited in
# T2.S1 (textproc). Do NOT report "backends don't strip newlines" as a gap — it's out of their scope.

# GOTCHA #5 — USE FULL PATHS. This machine aliases python3→uv run, pip→alias, tmux→zsh plugin. Invoke
# .venv/bin/python -m pytest explicitly. Never bare python/pytest/uv. (The audit itself notes WHY _TMUX is
# the full path — the same alias trap; that's point (c).)

# GOTCHA #6 — THIS PROJECT USES pytest (NO ruff/mypy in pyproject). Validation = pytest + grep. Do NOT
# invent ruff/mypy commands (the PRP template's ruff/mypy lines are N/A here).

# GOTCHA #7 — DO NOT run/restart the live daemon or open a real display. tests/test_typing_backends.py
# MOCKS subprocess.run (the `recorder` fixture) — no real wtype/ydotool/tmux keystroke is ever sent. Any
# real-binary execution means a hermetic seam leaked — that's a bug to report, not a test environment.

# GOTCHA #8 — THE OPTIONAL OBSERVATIONS ARE NON-BLOCKING. (1) No explicit "fallback-fail-propagates" test,
# but the behavior is correct-by-construction (the fallback call is unwrapped → any exception propagates).
# (2) The OSError superset (Gotcha #1). Record BOTH in the report's notes section so a future reader isn't
# confused — but NEITHER is a §4.3 defect and neither warrants a code change. (research §1 (b).)

# GOTCHA #9 — DO NOT modify PRD.md, tasks.json, prd_snapshot.md, .gitignore, or any test/source file (unless
# a real defect is found — none expected). The only new file is gap_typing.md (under architecture/).
```

## Implementation Blueprint

### Data models and structure

None. This subtask adds no code, no types, no config. The only "data" is the **audit report**
(`gap_typing.md`) produced by re-running the greps + pytest and transcribing the verified findings.

### Verification Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm the file under audit + the test target exist (no mutation)
  - RUN:
      cd /home/dustin/projects/voice-typing
      test -f voice_typing/typing_backends.py && echo "ok: typing_backends.py present" || echo "FAIL: missing"
      test -f tests/test_typing_backends.py && echo "ok: test file present" || echo "FAIL: missing"
      test -d plan/006_862ee9d6ef41/architecture && echo "ok: architecture/ dir exists (report home)" || echo "FAIL: dir missing"
      ls plan/006_862ee9d6ef41/architecture/gap_*.md   # the convention to mirror (gap_config.md, gap_textproc.md)
  - EXPECTED: both files present; the architecture/ dir exists with the sibling gap reports (the shape to mirror).

Task 2: STATIC AUDIT — re-verify the 5 PRD §4.3 points against typing_backends.py (the greps)
  - RUN (each MUST match — these are the file:line evidence for the report):
      cd /home/dustin/projects/voice-typing
      echo "(a) type_text interface (ABC + 4 impls):"
      grep -nE '@abstractmethod|def type_text\(self, text: str\) -> None' voice_typing/typing_backends.py
      echo "(b) auto-fallback WARNING + except + fallback call:"
      grep -nE 'except \(subprocess.CalledProcessError, OSError\)|logger.warning\("wtype typing failed|_fallback.type_text\(text\)' voice_typing/typing_backends.py
      echo "(c) _TMUX full path + TmuxBackend argv:"
      grep -nE '_TMUX = "/usr/bin/tmux"|\[_TMUX, "send-keys"' voice_typing/typing_backends.py
      echo "(d) ydotool --key-delay 2:"
      grep -nE '"--key-delay", "2"' voice_typing/typing_backends.py
      echo "(e) no-newline: tmux -l literal + NEVER EMIT docstring:"
      grep -nE '"-l", "--"|NEVER EMIT ENTER' voice_typing/typing_backends.py
      echo "(e-cont) confirm NO bare 'tmux' token in any subprocess argv:"
      grep -nE 'subprocess.run\(\["tmux"' voice_typing/typing_backends.py && echo "  >>> BARE TMUX (defect!)" || echo "  CLEAN: no bare tmux in any subprocess call"
  - EXPECTED: (a) 1 @abstractmethod + 5 type_text defs; (b) except @132 + warning @136 + fallback @139;
    (c) _TMUX @54 + [_TMUX,"send-keys"] @105; (d) --key-delay "2" @90; (e) "-l","--" @105 + NEVER EMIT @25;
    the bare-tmux check is CLEAN. (research §1.) Transcribe these file:line into the report's table.

Task 3: RUN the test suite (the contract command) — capture the count
  - RUN:
      cd /home/dustin/projects/voice-typing
      .venv/bin/python -m pytest tests/test_typing_backends.py -q 2>&1 | tail -5
  - EXPECTED: "27 passed in 0.01s" (baseline). Record the exact count + timing in the report. (research §2.)
  - IF a test fails (it won't): investigate via `pytest tests/test_typing_backends.py::<test> -v --tb=long`.
    A failure here would indicate a real defect OR a hermetic-seam leak (Gotcha #7) — classify + report; do
    NOT mask it. The only in-scope "fix" is a typing_backends.py §4.3 defect, which the audit proves absent.

Task 4: WRITE plan/006_862ee9d6ef41/architecture/gap_typing.md (the deliverable) — mirror the sibling shape
  - STRUCTURE (mirror gap_config.md / gap_textproc.md):
      1. Header + verdict: "# typing_backends.py — PRD §4.3 compliance audit" + "VERDICT: COMPLIANT (no fix needed)."
      2. Per-point compliance table: 5 rows (# | PRD §4.3 expected | typing_backends.py actual (file:line) | result).
         All PASS. Use the file:line from Task 2.
      3. Test-suite result: the exact line from Task 3 ("27 passed in 0.01s"), + a short coverage summary
         (wtype/ydotool/tmux argv, ABC, make_backend, auto-fallback — subprocess.run mocked).
      4. Mismatches / drift / notes: "None — fully §4.3-compliant." + the TWO non-blocking observations:
         - (b-superset) except (CalledProcessError, OSError) is a TESTED SUPERSET of "nonzero exit or
           FileNotFoundError" (also covers PermissionError); MORE robust than required, not a defect.
         - (b-optional) no explicit fallback-fail-propagates test, but correct-by-construction (the fallback
           call is unwrapped → exception propagates); §4.3 doesn't require that test — nice-to-have.
      5. Conclusion: COMPLIANT; no source changes; the typing backends faithfully implement PRD §4.3
         (interface, auto-fallback, /usr/bin/tmux, --key-delay 2, no Enter/newline).
  - DO NOT: put the report under P1M1T3S1/ (it goes under architecture/ — Gotcha #2); append to a sibling
    report; invent a defect; omit the two notes (they prevent a future mis-reading).

Task 5: VALIDATE — run the Validation Loop L1–L4 below. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M1.T3.S1: typing_backends PRD §4.3 audit — COMPLIANT (5/5 points, 27 tests pass,
  no fix needed); gap_typing.md recorded." (Or, if a real defect was found+fixed: "...fixed <defect> in
  typing_backends.py; recorded in gap_typing.md.")
```

### Implementation Patterns & Key Details

```bash
# This subtask has NO implementation patterns — it is read-only verification + report-writing. The
# load-bearing facts (each verified in this PRP's research note):
#
# FACT 1: all 5 PRD §4.3 points are satisfied — type_text interface (ABC @60-61 + impls), auto-fallback
#         (except (CalledProcessError,OSError) @132 + warning @136 + fallback @139), _TMUX="/usr/bin/tmux"
#         (@54, argv @105), ydotool --key-delay 2 (@90), no-newline (-l @105 + -- + NEVER EMIT docstring).
# FACT 2: tests/test_typing_backends.py = 27 passed (subprocess.run mocked; no real keystrokes).
# FACT 3: the fallback's except is a SUPERSET of the contract (OSError ⊇ FileNotFoundError + PermissionError)
#         — intentional + tested; record as compliant, do NOT narrow.
# FACT 4: the trailing-newline STRIP is textproc's job (§4.3; T2.S1's scope); backends only don't ADD one.
#
# THE DELIVERABLE (the whole task): gap_typing.md under architecture/, mirroring the sibling shape.
```

### Integration Points

```yaml
DELTA ACCEPTANCE (PRD §4.3 + §8 "wtype fails" risk mitigation):
  - This subtask produces the §4.3 compliance evidence for the typing backends (the LAST hop before text
    leaves the daemon). §8's "wtype fails on some window → auto-fallback to ydotool" is certified by point (b).
  - The gap_typing.md report IS the acceptance evidence. No repo source file is modified (expected).

PARALLEL — P1.M1.T2.S1 (textproc audit, in flight):
  - T2.S1 audits voice_typing/textproc.py + writes gap_textproc.md. T3.S1 audits typing_backends.py +
    writes gap_typing.md. DISJOINT files. Both follow the gap_<module>.md convention. No merge conflict.

DOWNSTREAM (consumers of the typing backends):
  - P1.M2.T1 (main-loop audit): daemon on_final → clean → make_backend(cfg.output).type_text(...). This
    audit confirms the type_text contract the daemon relies on.
  - P1.M7.T3 (E2E test): uses backend="tmux" to capture typed text. This audit confirms the /usr/bin/tmux
    + send-keys -l argv the E2E depends on.

NO INTERFACE / BEHAVIOR CHANGES:
  - voice_typing/typing_backends.py + tests/test_typing_backends.py: UNCHANGED (expected). The output is
    the gap_typing.md report. config.toml [output] (Mode A docs) is already correct (verified: documents
    wtype/ydotool/tmux + the auto-fallback) — DOCS: none for this subtask.
```

## Validation Loop

> Full paths in every command (zsh aliases shadow python3/pip on this machine). Run from the repo root
> `/home/dustin/projects/voice-typing`. This project uses pytest (NO ruff/mypy — Gotcha #6). All gates are
> pure/hermetic (subprocess.run is mocked in the tests; no display/ydotoold/keystrokes).

### Level 1: The 5 audit points pass statically (the file:line evidence)

```bash
cd /home/dustin/projects/voice-typing
echo "(a)"; grep -nE '@abstractmethod|def type_text\(self, text: str\) -> None' voice_typing/typing_backends.py
echo "(b)"; grep -nE 'except \(subprocess.CalledProcessError, OSError\)|logger.warning\("wtype typing failed|_fallback.type_text\(text\)' voice_typing/typing_backends.py
echo "(c)"; grep -nE '_TMUX = "/usr/bin/tmux"|\[_TMUX, "send-keys"' voice_typing/typing_backends.py
echo "(d)"; grep -nE '"--key-delay", "2"' voice_typing/typing_backends.py
echo "(e)"; grep -nE '"-l", "--"|NEVER EMIT ENTER' voice_typing/typing_backends.py
echo "(e-clean)"; grep -nE 'subprocess.run\(\["tmux"' voice_typing/typing_backends.py && echo "BARE TMUX DEFECT" || echo "CLEAN: no bare tmux"
# Expected: all 5 points present with file:line (research §1); the bare-tmux check is CLEAN.
```

### Level 2: The unit suite is green (the contract's run command)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_typing_backends.py -q 2>&1 | tail -5
# Expected: "27 passed in 0.01s" (baseline), 0 failed/errors. Record this line in the report.
```

### Level 3: The gap_typing.md report exists + is faithful (the deliverable)

```bash
cd /home/dustin/projects/voice-typing
F=plan/006_862ee9d6ef41/architecture/gap_typing.md
test -f "$F" && echo "L3 PASS: gap_typing.md exists (under architecture/)" || echo "L3 FAIL: report missing"
grep -qiE 'compliant|PASS' "$F" && echo "L3 PASS: records a compliance verdict" || echo "L3 FAIL: no verdict"
grep -qiE 'type_text|auto-fallback|/usr/bin/tmux|key-delay|newline|enter' "$F" && echo "L3 PASS: covers the 5 points" || echo "L3 FAIL: doesn't cover the 5 points"
grep -qiE '27 passed|tests? passed' "$F" && echo "L3 PASS: records the test count" || echo "L3 FAIL: no test count"
# Faithfulness: the report's verdict must match the live audit (COMPLIANT).
grep -qiE 'compliant|no fix|no source change' "$F" && echo "L3 PASS: verdict = compliant (matches live audit)" || echo "L3 CHECK: verdict wording"
# Expected: report exists under architecture/; records COMPLIANT + the 5 points + the 27-passed count.
```

### Level 4: Scope guards — only gap_typing.md created; no source/test changes (expected)

```bash
cd /home/dustin/projects/voice-typing
echo "--- EXPECTED: only the report is new (under plan/); no source/test changes ---"
git status --short | grep -vE '^\?\? plan/' || echo "(nothing outside plan/)"
git diff --exit-code -- voice_typing/typing_backends.py tests/test_typing_backends.py config.toml voice_typing/textproc.py voice_typing/daemon.py README.md pyproject.toml && echo "L4 PASS: no source/test/config changes (no-defect path)" || echo "L4 NOTE: a source file changed — confirm it was a REAL defect fix recorded in gap_typing.md (none expected)"
echo "--- read-only files UNCHANGED ---"
git diff --exit-code -- PRD.md plan/006_862ee9d6ef41/tasks.json plan/006_862ee9d6ef41/prd_snapshot.md .gitignore && echo "L4 PASS: read-only files unchanged" || echo "L4 NOTE: tasks.json may show orchestrator bookkeeping (M) — not this subtask"
# Expected (no-defect path): git status shows ONLY plan/ (the new gap_typing.md under architecture/ + this
# PRP/research) + tasks.json (orchestrator); typing_backends.py/test_typing_backends.py/config.toml unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: all 5 PRD §4.3 points present with file:line (type_text ABC+impls; auto-fallback except+warning+fallback; _TMUX; --key-delay 2; -l + no bare tmux).
- [ ] L2: `tests/test_typing_backends.py` → `<N> passed` (baseline 27), 0 failed/errors.
- [ ] L3: `gap_typing.md` exists under `architecture/`, records COMPLIANT + the 5 points + the test count + the 2 notes.
- [ ] L4: only `gap_typing.md` created (under plan/); no source/test/config/read-only changes (no-defect path).

### Feature Validation
- [ ] Verdict recorded: `typing_backends.py` is PRD §4.3-compliant (5/5 points) — no fix needed (expected).
- [ ] The 5 points each map to specific `typing_backends.py` file:line in the report.
- [ ] The two non-blocking observations (OSError superset; absent fallback-fail-propagates test) are recorded so they aren't mistaken for defects.
- [ ] If a REAL defect was found (none expected), it's fixed in `typing_backends.py` + recorded in the report.

### Code Quality / Scope Validation
- [ ] (Expected) ZERO source modifications — a no-fix verdict is the correct outcome (not a gap).
- [ ] The report mirrors the `gap_<module>.md` convention (gap_config.md/gap_textproc.md shape).
- [ ] No re-audit of textproc (T2.S1) / config (T1.S1) / daemon (P1.M2.T1); no test/source edit unless a real defect.
- [ ] No conflict with parallel T2.S1 (disjoint files — typing_backends vs textproc).

### Documentation & Deployment
- [ ] DOCS: none for this subtask (config.toml [output] Mode-A docs already correct — backend selection documented).
- [ ] The gap_typing.md report is the durable acceptance evidence for §4.3 typing-backends compliance.

---

## Anti-Patterns to Avoid

- ❌ Don't invent a defect to "fix" — the audit finds `typing_backends.py` fully §4.3-compliant (5/5 points + 27 tests pass). A no-change verdict is the correct, expected outcome. A source edit is warranted ONLY for a REAL §4.3 violation surfaced by the re-verification (it won't be). (Gotcha #3.)
- ❌ Don't narrow the fallback's `except (CalledProcessError, OSError)` to `(CalledProcessError, FileNotFoundError)` — the OSError superset is INTENTIONAL (also catches PermissionError) + explicitly tested. Record it as a compliant superset, not a defect. Narrowing it would re-introduce the swallowed-failure risk. (Gotcha #1.)
- ❌ Don't put `gap_typing.md` under `P1M1T3S1/` or append it to a sibling report — the convention is `plan/006_862ee9d6ef41/architecture/gap_<module>.md`. Write it there. (Gotcha #2.)
- ❌ Don't report "backends don't strip trailing newlines" as a gap — PRD §4.3 explicitly assigns the strip to textproc (T2.S1's scope); the backends only guarantee they don't ADD a newline (point (e), via `-l` + `--`). (Gotcha #4.)
- ❌ Don't run/restart the live daemon or open a real display — the tests MOCK subprocess.run; any real-binary execution means a hermetic seam leaked (a bug to report, not a test env to set up). (Gotcha #7.)
- ❌ Don't use bare `python`/`pytest`/`uv`/`tmux` (zsh aliases shadow them) — use `.venv/bin/python -m pytest`. (Gotcha #5.)
- ❌ Don't invent ruff/mypy gates — this project uses pytest only. (Gotcha #6.)
- ❌ Don't omit the two non-blocking notes from the report — the OSError superset + the absent fallback-fail-propagates test must be recorded so a future reader doesn't mis-read them as defects (or "fix" the superset into a regression). (Gotcha #8.)
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`, or any test/source file (unless a real defect is found — none expected). (Gotcha #9.)

---

## Confidence Score

**9.5/10** for one-pass verification success. The verdict is already verified in this PRP's research: **`typing_backends.py` is PRD §4.3-compliant on all 5 points (each with file:line) and `tests/test_typing_backends.py` = 27 passed.** The 5 audit greps + the pytest command are given verbatim, the gap-report convention (mirror `gap_config.md`/`gap_textproc.md` under `architecture/`) is confirmed, and the two non-blocking observations are documented so they aren't mistaken for defects. The parallel sibling T2.S1 edits disjoint files (textproc), so no merge conflict. The −0.5 residual is purely the small chance the implementing agent mis-reads the OSError superset as over-broad and "fixes" it into a regression — which Gotcha #1 + the report's notes section guard against. No GPU, daemon, display, or network is required.