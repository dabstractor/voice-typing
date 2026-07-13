# PRP — P1.M1.T2.S1: Add TimeoutStopSec=15 to systemd unit and verify no 90s SIGKILL

## Goal

**Feature Goal**: Bound systemd's stop of the voice-typing daemon so it is **never SIGKILLed at the 90-second default**. Today `systemd/voice-typing.service` sets **no** `TimeoutStopSec`, so systemd applies its **90s default** — which is exactly the hang the PRD §8 risk row calls out (`recorder.shutdown() hangs ~90s … SIGKILL after systemd TimeoutStopSec`, journal: `Failed with result timeout`). Add `TimeoutStopSec=15` to the `[Service]` section (after `RestartSec=2`), with a Mode A comment explaining why the daemon's own bounded teardown makes 15s safe. This is the **systemd-side half** of the bounded-teardown prerequisite (P1.M1.T2); the daemon-side half is P1.M1.T1.S2 (`_bounded_shutdown(timeout=10.0)`).

**Deliverable** (two files edited, no new files):
1. `systemd/voice-typing.service` — add a comment block + `TimeoutStopSec=15` in `[Service]`, immediately after `RestartSec=2` (line 41).
2. `tests/test_systemd_unit.py` — add `test_timeout_stop_sec_bounds_shutdown` asserting the unit contains `TimeoutStopSec=15` (mirroring the existing `test_restart_on_failure`).

