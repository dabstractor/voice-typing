# PRP — P1.M2.T3.S2: Audit Mode-Switch Reload & self._mode Tracking

## Goal

**Feature Goal**: Produce the authoritative **mode-switch reload & `self._mode` tracking audit** as a
new **section APPENDED to `plan/006_862ee9d6ef41/architecture/gap_lite.md`**, cross-checking the
daemon's mode-switch lifecycle (`start`/`toggle` → `_load_host("normal")`; `start_lite`/`toggle_lite`
→ `_load_host("lite")`; the `switch_mode` teardown-and-respawn branch; `self._mode` tracking;
`feedback.set_mode`; mode-agnostic `stop`) against **PRD §4.2ter arming rules** on the **6 item clauses
(a)-(f)**. This is a **verification/audit** subtask of compliance round `006_862ee9d6ef41`: the
deliverable is the report section; **code changes happen ONLY if a real defect is found — none is
expected; this PRP's author has already performed the audit and the mode-switch lifecycle is
PRD §4.2ter-COMPLIANT.**

> **VERIFIED VERDICT (this PRP's research): the mode-switch reload is COMPLIANT — no fix needed.**
> All 6 clauses (a)-(f) pass (file:line in the research note §0); the contract's run target
> `tests/test_daemon.py -q -k 'mode or toggle_lite or start_lite or switch'` = **15 passed, 178
> deselected in 0.04s** (re-ran live). Arming routes correctly (`toggle`/`start`→normal,
> `toggle-lite`/`start-lite`→lite; socket `_dispatch` + `ctl.py _COMMANDS` cover all 7 cmds);
> same-mode resident arms **instantly** (`_load_host@715-717 return True`); cross-mode resident arms
> **tear down + respawn in the new mode** via the bounded `_bounded_shutdown(timeout=5.0)`@738
> (the same primitive idle-unload uses — acceptance #10 "one bounded reload"); `self._mode`@766 is
> updated on a successful spawn; `feedback.set_mode`@998 is published on arm (de-facto-current on
> disarm, since disarm doesn't change mode — nuance §4.1); `stop`@1388→`_request_stop`@1054 is
> mode-agnostic (drains or disarms either mode).

**Deliverable** (ONE report SECTION appended to `gap_lite.md`; NO source edits, NO test edits unless a
real defect surfaces): `plan/006_862ee9d6ef41/architecture/gap_lite.md` gains a new **`## Gap Report —
P1.M2.T3.S2: Mode-Switch Reload & self._mode Tracking vs PRD §4.2ter`** section. Format mirrors the
`gap_lifecycle.md` per-subtask section pattern (P1.M2.T2.S1-S4 each appended a §N to one file): title +
date + scope + audited artifacts (file:line) + bottom-line verdict + §1 Method (grep + test commands)
+ §2 per-clause compliance table (PRD expected vs code actual vs verdict) for (a)-(f) + §3 test
evidence + §4 non-defect nuances + conclusion tying the verdict to PRD §4.2ter + acceptance #10.
**This PRP's author has already performed the audit** (findings in the research note) — the
implementing agent re-verifies, re-runs the tests, and transcribes the section.

> **FILE-OWNERSHIP NOTE (parallel with S1).** S1 (P1.M2.T3.S1) CREATES `gap_lite.md` as a standalone
> file (H1 `# Gap Report — P1.M2.T3.S1: Lite Recorder Construction vs PRD §4.2ter`). S2 APPENDS its
> section BELOW S1's content (S2's section is an `## ` H2 sibling). Because S1 and S2 are produced in
> the same compliance round, S2's implementation must be **robust to ordering**: if `gap_lite.md`
> already exists (S1 done — the expected case, since S1 is implemented before S2 in the batch),
> **append**; if it does NOT yet exist, **create** it with a minimal H1 `# Gap Reports — Lite Mode
> (PRD §4.2ter)` header followed by the S2 section (so the work is never lost; S1's section is
> reconciled by whoever runs second / by the P1.M5.T5 acceptance cross-check). See Task 6 + CRITICAL #5.

**Success Definition**:
- (a) `gap_lite.md` contains a section titled `## Gap Report — P1.M2.T3.S2: Mode-Switch Reload &
  self._mode Tracking vs PRD §4.2ter` with the 6 sub-parts (scope/artifacts, bottom line, §1 method,
  §2 compliance table, §3 test evidence, §4 nuances, conclusion).
- (b) The recorded findings match the live re-verification: all 6 clauses (a)-(f) are **compliant**,
  each with `voice_typing/daemon.py` (+ `feedback.py` / `recorder_host.py` / `ctl.py`) file:line.
- (c) `timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'mode or toggle_lite or
  start_lite or switch'` → all pass (record the count; verified baseline: **15 passed, 178 deselected
  in 0.04s**).
- (d) **No source or test files are modified** (because no defect exists — the mode-switch lifecycle is
  PRD-compliant per audit). If — and only if — the re-verification surfaces a REAL defect, fix it and
  record the fix; otherwise record "none — compliant per audit."
- (e) `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_lite.md` (modified — S2's
  appended section; or new — if S1 had not yet created it) — no `voice_typing/*`, no `tests/*`, no
  `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore` change.

## User Persona

**Target User**: the maintainer (human or AI agent) who needs to trust that lite/normal mode-switching
(a) routes each command to the correct mode (`toggle`/`start`≠`toggle-lite`/`start-lite`), (b) is
**instant** when the resident child is already in the requested mode (no needless reload), (c) costs
**exactly one bounded reload** (~1-3s + ≤~7s teardown) when switching modes (acceptance #10), (d)
correctly tracks the resident mode in `self._mode` so `voicectl status` + `state.json` report it, and
(e) disarms **regardless** of which mode is armed. Also the downstream **P1.M5.T5** acceptance-criteria
cross-check (maps acceptance #10 — "switching modes costs one bounded reload" — to this audit's
teardown-and-respawn evidence).

**Use Case**: A future change to `_load_host`'s `switch_mode` branch, to `start_lite`/`toggle_lite`
routing, to `self._mode` assignment, or to the `_bounded_shutdown` teardown. The audit + the 15
mode-switch tests are the reference that proves the change keeps (or breaks) the instant-same-mode /
bounded-cross-mode / mode-agnostic-stop contract.

**Pain Points Addressed**: Closes the "does a mode switch REALLY tear down the old child (no VRAM
leak), REALLY respawn in the new mode, REALLY stay instant on same-mode, REALLY update self._mode, and
does stop REALLY work in either mode?" question with recorded, re-runnable evidence — not an assumption.

## Why

- **One-bounded-reload is acceptance #10.** PRD §4.2ter + acceptance #10 require that switching modes
  "costs one reload" — the same ~1-3s cost as a first-arm / post-idle reload. The mechanism is the
  `switch_mode` branch (`_load_host@736-742` → `_bounded_shutdown(timeout=5.0)@738` → respawn). The
  audit certifies the OLD resident child is torn down exactly once (no VRAM leak, no dangling child)
  and the NEW child spawns in the requested mode. A regression that respawns but forgets to tear down
  the old host would leak VRAM — `test_mode_switch_stops_outgoing_host@2927` fails loudly. (PRD §4.2ter
  "Arming rules"; §7 #10.)
- **Instant same-mode arm is the warm-path guarantee.** PRD §4.2ter: "Arm in mode X while resident
  child is mode X → instant arm." The audit certifies `_load_host@715-717` short-circuits `return True`
  (no teardown, no respawn) when the resident child matches. `test_same_mode_arm_is_instant_no_reload
  @2892` pins it (SAME host object). (PRD §4.2ter "Arming rules" bullet 1.)
- **self._mode tracking makes status honest.** `voicectl status` reports `mode:` (§4.2ter "State /
  status"); `state.json` gains `"mode"`. The audit certifies `self._mode@766` is set on a successful
  spawn, threaded into `status_snapshot@1567` + `feedback.set_mode@998`, and defaults to "normal" at
  boot. (PRD §4.2ter "State / status".)
- **Stop must be mode-agnostic.** PRD §4.2ter: "`voicectl stop` disarms either." The audit certifies
  `stop()@1388→_request_stop()@1054` has NO mode check — it drains or disarms regardless of mode.
  (PRD §4.2ter "Commands / keybind".)
- **Scope discipline.** This subtask owns the mode-switch RELOAD mechanic + `self._mode` tracking + the
  command→mode routing + mode-agnostic stop. The lite CONSTRUCTION kwargs (one-model, silence gate,
  CPU fallback) is **P1.M2.T3.S1** (it CREATES `gap_lite.md`); the T7 live test COVERAGE audit is
  **P1.M2.T3.S3**; the bounded-teardown PRIMITIVE itself (`_bounded_shutdown` internals) is
  **P1.M2.T2.S3** (this task REFERENCES it as the reload's teardown, not re-audits it). THIS task audits
  the RELOAD LIFECYCLE (the 6 clauses) and APPENDS to the file S1 owns.

## What

Re-verify the mode-switch lifecycle against PRD §4.2ter by reading the cited code regions
(`daemon.py start@1365` / `start_lite@1376` / `stop@1388` / `toggle@1393` / `toggle_lite@1426`;
`_load_host@698-795` esp. the `switch_mode@718` + teardown `@736-742` + `self._mode=mode@766`;
`_request_stop@1054` / `_arm@998` / `_disarm@1041`; `ControlServer._dispatch@1892-1935`;
`status_snapshot@1567`; `feedback.set_mode@145`; `recorder_host.RecorderHost.mode@168`+`is_alive@173`;
`ctl.py _COMMANDS@37`+routing`@199-202`), re-running the contract's `-k 'mode or toggle_lite or
start_lite or switch'` slice, and APPENDING the `## Gap Report — P1.M2.T3.S2: ...` section to
`gap_lite.md` in the gap-report format (mirror `gap_lifecycle.md`'s per-subtask sections). The audit is
expected to confirm full compliance (no defects → no code changes). The section's compliance table maps
each clause (a)-(f) to PRD §4.2ter expected behavior vs the code's actual behavior (file:line).

### Success Criteria

- [ ] `gap_lite.md` contains the `## Gap Report — P1.M2.T3.S2: Mode-Switch Reload & self._mode Tracking
  vs PRD §4.2ter` section + the 6 sub-parts.
- [ ] Compliance table covers (a) command→mode routing (socket `_dispatch` + `ctl._COMMANDS` + the 4
  daemon methods); (b) same-mode resident → instant `_load_host@715-717`; (c) cross-mode →
  `_bounded_shutdown`@738 teardown + respawn `@749-757`; (d) `self._mode=mode`@766 +
  `status_snapshot`@1567; (e) `feedback.set_mode`@998 on arm (de-facto-current on disarm — nuance §4.1);
  (f) `stop`@1388→`_request_stop`@1054 mode-agnostic — each COMPLIANT with file:line.
- [ ] `timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'mode or toggle_lite or
  start_lite or switch'` → recorded pass count (baseline **15 passed, 178 deselected**).
- [ ] No source/test files modified (`git status --short` == `gap_lite.md` only — modified or new).
- [ ] Conclusion ties the verdict to PRD §4.2ter arming rules + acceptance #10 (one bounded reload;
  same-mode instant; cross-mode teardown+respawn; stop mode-agnostic; self._mode tracks resident).

## All Needed Context

### Context Completeness Check

_Pass._ The audit is **already performed** by this PRP's author (research note §0: every clause mapped
to `daemon.py`/`feedback.py`/`recorder_host.py`/`ctl.py` file:line with the COMPLIANT verdict + the
15-test evidence + the full command→mode→load chain §1 + the bounded-reload guarantee §2 + the 5
non-defect nuances §4). A developer new to this repo can re-verify from the research note + the cited
code regions: the exact line ranges, the grep commands to re-locate them, the test command, and the
`gap_*.md` section format (sibling `gap_lifecycle.md` + the S1-created `gap_lite.md`). The non-defect
nuances (set_mode in _arm not _disarm; switch uses _bounded_shutdown not _unload_host; read/act outside
_lock; default "normal" at boot; set_mode on success only) are documented so they are not mistaken for
gaps.

### Documentation & References

```yaml
# MUST READ — the pre-verified audit findings (file:line + COMPLIANT verdict + test evidence + chain).
- docfile: plan/006_862ee9d6ef41/P1M2T3S2/research/mode_switch_audit.md
  why: "§0 ★ THE 6-CLAUSE TABLE (each clause → daemon.py/feedback.py/recorder_host.py/ctl.py file:line
        + ✅ COMPLIANT). §1 the command→mode→_load_host chain + _load_host switch internals (8 steps).
        §2 the bounded-reload guarantee (acceptance #10: _bounded_shutdown@738 = ≤~7s teardown + spawn).
        §3 the 15 selected tests + which clause each pins. §4 the 5 non-defect nuances (set_mode in _arm
        not _disarm; switch uses _bounded_shutdown not _unload_host; read/act outside _lock; default
        normal at boot; set_mode on success only). §5 the gap_lite.md section structure. §6 scope
        boundaries (disjoint from S1/S3/T4.S1/T2.S3). §7 the re-grep commands."
  section: "ALL load-bearing. §0 (the table), §1 (the chain), §2 (acceptance #10), §5 (the section format)."

# MUST READ — the gap-report section format to mirror (per-subtask §N-append pattern).
- docfile: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
  why: "The canonical pattern for MULTIPLE subtasks appending sections to ONE gap file: P1.M2.T2.S1-S4
        each appended a §N section (title + Date/Scope/Audited-artifacts(file:line) + 'Bottom line:'
        verdict + §1 Method (grep + test commands) + §2 per-property compliance table (PRD expected vs
        code actual vs Verdict) + §3 test pass/fail count + §4 non-defect nuances + conclusion).
        gap_lite.md is the lite-mode area file (S1 creates it; S2 + S3 append sections to it)."
  critical: "Mirror the SECTION format (## title), not a whole-file rewrite. S1's section is the H1
             content; S2's section is an ## H2 sibling BELOW it. If gap_lite.md does NOT yet exist
             (S1 not run), create it with a minimal H1 + the S2 section (CRITICAL #5)."

# MUST READ — the file S1 creates (S2 appends to it). Read if it exists to confirm S1's section shape.
- docfile: plan/006_862ee9d6ef41/architecture/gap_lite.md
  why: "S1 (P1.M2.T3.S1) CREATES this file with H1 '# Gap Report — P1.M2.T3.S1: Lite Recorder
        Construction vs PRD §4.2ter'. S2 APPENDS its '## Gap Report — P1.M2.T3.S2: ...' section below
        S1's content. If present, confirm the H1 + append after it. If ABSENT (S1 not yet run), create
        with a minimal H1 '# Gap Reports — Lite Mode (PRD §4.2ter)' + the S2 section."
  critical: "Do NOT overwrite S1's section. Use append (>> or read-modify-write preserving S1 content).
             The whole file stays in git as ONE artifact accumulating lite-audit sections."

# MUST READ — the primary audited source (the 4 arm methods + _load_host + _request_stop live here).
- file: voice_typing/daemon.py
  why: "start@1365 / start_lite@1376 (call _load_host('normal'/'lite') then _arm). stop@1388→
        _request_stop@1054 (mode-AGNOSTIC drain/disarm). toggle@1393 / toggle_lite@1426 (read
        listening+mode under _lock @1411-1412/@1436-1437, then _load_host OUTSIDE _lock, then _arm —
        with the failed-cross-mode _disarm fallback @1419-1424/@1451-1456). _load_host@698-795 (mode
        param @698; @715-717 same-mode instant return True; @718 switch_mode=True; @736-742 switch
        teardown _bounded_shutdown(timeout=5.0) + _host=None + _models_loaded=False; @749-757 spawn
        mode=mode; @766 self._mode=mode on success). _arm@998 feedback.set_mode(self._mode).
        _disarm@1041 (does NOT call set_mode — nuance §4.1). _dispatch@1892-1935 (cmd routing).
        status_snapshot@1567 'mode':self._mode. self._mode field init @644."
  pattern: "_load_host is the SINGLE decision point for instant-same-mode vs teardown-respawn-cross-mode;
            the 4 public arm methods are thin wrappers that pass the mode string; stop is mode-agnostic."
  gotcha: "The switch branch @738 calls _bounded_shutdown DIRECTLY, not _unload_host (which has
           idle-threshold guards that would no-op during a switch — nuance §4.2). Do NOT flag this as a
           gap; both delegate to the same bounded-teardown primitive."

# MUST READ — the feedback mode field + set_mode writer.
- file: voice_typing/feedback.py
  why: "set_mode@145-150 (writes _state['mode'] + _write(); 'Always writes; never notifies'). _state
        init @99 'mode':'normal' (boot default). Driven by daemon._arm@998 (set_mode(self._mode))."
  gotcha: "_disarm does NOT call set_mode (only set_listening(False)+set_phase('idle')). De-facto
           correct: disarm doesn't change self._mode, so the value from the last _arm persists.
           (Nuance §4.1.)"

# MUST READ — the child's mode property + is_alive (the same-mode/instant check reads these).
- file: voice_typing/recorder_host.py
  why: "RecorderHost.mode@property@168-170 (returns self._mode, set @125 in __init__ from the spawn
        arg). is_alive@173-175 (proc.is_alive() and not _dead). spawn@181-228 (@194-196 threads
        self._mode as the 6th _worker_main arg). _load_host@716 getattr(self._host,'mode','normal')
        reads this property for the same-mode short-circuit."
  gotcha: "The mode property is the SAME value _load_host compares against the requested mode — if a
           future change broke the RecorderHost.mode→spawn-arg link, the same-mode arm would falsely
           reload. Verified correct by the mode-switch tests."

# MUST READ — the CLI command set + routing (the user-facing mode-switch entry points).
- file: voice_typing/ctl.py
  why: "_COMMANDS@37 = ('toggle','start','stop','status','quit','toggle-lite','start-lite') — all 7.
        Routing@199-202: start/toggle/start-lite/toggle-lite use _send_command_with_loading_hint
        (prints 'loading models…' if the daemon is slow on a cold arm / mode switch); stop/status/quit
        use plain send_command. format_result@48 renders 'mode:' for status (if present)."
  pattern: "voicectl is a thin JSON-line client; the mode string ('toggle-lite'/'start-lite') is the
            sole signal of which mode to arm — verified it round-trips to _dispatch→start_lite/toggle_lite."

# MUST READ — the 15 mode-switch tests (the clause-specific assertions live here).
- file: tests/test_daemon.py
  why: "test_start_lite_loads_lite_host_and_arms@2863 (a+d: start_lite→lite host; d._mode=='lite';
        fb.modes==['lite']). test_mode_switch_normal_to_lite_reloads@2875 (c: reload; new host lite).
        test_same_mode_arm_is_instant_no_reload@2892 (b: SAME host object). test_toggle_lite_while_
        listening_in_lite_stops@2904 (f: stop disarms lite). test_status_snapshot_reports_mode@2918
        (d: boot normal, post-arm-lite lite). test_mode_switch_stops_outgoing_host@2927 (c+#10:
        outgoing stop_calls==1). test_start_lite_after_idle_unload_reloads_in_lite@2951 (c). The
        toggle_lite/toggle semantics tests @3696-3826 (a+c+e-edge). test_toggle_lite_docstring@3851."
  critical: "The contract run target is `-k 'mode or toggle_lite or start_lite or switch'` = 15 passed,
             178 deselected. Record '15 passed, 178 deselected' as the baseline; the named tests above
             are the clause-specific assertions."

# CONTEXT — the PRD spec being audited against.
- docfile: PRD.md   # §4.2ter arming rules + State/status + Commands/keybind + §7 acceptance #10
  why: "§4.2ter 'Mode is a spawn-time property… Arming rules' (3 bullets: same-mode instant; cross-mode
        teardown+respawn ~1-3s; unloaded spawn). §4.2ter 'Commands / keybind' (toggle/start normal;
        toggle-lite/start-lite lite; stop disarms either). §4.2ter 'State / status' (state.json 'mode';
        voicectl status mode:; written on arm/disarm). §7 #10 (switching modes costs one bounded reload).
        Match these against the code in the compliance table."

# CONTEXT — the parallel/sibling tasks (disjoint scope; S2 APPENDS to S1's file).
- docfile: plan/006_862ee9d6ef41/P1M2T3S1/PRP.md
  why: "S1 CREATES gap_lite.md (H1 '# Gap Report — P1.M2.T3.S1: Lite Recorder Construction vs PRD
        §4.2ter'). S2 APPENDS its H2 section below. SAME FILE, disjoint TOPIC (S1=lite construction
        kwargs; S2=reload lifecycle). If S1's file is present, append; if absent, create with a
        minimal H1 + S2 section (CRITICAL #5)."
```

### Current Codebase tree (relevant slice — audit reads these; writes ONLY the gap_lite.md section)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py          # READ: start@1365, start_lite@1376, stop@1388, toggle@1393, toggle_lite@1426,
│   │                      #       _load_host@698-795 (switch_mode@718, teardown@736-742, self._mode@766),
│   │                      #       _request_stop@1054, _arm@998 (set_mode), _disarm@1041, _dispatch@1892,
│   │                      #       status_snapshot@1567, _bounded_shutdown@1620, self._mode field@644
│   ├── feedback.py        # READ: set_mode@145, _state['mode']@99
│   ├── recorder_host.py   # READ: mode@property@168, is_alive@173, spawn@194-196, _mode@125
│   └── ctl.py             # READ: _COMMANDS@37, routing@199-202, format_result@48
├── tests/
│   └── test_daemon.py     # RUN: -k 'mode or toggle_lite or start_lite or switch' (15 tests)
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_lifecycle.md   # READ: the per-subtask section format to mirror
    └── gap_lite.md        # APPEND (S2's H2 section) — created by S1; created-with-H1 if absent
```

### Desired Codebase tree (what this task produces)

```bash
plan/006_862ee9d6ef41/architecture/gap_lite.md   # S2's section APPENDED (or created w/ H1 + section if S1 absent)
# No source/test changes. git status --short == gap_lite.md (modified or new).
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — FULL PATHS in every bash command (zsh aliases python3→uv run). Use .venv/bin/python,
#   NEVER bare python/pytest. The unit tests are mocked-CUDA (no real models) → ~0.04s; wrap in
#   `timeout 600` as the sibling gap reports do (inner timeout) + the bash tool `timeout` above it
#   (outer backstop). Per AGENTS.md: two timeouts on every non-trivial command.

# CRITICAL #2 — The switch branch @738 calls _bounded_shutdown(timeout=5.0) DIRECTLY, not _unload_host.
#   _unload_host@1204 is the IDLE-triggered wrapper (re-checks the idle threshold + listening under
#   _lock — would no-op during a switch). The switch reuses the bounded-teardown PRIMITIVE
#   (_bounded_shutdown, the same one _unload_host delegates to @1239). Do NOT flag "switch should call
#   _unload_host" as a gap — it is correct factoring. (Nuance §4.2.)

# CRITICAL #3 — _disarm@1041 does NOT call feedback.set_mode (only set_listening(False)+set_phase).
#   This is CORRECT, not a gap: disarm does not change self._mode (the resident child is unchanged on
#   disarm), so the mode value from the most recent _arm persists in state.json and is already current.
#   PRD §4.2ter "written on every arm/disarm" describes the OUTCOME (mode stays current), satisfied
#   de facto. The failed-cross-mode-switch edge (resident X torn down, Y load failed, then _disarm)
#   leaves self._mode at the prior value with _models_loaded=False; status is still honest via
#   listening:off + load_error (test_failed_cross_mode_toggle_status_snapshot_is_honest@3826). (Nuance §4.1.)

# CRITICAL #4 — self._mode@766 is set on SUCCESS only. On a failed spawn, self._mode is left unchanged
#   (the prior value). Intentional: a failed load leaves no resident child (_models_loaded=False,
#   _host=None), so self._mode reflects the last SUCCESSFUL mode + status_snapshot pairs it with
#   models_loaded:False + load_error. Not a gap. (Nuance §4.5.)

# CRITICAL #5 — FILE-OWNERSHIP RACE with S1. S1 CREATES gap_lite.md; S2 APPENDS. Because they share a
#   round, S2's implementation must be robust to ordering:
#     • If `ls plan/006_862ee9d6ef41/architecture/gap_lite.md` SUCCEEDS (S1 done — expected): APPEND
#       the '## Gap Report — P1.M2.T3.S2: ...' section BELOW S1's H1 content (read-modify-write that
#       PRESERVES S1's section; or `>> ` to append). Do NOT overwrite S1.
#     • If it FAILS (S1 not yet run): CREATE gap_lite.md with a minimal H1 '# Gap Reports — Lite Mode
#       (PRD §4.2ter)' + the S2 section, so the work is not lost (S1's section is reconciled later /
#       by P1.M5.T5).
#   In BOTH cases the deliverable is the SAME S2 section content; only the file-prelude differs.

# CRITICAL #6 — This is a RE-VERIFICATION of an already-compliant feature. Do NOT invent defects to
#   look thorough: if the 6 clauses pass (they do) + the 15 tests pass, the verdict is ✅ COMPLIANT
#   and NO source/test files change. Code changes occur ONLY if re-verification surfaces a REAL defect
#   (record it + the fix).

# CRITICAL #7 — Do NOT re-audit the bounded-teardown PRIMITIVE (_bounded_shutdown internals, killpg,
#   join(5s) budget). That is P1.M2.T2.S3's gap_lifecycle.md §3 scope. S2 REFERENCES _bounded_shutdown
#   @738 as the reload's teardown (cites the line + the ≤~7s budget for acceptance #10) but does NOT
#   re-derive the SIGKILL/join mechanics. Stay in scope (the reload LIFECYCLE, not the teardown guts).
```

## Implementation Blueprint

### Data models and structure

None (audit only). The "data" is the 6-clause compliance table + file:line evidence transcribed into
the `gap_lite.md` section.

### Implementation Tasks (ordered by dependencies — a re-verify + transcribe runbook)

```yaml
Task 1: RE-VERIFY clause (a) — command→mode routing (4 daemon methods + socket + CLI)
  - READ daemon.py start@1365-1372 (calls _load_host("normal")@1370 then _arm); start_lite@1376-1386
    (_load_host("lite")@1384 then _arm); toggle@1393-1424 (arm branch _load_host("normal")@1415);
    toggle_lite@1426-1456 (arm branch _load_host("lite")@1447).
  - READ daemon.py ControlServer._dispatch@1892-1935: "toggle"@1901→toggle()@1903; "start"@1913→
    start()@1914; "start-lite"@1916→start_lite()@1917; "toggle-lite"@1919→toggle_lite()@1921;
    "stop"@1926→stop()@1927; "status"@1929→status_snapshot()@1930; "quit"@1931→request_shutdown()+on_quit.
  - READ ctl.py _COMMANDS@37 (all 7) + routing@199-202 (the 4 arm cmds use _send_command_with_loading_hint).
  - VERDICT: routing is complete + correct (research §0 row a). Record file:line in §2 row (a).

Task 2: RE-VERIFY clause (b) — same-mode resident → instant arm
  - READ daemon.py _load_host@713-720: @715 `if self._models_loaded and self._host is not None and
    self._host.is_alive:` → @716 `if getattr(self._host, "mode", "normal") == mode:` → @717 `return True`
    (instant, SAME mode, no reload). READ recorder_host.py mode@property@168-170 + is_alive@173-175.
  - RUN test: test_same_mode_arm_is_instant_no_reload@2892 (asserts d._host is host1, no teardown).
  - VERDICT: compliant (research §0 row b). Record file:line in §2 row (b).

Task 3: RE-VERIFY clause (c) — cross-mode → tear down + respawn in new mode (acceptance #10)
  - READ daemon.py _load_host@718-742: @718 switch_mode=True (resident but WRONG mode); @736 `if
    switch_mode and self._host is not None:` → @737 log → @738 `with self._lock: self._bounded_shutdown
    (timeout=5.0); @740 self._host=None; @741 self._models_loaded=False` → falls through to @749-757
    factory(..., mode=mode) spawn (OUTSIDE _lock).
  - READ daemon.py _bounded_shutdown@1620-1645 (the bounded teardown primitive: host.stop(timeout=5) →
    killpg, ≤~7s; SAME primitive _unload_host@1239 uses — nuance §4.2). Cite the ≤~7s budget for #10.
  - RUN tests: test_mode_switch_normal_to_lite_reloads@2875 (new host mode=='lite') +
    test_mode_switch_stops_outgoing_host@2927 (outgoing host.stop_calls==1, new host.stop_calls==0).
  - VERDICT: compliant (research §0 row c + §2 the bounded-reload guarantee). Record file:line in §2
    row (c) + note the _bounded_shutdown-not-_unload_host factoring (nuance §4.2).

Task 4: RE-VERIFY clause (d) — self._mode updated on arm + reported in status
  - READ daemon.py _load_host@759-766: @766 `self._mode = mode` (success branch ONLY); field init
    @644 `self._mode: str = "normal"`; status_snapshot@1567 `"mode": self._mode`.
  - READ recorder_host.py RecorderHost._mode@125 (set from the spawn arg) + mode@property@168 (what
    _load_host@716 compares against).
  - RUN tests: test_start_lite_loads_lite_host_and_arms@2863 (d._mode=="lite") +
    test_status_snapshot_reports_mode@2918 (boot normal, post-arm-lite lite).
  - VERDICT: compliant (research §0 row d). Record file:line in §2 row (d) + note success-only (§4.5).

Task 5: RE-VERIFY clause (e) — feedback.set_mode on arm (+ de-facto on disarm)
  - READ daemon.py _arm@998 `self._feedback.set_mode(self._mode)`; _disarm@1041-1051 (does NOT call
    set_mode — only set_listening(False)@1049 + set_phase("idle")@1050).
  - READ feedback.py set_mode@145-150 (writes _state["mode"] + _write()) + _state init @99 ("normal").
  - RUN test: test_start_lite_loads_lite_host_and_arms@2863 (fb.modes==["lite"]) +
    test_failed_cross_mode_toggle_status_snapshot_is_honest@3826 (failed-switch edge: status honest).
  - VERDICT: compliant DE FACTO (research §0 row e + nuance §4.1): mode is unchanged on disarm, so the
    value from the last _arm persists and is current. Record file:line in §2 row (e) + the nuance.

Task 6: RE-VERIFY clause (f) — stop disarms regardless of mode
  - READ daemon.py stop@1388-1390 (→ _request_stop()@1054); _request_stop@1054-1064: @1056 `if
    self._host is not None and self._text_in_flight.is_set() and self._final_pending:` → _begin_drain
    (graceful); else @1062-1064 `with self._lock: self._disarm(); ... self._safe_abort()`. NO mode check.
  - READ _dispatch "stop"@1926-1928 → self._daemon.stop().
  - RUN test: test_toggle_lite_while_listening_in_lite_stops@2904 (disarms lite). (stop is mode-agnostic
    by construction — no mode branch exists to test the "other" mode separately; the absence of a mode
    check IS the compliance evidence.)
  - VERDICT: compliant (research §0 row f). Record file:line in §2 row (f).

Task 7: RUN the contract test target + record the count
  - CMD: timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'mode or toggle_lite or
    start_lite or switch'
  - EXPECTED: 15 passed, 178 deselected in ~0.04s (baseline; research §3). Record in §3 + name the
    clause-specific tests (research §0 / §3).

Task 8: APPEND the section to gap_lite.md (mirror gap_lifecycle.md's per-subtask section format)
  - CHECK: `ls plan/006_862ee9d6ef41/architecture/gap_lite.md` (CRITICAL #5):
    • EXISTS (S1 done): read-modify-write PRESERVING S1's H1 content; APPEND the S2 H2 section below it.
    • ABSENT (S1 not run): CREATE with H1 `# Gap Reports — Lite Mode (PRD §4.2ter)` + the S2 H2 section.
  - SECTION TITLE: "## Gap Report — P1.M2.T3.S2: Mode-Switch Reload & self._mode Tracking vs PRD §4.2ter"
  - Date + Scope (the 6 clauses a-f) + Audited artifacts (file:line list from Tasks 1-6).
  - "Bottom line:" ✅ COMPLIANT (all 6 clauses) + the 15-test count + acceptance #10 (one bounded reload).
  - §1 Method: the grep commands + the test command (Task 7).
  - §2 per-clause compliance table (research §0): PRD §4.2ter expected | code actual (file:line) | ✅.
  - §3 test evidence (15 passed, 178 deselected; the named tests + their clauses — research §3).
  - §4 non-defect nuances (research §4): (1) set_mode in _arm not _disarm; (2) switch uses
    _bounded_shutdown not _unload_host; (3) read/act outside _lock; (4) default "normal" at boot;
    (5) set_mode on success only.
  - Conclusion: ties verdict to PRD §4.2ter arming rules + acceptance #10 (same-mode instant;
    cross-mode teardown+respawn bounded; stop mode-agnostic; self._mode tracks resident).

Task 9: SCOPE GUARD — verify no source/test files changed
  - CMD: git status --short
  - EXPECTED: ONLY `plan/006_862ee9d6ef41/architecture/gap_lite.md` (modified — S2 appended; or new — if
    S1 had not created it). No voice_typing/*, no tests/*, no PRD.md/tasks.json/prd_snapshot.md/.gitignore.
    (If a real defect was found + fixed in Task X, that source change is ALSO expected — record it in
    the section; otherwise none.)
```

### Implementation Patterns & Key Details

```bash
# PATTERN — a re-verification audit: read the cited lines, run the -k slice, transcribe the section.

# 1. Re-locate every mode-switch site (the grep the gap report's §1 will cite):
grep -nE 'def start|def start_lite|def stop|def toggle|def toggle_lite|_load_host\(|switch_mode|self\._mode|set_mode|_bounded_shutdown|def _dispatch|"toggle"|"start"|"stop"|"status"|"quit"|"toggle-lite"|"start-lite"' voice_typing/daemon.py
grep -nE 'def set_mode|"mode"|self\._state\["mode"\]' voice_typing/feedback.py
grep -nE 'def mode|is_alive|self\._mode|target=_worker_main' voice_typing/recorder_host.py
grep -nE '_COMMANDS|toggle-lite|start-lite|def send_command|def _send_command_with_loading_hint' voice_typing/ctl.py

# 2. Re-run the contract target (record the count for §3):
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'mode or toggle_lite or start_lite or switch'
#   → 15 passed, 178 deselected in 0.04s.

# 3. Append the section to gap_lite.md (CRITICAL #5: append if exists, create-with-H1 if absent):
F=plan/006_862ee9d6ef41/architecture/gap_lite.md
if [ -f "$F" ]; then echo "exists → append S2 section below S1's H1"; else echo "absent → create H1 + S2 section"; fi
#   (use read-modify-write that PRESERVES S1's content; do NOT overwrite.)

# 4. Scope guard:
git status --short   # → ONLY gap_lite.md (modified or new). No voice_typing/*, no tests/*, no PRD/tasks.json.
```

### Integration Points

```yaml
CONSUMED (read-only — verify, don't change):
  - voice_typing/daemon.py: start@1365, start_lite@1376, stop@1388, toggle@1393, toggle_lite@1426,
    _load_host@698-795 (switch_mode@718, teardown@736-742, self._mode@766), _request_stop@1054,
    _arm@998 (set_mode), _disarm@1041, _dispatch@1892, status_snapshot@1567, _bounded_shutdown@1620,
    self._mode field@644.
  - voice_typing/feedback.py: set_mode@145, _state["mode"]@99.
  - voice_typing/recorder_host.py: mode@property@168, is_alive@173, spawn@194-196, _mode@125.
  - voice_typing/ctl.py: _COMMANDS@37, routing@199-202, format_result@48.
  - tests/test_daemon.py: the 15 mode-switch tests (@2863-3851).
PRODUCED (this task):
  - plan/006_862ee9d6ef41/architecture/gap_lite.md — S2's "## Gap Report — P1.M2.T3.S2: ..." section
    APPENDED (or the file created with H1 + S2 section if S1 had not run).
DOWNSTREAM CONSUMERS:
  - P1.M2.T3.S3 (T7 coverage audit): references this audit's reload-test inventory.
  - P1.M5.T5 (acceptance cross-check): maps acceptance #10 ("switching costs one bounded reload") to
    this audit's _bounded_shutdown@738 teardown + test_mode_switch_stops_outgoing_host@2927 evidence.
DO NOT TOUCH:
  - voice_typing/* (no defect exists), tests/*, PRD.md, **/tasks.json, **/prd_snapshot.md, .gitignore,
    pyproject.toml, uv.lock. No new deps. Do NOT overwrite S1's section in gap_lite.md (append only).
```

## Validation Loop

> Full paths in every command (CRITICAL #1). The unit tests are mocked-CUDA (~0.04s); wrap in
> `timeout 600` (inner) + set the bash tool `timeout` above it (outer backstop, per AGENTS.md).

### Level 1: Re-verify the 6 clauses against the live source (read the cited lines)

```bash
cd /home/dustin/projects/voice-typing
grep -nE 'def start|def start_lite|def stop|def toggle|def toggle_lite|_load_host\(|switch_mode|self\._mode|set_mode|_bounded_shutdown|def _dispatch|"toggle"|"start"|"stop"|"status"|"quit"|"toggle-lite"|"start-lite"' voice_typing/daemon.py
grep -nE 'def set_mode|"mode"|self\._state\["mode"\]' voice_typing/feedback.py
grep -nE 'def mode|is_alive|self\._mode|target=_worker_main' voice_typing/recorder_host.py
grep -nE '_COMMANDS|toggle-lite|start-lite|def send_command|def _send_command_with_loading_hint' voice_typing/ctl.py
# Expected: each clause's file:line from the research note §0 is present and reads as documented.
#   (a) start/start_lite/toggle/toggle_lite → _load_host('normal'/'lite'); _dispatch routes all 7 cmds.
#   (b) _load_host@715-717 same-mode resident → return True (instant).
#   (c) _load_host@718 switch_mode=True; @736-742 _bounded_shutdown(5.0) + _host=None + respawn mode=mode.
#   (d) _load_host@766 self._mode=mode (success); status_snapshot@1567 "mode":self._mode.
#   (e) _arm@998 feedback.set_mode(self._mode); _disarm@1041 (no set_mode — de-facto current).
#   (f) stop@1388→_request_stop@1054 (NO mode check — drains/disarms either mode).
```

### Level 2: Run the contract test target (the acceptance gate)

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'mode or toggle_lite or start_lite or switch'
# Expected: 15 passed, 178 deselected in ~0.04s. (Clause-specific: test_start_lite_loads_lite_host_and_arms,
#   test_mode_switch_normal_to_lite_reloads, test_same_mode_arm_is_instant_no_reload,
#   test_toggle_lite_while_listening_in_lite_stops, test_status_snapshot_reports_mode,
#   test_mode_switch_stops_outgoing_host, test_start_lite_after_idle_unload_reloads_in_lite,
#   the toggle_lite/toggle semantics tests @3696-3826, test_toggle_lite_docstring@3851.)
# On a real FAILURE: it would indicate a regression in the mode-switch lifecycle — debug the root cause
#   (do NOT weaken the assertion); record the defect + fix in the gap_lite.md section. (None expected.)
```

### Level 3: Transcribe the section + scope guard

```bash
cd /home/dustin/projects/voice-typing
F=plan/006_862ee9d6ef41/architecture/gap_lite.md
# CRITICAL #5 — robust to S1 ordering:
if [ -f "$F" ]; then echo "EXISTS (S1 done) → APPEND '## Gap Report — P1.M2.T3.S2: ...' below S1's H1"; \
else echo "ABSENT (S1 not run) → CREATE with H1 '# Gap Reports — Lite Mode (PRD §4.2ter)' + the S2 section"; fi
# (read-modify-write PRESERVING S1's content if present; do NOT overwrite.)
git status --short
# Expected: ONLY gap_lite.md (modified — S2 appended; or new — if S1 absent). No voice_typing/*, no tests/*,
#   no PRD.md/tasks.json/prd_snapshot.md/.gitignore change.
```

### Level 4: Report completeness check (the deliverable quality gate)

```bash
cd /home/dustin/projects/voice-typing
F=plan/006_862ee9d6ef41/architecture/gap_lite.md
grep -qE '## Gap Report — P1.M2.T3.S2: Mode-Switch Reload & self._mode Tracking' "$F" && echo "S2 section title OK"
grep -qE 'Bottom line.*COMPLIANT|✅' "$F" && echo "verdict OK"
grep -qE '15 passed' "$F" && echo "test evidence OK"
grep -qE '_load_host|switch_mode|_bounded_shutdown|self\._mode|set_mode|_dispatch' "$F" && echo "file:line evidence OK"
grep -qiE 'nuance|non-defect' "$F" && echo "nuances section OK"
grep -qE 'acceptance #10|one bounded reload' "$F" && echo "acceptance #10 tie-in OK"
# Expected: all 6 checks pass → the section has title + verdict + test count + file:line evidence +
#   nuances + the acceptance #10 tie-in.
```

## Final Validation Checklist

### Technical Validation
- [ ] Level 1: all 6 clauses' file:line present in the live source and read as documented (research §0).
- [ ] Level 2: `timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'mode or toggle_lite or
      start_lite or switch'` → `15 passed, 178 deselected` (recorded in the section).
- [ ] Level 3: `gap_lite.md` section appended (or created with H1 + section if S1 absent); `git status
      --short` == `gap_lite.md` only (modified or new).
- [ ] Level 4: section has title + ✅ verdict + test count + file:line evidence + nuances + acceptance #10.

### Feature (Audit) Validation
- [ ] (a) command→mode routing verified (4 daemon methods + socket `_dispatch` + `ctl._COMMANDS`).
- [ ] (b) same-mode resident → instant `_load_host@715-717 return True` (no reload).
- [ ] (c) cross-mode → `_bounded_shutdown@738` teardown + respawn `@749-757` (acceptance #10: one bounded reload).
- [ ] (d) `self._mode=mode`@766 (success) + `status_snapshot`@1567 + field init @644.
- [ ] (e) `feedback.set_mode`@998 on arm (de-facto-current on disarm — nuance §4.1).
- [ ] (f) `stop`@1388→`_request_stop`@1054 mode-agnostic (drains/disarms either mode).
- [ ] Compliance table maps each clause to PRD §4.2ter expected vs code actual (file:line) vs ✅.

### Code Quality / Scope Validation
- [ ] No source/test files modified (no defect exists → no fix; the mode-switch lifecycle is compliant).
- [ ] S2 section is an `## ` H2 appended to gap_lite.md (NOT a new file, NOT overwriting S1's H1).
- [ ] Section follows the gap-report format (mirror gap_lifecycle.md's per-subtask sections).

### Forbidden-Operations Compliance
- [ ] `voice_typing/*` NOT modified. `tests/*` NOT modified.
- [ ] `PRD.md`, `**/tasks.json`, `**/prd_snapshot.md`, `.gitignore` NOT modified.
- [ ] S1's section in gap_lite.md NOT overwritten (append-only; create-with-H1 only if file absent).
- [ ] No new deps; no `pyproject.toml`/`uv.lock` change.

---

## Anti-Patterns to Avoid

- ❌ Don't invent defects to look thorough — the mode-switch lifecycle is COMPLIANT (pre-verified). If
  the 6 clauses pass (they do) + the 15 tests pass, the verdict is ✅ and NO source/test files change.
  Record nuances, not phantom gaps.
- ❌ Don't flag the switch branch calling `_bounded_shutdown` (not `_unload_host`) as a gap —
  `_unload_host` has idle-threshold guards that would no-op during a switch; the switch correctly
  reuses the bounded-teardown primitive (CRITICAL #2 / nuance §4.2).
- ❌ Don't flag `_disarm` not calling `set_mode` as a gap — disarm doesn't change `self._mode`, so the
  value from the last `_arm` persists and is already current in state.json (CRITICAL #3 / nuance §4.1).
- ❌ Don't flag `self._mode` being set on success-only as a gap — a failed load leaves no resident
  child; `self._mode` reflects the last SUCCESSFUL mode + status pairs it with `models_loaded:False` +
  `load_error` (CRITICAL #4 / nuance §4.5).
- ❌ Don't overwrite S1's `gap_lite.md` content — APPEND the S2 H2 section below S1's H1 (or create
  with a minimal H1 + S2 section ONLY if the file is absent) (CRITICAL #5).
- ❌ Don't re-audit the `_bounded_shutdown` teardown internals (killpg, join(5s) budget) — that's
  P1.M2.T2.S3's scope (gap_lifecycle.md §3). S2 cites the line + the ≤~7s budget for acceptance #10
  only (CRITICAL #7).
- ❌ Don't use bare `python`/`pytest` (zsh aliases). Full paths: `.venv/bin/python`. Two timeouts
  (inner `timeout 600` + outer bash-tool `timeout`), per AGENTS.md.
- ❌ Don't modify `gap_lifecycle.md`, `PRD.md`, `tasks.json`, or any `voice_typing/*`/`tests/*` file.

---

## Confidence Score

**9.5/10** for one-pass success. This is a re-verification audit with every fact pre-verified against
the live tree: the 6-clause compliance table with exact file:line (research §0), the full command→mode
→load chain + `_load_host` switch internals (§1), the bounded-reload guarantee for acceptance #10 (§2),
the verified test baseline (`15 passed, 178 deselected in 0.04s` — re-ran live), the gap-report section
format to mirror, and the 5 non-defect nuances documented so they are not mistaken for gaps. The
file-ownership race with S1 is handled explicitly (CRITICAL #5: append if exists, create-with-H1 if
absent). Residual risk (−0.5): (i) a future code shift between this PRP's research and implementation
could move a line number — the implementer re-runs the greps + the test, so the section always reflects
the live tree (line numbers are re-derived, not copy-pasted); (ii) if S1 has NOT yet created
`gap_lite.md` when S2 runs, S2 creates it with a minimal H1 + its section, and S1's section is
reconciled later (the content is preserved either way).