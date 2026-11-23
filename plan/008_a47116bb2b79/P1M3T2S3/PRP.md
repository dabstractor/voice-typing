# PRP — P1.M3.T2.S3: G2 gate — full fake-target trace matrix green + evidence record (PRD §4.2sexies R.7)

## Goal

**Feature Goal**: Execute PRD §4.2sexies R.7's **G2 gate** — "controller, fake target" — as ONE
addressable, deterministic pytest module running the **complete 13-trace matrix** (append; first-word
change; identical update and final; retraction; Unicode; rejected/lost final; repeated cancel;
timeout-after-apply; held key; out-of-order results; stop + immediate re-arm; child death; focus
change mid-operation) against S1+S2's `BulkController`, enforcing R.7's **six assertion families on
every trace** (exact text/caret, bounded queue, ZERO legacy-backend calls, no duplicates, no extra
writes, no post-takeover mutations), then record the pass as the **gate artifact**
(`architecture/g2_gate_record.md`) — with the law stamped in: **G2 is necessary, NEVER sufficient; a
G2 pass never marks a field row verified.**

**Deliverable** (TWO new files + ONE conditional modify; nothing else):
1. `tests/test_g2_bulk_gate.py` — NEW: the gate module. A field-modeling `G2FakeTarget` (text/caret/
   owned-range/edit-count/op-log/thread-ids — §1 of the research note), the 13 traces (§2), the six
   families woven into every trace + a machine-checked `test_g2_gate_summary` (§2b), and a
   legacy-backend sentinel fixture (monkeypatched `typing_backends` recorders that FAIL on any call).
2. `plan/008_a47116bb2b79/architecture/g2_gate_record.md` — NEW: the gate record (tabular, mirrors
   `d3_defects_g1_baseline.md`; matrix table + live pass counts + the six families + the
   necessary-never-sufficient caveat verbatim).
3. `voice_typing/bulk_controller.py` — **CONDITIONAL minimal modify**: add the ~30-line `cancel()`
   entry (research §3) ONLY if the landed S1+S2 class lacks it (preflight `grep -n "def cancel"`).

**Success Definition**:
- (a) `timeout 60 .venv/bin/python -m pytest tests/test_g2_bulk_gate.py -v` → all pass, ≥13 trace
  tests + summary, deterministic (Event-bounded fakes, `op_deadline=0.02`, `drain()`-driven; ×3
  identical counts).
- (b) Every trace asserts ALL applicable families: exact `fake.text`/`fake.caret` (adjacent user text
  survives byte-exact); `edit_count` equals the event-count-law number (insertion=1, correction=1,
  zero-diff=0); the op log shows no duplicate mutations / no post-stop calls;
  `len(ctrl._dq) <= queue_size` throughout; legacy sentinels recorded ZERO calls.
- (c) The repeated-cancel trace is GREEN through the controller seam (pending → ONE `target.cancel`
  APPLIED, text restored, still `is_active()`; repeat → no target call, edit flat).
- (d) The record cites LIVE counts: `test_g2_bulk_gate.py` + `test_bulk_controller.py` (S1+S2 suites
  re-run green, untouched) + `test_bulk_delivery.py` + `test_zero_diff_rewind.py` (3/0) +
  `test_streaming_commit.py` showing NO NEW failures vs the G1 baseline (22 passed / **10 failed**).
- (e) `git status --short` shows exactly: the two new files + (if the gap-fill fired) the one
  modified controller. No S1/S2 test edits, no `bulk_delivery.py`/streaming/typing_backends/daemon/
  config/feedback changes.

## User Persona

**Target User**: the graduation path — P1.M4.T5 (G3 real-field matrix, which requires a G2 pass as
its precondition), P1.M7.T1 (G6 assessment, which cites the gate record), and the human reviewer who
needs one artifact proving the controller's determinism under every R.7 trace before ANY real field
is touched.

**Use Case**: Before an adapter is pointed at a real editor, run one command — the G2 module — and
get a green matrix proving the controller alone: appends/corrects/retracts exactly, never duplicates,
never over-writes, never calls the legacy backends, survives every failure trace without post-takeover
mutations.