**Success Definition**:
- (a) `systemd/voice-typing.service` contains exactly one `TimeoutStopSec=15` directive inside `[Service]`, after `RestartSec=2` and before `[Install]`.
- (b) The directive carries a Mode A comment citing: the 90s default root cause (unbounded `threading.Thread.join()` in `shutdown_recorder()` → SIGKILL at 90s), the daemon's `_bounded_shutdown(timeout=10.0)` (P1.M1.T1.S2) that makes it safe, and the 15s = 10s + 5s-grace budget.
- (c) `tests/test_systemd_unit.py::test_timeout_stop_sec_bounds_shutdown` passes; the full `tests/test_systemd_unit.py` suite stays green (no regression to the ExecStart/Restart/ExecStartPre/offline tests).
- (d) `systemd-analyze verify systemd/voice-typing.service` (if available) reports no NEW error attributable to the added directive (pre-existing absolute-path/ExecStartPre notes are benign).
- (e) `install.sh` is **unchanged** (it copies the unit verbatim at L112, so the directive flows to the deployed unit automatically on the next install).
- (f) No conflict with the parallel P1.M1.T1.S2 (which owns `daemon.py`'s `_bounded_shutdown` and explicitly does NOT touch the unit).

## User Persona

**Target User**: The user/maintainer who runs `voicectl quit` or `systemctl --user stop voice-typing` (and, after M3, the idle-unload path), and expects the daemon to stop promptly instead of hanging ~90s before a `SIGKILL`.

**Use Case**: User stops/restarts the daemon. systemd sends SIGTERM; the daemon's signal handler → `request_shutdown()` → `run()` exits → `main()` finally → `shutdown()` → `_bounded_shutdown(timeout=10)` returns within ~10s; the process exits **well inside** the 15s budget, so systemd never reaches SIGKILL. If a wedge ever recurs, SIGKILL lands at 15s (not 90s).

**Pain Points Addressed**: Every `voicectl quit` today runs `run() loop exiting` → ~90s → systemd `SIGKILL` / `Failed with result 'timeout'` in the journal (root-caused in P1.M1.T1.S1). With M3's idle-unload, this would recur every ~30 min. Bounded teardown (T1.S2) + `TimeoutStopSec=15` (this subtask) together make the stop prompt and the worst case 15s, not 90s.

## Why

- **PRD §8 risk row is the mandate.** It prescribes: *"recorder.shutdown() hangs ~90s (seen on every quit: SIGKILL after systemd TimeoutStopSec) — The teardown MUST be bounded/non-blocking … Root-cause the wedge … and fix it."* T1.S1 root-caused it (unbounded `threading.Thread.join()` in `shutdown_recorder()`; 90s = systemd default `TimeoutStopSec`). T1.S2 bounds the daemon side (`_bounded_shutdown(timeout=10)`). **This subtask bounds the systemd side** so the two halves compose: 10s daemon bound + 5s grace = the 15s unit budget.
- **Without it, systemd's 90s default still applies even after T1.S2.** T1.S2 makes the daemon return within ~10s, but if a future regression reintroduces an unbounded join (or any new shutdown path wedges), systemd would still wait the full 90s before SIGKILL. `TimeoutStopSec=15` caps that worst case at 15s and makes the journal say `Failed with result 'timeout'` at 15s, not 90s — a tight, obvious signal.
- **Defense in depth, not a substitute.** `TimeoutStopSec=15` does NOT replace T1.S2's bounded teardown — it is the outer safety net. The comment must say so: the daemon is EXPECTED to exit in ~seconds; the 15s is the bound, not the target. (SIGKILL at 15s skips the daemon's clean VRAM/process release, so the bounded teardown is still the primary path.)
- **Mode A docs.** Per the contract, the `TimeoutStopSec` comment in the `.service` file **IS** the documentation (no README change here — the README teardown note is M3.T3's Mode B changeset sweep).

## What

Two edits:

1. **`systemd/voice-typing.service`** — in `[Service]`, immediately after `RestartSec=2` (L41), insert a comment block + `TimeoutStopSec=15`. The comment explains: (i) the 90s default + the `Failed with result timeout`/SIGKILL symptom; (ii) the daemon's `_bounded_shutdown(timeout=10.0)` (P1.M1.T1.S2) that makes shutdown return ≤~10s; (iii) the 15s = 10s + 5s-grace arithmetic + the SIGTERM→handler→run-loop→finally flow; (iv) that SIGKILL at 15s is the outer safety net (skips clean release), not the target.
2. **`tests/test_systemd_unit.py`** — add `test_timeout_stop_sec_bounds_shutdown` after `test_restart_on_failure` (L89-91), asserting `any(ln == "TimeoutStopSec=15" for ln in _unit_lines())`.

### Success Criteria

- [ ] `grep -n '^TimeoutStopSec=15$' systemd/voice-typing.service` returns exactly one match, located after `Restart=on-failure`/`RestartSec=2` and before `[Install]`.
- [ ] The directive is preceded by a comment block mentioning `_bounded_shutdown`, `10` (seconds), `15`, and the 90s default / SIGKILL.
- [ ] `systemd/voice-typing.service` still has exactly one `[Service]` section; no other directive changed.
- [ ] New `test_timeout_stop_sec_bounds_shutdown` passes; `uv run pytest tests/test_systemd_unit.py -v` fully green.
- [ ] `install.sh` byte-identical (it copies the unit unchanged); `launch_daemon.sh`, `daemon.py`, `config.toml`, README all unchanged.
- [ ] No `TimeoutStopSec` duplicate; no directive outside `[Service]`.

## All Needed Context

### Context Completeness Check

_Pass._ The exact edit site (verbatim current line 41 `RestartSec=2`), the exact test-helper semantics (`_unit_lines()` returns stripped non-comment directive lines → `ln == "TimeoutStopSec=15"` matches), the daemon-side bound it depends on (`_bounded_shutdown(timeout=10.0)` from T1.S2), the 90s root cause (T1.S1), the systemd stop semantics (SIGTERM → TimeoutStopSec → SIGKILL), and the no-conflict boundary with T1.S2 are all verified below with line citations. A developer new to this repo can apply the patch from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the mandate (the 90s risk + the prescribed mitigation)
- docfile: plan/003_27d1f88f5a9f/prd_snapshot.md
  why: §8 risk row "recorder.shutdown() hangs ~90s (SIGKILL after systemd TimeoutStopSec)" prescribes
       a bounded teardown AND ties it to systemd's TimeoutStopSec. §4.9 is the unit-file spec.
  critical: "The mitigation is two-sided: daemon-side bounded teardown (T1.S2) + systemd-side
            TimeoutStopSec (this subtask). Both are required; neither alone is sufficient."

# MUST READ — the 90s root cause (Complete) — drives the comment's rationale
- docfile: plan/003_27d1f88f5a9f/architecture/realtimestt_shutdown_analysis_confirmed.md
  why: Verdict: the ~90s wedge is an UNBOUNDED threading.Thread.join() inside RealtimeSTT v1.0.2
       shutdown_recorder() (recording_thread.join() / realtime_thread.join(), NO timeout); the 90s
       IS systemd's DEFAULT TimeoutStopSec=90s (the unit sets none), which fires SIGKILL at 90s. The
       two mp.Process joins ARE already bounded (timeout=10 + terminate()).
  critical: "The unit setting NONE is the systemd half of the bug — adding TimeoutStopSec=15 is the
            direct fix for the 90s default. The daemon half (T1.S2) bounds the join so 15s is never hit."

# MUST READ — the daemon-side bound (parallel item, treats as a CONTRACT)
- docfile: plan/003_27d1f88f5a9f/P1M1T1S2/PRP.md
  why: Defines _bounded_shutdown(self, timeout=10.0) — DEFAULT 10.0s (its CRITICAL #4: "Use 10.0, not
       the analysis sketch's 15.0"). On timeout it force-terminates transcript_process +
       reader_process. Its PRP explicitly states "systemd/voice-typing.service # UNTOUCHED (T2.S1
       owns TimeoutStopSec)" and "T2.S1 adds TimeoutStopSec=15. S2 does NOT touch the unit."
  critical: "The 15s budget = T1.S2's 10.0s default + 5s grace. The comment MUST cite _bounded_shutdown
            + the 10s figure so a future reader sees the arithmetic. T1.S2 does NOT touch the unit ->
            no merge conflict; the two subtasks compose."

# THE EDIT SITE — the unit file
- file: systemd/voice-typing.service
  why: [Service] at L5; ExecStartPre L19; ExecStart L39; Restart=on-failure L40; RestartSec=2 L41;
        blank L42; [Install] L43. TimeoutStopSec slots after L41, before the blank/[Install].
  pattern: "Each directive has a generous Mode A comment block above it (the ExecStart block is ~15
            lines). A ~7-line comment for TimeoutStopSec is consistent with the file's style."
  gotcha: "TimeoutStopSec goes in [Service], AFTER RestartSec=2 (NOT in [Unit]/[Install]). The value
           is a bare integer '15' (= seconds); systemd also accepts '15s' but the contract + the
           existing integer-style directives (RestartSec=2) favor the bare '15'."

