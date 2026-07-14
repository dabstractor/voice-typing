# PRP — P1.M4.T1.S2: Update tests/ACCEPTANCE.md teardown criteria + SIGTERM-path test coverage note

## Goal

**Feature Goal**: Bring `tests/ACCEPTANCE.md` into agreement with the **landed** bugfix behavior and
the **landed** regression-test coverage, so the project's acceptance-evidence document no longer states
the stale pre-fix teardown budget and no longer omits the SIGTERM-path / Issue-2 / Issue-3 test
coverage. This is the ACCEPTANCE.md half of the changeset-level documentation sync (item DOCS: "This IS
the documentation subtask"). **Two prose-only edits within one existing section** (Notes on the method):
(a) correct the teardown budget from `≤10 s` to the post-fix `≤5 s` single-flight budget; (b) append a
new bullet documenting the SIGTERM/systemctl-stop test coverage (the previously-missing test that let
Issue 1 slip through) plus the Issue 2 (phase-after-disarm) and Issue 3 (child-crash recovery)
regression tests. **No code, no tests, no new files, no heading changes.**

**Deliverable** (ONE artifact — `tests/ACCEPTANCE.md`, two edits):
1. **Edit 1 (T6 GPU residency bullet, ~L130)** — change `≤10 s bounded teardown` → the post-fix
   `≤5 s single-flight teardown` (per-call `host.stop()` join budget; was ≤10 s), reflecting
   `P1.M1.T2.S2` (`_bounded_shutdown` default 10→5) + `P1.M1.T1.S1`/`P1.M1.T2.S1` single-flight.
2. **Edit 2 (append a new bullet at the end of "Notes on the method", after the Cleanup bullet ~L146)**
   — a **"Regression-test coverage (bugfix Issues 1–3)"** bullet naming the landed tests: the
   SIGTERM-path `test_concurrent_request_shutdown_and_shutdown_only_one_stop` (previously only
   `voicectl quit` was covered — exactly why Issue 1 slipped through), the Issue 2 phase-reset tests,
   and the Issue 3 child-crash tests.

**Success Definition**:
- (a) `tests/ACCEPTANCE.md` still parses as valid Markdown; code-fence count even; **no heading
  text/level changed**; the ~76-col manual soft-wrap and 2-space bullet indent preserved.
- (b) The stale `≤10 s bounded teardown` is gone, replaced by a `≤5 s` single-flight claim that matches
  the LANDED code (`recorder_host.py:87 _STOP_JOIN_TIMEOUT_S=5.0`; `daemon.py:1338
  _bounded_shutdown(timeout=5.0)`; `recorder_host.py:140/:265 _stop_lock`; `systemd … TimeoutStopSec=15`).
- (c) The new bullet names ONLY tests that ACTUALLY EXIST (verified): the SIGTERM-path concurrent test
  (`test_concurrent_request_shutdown_and_shutdown_only_one_stop`, tests/test_daemon.py:1029) + the
  recorder-host single-flight test (`test_concurrent_stop_calls_share_one_teardown`,
  tests/test_recorder_host.py:232); the Issue 2 tests (`test_disarm_resets_phase_to_idle` /
  `test_toggle_off_resets_phase_to_idle` / `test_auto_stop_resets_phase_to_idle`); the Issue 3 tests
  (`test_run_loop_detects_dead_host_and_transitions_to_unloaded` /
  `test_load_host_respawns_after_dead_child` / `test_status_reports_unloaded_after_child_death`).
- (d) `git status --short` shows **ONLY** `tests/ACCEPTANCE.md` modified. NO edit to `README.md`
  (sibling P1.M4.T1.S1 owns it), NO `.py` file, NO `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/
  `config.toml`/`pyproject.toml`/`uv.lock`.

## User Persona

**Target User**: The maintainer/future-contributor reading `tests/ACCEPTANCE.md` to understand how the
PRD §7 acceptance criteria are demonstrated and what the teardown/test-coverage guarantees are — and any
auditor verifying that the bugfix (Issues 1–3) is actually backed by tests.

**Use Case**: (1) A maintainer re-runs `test_idle_and_gpu.sh` and reads the T6 note to interpret the
T6(d-gone) poll ceiling — the note's teardown-budget figure must match the real `host.stop()` budget.
(2) A reviewer assessing whether the SIGTERM regression is covered looks at ACCEPTANCE.md and finds the
explicit pointer to `test_concurrent_request_shutdown_and_shutdown_only_one_stop` (and the explanation
of why it was missing before).

**Pain Points Addressed**: The doc currently (1) over-states the teardown budget (`≤10 s` is the
pre-fix value) and (2) is silent on the SIGTERM-path coverage — the very gap that let the Critical
Issue 1 reach production. Both are corrected.

## Why

- **The doc must not state a stale teardown budget.** Issue 1's fix reduced the per-call budget (10→5)
  and made teardown single-flight. The T6 note's `≤10 s` figure is now wrong and would mislead anyone
  reasoning about the T6(d-gone) timing headroom. The figure is a one-token fix (`≤10 s` → `≤5 s`).
- **The SIGTERM coverage gap is the headline lesson of Issue 1.** PRD §Testing Summary explicitly calls
  out that "the existing tests only cover `voicectl quit` and legacy stub shutdowns, never a real armed
  SIGTERM — which is exactly why Issue 1 slipped through." ACCEPTANCE.md — the project's acceptance
  record — must record that this gap is now closed (the `test_concurrent_request_shutdown_and_shutdown_only_one_stop`
  test from P1.M1.T2.S3), so a future regression is caught and the lesson is durable.
- **Issues 2 + 3 are now regression-tested; the doc should say so.** Without the note, a reader has no
  signal that phase-after-disarm (Issue 2) or child-crash recovery (Issue 3) have tests at all.
- **Small, surgical, low-risk, closes the changeset.** P1.M4 (Documentation Sync) = S1 (README) + S2
  (ACCEPTANCE.md). This task is prose-only and touches one file on a disjoint path from S1.

## What

Two edits to `tests/ACCEPTANCE.md`, each an exact `edit`-tool replacement (verbatim `oldText`/`newText`
in Implementation Blueprint → Tasks 1–2). Both live in the **Notes on the method** section (L108–146):
- **Edit 1** fixes one fragment inside the **T6 GPU residency** bullet (~L130).
- **Edit 2** appends a **new bullet** after the **Cleanup** bullet (the section's last bullet, ~L146).

No heading, table, or evidence-block line is touched.

### Success Criteria

- [ ] `tests/ACCEPTANCE.md` parses as Markdown; fence count even; heading set byte-identical before/after.
- [ ] Edit 1 present: the file no longer contains `≤10 s bounded teardown`; it contains a `≤5 s`
      single-flight teardown claim in the T6 bullet.
- [ ] Edit 2 present: the file contains a **"Regression-test coverage"** bullet naming
      `test_concurrent_request_shutdown_and_shutdown_only_one_stop` and stating the prior gap (only
      `voicectl quit` was covered); plus the Issue 2 + Issue 3 test names.
- [ ] Every test named in Edit 2 EXISTS (L2 grep against the live test files passes — no phantom tests).
- [ ] Factual-accuracy greps (L2) pass: `_STOP_JOIN_TIMEOUT_S: float = 5.0`, `_bounded_shutdown(self,
      timeout: float = 5.0)`, `_stop_lock`, `TimeoutStopSec=15`, `set_phase("idle")` all present in code.
- [ ] `git status --short` shows ONLY `tests/ACCEPTANCE.md`; `README.md` untouched.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge of this codebase: both exact `oldText`/`newText` blocks
are provided verbatim for the `edit` tool; the post-fix facts each edit documents are VERIFIED against
the landed code with file:line citations (research §2); the test names in Edit 2 are VERIFIED to exist
(research §3, with `def test_…` line numbers); the sibling-task scope boundary (`README.md` =
P1.M4.T1.S1) is explicit; and the validation gates (markdown validity + accuracy grep + test-existence
grep + scope guard) are all executable as written.

### Documentation & References

```yaml
# MUST READ — this task's research (exact anchors + verified code facts + verified test names + scope).
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M4T1S2/research/acceptance_doc_sync_facts.md
  why: "§1 the two ACCEPTANCE.md anchors (T6 bullet ~L130 for Edit 1; end-of-Notes append for Edit 2)
        with exact current text. §2 the VERIFIED post-fix code facts each claim must match
        (5.0s _STOP_JOIN_TIMEOUT_S; _bounded_shutdown(timeout=5.0); _stop_lock single-flight;
        _TEARDOWN_WAIT_TIMEOUT=8.0; TimeoutStopSec=15; _disarm->set_phase('idle')). §3 the VERIFIED
        landed test names + file:line for Edit 2 (Issue 1 SIGTERM test + recorder-host single-flight;
        Issue 2 phase tests; Issue 3 child-crash tests). §4 scope (ACCEPTANCE.md ONLY; README.md = S1).
        §5 markdown conventions (bold lead term, 2-space indent, ~76-col wrap, no heading changes)."
  section: "ALL load-bearing. §1 (anchors), §2 (facts), §3 (tests), §5 (style)."

# MUST READ — the file being edited. READ to confirm the exact anchor text before editing.
- file: tests/ACCEPTANCE.md
  why: "The TARGET file (146 lines). Edit 1 anchor = the `≤10 s bounded teardown` fragment in the T6
        GPU residency bullet (~L130). Edit 2 anchor = the Cleanup bullet's final line `silence on the
        real mic).` (~L146, the file's last line). READ these regions to confirm the verbatim oldText
        matches byte-for-byte (including the `≤` and `—` glyphs) before applying each edit."
  critical: "The edit tool requires EXACT oldText. Run the Task 0 preflight (greps a unique substring of
             each region) to confirm the anchors before editing. Do NOT touch the Criteria table (L26-37)
             or the Evidence block (L39-106) — only the Notes section."

# MUST READ — the consumed/fixed code (READ-ONLY; do NOT edit). Confirms Edit 1's claim is true.
- file: voice_typing/recorder_host.py
  why: ":87 _STOP_JOIN_TIMEOUT_S: float = 5.0 (the ≤5s per-call join budget); :255 stop() default
        timeout=_STOP_JOIN_TIMEOUT_S; :140 _stop_lock; :265 the SINGLE-FLIGHT body-under-lock comment.
        Edit 1 cites '≤5 s single-flight teardown' from these."
- file: voice_typing/daemon.py
  why: ":1338 def _bounded_shutdown(self, timeout: float = 5.0) (was 10.0 — P1.M1.T2.S2); :342
        _TEARDOWN_WAIT_TIMEOUT = 8.0 (the single-flight wait budget); :918 _disarm()->set_phase('idle')
        (Issue 2). Edit 1 + Edit 2 cite these."
- file: systemd/voice-typing.service
  why: ":52 TimeoutStopSec=15 (the budget the ≤5s teardown must fit under)."

# MUST READ — verify Edit 2's test names EXIST before claiming coverage (do NOT edit the tests).
- file: tests/test_daemon.py
  why: "Edit 2 names: test_concurrent_request_shutdown_and_shutdown_only_one_stop (:1029, Issue 1
        SIGTERM path); test_request_shutdown_claims_and_signals_teardown_done (:1647) and the 4 sibling
        coordination tests (P1.M1.T2.S1); test_disarm_resets_phase_to_idle (:3021) /
        test_toggle_off_resets_phase_to_idle (:3032) / test_auto_stop_resets_phase_to_idle (:3043)
        (Issue 2); test_run_loop_detects_dead_host_and_transitions_to_unloaded (:3076) /
        test_load_host_respawns_after_dead_child (:3116) / test_status_reports_unloaded_after_child_death
        (:3155) (Issue 3). CONFIRM these are present (L2 grep)."
- file: tests/test_recorder_host.py
  why: ":232 test_concurrent_stop_calls_share_one_teardown (P1.M1.T1.S2 recorder-host single-flight;
        named in Edit 2)."

# CONTEXT — the bug analysis + PRD testing summary (READ-ONLY).
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/bug_analysis.md
  why: "Issue 1 (SIGTERM double-teardown race), Issue 2 (phase stuck on disarm), Issue 3 (silent child
        crash) root causes + the explicit 'Test Gap' mandate (no test exercised the concurrent
        request_shutdown+shutdown SIGTERM path) — confirms WHY the new bullet's framing is correct."
- docfile: PRD.md
  why: "§Testing Summary: 'the existing tests only cover voicectl quit ... never a real armed SIGTERM —
        which is exactly why Issue 1 slipped through'. Edit 2 restates this gap-closure."
  critical: "Do NOT edit PRD.md (forbidden)."

# CONTEXT — the sibling task that owns README.md (do NOT collide).
- file: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M4T1S1/PRP.md
  why: "P1.M4.T1.S1 = 'Update README.md teardown claims + phase lifecycle + config-validation'. Its
        Critical #1 + scope guard enforce tests/ACCEPTANCE.md untouched. This task (S2) is the MIRROR:
        ACCEPTANCE.md ONLY, README.md untouched. The two edits compose with S1's README edits
        (disjoint files) — S1 even cites the same 5.0s / TimeoutStopSec=15 facts, so the docs stay
        consistent."
```