**Pain Points Addressed**: The R.2 incident class (dropped-insertion desync, duplicate finals,
post-stop writes) must be provably impossible at the controller level BEFORE field risk exists; and
"we ran some unit tests" is not a gate — R.7 demands the enumerated matrix with the enumerated
assertions, recorded.

## Why

- **R.7 mandates G2 as the controller-level gate** with an enumerated trace list and assertion
  families; P1.M4.T5's G3 rows are gated on it. G2's verdict must be a durable artifact, not a log.
- **S1/S2 unit tests prove laws individually; the gate proves the MATRIX holistically** — the six
  families are cross-cutting invariants (exact text/caret, edit counts, legacy sentinels) their unit
  fakes don't model. The gate fake models the FIELD (the R.2 GTK-probe discipline: text, caret,
  edit-count), which is what "assert exact text/caret" means.
- **The trace matrix is the acceptance vocabulary**: every later gate (G3/G5/G6) references these
  trace names; making the module machine-check its own coverage (summary test) keeps the record
  honest.
- Pure stdlib threads — hermetic, seconds-fast, CI-safe; no Wayland/subprocess/CUDA.

## What

Create `tests/test_g2_bulk_gate.py` per research §1-§2b EXACTLY (the fake model, the 13-trace drive/
assert table, the six families, the sentinel fixture, the summary test); conditionally add the
minimal `cancel()` to `BulkController` per research §3 (uncertain ⇒ refuse, nothing-pending ⇒ no
edit, ONE target op, stays armed, S2's deadline/no-retry honored, NO len(tail)-1 compensation — that
is legacy-only per R.5); write `architecture/g2_gate_record.md` per research §4 with the
necessary-never-sufficient caveat in bold.

### Success Criteria

- [ ] 13/13 traces green as named tests; summary test machine-checks coverage.
- [ ] Repeated cancel: 1st → ONE `target.cancel` APPLIED + pending discarded + `is_active()` True; 2nd → zero target calls, `edit_count` flat.
- [ ] Timeout-after-apply: ONE call, stop `"op-deadline"`, late APPLIED discarded (revision/`confirmed_visible()` unchanged, `late_results_discarded +1`).
- [ ] Held key + focus change mid-op: stop `"refused"`, `on_stopped` once, no retry, queued op never dispatched, `edit_count` frozen after.
- [ ] Identical update AND final: zero-diff partial = ZERO target calls; identical final = finalize once → UNCHANGED, edit 0, no duplicate text.
- [ ] Rejected/lost final: NO finalize; tail preserved; boundary closed; queue empties.
- [ ] Unicode spans byte/codepoint-exact (text + caret char-index).
- [ ] Legacy sentinels: zero `type_text`/`press_backspace`/`make_backend`/backend calls across every trace.
- [ ] Gate record written with live counts + the caveat; only the allowed files in git status.

## All Needed Context

### Context Completeness Check

_Pass._ The research note pins: what exists at start (§0 — S1/S2 APIs quoted, the landed contracts,
the G1 baseline numbers, the cancel GAP), the gate fake's full model (§1), the 13-trace drive/assert
table (§2), the six families with concrete mechanisms (§2b), the cancel gap-fill design (§3), the
deliverables + record format (§4), tooling/boundaries (§5). A developer with no prior repo knowledge
implements from it + the two sibling PRPs.

### Documentation & References