# THE TEST FILE — helper semantics + the sibling assertion to mirror
- file: tests/test_systemd_unit.py
  why: _unit_lines() (L45-55) returns stripped, NON-comment, non-empty lines (so 'TimeoutStopSec=15'
        appears verbatim). test_restart_on_failure (L89-91) is the EXACT pattern: `assert any(ln ==
        "Restart=on-failure" for ln in _unit_lines())`. _unit_path() (L40) resolves the file.
  pattern: "Mirror test_restart_on_failure: a one-line `assert any(ln == 'TimeoutStopSec=15' for ln in
            _unit_lines())` + a docstring citing the PRD §8 row + the 10s/15s arithmetic."
  critical: "_unit_lines() STRIPS each line, so assert the stripped form 'TimeoutStopSec=15' (no
            leading spaces, no trailing comment on the same line — put the rationale in the comment
            BLOCK above the directive, not inline)."

# install.sh — why it needs NO change
- file: install.sh
  why: L112 `cp "$SRC_UNIT" "$USER_UNIT_DIR/voice-typing.service"` copies the unit verbatim into the
        user unit dir, then daemon-reload. So the new TimeoutStopSec flows to the DEPLOYED unit on the
        next install with no install.sh edit.
  critical: "Do NOT edit install.sh. The contract is explicit: 'install.sh does not need changes — it
            already copies the unit file.' (The deployed unit only picks up the directive after the
            next `./install.sh` or a manual cp+daemon-reload; that is expected.)"
```

### Current Codebase tree (relevant slice — T1.S2 edits daemon.py in parallel; unit untouched by it)

```bash
/home/dustin/projects/voice-typing/
├── systemd/
│   └── voice-typing.service    # ← EDIT (+TimeoutStopSec=15 + comment after L41). NO TimeoutStopSec today.
├── tests/
│   └── test_systemd_unit.py    # ← EDIT (+test_timeout_stop_sec_bounds_shutdown after L89-91).
│                               #   _unit_lines() L45-55; test_restart_on_failure L89-91 = pattern.
├── install.sh                  # UNCHANGED (copies the unit verbatim at L112).
└── voice_typing/
    └── daemon.py               # T1.S2 (parallel) adds _bounded_shutdown(timeout=10.0) here; NOT this subtask.
```

### Desired Codebase tree with files to be added/changed