### Current Codebase tree (state at P1.M4.T1.S2 start)

The bugfixes P1.M1 (Issue 1), P1.M2 (Issues 2+3), P1.M3 (Issue 4) are **Complete/landed**, including
all regression tests named in Edit 2 (verified present). `tests/ACCEPTANCE.md` (146 lines) still states
the stale `≤10 s` budget and is silent on the SIGTERM/Issue-2/Issue-3 coverage.

```bash
/home/dustin/projects/voice-typing/
├── tests/
│   └── ACCEPTANCE.md          # ← EDIT (2 prose edits in "Notes on the method"). Edit 1 ~L130; Edit 2 append ~L146.
├── README.md                  # DO NOT TOUCH (sibling P1.M4.T1.S1 owns it — parallel).
├── PRD.md                     # READ-ONLY (forbidden).
├── systemd/voice-typing.service  # READ-ONLY (:52 TimeoutStopSec=15).
├── voice_typing/
│   ├── daemon.py              # LANDED (READ-ONLY): :1338 _bounded_shutdown(timeout=5.0); :918 _disarm->idle.
│   ├── recorder_host.py       # LANDED (READ-ONLY): :87 _STOP_JOIN_TIMEOUT_S=5.0; :140/:265 _stop_lock.
│   └── config.py              # LANDED (READ-ONLY).
└── tests/
    ├── test_daemon.py         # LANDED (READ-ONLY): the Issue 1/2/3 tests Edit 2 names.
    └── test_recorder_host.py  # LANDED (READ-ONLY): test_concurrent_stop_calls_share_one_teardown.
# NO new files. NO code edits. NO heading changes.
```

