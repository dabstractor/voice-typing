# G2 gate record — controller, fake target (P1.M3.T2.S3 / PRD §4.2sexies R.7)

Date 2026-11-23, HEAD `55f801f` (main). Gate module: `tests/test_g2_bulk_gate.py` (NEW). Conditional
cancel gap-fill: `voice_typing/bulk_controller.py` (+1 method, see below). Evidence discipline
(AGENTS.md Rule 3 / R.7): this record quotes pytest summary lines only; all fixtures live in
`tests/` under version control; no `/tmp` dumps. Every run used
`timeout 60 .venv/bin/python -m pytest <file> -q` with a bash-tool backstop.

**G2 is necessary, NEVER sufficient — this pass marks NO field row verified; G3 (P1.M4.T5) is the
real-field gate and a G2 pass never flips any R.2 row to "passed".**

---

## The R.7 mandate (verbatim)

> "**G2 controller, fake target:** deterministic traces — append; first-word change; identical
> update and final; retraction; Unicode; rejected/lost final; repeated cancel; timeout-after-apply;
> held key; out-of-order results; stop + immediate re-arm; child death; focus change mid-operation.
> Assert exact text/caret, bounded queue, zero legacy-backend calls, no duplicates, no extra writes,
> no post-takeover mutations. **Necessary, never sufficient.**"

The module machine-checks its own coverage (`test_g2_gate_summary` asserts the frozen 13-name list),
so "13/13 green" below is enforced by pytest, not hand-claimed.

## The 13-trace matrix — verdicts

| # | R.7 trace | Test | Verdict | Families exercised |
|---|-----------|------|---------|--------------------|
| 1 | append | `test_trace_01_append` | ✅ | F1 F2 F3 F4 F5 F6 |
| 2 | first-word change | `test_trace_02_first_word_change` | ✅ | F1 F2 F3 F4 F5 F6 |
| 3 | identical update and final | `test_trace_03_identical_update_and_final` | ✅ | F1 F2 F3 F4 F5 F6 |
| 4 | retraction | `test_trace_04_retraction` | ✅ | F1 F2 F3 F4 F5 F6 |
| 5 | Unicode | `test_trace_05_unicode` | ✅ | F1 F2 F3 F4 F5 F6 |
| 6 | rejected/lost final | `test_trace_06_rejected_lost_final` | ✅ | F1 F2 F3 F4 F5 F6 |
| 7 | repeated cancel | `test_trace_07_repeated_cancel` | ✅ | F1 F2 F3 F4 F5 F6 |
| 8 | timeout-after-apply | `test_trace_08_timeout_after_apply` | ✅ | F2 F3 F5 F6 |
| 9 | held key | `test_trace_09_held_key` | ✅ | F1 F2 F3 F5 F6 |
| 10 | out-of-order results | `test_trace_10_out_of_order_results` | ✅ | F1 F2 F3 F4 F5 F6 |
| 11 | stop + immediate re-arm | `test_trace_11_stop_and_immediate_rearm` | ✅ | F1 F2 F3 F4 F5 F6 |
| 12 | child death | `test_trace_12_child_death` | ✅ | F1 F2 F3 F5 F6 |
| 13 | focus change mid-operation | `test_trace_13_focus_change_mid_operation` | ✅ | F1 F2 F3 F5 F6 |

Plus `test_g2_gate_summary` (coverage machine-check): 14 collected, **14 passed**. Determinism:
three consecutive runs → `14 passed in 0.07s` / `0.07s` / `0.08s` — identical counts.

Trace highlights (the semantics the gate pins):

- **7 repeated cancel** — 1st `ctl.cancel()`: exactly ONE `target.cancel` op, APPLIED, owned range
  removed (field back to pre-utterance bytes), `is_active()` still True; late partial for the
  canceled utterance discarded; 2nd cancel: nothing pending → ZERO target calls, `edit_count` flat.
- **8 timeout-after-apply** — ONE show begun, stop `"op-deadline"`, `on_stopped` exactly once; after
  the gate releases, the late APPLIED is discarded (`late_results_discarded == 1`): the FAKE's field
  shows the edit while the controller's view stays frozen (`expected_revision == 0`,
  `confirmed_visible() == ""`) — discarded ≠ not-happened.