```bash
systemd/voice-typing.service    # MODIFY: +comment block + 'TimeoutStopSec=15' in [Service] after RestartSec=2.
tests/test_systemd_unit.py      # MODIFY: +1 test (test_timeout_stop_sec_bounds_shutdown).
# No new files. No install.sh / launch_daemon.sh / daemon.py / config / README changes.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — TIMEOUTSTOPSEC GOES IN [Service], after RestartSec=2. Not in [Unit] or [Install].
# Place it immediately after line 41 (RestartSec=2) and before the blank line + [Install]. A directive
# accidentally placed AFTER [Install] would bind to the [Install] section and be ignored by systemd at
# runtime (silently — systemd does not error on an unknown section key in some cases).

# CRITICAL #2 — THE 15s IS THE OUTER NET, NOT THE TARGET. The daemon is EXPECTED to exit in ~seconds
# (SIGTERM → signal-handler thread → request_shutdown → run() loop exits → main() finally →
# shutdown() → _bounded_shutdown(timeout=10) ≤ ~10s). TimeoutStopSec=15 caps the WORST case (a
# regression wedge) at 15s instead of 90s. The comment must say SIGKILL@15s skips the daemon's clean
# VRAM/process release — so bounded teardown (T1.S2) remains the primary path; this is the safety net.

# CRITICAL #3 — VALUE FORM = bare '15' (seconds). systemd accepts '15' or '15s'. Use bare '15' to
# match the contract verbatim AND the existing integer-style 'RestartSec=2'. The test asserts the
# stripped line == 'TimeoutStopSec=15' (exactly), so do NOT write 'TimeoutStopSec=15s' or pad spaces.

# CRITICAL #4 — PUT THE RATIONALE IN A COMMENT BLOCK, NOT INLINE. _unit_lines() returns the STRIPPED
# line; an inline trailing comment ('TimeoutStopSec=15  # foo') would make the stripped line
# 'TimeoutStopSec=15  # foo' != 'TimeoutStopSec=15' → the test fails. Put the WHY in comment lines
# (# ...) ABOVE the directive (matching the file's existing style; see the ExecStart block).

# CRITICAL #5 — DEFAULT TIMEOUTSTOPSEC IS 90s (systemd). The unit currently sets none → 90s applies
# → the exact hang. This is NOT a no-op edit: without TimeoutStopSec=15, even with T1.S2's bounded
# teardown, a regression wedge still waits 90s. Adding the directive is the direct fix for the 90s.

# GOTCHA #6 — systemd-analyze verify may emit BENIGN warnings about the absolute ExecStart path /
# ExecStartPre. Those are pre-existing (the ExecStart is a repo-absolute path by design). The gate is
# "no NEW error attributable to TimeoutStopSec", not "zero output".

# GOTCHA #7 — DO NOT add WatchdogSec, KillMode, or KillSignal here. The contract is TimeoutStopSec=15
# ONLY. The default KillSignal=SIGTERM + KillMode=control-group is correct for this daemon (the signal
# handler triggers request_shutdown). Adding KillMode/KillSignal is out of scope and could change
# behavior (e.g. KillMode=process would leave worker threads alive). Keep the change minimal.

# GOTCHA #8 — DO NOT edit daemon.py / launch_daemon.sh / install.sh / config / README. T1.S2 owns
# daemon.py; install.sh copies the unit unchanged (L112); the README teardown note is M3.T3 (Mode B).
# This subtask = the unit file + the unit test, full stop.

# GOTCHA #9 — FULL PATHS in validation commands. systemd-analyze is at /usr/bin/systemd-analyze (or
# just `systemd-analyze` on PATH in bash, not the zsh-aliased shell). uv at /home/dustin/.local/bin/uv.
```

## Implementation Blueprint

### Data models and structure

None. No code, no types, no config schema. The only "structure" is one ini directive + one comment block + one Python test function.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY systemd/voice-typing.service — add TimeoutStopSec=15 + Mode A comment
  - FIND the [Service] tail (lines 40-42):
        Restart=on-failure
        RestartSec=2

        [Install]
  - EDIT: insert the comment block + directive immediately AFTER 'RestartSec=2' and BEFORE the blank
    line / [Install]:
        Restart=on-failure
        RestartSec=2
        # Bound systemd's stop so the daemon is never SIGKILLed at the 90s DEFAULT (PRD §8 risk row:
        # "recorder.shutdown() hangs ~90s … SIGKILL after systemd TimeoutStopSec"; journal:
        # 'Failed with result timeout'). With no TimeoutStopSec, systemd applies its 90s default.
        # The daemon's own _bounded_shutdown(timeout=10) (P1.M1.T1.S2) makes VoiceTypingDaemon.shutdown()
        # return within ~10s even when RealtimeSTT's shutdown_recorder() wedges at an unbounded
        # threading.Thread.join() (root-caused in P1.M1.T1.S1). The 15s budget = 10s bound + 5s grace
        # for the SIGTERM → signal-handler → request_shutdown → run() exits → main() finally latency.
        # Normal stop exits in ~seconds; SIGKILL@15s is the outer safety net for a regression wedge
        # (it skips the daemon's clean VRAM/process release, so bounded teardown remains the primary path).
        TimeoutStopSec=15

        [Install]
  - WHY: 15s = T1.S2's 10.0s default + 5s grace; the comment (Mode A) IS the documentation; bare '15'
    matches RestartSec=2's integer style and the test's exact 'TimeoutStopSec=15' assertion.
  - DO NOT: add KillMode/KillSignal/WatchdogSec; use '15s'; put a trailing inline comment on the
    directive line; or move/rename Restart/RestartSec.