### Desired Codebase tree with files to be added

```bash
tests/ACCEPTANCE.md   # MODIFIED: Edit 1 (≤10s→≤5s single-flight in T6 bullet) + Edit 2 (new regression-test-coverage bullet).
# NOTHING ELSE.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — tests/ACCEPTANCE.md ONLY. This is the documentation subtask (ACCEPTANCE half). Do NOT
#   edit README.md (that is sibling P1.M4.T1.S1 — colliding causes a merge conflict/scope violation),
#   do NOT edit any .py file (the fixes + tests are LANDED; you only document them), do NOT edit
#   PRD.md/tasks.json/prd_snapshot.md/.gitignore/config.toml/pyproject.toml/uv.lock. (research §4; item OUTPUT.)

# CRITICAL #2 — the edit tool needs EXACT oldText (byte-for-byte incl. the ≤ and — glyphs and the
#   2-space continuation indent). Run the Task 0 preflight greps to confirm each anchor substring is
#   present + unique before editing. If an anchor does not match, re-read the exact region and adjust
#   oldText — do NOT guess. (research §1.)

# CRITICAL #3 — ONLY name tests that EXIST. Edit 2's whole value is "the SIGTERM path is now covered".
#   Every test name in the new bullet MUST be present in the live test files (L2 grep). The names are
#   pre-verified in research §3 (with file:line) — copy them verbatim; do NOT invent or paraphrase a
#   name (a phantom test would make the doc a lie). If L2 grep fails for any name, STOP and reconcile.

# CRITICAL #4 — PRESERVE the ~76-column manual soft-wrap + 2-space bullet hanging indent. The Notes
#   bullets are hand-wrapped (NOT a single reflowed line). New/edited prose wraps the same way. Do NOT
#   reflow the whole section — edit only the one fragment (Edit 1) and append the one bullet (Edit 2).
#   (research §5.)

# CRITICAL #5 — DO NOT change any heading (#/##/###) or touch the Criteria table (L26-37) or the
#   Evidence block (L39-106). Your edits are prose WITHIN the Notes section only. L1 validates the
#   heading set is unchanged. (research §5.)

# CRITICAL #6 — accuracy over marketing. The budget figure must be ≤5 s (NOT "instant", NOT "≤10s"),
#   matching _STOP_JOIN_TIMEOUT_S=5.0 + _bounded_shutdown(timeout=5.0). Frame the teardown as
#   single-flight (ONE host.stop() on the SIGTERM path). Cite TimeoutStopSec=15 only if natural — the
#   T6 bullet's budget list does not currently name it, so Edit 1 need not add it (keep the edit tight).
#   (research §2.)

# GOTCHA #7 — the `≤10 s bounded teardown` fragment is the ONLY stale teardown budget in the file.
#   There is exactly ONE occurrence (L130) — verified. Edit 1 replaces just that fragment; do not
#   search-and-replace broadly. (research §1.)
```