```yaml
# MUST READ — this task's spec: fake model, trace table, families, cancel design, record format
- docfile: plan/008_a47116bb2b79/P1M3T2S3/research/g2_gate_design.md
  section: "ALL load-bearing (§0-§5)."

# MUST READ — the class under test (CONTRACT; assume landed EXACTLY as specified)
- file: plan/008_a47116bb2b79/P1M3T2S1/PRP.md
  why: "BulkController's API/invariants/seams (acquire/start/stop/arm/on_partial/on_final/
        on_final_dropped/_process_next/drain/stats; zero-diff skip; overflow STOP; mutation-time
        re-checks; on_stopped seam) + its _FakeTarget style the gate fake extends."
  critical: "bulk_controller.py may not exist yet when this task starts (S1 was 'Implementing' at
             research time) → the gate module is TDD RED until S1+S2 land. NEVER vendor the class."
- file: plan/008_a47116bb2b79/P1M3T2S2/PRP.md
  why: "The failure layer the gate exercises: op_deadline kwarg, _dispatch_epoch give-up guard, stop
        reasons (queue-overflow|op-deadline|refused|unknown|target-error), on_stopped-once,
        latest_recognized/accepted_final/confirmed_visible, retention, extended stats(). Its §3 test
        matrix overlaps traces 8-13 — the gate RE-RUNS them holistically, never edits them."

# MUST READ — the LANDED contracts (import; never duplicate)
- file: voice_typing/bulk_delivery.py
  why: "ShowResult/AcquireResult/DeliveryTarget/rendered_equal — the branch surface. Landed at
        2a0032e; read-only."

# MUST READ — the separation law + baseline + record format
- docfile: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  why: "§3: no type_text/press_backspace/make_backend/StreamingOutput — encode as the sentinel
        fixture. §2: the daemon-side cancel intercept is P1.M6.T2.S1's (why the controller-level
        cancel here is minimal + why NO len(tail)-1 compensation)."
- docfile: plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md
  why: "The no-new-failures reference (test_streaming_commit.py 22/10) + the tabular record style
        g2_gate_record.md mirrors."

# MUST READ — the spec source
- docfile: PRD.md
  why: "§4.2sexies R.7 (the G2 bullet — the trace list + assertion families + 'Necessary, never
        sufficient'), R.1 (event-count law), R.3 (show/finalize/leave/cancel semantics), R.5
        (ordering/takeover/failure; the cancel-compensation prohibition)."
  critical: "READ-ONLY. Quote R.7's G2 bullet + 'Necessary, never sufficient' in the gate module
             docstring and the record."

# STYLE REFS (pattern only)
- file: tests/test_bulk_delivery.py
  why: "Plain-function style, protocol-conforming fakes, purity guards, sys.path bootstrap."
- file: tests/test_zero_diff_rewind.py
  why: "Characterization style (3/3 at baseline); re-run untouched."
```

### Current Codebase tree (excerpt)

```bash
voice_typing/
  bulk_delivery.py       # LANDED contracts (2a0032e) — read-only
  bulk_controller.py     # ← S1+S2 (landing per their PRPs) — CONDITIONAL +cancel() (this task)
  typing_backends.py streaming.py daemon.py   # FORBIDDEN to import into gate/controller (d2 §3)
tests/
  test_bulk_controller.py# S1+S2's — re-run green, NEVER edited
  test_bulk_delivery.py test_zero_diff_rewind.py test_streaming_commit.py  # re-run / baseline
  test_g2_bulk_gate.py   # ← CREATE (this task) — THE gate module
plan/008_a47116bb2b79/architecture/
  d3_defects_g1_baseline.md   # record style + baseline numbers
  g2_gate_record.md           # ← CREATE (this task) — the gate artifact
```

### Desired Codebase tree with files to be added

```bash
tests/test_g2_bulk_gate.py                       # NEW: 13 traces + six families + summary + sentinels
plan/008_a47116bb2b79/architecture/g2_gate_record.md  # NEW: the G2 gate record (the OUTPUT artifact)
voice_typing/bulk_controller.py                  # CONDITIONAL: minimal cancel() ONLY if preflight lacks it
```

### Known Gotchas