Task 2: MODIFY tests/test_systemd_unit.py — add the drift-guard test
  - FIND test_restart_on_failure (lines 89-91):
        def test_restart_on_failure():
            """Restart=on-failure keeps the daemon alive across crashes (PRD §4.9 auto-restart)."""
            assert any(ln == "Restart=on-failure" for ln in _unit_lines())
  - EDIT: add a sibling test immediately AFTER it:
        def test_timeout_stop_sec_bounds_shutdown():
            """TimeoutStopSec=15 bounds systemd's stop so the daemon is never SIGKILLed at the 90s default.

            The daemon's own _bounded_shutdown(timeout=10) (P1.M1.T1.S2) returns within ~10s; the 15s
            unit budget = 10s bound + 5s grace for the SIGTERM → handler → run-loop → finally latency.
            Without this directive systemd applies its 90s default, which produced
            'Failed with result timeout' / SIGKILL on every quit (PRD §8 risk row; root-caused in
            P1.M1.T1.S1). Companion to the daemon-side bound; both are required.
            """
            assert any(ln == "TimeoutStopSec=15" for ln in _unit_lines()), (
                "systemd unit missing TimeoutStopSec=15 — without it the 90s default SIGKILLs the "
                "daemon on stop (PRD §8 risk row)."
            )
  - WHY: _unit_lines() returns stripped non-comment lines, so 'TimeoutStopSec=15' matches verbatim
    (the rationale is in the comment BLOCK above the directive, not inline — CRITICAL #4). Mirrors the
    minimal, single-directive style of test_restart_on_failure.
  - DO NOT: also assert section ordering (the sibling tests don't — keep parity); over-constrain with
    a full-line regex (a stripped-equality assert is robust to whitespace).

Task 3: VALIDATE — run the Validation Loop L1–L4 below; fix until all green. No git commit unless the
  orchestrator directs it. If asked, message:
  "P1.M1.T2.S1: add TimeoutStopSec=15 to systemd unit + drift-guard test (bound the 90s SIGKILL)".
```

### Implementation Patterns & Key Details

```bash
# PATTERN 1 — a Mode A directive comment (the file's established style). Each directive in this unit
# is preceded by a generous # comment block explaining the WHY (ExecStart's is ~15 lines). The
# TimeoutStopSec block follows suit: cite the symptom (90s/SIGKILL/'Failed with result timeout'),
# the root cause (unbounded join), the daemon-side bound it composes with (_bounded_shutdown@10s),
# and the arithmetic (10 + 5 grace = 15). The comment IS the documentation (Mode A).

# PATTERN 2 — the stripped-line drift-guard test. _unit_lines() (L45-55) strips + drops comments, so a
# directive line appears verbatim. Assert equality (==), not substring, so a stray inline comment or
# value typo (15s, 15.0, 20) fails loudly. This is exactly test_restart_on_failure's shape:
#     assert any(ln == "Restart=on-failure" for ln in _unit_lines())
# -> assert any(ln == "TimeoutStopSec=15" for ln in _unit_lines())

# PATTERN 3 — the two-sided bound. systemd stop flow: SIGTERM (KillSignal default) -> the daemon's
# install_shutdown_signal_handlers handler (spawns a thread -> request_shutdown: sets _shutdown +
# aborts) -> run()'s loop sees _shutdown -> exits -> main() finally -> shutdown() ->
# _bounded_shutdown(timeout=10) -> process exits. TimeoutStopSec=15 is the wall clock systemd waits
# before SIGKILL. 10s daemon bound + ~5s of handler/run-loop/finally slop = comfortably under 15s.
```

### Integration Points

```yaml
PRODUCTION RUNTIME (systemd → launch_daemon.sh → daemon):
  - On stop/restart, systemd sends SIGTERM, waits TimeoutStopSec=15, then SIGKILL. With T1.S2's
    _bounded_shutdown(timeout=10), the daemon exits in ~seconds → the 15s is never hit in normal
    operation. A regression wedge (unbounded join reintroduced) lands SIGKILL at 15s, not 90s.
  - The directive takes effect for the DEPLOYED unit only after the next `./install.sh` (which cp's
    the unit + daemon-reload, L112-113) or a manual cp + `systemctl --user daemon-reload`. The
    in-tree unit is the source of truth install.sh copies.

DOWNSTREAM — P1.M3 (idle-unload) + the lazy-load feature:
  - Idle-unload tears the recorder down every ~30 min (auto_unload_idle_seconds) and calls the SAME
    bounded shutdown. With TimeoutStopSec=15 + _bounded_shutdown(10), an idle-unload that wedges is
    capped at 15s on the next stop/restart — critical for the "not blocked for 90s every 30 min"
    guarantee in PRD §4.2bis/§8. This subtask is the PREREQUISITE (P1.M1) that unblocks M3.

DOWNSTREAM — P1.M3.T3 (README Mode B sweep):
  - The README teardown/quit note (documenting bounded stop) is M3.T3's job. This subtask's Mode A
    comment in the .service file is the in-file doc; M3.T3 references it from the README. Do NOT edit
    README here.

NO INTERFACE CHANGES beyond the unit file:
  - launch_daemon.sh, daemon.py, config.toml, install.sh, README, ctl.py: UNCHANGED.
  - The control-socket protocol, voicectl exit codes, and status_snapshot are unaffected.
  - KillSignal (default SIGTERM) / KillMode (default control-group) are deliberately NOT changed —
    they are correct for this daemon's signal-handler-driven shutdown.
```

## Validation Loop

> Full paths where invoked. The deterministic gates (L1–L3) are hermetic — NO live daemon/GPU/systemd
> restart required. L4 is OPTIONAL manual corroboration (heavy; depends on T1.S2 being in place).

### Level 1: The directive is present, correctly placed, well-formed

```bash
cd /home/dustin/projects/voice-typing
echo "--- exactly one 'TimeoutStopSec=15', in [Service], after RestartSec=2, before [Install] ---"
matches=$(grep -c '^TimeoutStopSec=15$' systemd/voice-typing.service); echo "count=$matches"
[ "$matches" -eq 1 ] && echo "L1 PASS: exactly one TimeoutStopSec=15" || echo "L1 FAIL: expected 1 match"
echo "--- placement: it appears AFTER RestartSec=2 and BEFORE [Install] ---"
awk '/^RestartSec=2/{seen_restart=1} /^TimeoutStopSec=15$/&&seen_restart{print "L1 PASS: after RestartSec=2"} /^\[Install\]/{if(seen_restart) seen_install=1; exit} END{}' systemd/voice-typing.service
grep -q '^TimeoutStopSec=15$' systemd/voice-typing.service && ! awk '/^\[Install\]/{f=1} f&&/^TimeoutStopSec=15$/{print "L1 FAIL: directive after [Install]"; exit 1}' systemd/voice-typing.service && echo "L1 PASS: not after [Install]"
echo "--- no inline trailing comment on the directive line (would break the stripped-line test) ---"
grep -nE '^TimeoutStopSec=15[[:space:]]' systemd/voice-typing.service && echo "L1 FAIL: trailing token on directive line" || echo "L1 PASS: directive line is bare"
echo "--- comment block cites the load-bearing facts ---"
grep -q '_bounded_shutdown' systemd/voice-typing.service && grep -q '90s' systemd/voice-typing.service && grep -q 'SIGKILL\|Failed with result timeout' systemd/voice-typing.service && echo "L1 PASS: comment cites _bounded_shutdown + 90s + SIGKILL" || echo "L1 FAIL: comment missing rationale"
# Expected: count=1; after RestartSec=2; not after [Install]; bare directive line; comment cites facts.
```

### Level 2: systemd syntax (best-effort; benign pre-existing path warnings OK)

```bash
cd /home/dustin/projects/voice-typing
if command -v systemd-analyze >/dev/null 2>&1; then
  out=$(systemd-analyze verify systemd/voice-typing.service 2>&1 || true)
  echo "$out" | grep -i 'TimeoutStopSec' && echo "L2 FAIL: verify flags TimeoutStopSec" || echo "L2 PASS: no TimeoutStopSec error from systemd-analyze verify"
  echo "$out" | grep -iE 'error|failed' | grep -vi 'execstart\|launch_daemon\|/home/dustin' && echo "L2 (review any non-path errors above)" || echo "L2 PASS: no new errors (path-related notes are benign/pre-existing)"
else
  echo "L2 SKIP: systemd-analyze not available (non-blocking) — L1 + L3 cover structure + assertion"
fi
# Expected: no error mentioning TimeoutStopSec. Pre-existing notes about the absolute ExecStart path
# or ExecStartPre are benign (they exist before this change). If systemd-analyze is absent, L1+L3 stand.
```

### Level 3: pytest drift-guard + no regressions (the hard gate)

```bash
cd /home/dustin/projects/voice-typing
/home/dustin/.local/bin/uv run pytest tests/test_systemd_unit.py -v
# Expected: ALL PASS, including the new test_timeout_stop_sec_bounds_shutdown AND the existing
# test_execstart_points_at_launch_daemon_wrapper / test_execstartpre_imports_wayland_and_display_env /
# test_restart_on_failure / test_launch_daemon_exports_offline_vars / test_install_sh_offline_grep_and_summary.
# Then a broad regression sweep to confirm nothing else broke:
/home/dustin/.local/bin/uv run pytest tests/ -q 2>&1 | tail -5
# Expected: full fast suite green (only an ADDITIVE test was added; the unit-file change doesn't affect
# daemon/config/ctl/feedback/textproc tests).
```

### Level 4: OPTIONAL manual corroboration (heavy; needs T1.S2 in place + a live restart)

```bash
cd /home/dustin/projects/voice-typing
# ONLY if: T1.S2 (bounded teardown) has landed AND a login session + GPU + cached models are available.
# Re-install the unit (so the deployed copy has TimeoutStopSec=15), restart, time a stop, and confirm
# no 90s 'Failed with result timeout'.
./install.sh >/dev/null 2>&1 || systemctl --user daemon-reload   # pick up the new directive
systemctl --user restart voice-typing.service
sleep 3
t0=$(date +%s); systemctl --user stop voice-typing.service; rc=$?; t1=$(date +%s)
echo "stop exit=$rc elapsed=$((t1 - t0))s (expect well under 15s; DEFINITELY under 90s)"
journalctl --user -u voice-typing --since '1 min ago' --no-pager | grep -i 'Failed with result\|timeout\|SIGKILL' && echo "L4: stop signal present (review)" || echo "L4 PASS: no timeout/kill on stop"
systemctl --user show voice-typing -p TimeoutStopSecUSec   # expect TimeoutStopSecUSec=15s
# Expected: stop completes in ~seconds (bounded teardown), rc=0, NO 'Failed with result timeout', and
# `systemctl show` reports TimeoutStopSecUSec=15s. This is the empirical "no 90s SIGKILL" confirmation;
# it is the runtime proof that composes with T1.S2's daemon-side bound. (Skip if T1.S2 not yet landed.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: exactly one `TimeoutStopSec=15`; after `RestartSec=2`; before `[Install]`; bare directive line (no inline comment); comment cites `_bounded_shutdown` + 90s + SIGKILL.
- [ ] L2 (if systemd-analyze present): no NEW verify error attributable to TimeoutStopSec (pre-existing path notes benign).
- [ ] L3: `pytest tests/test_systemd_unit.py` green (new test + all existing); full fast suite green.
- [ ] L4 (optional, needs T1.S2): live stop completes < 15s, rc=0, no `Failed with result timeout`; `systemctl show … TimeoutStopSecUSec=15s`.

### Feature Validation
- [ ] The 90s default no longer applies (TimeoutStopSec=15 overrides it).
- [ ] 15s = T1.S2's 10s `_bounded_shutdown` + 5s grace (the comment states the arithmetic).
- [ ] The directive composes with (does not replace) T1.S2's bounded teardown.
- [ ] install.sh copies the new directive to the deployed unit on next install (no install.sh edit needed).

### Code Quality Validation
- [ ] The comment follows the unit file's Mode A style (generous `#` block above the directive).
- [ ] The test mirrors `test_restart_on_failure` (single stripped-line equality assertion).
- [ ] Bare `15` value matches the integer style of `RestartSec=2` and the exact test assertion.
- [ ] No bare `python`/`pip`/`uv` in commands (`.venv/bin` + `/home/dustin/.local/bin/uv`).

### Scope Boundary Validation
- [ ] `git diff --name-only` == `systemd/voice-typing.service` + `tests/test_systemd_unit.py` ONLY.
- [ ] No touch to `daemon.py` (T1.S2), `launch_daemon.sh`, `install.sh`, `config.toml`, README, `ctl.py`.
- [ ] No KillMode/KillSignal/WatchdogSec added (out of scope; defaults are correct).
- [ ] No conflict with parallel T1.S2 (it explicitly leaves the unit to this subtask).
- [ ] PRD.md, tasks.json, prd_snapshot.md, .gitignore NOT modified (read-only).

### Documentation & Deployment
- [ ] Mode A: the TimeoutStopSec comment in the .service file IS the documentation (cites the 90s root cause + the daemon-side bound + the 15s arithmetic).
- [ ] No README change here (the README teardown note is M3.T3's Mode B sweep).

---

## Anti-Patterns to Avoid

- ❌ Don't put `TimeoutStopSec` in `[Unit]` or `[Install]`, or after `[Install]` — it must be in `[Service]` after `RestartSec=2` (CRITICAL #1).
- ❌ Don't add a trailing inline comment on the directive line (`TimeoutStopSec=15  # foo`) — `_unit_lines()` returns the stripped line and the test asserts exact equality; put the rationale in the comment BLOCK above (CRITICAL #4).
- ❌ Don't write `TimeoutStopSec=15s` or `15.0` or `20` — the contract + the integer style (`RestartSec=2`) + the test assertion all want bare `15` (CRITICAL #3).
- ❌ Don't frame 15s as the TARGET — it's the outer safety net. The daemon exits in ~seconds (T1.S2's bound); 15s caps a regression wedge. SIGKILL@15s skips clean VRAM/process release, so say so (CRITICAL #2).
- ❌ Don't treat this as a substitute for T1.S2 — both halves are required. The daemon-side `_bounded_shutdown(timeout=10)` is what makes 15s safe; this directive caps the systemd worst case (CRITICAL #2).
- ❌ Don't add `KillMode`/`KillSignal`/`WatchdogSec` — defaults (SIGTERM + control-group) are correct for the signal-handler-driven shutdown; changing them is out of scope and risky (Gotcha #7).
- ❌ Don't edit `daemon.py` (T1.S2 owns it), `install.sh` (copies the unit unchanged), `launch_daemon.sh`, `config.toml`, or README (M3.T3 owns the teardown note).
- ❌ Don't assert section ordering or a full-line regex in the test — mirror `test_restart_on_failure`'s minimal stripped-equality assertion for parity and robustness.
- ❌ Don't run a live `systemctl stop` timing as the unit gate — it's heavy and depends on T1.S2. The deterministic gates are L1 (structure) + L3 (pytest); the live timing is optional corroboration (L4).
- ❌ Don't forget the comment is the documentation (Mode A) — it must cite `_bounded_shutdown`, the 10s figure, and the 90s/SIGKILL root cause so a future reader sees why 15s is safe.

---

## Confidence Score

**9.5/10** for one-pass implementation success. The change is minimal and surgical — one ini directive + a Mode A comment block + one stripped-line pytest assertion — and every load-bearing fact is **verified against the actual repo**: the exact edit site (unit L40-42: `Restart=on-failure` / `RestartSec=2` / blank / `[Install]`), the `_unit_lines()` semantics (L45-55: stripped, non-comment → `ln == "TimeoutStopSec=15"` matches), the exact sibling assertion to mirror (`test_restart_on_failure` L89-91), the 90s root cause (T1.S1 Complete: unbounded `threading.Thread.join()` + systemd default 90s), the daemon-side bound it composes with (T1.S2's `_bounded_shutdown(timeout=10.0)`, CRITICAL #4 "Use 10.0"), and the explicit no-conflict boundary (T1.S2's PRP: "systemd/voice-typing.service # UNTOUCHED (T2.S1 owns TimeoutStopSec)"). The 15s = 10s + 5s grace arithmetic is consistent across the contract, T1.S2's default, and the comment. The −0.5 residual is environmental: the optional live `systemctl stop` timing (L4) depends on T1.S2 having landed and a running GPU daemon, which is why L4 is optional and the verdict rests on the deterministic L1+L3 gates that need no GPU/systemd.