## Implementation Blueprint

### Data models and structure

None — documentation only. The edits consume the landed code's behavior + the landed tests (cited
file:line in research §2/§3) and restate them in maintainer-facing prose.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — confirm the two anchors are present + unique + the named tests exist (no mutation).
  - RUN (from /home/dustin/projects/voice-typing):
      test -f tests/ACCEPTANCE.md && echo "ok: ACCEPTANCE.md present" || echo "PREFLIGHT FAIL"
      # Edit 1 anchor — must be present exactly once:
      grep -c "≤10 s bounded teardown" tests/ACCEPTANCE.md            # expect 1
      # Edit 2 anchor — the file's last line (append after it):
      tail -1 tests/ACCEPTANCE.md | grep -q "silence on the real mic)\." && echo "ok: append anchor present" || echo "note: tail differs — re-read end of file"
      # Heading set (capture BEFORE; L1 compares AFTER):
      grep -nE '^#{1,3} ' tests/ACCEPTANCE.md > /tmp/accept_headings_before.txt
      # Named tests MUST exist (Edit 2 truthfulness):
      grep -q "def test_concurrent_request_shutdown_and_shutdown_only_one_stop" tests/test_daemon.py && echo "ok: sigterm test" || echo "PREFLIGHT FAIL: missing sigterm test"
      grep -q "def test_concurrent_stop_calls_share_one_teardown" tests/test_recorder_host.py && echo "ok: host single-flight test" || echo "PREFLIGHT FAIL"
      for t in test_disarm_resets_phase_to_idle test_toggle_off_resets_phase_to_idle test_auto_stop_resets_phase_to_idle test_run_loop_detects_dead_host_and_transitions_to_unloaded test_load_host_respawns_after_dead_child test_status_reports_unloaded_after_child_death; do
        grep -q "def $t" tests/test_daemon.py && echo "ok: $t" || echo "PREFLIGHT FAIL: missing $t"
      done
      # README.md must NOT be touched by this task:
      test -f README.md && echo "note: README.md exists (S1 owns it; do NOT edit)" || true
  - EXPECTED: ACCEPTANCE.md present; the `≤10 s` grep returns 1 (unique); append anchor present; ALL
    named tests found (8 "ok" lines); heading count recorded. If any test is missing, STOP — Edit 2
    would name a phantom test; reconcile against research §3 first.
  - DO NOT: edit anything yet, or touch any non-ACCEPTANCE.md file.

