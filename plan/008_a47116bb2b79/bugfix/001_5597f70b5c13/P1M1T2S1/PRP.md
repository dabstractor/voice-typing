# PRP — P1.M1.T2.S1: Pin the exact panic exception in the portability check

## Goal

**Feature Goal**: Fix BUG-003 — `tests/test_systemd_unit.py::test_hypr_binds_use_portable_home_launcher` (VT-003) fails on every run because it demands `$HOME/.local/bin/voicectl` on EVERY `bind =` line, while `hypr-binds.conf:60` intentionally ships the documented hard-kill panic bind `bind = SUPER ALT, Escape, exec, systemctl --user stop voice-typing` (PRD Rev 3(4): deliberately bypasses voicectl and the control socket when the socket is wedged). The fix is a **narrow, exact-match exception** — not a rule relaxation: pin the exact chord (`SUPER ALT, Escape`), dispatcher (`exec`), and command (`systemctl --user stop voice-typing`), allow harmless field whitespace only, require it **exactly once**, and keep the ordinary rules (`$HOME/.local/bin/voicectl` required; `/home/` forbidden) for every other bind. Lookalikes (trailing `;`/`&&`, chained commands, wrong chord/command, extra args) are NOT exempt — they fall back to the ordinary rules and fail.

**Deliverable**: One file edited — `tests/test_systemd_unit.py`: (1) rewrite `test_hypr_binds_use_portable_home_launcher` with the panic exemption logic; (2) extract a small helper (e.g. `_hypr_bind_lines()` + a normalized-field parser) if it keeps the test readable; (3) add string-fixture tests covering duplicate panic, missing panic, lookalikes, chained commands, and arbitrary nonportable binds. **No source changes** — `hypr-binds.conf` is NOT rewritten, no systemctl is ever invoked.