- **10 out-of-order results** — the stale gen1 op applies in the field after the give-up, gen2's
  write replaces that owned range, and the controller consumes only gen2's result (revision 1, not
  2; `confirmed_visible() == "fresh"`; the field contains gen2's span exactly once).
- **9 / 13 refusals** — stop `"refused"`, `on_stopped` once, no retry (one op begun), the op queued
  behind never dispatched, `edit_count` frozen at the refusal, recognition retained.

## The six assertion families — how each is enforced

1. **Exact text/caret** — `G2FakeTarget` models the FIELD (text, owned char span, caret, visible
   edit count): show/finalize replace EXACTLY the owned range, so seeded user prefix/suffix text
   survives byte-exact; caret lands on the owned end after every APPLIED op; every trace asserts the
   full expected `text`/`caret` (`F1` in `_families`).
2. **Bounded queue** — `len(ctrl._dq) <= 32` re-asserted after every enqueue/drain step; the
   overflow-STOPS-not-drops variant stays covered by S1's re-run suite.
3. **ZERO legacy-backend calls** — behavioral, not just source-scan: an autouse fixture replaces
   `typing_backends.make_backend`, all three backend classes, and `type_text`/`press_backspace`
   (`raising=False`) with sentinels that FAIL the test on any call; 13/13 traces ran with zero
   recorded calls (fixture teardown re-asserts). S1's source-scan purity guards still pass on top.
4. **No duplicates** — per-trace op-log asserts: finalize called ONCE on identical finals; the
   zero-diff partial makes ZERO target calls; the final text contains the span exactly once; exactly
   ONE cancel op across the repeated-cancel trace.
5. **No extra writes** — `edit_count` equals the R.1 event-count-law number per trace (insertion 1,
   correction 1, zero-diff 0, refused/unknown/child-death 0, `leave()` and the idempotent second
   cancel add 0).
6. **No post-takeover mutations** — after any REFUSED/stop/epoch bump: `edit_count` frozen,
   `drain()` post-stop performs zero target calls, and the mutating-call thread-id set never exceeds
   one writer per delivery lifetime (trace 11 documents the fresh-runner-per-lifetime exception).

## Cancel gap-fill note (the one conditional code change)

Preflight `grep -n "def cancel" voice_typing/bulk_controller.py` → ABSENT (S1/S2 land no cancel
entry; the daemon-side intercept is P1.M6.T2.S1's). Added ONE minimal method
`BulkController.cancel(*, gen=None) -> bool` implementing R.5/R.3 semantics at the controller seam:
purge + close the pending utterance under the condition lock; ONE `target.cancel` op through the
same single-worker deadline-bounded runner (`op_deadline` applies); APPLIED → `expected_revision`
+1, delivery STAYS armed; UNCHANGED → fine (nothing pending at the target); REFUSED/UNKNOWN/
deadline/exception → the SAME one-word stop path as any failed op, never retried; nothing pending →
True with ZERO target calls (idempotent). NO `len(tail)-1` physical-character compensation anywhere
— that backspace math is legacy-only (R.5; the trace-7 sentinel proves zero `press_backspace`
reachability). S1+S2 suites re-ran green immediately after the addition (39 + 34 passed).

## Live pass counts (vs the G1 baseline, `d3_defects_g1_baseline.md`)

| # | File | Passed | Failed | Note |
|---|------|-------:|-------:|------|
| 1 | tests/test_g2_bulk_gate.py | 14 | 0 | 13 traces + summary; ×3 identical |
| 2 | tests/test_bulk_controller.py | 39 | 0 | S1+S2, re-run, untouched |
| 3 | tests/test_bulk_delivery.py | 34 | 0 | re-run, untouched |
| 4 | tests/test_zero_diff_rewind.py | 3 | 0 | matches baseline (3/0) |
| 5 | tests/test_streaming_commit.py | 22 | **10** | EXACT G1 baseline — **no new failures** |
| — | gate + #2–#4 combined | 90 | 0 | single run |

Scope guard: `git status --porcelain` (implementation tree) shows exactly
`M voice_typing/bulk_controller.py` + `?? tests/test_g2_bulk_gate.py` (+ this record). No S1/S2 test
edits; no `bulk_delivery.py`/streaming/typing_backends/daemon/config/feedback changes.