Task 1: EDIT 1 — fix the teardown budget in the T6 GPU residency bullet (item clause (a), Issue 1).
        Use the `edit` tool with the EXACT oldText/newText in "Edit 1 SOURCE" below.
  - FILE: tests/ACCEPTANCE.md
  - REGION: the T6 GPU residency bullet, ~L130 (`≤10 s bounded teardown` fragment).
  - MUST: replace `≤10 s bounded teardown` with the post-fix `≤5 s single-flight teardown` (per-call
    host.stop() join budget; the budget was reduced 10→5 by P1.M1.T2.S2 + single-flight by
    P1.M1.T1.S1/P1.M1.T2.S1).
  - MUST REMOVE: `≤10 s bounded teardown` (the stale pre-fix figure).

Task 2: EDIT 2 — append the regression-test-coverage bullet (item clauses (b)+(c), Issues 1/2/3).
        Use the `edit` tool with the EXACT oldText/newText in "Edit 2 SOURCE" below.
  - FILE: tests/ACCEPTANCE.md
  - REGION: append a NEW bullet after the Cleanup bullet (the last bullet in "Notes on the method", ~L146).
  - MUST name (verbatim, all pre-verified to exist):
      * test_concurrent_request_shutdown_and_shutdown_only_one_stop (tests/test_daemon.py) — the SIGTERM
        path; state it was previously UNCOVERED (only voicectl quit was tested) — the gap that let
        Issue 1 slip through.
      * test_concurrent_stop_calls_share_one_teardown (tests/test_recorder_host.py) — host single-flight.
      * test_disarm_resets_phase_to_idle / test_toggle_off_resets_phase_to_idle /
        test_auto_stop_resets_phase_to_idle (Issue 2).
      * test_run_loop_detects_dead_host_and_transitions_to_unloaded / test_load_host_respawns_after_dead_child /
        test_status_reports_unloaded_after_child_death (Issue 3).
  - DO NOT: invent or paraphrase a test name; touch the Criteria table or Evidence block; add a heading.

Task 3: VALIDATE — run L1 (markdown validity + heading-unchanged) + L2 (accuracy + test-existence grep)
        + L3 (scope guard) + L4 (new-phrase presence + stale-claim removal). Iterate until all pass.
        No git commit unless the orchestrator directs it. If asked: message
        "P1.M4.T1.S2: tests/ACCEPTANCE.md teardown-budget fix + SIGTERM/Issue2/Issue3 test-coverage note".
```

#### Edit 1 SOURCE — teardown-budget fragment (write verbatim via `edit`)

oldText (current ACCEPTANCE.md, the T6 bullet ~L129-130; includes the `≤` glyph and 2-space indent):

```
  literal "7 s" under-budgets the 1 s watchdog tick + 5 s threshold + ≤10 s bounded teardown + driver
  accounting lag. T6(d-gone) relies on the daemon terminating the recorder-host CHILD PROCESS
```

newText (≤10 s → ≤5 s single-flight; the surrounding `literal "7 s" …` and `T6(d-gone) relies …` lines
are kept verbatim as the unique anchor, only the budget token changes):

```
  literal "7 s" under-budgets the 1 s watchdog tick + 5 s threshold + ≤5 s single-flight teardown + driver
  accounting lag. T6(d-gone) relies on the daemon terminating the recorder-host CHILD PROCESS
```

> The ONLY token change is `≤10 s bounded teardown` → `≤5 s single-flight teardown`. The two flanking
> lines are included solely to make `oldText` unique + byte-exact (the `≤10 s` fragment alone is unique,
> but including the flanking lines protects against a future similar phrase). If the preflight shows the
> flanking text differs, narrow `oldText` to just `+ ≤10 s bounded teardown +` → `+ ≤5 s single-flight teardown +`.

#### Edit 2 SOURCE — regression-test-coverage bullet (write verbatim via `edit`)

oldText (current ACCEPTANCE.md, the Cleanup bullet's final two lines — the file's last lines, ~L145-146):

```
  Ctrl-C (`SIGINT`). The default audio source is never touched (this test listens to ambient room
  silence on the real mic).