```python
# CRITICAL #1 — TDD RED UNTIL S1+S2 LAND. Verified at research time: bulk_controller.py does NOT
#   exist yet. Preflight (Task 1) must confirm BOTH voice_typing/bulk_controller.py AND
#   tests/test_bulk_controller.py exist and pass before writing the gate. If missing: STOP and report
#   (do NOT vendor the class — S1's PRP Critical #1 discipline).
# CRITICAL #2 — THE CANCEL GAP-FILL IS PREFLIGHT-GATED. grep -n "def cancel" bulk_controller.py:
#   absent → add research §3's ~30-line entry; present → use theirs, touch nothing. Either way the
#   repeated-cancel trace asserts the SEMANTICS (pending→ONE op+still-active; repeat→no op), not a name.
# CRITICAL #3 — NO len(tail)-1 COMPENSATION ANYWHERE. R.5: bulk cancel performs NO physical-character
#   compensation — that backspace math is the legacy path (daemon.cancel, P1.M6.T2.S1's intercept).
#   The gate's cancel asserts ZERO press_backspace (the sentinel fixture enforces it globally).
# CRITICAL #4 — EXACT TEXT/CART MEANS THE FAKE MODELS THE FIELD. show/finalize replace EXACTLY the
#   owned range (R.3); adjacent user text (seed prefix/suffix in traces) survives byte-exact; caret =
#   owned_end after APPLIED; edit_count increments ONLY on real mutations (event-count law).
# CRITICAL #5 — LATE APPLIED IS DISCARDED, NOT "NOT HAPPENED". In timeout-after-apply the FAKE's text
#   may show the edit (it applied!) — assert the CONTROLLER's view froze (revision unchanged,
#   confirmed_visible unchanged, late_results_discarded +1). Do not "fix" the fake to un-apply.
# CRITICAL #6 — NEVER EDIT S1/S2's TESTS. The gate is a NEW file. If a sibling test contradicts the
#   matrix, report — do not reconcile by editing theirs.
# CRITICAL #7 — ZERO LEGACY CALLS IS BEHAVIORAL, NOT JUST SOURCE-SCAN. The sentinel fixture patches
#   typing_backends' attrs with recorders that fail the test; S1's source-scan purity guards remain
#   the static layer. Both must pass.
# CRITICAL #8 — BOUNDED EVIDENCE (AGENTS.md Rule 3). No /tmp dumps; the record quotes summary lines
#   only ("N passed in Xs", fail counts); fixtures live in tests/ under version control.
# CRITICAL #9 — THE RECORD MUST CARRY THE CAVEAT VERBATIM: "G2 is necessary, NEVER sufficient — a G2
#   pass never marks a field row verified" + "a passing transport probe NEVER flips any R.2 row to
#   'passed'". G3 (P1.M4.T5) is the real-field gate.
# GOTCHA #10 — .venv/bin/python (zsh aliases); timeout 60 inner + bash-tool outer; mypy NOT installed;
#   ruff optional. The suite is pure-stdlib threads — seconds.
# GOTCHA #11 — do NOT "fix" the 10 pre-existing test_streaming_commit.py reds (G1 baseline); assert
#   NO NEW failures only.
# GOTCHA #12 — DETERMINISM: Event-bounded fakes (wait ≤1.0s), op_deadline=0.02, drain()-driven; the
#   only real-thread use is S2's runner path (Event-gated). Re-run gate ×3 → identical counts.
```

## Implementation Blueprint

### Data models and structure