**Success Definition**:
- (a) `timeout 120 .venv/bin/pytest tests/test_systemd_unit.py -q` → **all green**, including the formerly-permanently-red `test_hypr_binds_use_portable_home_launcher` (the suite carries no unexplained red — closes BUG-003's classification hole).
- (b) The panic exemption matches the exact tuple `SUPER ALT, Escape, exec, systemctl --user stop voice-typing` after whitespace-only normalization (fields split/strip on `,` and spaces); ANY other deviation (case, order, extra tokens, `;`, `&&`, `|`, redirection) is rejected.
- (c) Exactly one panic line allowed: zero (missing) or two+ (duplicate) → the test fails.
- (d) Ordinary binds unchanged: `$HOME/.local/bin/voicectl` required AND `/home/` forbidden — the two current binds (`hypr-binds.conf:49` toggle, `:55` cancel) pass as-is.
- (e) New fixture tests pin the negative space: lookalike with `; reboot`, chained `&&`, wrong chord (`SUPER, Escape`), wrong command (`systemctl --user restart`), duplicate panic, missing panic, nonportable `/home/dustin/...` bind — each fails the checker.
- (f) `git diff --name-only` == `tests/test_systemd_unit.py` only; `hypr-binds.conf` byte-identical.

## User Persona

**Target User**: The maintainer running the suite (currently sees a permanently red, unclassified test on every run — exactly the "unexplained new failure" the delta's consistency sweep was supposed to prevent) and the P1.M2.T3.S2 README sync that needs a documented command contract for the panic route.

**Use Case**: CI/sweep runs `tests/test_systemd_unit.py` → green; a future edit adds a bind → the checker still enforces VT-003 portability for ordinary binds and fails loudly on any panic-bind mutation (chord drift, command drift, duplicates).

**Pain Points**: The permanently red test (pre-existing since the bind landed 2026-10-25, classified nowhere because test_systemd_unit.py was excluded from the G1 baseline); a naive `# VT-003-exempt` marker would silently accept any future lookalike.

## Why

- **The bug report + arch note mandate the narrow shape.** `system_context.md` §BUG-003: "Pin the exact chord, dispatcher, and command (only harmless spacing may be normalized), exactly once; preserve portable-launcher and no-hardcoded-home assertions for every other binding and reject a lookalike with appended commands. No rewiring of the panic bind."
- **Why exact-match, not a marker/comment exemption**: a comment-based exemption (`# exempt`) would keep passing if someone changed the command to `systemctl --user restart` or appended `; something` — silently breaking the documented panic contract. The test must encode the contract itself.
- **Why "exactly once"**: the panic bind is part of the shipped contract (one hard-kill route). A duplicate = a copy-paste error; a missing one = the contract regressed. Both must fail.
- **Why NOT rewrite the bind**: PRD Rev 3(4) documents the systemd-stop bypass as intentional (the control socket can wedge; `systemctl --user stop` is the escape hatch). The test was wrong to over-generalize; the bind is right.
- **Documentation contract handoff**: the pinned tuple becomes the documented command contract P1.M2.T3.S2 cites in the README Hotkey overview (Mode B — not this task).

## What

Rewrite the VT-003 test with the exemption logic + add negative-space fixture tests. Static-only (read text, parse, assert); no subprocess, no systemctl, no bind rewrite.

### Success Criteria

- [ ] `test_hypr_binds_use_portable_home_launcher` passes against the shipped `hypr-binds.conf` (3 binds: 2 ordinary portable + 1 exact panic).
- [ ] The exemption is a parsed tuple match, not a substring/markers: `mods=["SUPER","ALT"]`, `key="Escape"`, `dispatcher="exec"`, `command="systemctl --user stop voice-typing"` — whitespace-insensitive, everything-else-exact.
- [ ] Panic count enforced == 1 (0 or ≥2 → assert fails with a clear message).
- [ ] Ordinary binds: `$HOME/.local/bin/voicectl` in line AND `/home/` not in line (both existing asserts preserved for non-panic lines).
- [ ] New fixture tests: lookalike-chained (`;`/`&&`), wrong-chord, wrong-command, duplicate-panic, missing-panic, nonportable-path bind — all RED against the checker (i.e. the checker function raises/asserts for each).
- [ ] Full `tests/test_systemd_unit.py` green; only that file changed.

## All Needed Context

### Context Completeness Check

_Pass._ The exact current test body (read verbatim, :328-339), the three shipped bind lines (:49/:55/:60), the arch-note's narrow-exception spec, and the sibling-boundary (T1.S3 touches daemon-test fixtures, not this file) are all verified. Pure static test edit; no CUDA/daemon/systemctl anywhere.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/system_context.md
  why: §BUG-003 is the authoritative fix shape: exact chord/dispatcher/command, whitespace-only
       normalization, exactly once, preserve both ordinary assertions, reject appended-command
       lookalikes, no bind rewiring. Also documents why systemd-stop (not SIGKILL): the unit has
       KillMode=mixed / TimeoutStopSec=15 / Restart=on-failure — describe it as a socket-bypassing
       stop, never as "kill" or "no auto-restart".
  critical: "This note IS the contract for the exemption logic. Do not generalize it."

- file: tests/test_systemd_unit.py
  why: The test under edit (:328-339). Current shape: `_hypr_binds_path()` helper; collects lines
        starting 'bind ='; asserts voicectl-substring + no-'/home/' per line — the over-general loop
        that rejects :60. Existing file style: plain functions, f-string assert messages citing the
        VT id (mirror that style in the new messages).
  pattern: "Keep the docstring's VT-003 rationale and EXTEND it with the panic exception paragraph
            (documented hard-kill route, PRD Rev 3(4); exact-match exemption; exactly once)."

- file: hypr-binds.conf
  why: The shipped lines the checker must accept: :49 'CTRL SUPER ALT, D, exec, $HOME/.local/bin/
        voicectl toggle'; :55 'SUPER ALT, Backspace, exec, $HOME/.local/bin/voicectl cancel'; :60
        'SUPER ALT, Escape, exec, systemctl --user stop voice-typing'. READ-ONLY for this task.
  gotcha: "Hyprland bind syntax: bind = MODS, key, dispatcher, params — MODS space/underscore-
           insensitive ('SUPER ALT' == 'SUPER_ALT'). Normalize whitespace BETWEEN fields only; do
           not reorder or case-fold the command."

- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M1T1S3/PRP.md
  why: The PARALLEL item (hermetic ducking fixtures) — touches test_daemon.py fixtures/_FakeDucker,
        NOT test_systemd_unit.py. Zero file overlap; no coordination needed beyond commit ordering.
```

### Current / Desired tree

```bash
tests/test_systemd_unit.py   # ← EDIT: rewritten VT-003 test (panic exemption) + fixture tests. ONLY file.
# hypr-binds.conf — READ-ONLY (shipped lines verified above).
# README.md — P1.M2.T3.S2 (Mode B) consumes the pinned tuple as the documented command contract.
```

### Known Gotchas

```python
# CRITICAL #1 — EXACT-MATCH, NOT SUBSTRING. The panic exemption must be a parsed comparison of the
# full normalized line: mods-set {"SUPER","ALT"} (accept SUPER_ALT too), key "Escape", dispatcher
# "exec", command "systemctl --user stop voice-typing" (split the command field on whitespace and
# compare token lists — so 'systemctl  --user stop voice-typing' with double space still matches,
# but ANY extra/missing/reordered/case-changed token fails). Substring matching would accept
# '... stop voice-typing; reboot' — exactly the lookalike the arch note says to reject.

# CRITICAL #2 — EXACTLY ONCE. Count panic matches; assert == 1 with a message distinguishing
# missing ("the documented panic bind was removed — restore it (PRD Rev 3(4))") from duplicate
# ("two panic binds shipped — deduplicate").

# CRITICAL #3 — ORDINARY RULES UNTOUCHED. Non-panic lines keep BOTH asserts ($HOME launcher
# required; '/home/' forbidden). The panic line is exempt from the launcher requirement but still
# must not contain '/home/' (it doesn't — and the exemption must not waive that check: a panic
# lookalike containing /home/ should fail anyway via non-match + ordinary rules).

# CRITICAL #4 — FIXTURES ARE STRINGS, NOT FILE EDITS. The negative-space tests call the checker
# against inline bind-line strings (a small pure helper, e.g. _classify_binds(lines) -> (ordinary,
# panic_count) or assert-style _check_bind_line(ln)) — NEVER by rewriting hypr-binds.conf. No
# tmp_path file needed if the helper takes lines.

# GOTCHA #5 — FULL PATHS + timeout (AGENTS.md): `timeout 120 .venv/bin/pytest
# tests/test_systemd_unit.py -q`. No ruff/mypy. Do not run systemctl or touch the live unit.
```

## Implementation Blueprint

### Tasks

```yaml
Task 1: EDIT tests/test_systemd_unit.py — the panic-exempt checker + rewritten VT-003 test
  - Add a module-level constant + helper near _hypr_binds_path():
        _PANIC_BIND = ("SUPER ALT", "Escape", "exec", "systemctl --user stop voice-typing")
        def _is_panic_bind(ln: str) -> bool:
            """Exact match of the documented hard-kill panic bind (PRD Rev 3(4)) — whitespace
            between fields/tokens only; any other deviation (chord, dispatcher, command tokens,
            chained ';'/&&') is NOT the panic bind and must satisfy the ordinary VT-003 rules."""
            parts = [p.strip() for p in ln.split(",", 3)]        # mods, key, dispatcher, command
            if len(parts) != 4 or not parts[0]: return False
            mods = parts[0].replace("_", " ").split()            # SUPER_ALT == SUPER ALT
            if sorted(mods) != ["ALT", "SUPER"]: return False
            cmd = parts[3].split()                                # token-list compare (CRITICAL #1)
            return (parts[1] == "Escape" and parts[2] == "exec"
                    and cmd == _PANIC_BIND[3].split())
  - Rewrite test_hypr_binds_use_portable_home_launcher:
        bind_lines = [ln for ln in text.splitlines() if ln.lstrip().startswith("bind =")]
        panic = [ln for ln in bind_lines if _is_panic_bind(ln)]
        assert len(panic) == 1, f"exactly one documented panic bind required; got {len(panic)}: {panic!r}"
        for ln in bind_lines:
            if _is_panic_bind(ln): continue
            assert "$HOME/.local/bin/voicectl" in ln, (...)
            assert "/home/" not in ln, (...)
  - Extend the test docstring with the exception paragraph (chord+command pinned; exactly once;
    PRD Rev 3(4) rationale; socket-bypassing stop — not a SIGKILL, auto-restart untouched).

Task 2: ADD tests/test_systemd_unit.py — negative-space fixture tests (string fixtures; CRITICAL #4)
        def _check_binds(lines): <run the same loop+asserts; call from the main test too>
        def test_panic_bind_lookalike_with_chained_command_rejected():
            with pytest.raises(AssertionError):
                _check_binds([_PORTABLE_TOGGLE, "bind = SUPER ALT, Escape, exec, systemctl --user stop voice-typing; reboot"])
        def test_panic_bind_wrong_chord_rejected():   # "SUPER, Escape, ..." → ordinary rules fail it
        def test_panic_bind_wrong_command_rejected(): # "systemctl --user restart voice-typing"
        def test_duplicate_panic_bind_rejected():     # two exact panic lines → count != 1
        def test_missing_panic_bind_rejected():       # only ordinary binds → count == 0
        def test_nonportable_ordinary_bind_still_rejected():  # /home/dustin/... launcher
  - Fixtures = the two shipped ordinary lines (copy verbatim from :49/:55) + crafted bad lines.

Task 3: VALIDATE (Loop below). Commit msg if asked: "P1.M1.T2.S1: pin the exact SUPER+ALT+Escape
  panic exception in the VT-003 portability check (BUG-003) — closes the permanently red test".
```

### Integration Points

```yaml
DOWNSTREAM — P1.M2.T3.S2 (README Mode B): cites the pinned tuple as the documented panic command
  contract ("SUPER+ALT+Escape → systemctl --user stop voice-typing — bypasses the control socket;
  systemd stops the unit cleanly (KillMode=mixed, TimeoutStopSec=15) and Restart=on-failure still
  applies after a crash"). This task changes NO user-facing docs.
SIBLING — P1.M1.T3.S1 (G1 classification): records test_systemd_unit.py's status; this task turns
  its one red green — note that in the baseline if it lands first.
NO SOURCE/CONFIG CHANGES: hypr-binds.conf, systemd unit, daemon — untouched.
```

## Validation Loop

```bash
cd /home/dustin/projects/voice-typing
# L1: the formerly-red test now passes + full file green:
timeout 120 .venv/bin/pytest tests/test_systemd_unit.py::test_hypr_binds_use_portable_home_launcher -q 2>&1 | tail -2
timeout 120 .venv/bin/pytest tests/test_systemd_unit.py -q 2>&1 | tail -2          # all green
# L2: the new negative-space fixtures pass:
timeout 120 .venv/bin/pytest tests/test_systemd_unit.py -k "panic or nonportable" -q 2>&1 | tail -2
# L3: scope:
git diff --name-only | grep -v test_systemd_unit.py && echo "L3 FAIL" || echo "L3 PASS"
git diff --quiet hypr-binds.conf && echo "binds untouched PASS"
```

## Final Validation Checklist

- [ ] L1: VT-003 test green; full test_systemd_unit.py green (no unexplained red — BUG-003 closed).
- [ ] L2: all panic/lookalike/nonportable fixture tests green.
- [ ] L3: only tests/test_systemd_unit.py changed; hypr-binds.conf byte-identical.
- [ ] Exemption = parsed exact tuple (mods-set + key + dispatcher + command token-list), whitespace-only tolerance; exactly-once enforced; ordinary binds keep both asserts.
- [ ] No systemctl invocation, no bind rewrite, no README change (Mode B is P1.M2.T3.S2).

## Anti-Patterns

- ❌ Don't use a substring or `# exempt` marker — it would accept future lookalikes (CRITICAL #1; the arch note's core demand).
- ❌ Don't waive `/home/` for the panic line or drop either ordinary assert (CRITICAL #3).
- ❌ Don't allow ≠1 panic binds (missing/duplicate both fail — CRITICAL #2).
- ❌ Don't test by editing hypr-binds.conf (fixtures are strings — CRITICAL #4).
- ❌ Don't describe the bind as SIGKILL/no-auto-restart (it's a clean socket-bypassing stop; arch note).
- ❌ No bare pytest; `timeout 120` + `.venv/bin/python -m pytest` (GOTCHA #5).

## Confidence Score

**9.5/10** — pure static test edit with the exact current bodies read verbatim, the arch note specifying the exception shape, and the shipped bind lines confirmed; the only design freedom (helper structure) is pinned by the fixture requirement; −0.5 for Hyprland-syntax edge tolerance (SUPER_ALT normalization) already handled in the helper spec.