```

newText (the same two lines UNCHANGED, then a blank line, then the NEW bullet appended):

```
  Ctrl-C (`SIGINT`). The default audio source is never touched (this test listens to ambient room
  silence on the real mic).

- **Regression-test coverage (bugfix Issues 1–3).** The SIGTERM/systemctl-stop teardown path now has
  explicit automated coverage — `test_concurrent_request_shutdown_and_shutdown_only_one_stop`
  (`tests/test_daemon.py`) drives `request_shutdown()` (the signal-handler thread) and `shutdown()`
  (the main-thread `finally`) **concurrently** against a live armed daemon and asserts that exactly
  ONE `host.stop()` runs and the teardown stays bounded in time (the daemon single-flight of
  P1.M1.T2.S1 + the ≤5 s per-call budget of P1.M1.T2.S2; the recorder-host-level single-flight is
  covered by `test_concurrent_stop_calls_share_one_teardown` in `tests/test_recorder_host.py`).
  Previously only the `voicectl quit` path was exercised — which is exactly why Issue 1 (the SIGTERM
  double-teardown hang → SIGKILL + `Failed with result 'timeout'`) slipped through. Issue 2 (`phase`
  stuck `listening`/`speaking` after disarm) and Issue 3 (silent recorder-host child crash leaving
  `listening: on`) likewise now have regression tests in `tests/test_daemon.py`:
  `test_disarm_resets_phase_to_idle`, `test_toggle_off_resets_phase_to_idle`, and
  `test_auto_stop_resets_phase_to_idle` (Issue 2); `test_run_loop_detects_dead_host_and_transitions_to_unloaded`,
  `test_load_host_respawns_after_dead_child`, and `test_status_reports_unloaded_after_child_death`
  (Issue 3).
```

> The new bullet uses the section's existing style: bold lead term, 2-space hanging indent, ~76-col
> hand-wrap, single-backtick inline code, em dash. All eight test names are pre-verified to EXIST
> (research §3 / Task 0 preflight). Do NOT reflow the Cleanup bullet — it is reproduced verbatim as the
> append anchor.

### Implementation Patterns & Key Details

```python
# PATTERN: documentation edits consume the LANDED code + LANDED tests — cite real names/numbers, never invent.
#   Edit 1: "≤5 s single-flight teardown" <- recorder_host.py:87 _STOP_JOIN_TIMEOUT_S=5.0 +
#           daemon.py:1338 _bounded_shutdown(timeout=5.0) + recorder_host.py:140/:265 _stop_lock.
#           (was "≤10 s" — the pre-P1.M1.T2.S2 default.)
#   Edit 2: every test name <- a real `def test_…` in tests/test_daemon.py / tests/test_recorder_host.py
#           (verified via grep; see research §3 for file:line).

# GOTCHA: the oldText must match byte-for-byte incl. the ≤ glyph and the 2-space continuation indent.
#   The preflight greps confirm each anchor before editing; if a flank line shifted, narrow oldText.

# GOTCHA: preserve the ~76-col manual soft-wrap + 2-space bullet indent. Wrap new prose at ~76 cols,
#   matching the surrounding Notes bullets. Do NOT collapse a bullet onto one line or reflow the section.

# GOTCHA: do NOT change headings or touch the Criteria table / Evidence block. Edits are prose WITHIN
#   the Notes section only. L1 asserts the heading set is byte-identical before/after.

# GOTCHA: ONLY name tests that EXIST. The preflight (Task 0) + L2 grep enforce this — a phantom test
#   name would make the acceptance doc false. Copy the names verbatim from Edit 2 SOURCE.
```

### Integration Points

```yaml
tests/ACCEPTANCE.md (the ONLY file modified):
  - Edit 1: T6 GPU residency bullet, ~L130 (≤10 s → ≤5 s single-flight)
  - Edit 2: append new "Regression-test coverage (bugfix Issues 1–3)" bullet after the Cleanup bullet, ~L146