No production data model. The gate fake (§1) + tests. Conditional controller addition per §3:
`cancel(self, *, gen=None) -> bool` (refuse-if-uncertain; purge pending under `_cond`; ONE
`target.cancel()` through the op-runner path so the deadline applies; APPLIED→stay active;
REFUSED/UNKNOWN→S2's stop; no retry).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT (no mutation)
  - RUN: ls voice_typing/bulk_controller.py tests/test_bulk_controller.py
         grep -n "def cancel\|def drain\|def _process_next\|op_deadline\|def stats" voice_typing/bulk_controller.py
         timeout 60 .venv/bin/python -m pytest tests/test_bulk_controller.py tests/test_bulk_delivery.py -q | tail -2
  - EXPECTED: S1+S2 landed + green (record the pass count — the record's S-suite line). If NOT
    landed: STOP, report (Critical #1). Record whether `def cancel` exists (Task 2's gate).

Task 2: CONDITIONAL — add the minimal cancel() to voice_typing/bulk_controller.py
  - ONLY if preflight shows it absent: implement research §3 verbatim (docstring anchored to the
    R.5/R.3 quotes; NO compensation; stays active on success; S2's stop path on REFUSED/UNKNOWN).
  - DO NOT: touch anything else in the file; add config; touch daemon/streaming/typing_backends.

Task 3: CREATE tests/test_g2_bulk_gate.py
  - Module docstring: quote R.7's G2 bullet + "Necessary, never sufficient". G2FakeTarget per §1;
    the 13 traces per §2 (one named test each: test_trace_01_append … test_trace_13_focus_change);
    the sentinel fixture (monkeypatch type_text/press_backspace/make_backend + backend classes);
    families asserted per trace per §2b; test_g2_gate_summary asserts the frozen 13-name coverage.
  - DO NOT: edit sibling tests; use bare sleeps; normalize Unicode spans; un-apply late fakes (C5).

Task 4: RUN the gate + write plan/008_a47116bb2b79/architecture/g2_gate_record.md
  - Run: gate module ×3 (determinism), then test_bulk_controller.py, test_bulk_delivery.py,
    test_zero_diff_rewind.py, test_streaming_commit.py (baseline compare). Record per research §4:
    date/HEAD, matrix table, live counts, six families confirmed, cancel gap-fill note, the verbatim
    caveat. Then the Validation Loop below. No commit unless directed.
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the sentinel fixture (family 3). Module scope so EVERY trace runs under it:
@pytest.fixture(autouse=True)
def _no_legacy_backend(monkeypatch):
    import voice_typing.typing_backends as tb
    calls = []
    for name in ("type_text", "press_backspace", "make_backend"):
        monkeypatch.setattr(tb, name, lambda *a, _n=name, **k: calls.append(_n) or (_ for _ in ()).throw(
            AssertionError(f"legacy backend {_n} reached in bulk mode")))
    return calls   # every trace asserts not calls

# PATTERN 2 — the fake's owned-range replacement (family 1/4/5). show/finalize:
#   new_text = text[:owned_start] + span + text[owned_end:]   # ONLY our range changes
#   owned = (owned_start, owned_start + len(span)); caret = owned_end; edit_count += 1
#   finalize: rendered_equal(current_owned_text, span) -> ShowResult.UNCHANGED (edit_count += 0)

# PATTERN 3 — timeout-after-apply (family 5/6). Gate the fake's show on an Event; ctl op_deadline=0.02;
#   drain fires the give-up; assert stop "op-deadline" + ONE op in the log; gate.set(); op completes;
#   assert stats()["late_results_discarded"] == 1 and ctl.confirmed_visible() UNCHANGED — while the
#   fake's text MAY show the edit (Critical #5: discarded ≠ not-happened).

# PATTERN 4 — repeated cancel. ctl.arm(1); on_partial(...); ctl.cancel() ->
#   assert one target.cancel op (APPLIED), fake.text restored to pre-utterance, ctl.is_active() True;
#   ctl.cancel() again -> NO new target op, fake.edit_count flat. If the runner wraps cancel: an
#   Event-bounded fake as in S2's tests.
```

### Integration Points

```yaml
CONSUMED (read-only): "voice_typing.bulk_delivery (taxonomy/protocol); BulkController per S1+S2 PRPs"
CONDITIONALLY MODIFIED: "voice_typing/bulk_controller.py — the minimal cancel() only (Task 2 gate)"
GATE ARTIFACT: "plan/008_a47116bb2b79/architecture/g2_gate_record.md (the OUTPUT)"
CONSUMERS (later, not here):
  - P1.M4.T5: "G3 real-field rows — gated on this G2 pass; never verifies a row from it"
  - P1.M6.T2.S1: "daemon cancel intercept calls ctl.cancel() (the seam this gate pins)"
  - P1.M7.T1: "G6 assessment cites the record"
DEPENDENCIES: "none new (stdlib: threading, collections, concurrent.futures via the controller)."
```

## Validation Loop

### Level 1: Syntax + purity

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m py_compile tests/test_g2_bulk_gate.py voice_typing/bulk_controller.py && echo "L1 OK"
grep -nE 'import (voice_typing\.)?(streaming|typing_backends|daemon)' tests/test_g2_bulk_gate.py  # typing_backends is imported ONLY for monkeypatching — allowed; streaming/daemon: no match expected
```

### Level 2: The gate run

```bash
timeout 60 .venv/bin/python -m pytest tests/test_g2_bulk_gate.py -v | tail -25   # all green, ≥14 tests
timeout 120 .venv/bin/python -m pytest tests/test_g2_bulk_gate.py tests/test_bulk_controller.py \
  tests/test_bulk_delivery.py tests/test_zero_diff_rewind.py -q | tail -2        # 0 failed
timeout 60 .venv/bin/python -m pytest tests/test_streaming_commit.py -q | tail -1 # 22 passed / 10 failed — NO NEW
```

### Level 3: Determinism + scope guard

```bash
for i in 1 2 3; do timeout 60 .venv/bin/python -m pytest tests/test_g2_bulk_gate.py -q | tail -1; done  # identical
git status --porcelain   # exactly: ?? tests/test_g2_bulk_gate.py ?? plan/.../g2_gate_record.md
                          # (+ M voice_typing/bulk_controller.py ONLY if Task 2 fired)
! git status --porcelain | grep -qE 'test_bulk_controller|test_bulk_delivery|bulk_delivery\.py|streaming|daemon|config|feedback' && echo "L3 ok"
```

### Level 4: Record integrity

```bash
grep -q "never sufficient" plan/008_a47116bb2b79/architecture/g2_gate_record.md && echo "caveat present"
grep -c "✅" plan/008_a47116bb2b79/architecture/g2_gate_record.md   # = 13 trace rows
test -f plan/008_a47116bb2b79/architecture/g2_gate_record.md && echo "record present"
```

## Final Validation Checklist

- [ ] L1-L4 green; gate ×3 deterministic; only the allowed files in git status.
- [ ] 13/13 traces green + summary machine-check; all six families asserted per trace.
- [ ] Repeated cancel green through the controller seam (gap-fill recorded as added-or-preexisting).
- [ ] Zero legacy-backend calls (sentinels) across every trace; no duplicates; no post-stop writes.
- [ ] Record written: live counts, matrix table, six families, the verbatim necessary-never-sufficient caveat.
- [ ] S1+S2 suites re-run green, untouched; test_streaming_commit.py at baseline (no new reds).

## Anti-Patterns to Avoid

- ❌ Don't vendor BulkController or edit S1/S2's tests — the gate is a NEW module; report conflicts.
- ❌ Don't mark any field row "verified" from a G2 pass — the record's caveat is mandatory (Critical #9).
- ❌ Don't add len(tail)-1 compensation or any press_backspace path — R.5 forbids it in bulk mode (Critical #3).
- ❌ Don't assert "late result never happened" — assert the controller DISCARDED it (Critical #5).
- ❌ Don't use bare sleeps / unbounded waits — Event-bounded, op_deadline=0.02 (Gotcha #12).
- ❌ Don't dump unbounded evidence — the record quotes summary lines only (Critical #8).
- ❌ Don't run mypy/bare python; timeout wrappers everywhere (Gotcha #10); don't "fix" the 10 baseline reds (Gotcha #11).

---

**Confidence Score: 8/10.** The matrix, fake model, assertion families, record format, and the cancel
gap-fill are fully pinned in the research note; the consumed APIs are quoted from the two sibling
PRPs; the gate is a pure-stdlib module over deterministic seams. −1: S1+S2 had NOT landed at research
time — their exact seam names (`drain`, `stats` keys, `confirmed_visible`) are contract-derived and
Task 1's preflight must reconcile any drift before writing (the same discipline S2 used against S1).
−1: the cancel gap-fill touches a parallel-owned file — bounded to ~30 lines, preflight-gated,
semantics-first tests (so a differently-named S1/S2 seam still passes).