DO NOT TOUCH:
  - "README.md"            # sibling P1.M4.T1.S1 owns it (parallel; disjoint file)
  - any voice_typing/*.py  # fixes + tests are LANDED; this task only documents them
  - any tests/*.py         # the tests are LANDED; this task only NAMES them in prose
  - PRD.md / tasks.json / prd_snapshot.md / .gitignore / config.toml / pyproject.toml / uv.lock
DEPENDENCIES: none (pure markdown; no tooling beyond bash + the edit tool).
```

## Validation Loop

> Documentation has no pytest. Gates = markdown validity + factual-accuracy grep + test-existence grep +
> scope guard + new-phrase presence. Run via bash from the repo root (zsh aliases bare python).

### Level 1: Markdown validity + structural integrity

```bash
cd /home/dustin/projects/voice-typing
# 1a — fence count is EVEN (no unclosed ``` block).
FENCES=$(grep -c '```' tests/ACCEPTANCE.md); echo "fences=$FENCES"; [ $((FENCES % 2)) -eq 0 ] && echo "L1 ok: fences balanced" || echo "L1 FAIL: unbalanced fences"
# 1b — heading set UNCHANGED (no heading text/level added/removed/renamed).
grep -nE '^#{1,3} ' tests/ACCEPTANCE.md > /tmp/accept_headings_after.txt
diff -u /tmp/accept_headings_before.txt /tmp/accept_headings_after.txt && echo "L1 ok: headings unchanged" || echo "L1 FAIL: heading set changed"
# 1c — the ≤ and — glyphs survived (UTF-8 intact in edited regions).
grep -q "≤" tests/ACCEPTANCE.md && grep -q "—" tests/ACCEPTANCE.md && echo "L1 ok: special glyphs present"
# Expected: fences balanced; headings diff EMPTY; glyphs present.
```

### Level 2: Factual accuracy + test existence (the new claims are TRUE)

```bash
cd /home/dustin/projects/voice-typing
# Edit 1 must be true: the ≤5s budget + single-flight are in the LANDED code.
grep -q "_STOP_JOIN_TIMEOUT_S: float = 5.0" voice_typing/recorder_host.py && echo "L2 ok: 5.0s join budget" || echo "L2 FAIL"
grep -q "_bounded_shutdown(self, timeout: float = 5.0)" voice_typing/daemon.py && echo "L2 ok: _bounded_shutdown 5.0 default" || echo "L2 FAIL"
grep -q "_stop_lock" voice_typing/recorder_host.py && echo "L2 ok: single-flight lock" || echo "L2 FAIL"
# Edit 2 must be true: EVERY named test EXISTS (no phantom coverage claims).
grep -q "def test_concurrent_request_shutdown_and_shutdown_only_one_stop" tests/test_daemon.py && echo "L2 ok: sigterm test exists" || echo "L2 FAIL"
grep -q "def test_concurrent_stop_calls_share_one_teardown" tests/test_recorder_host.py && echo "L2 ok: host single-flight test exists" || echo "L2 FAIL"
for t in test_disarm_resets_phase_to_idle test_toggle_off_resets_phase_to_idle test_auto_stop_resets_phase_to_idle test_run_loop_detects_dead_host_and_transitions_to_unloaded test_load_host_respawns_after_dead_child test_status_reports_unloaded_after_child_death; do
  grep -q "def $t" tests/test_daemon.py && echo "L2 ok: $t exists" || echo "L2 FAIL: missing $t"
done
# Expected: all "L2 ok" lines (3 code facts + 8 test-existence checks). If any test is missing, the doc
#   claims coverage that doesn't exist — REMOVE that name from Edit 2 (do NOT edit the test files).
```

### Level 3: Scope guard — ONLY tests/ACCEPTANCE.md changed

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: ONLY " M tests/ACCEPTANCE.md". Any other file (esp. README.md, any .py, config.toml,
#   PRD.md, tasks.json) is a SCOPE VIOLATION.
git diff --name-only
# Expected: tests/ACCEPTANCE.md
# Explicitly confirm the sibling-owned file was NOT touched:
git diff --quiet README.md 2>/dev/null && echo "L3 ok: README.md untouched (S1 owns it)" || echo "L3 FAIL: README.md modified"
```

### Level 4: New-phrase presence + stale-claim removal

```bash
cd /home/dustin/projects/voice-typing
# Edit 1 — new claim present; stale claim gone.
grep -q "≤5 s single-flight teardown" tests/ACCEPTANCE.md && echo "L4 ok: '≤5 s single-flight teardown' present" || echo "L4 FAIL"
grep -q "≤10 s bounded teardown" tests/ACCEPTANCE.md && echo "L4 FAIL: stale '≤10 s bounded teardown' still present" || echo "L4 ok: stale '≤10 s' removed"
# Edit 2 — the regression-test-coverage bullet + the gap framing present.
grep -q "Regression-test coverage (bugfix Issues 1–3)" tests/ACCEPTANCE.md && echo "L4 ok: coverage bullet present" || echo "L4 FAIL"
grep -q "test_concurrent_request_shutdown_and_shutdown_only_one_stop" tests/ACCEPTANCE.md && echo "L4 ok: sigterm test named" || echo "L4 FAIL"
grep -qE "only the .voicectl quit. path was exercised|previously only the .voicectl quit." tests/ACCEPTANCE.md && echo "L4 ok: gap framing present" || echo "L4 FAIL"
grep -q "test_run_loop_detects_dead_host_and_transitions_to_unloaded" tests/ACCEPTANCE.md && echo "L4 ok: Issue 3 test named" || echo "L4 FAIL"
# Expected: all "L4 ok" lines; the stale '≤10 s bounded teardown' is gone.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: ACCEPTANCE.md parses; fence count even; heading set byte-identical; glyphs survived.
- [ ] L2: 3 code-fact greps pass (5.0s join, `_bounded_shutdown` 5.0 default, `_stop_lock`) + all 8 named tests verified present.
- [ ] L3: `git status --short` shows ONLY ` M tests/ACCEPTANCE.md`; `README.md` untouched.
- [ ] L4: `≤5 s single-flight teardown` present; `≤10 s bounded teardown` removed; coverage bullet + sigterm/gap/Issue-3 phrases present.

### Feature Validation
- [ ] Edit 1: the T6 bullet's teardown budget now reads ≤5 s single-flight (matches the LANDED 5.0s budget + single-flight).
- [ ] Edit 2: the new bullet names the SIGTERM-path test AND explains the prior gap (only `voicectl quit` covered → why Issue 1 slipped through).
- [ ] Edit 2: the new bullet names the Issue 2 (phase-reset) and Issue 3 (child-crash) regression tests.
- [ ] No claim in the new prose names a test that does not exist (L2 enforces).

### Code Quality Validation
- [ ] Edited prose follows the existing ~76-col manual soft-wrap + 2-space bullet indent (no reflow of unrelated lines).
- [ ] Bold lead term, single-backtick inline code, em dashes/`≤` consistent with the surrounding Notes bullets.
- [ ] No heading text/level changed; no new heading; Criteria table + Evidence block untouched.
- [ ] Tone matches the surrounding maintainer-facing prose (factual).

### Documentation & Deployment
- [ ] The stale `≤10 s` teardown budget is gone; the SIGTERM/Issue-2/Issue-3 coverage is now recorded.
- [ ] `README.md` left for sibling task P1.M4.T1.S1 (no collision); the two docs stay consistent (same 5.0s / single-flight facts).

---

## Anti-Patterns to Avoid

- ❌ Don't edit any file other than `tests/ACCEPTANCE.md` — especially not `README.md` (sibling P1.M4.T1.S1 owns it) or any `.py`/`tests/*.py` file (fixes + tests are LANDED; you only document them) (Critical #1).
- ❌ Don't keep `≤10 s bounded teardown` — it is the stale pre-fix figure this task corrects; replace it with `≤5 s single-flight teardown` (Critical #6, Gotcha #7).
- ❌ Don't name a test that doesn't exist — every name in Edit 2 must pass the L2 existence grep; copy the pre-verified names verbatim from Edit 2 SOURCE (Critical #3).
- ❌ Don't change any heading or touch the Criteria table / Evidence block — edits are prose WITHIN the Notes section only (Critical #5).
- ❌ Don't reflow the Notes section or collapse bullets onto one line — preserve the ~76-col wrap + 2-space indent; edit only the one fragment + append the one bullet (Critical #4).
- ❌ Don't invent numbers — cite the real budget (`≤5 s` ← `_STOP_JOIN_TIMEOUT_S=5.0` + `_bounded_shutdown(timeout=5.0)`); do not add `TimeoutStopSec=15` to the T6 bullet unless natural (keep Edit 1 tight) (Critical #6).
- ❌ Don't guess the `oldText` — run the Task 0 preflight greps to confirm each anchor is present + unique byte-for-byte (incl. `≤`/`—`/indent) before editing (Critical #2).

---

## Confidence Score

**9.5/10** for one-pass success. This is two surgical prose edits to one Markdown file, each with verbatim
`oldText`/`newText` for the `edit` tool. Every factual claim is VERIFIED against the LANDED code with
file:line (research §2: `_STOP_JOIN_TIMEOUT_S=5.0`, `_bounded_shutdown(timeout=5.0)`, `_stop_lock`,
`TimeoutStopSec=15`), and EVERY test named in Edit 2 is VERIFIED present via `grep` (research §3, with
`def test_…` line numbers) — enforced again by the Task 0 preflight + L2. The sibling-task boundary
(`README.md` = P1.M4.T1.S1) is explicit and the scope guard (L3) enforces it; the two edits compose
with S1's README edits on a disjoint file. The only residual risk (the −0.5) is byte-exact `oldText`
matching ACCEPTANCE.md's current text — mitigated by the Task 0 preflight greps that confirm each anchor
substring is present + unique before editing; if an anchor shifts, narrowing `oldText` to the minimal
unique fragment (e.g. `+ ≤10 s bounded teardown +`) is a trivial, bounded fix gated by the L4 checks.
