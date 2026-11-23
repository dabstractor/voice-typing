# Research Note — P1.M3.T2.S3: the G2 gate (fake-target trace matrix + evidence record)

PRD §4.2sexies R.7, second bullet, verbatim: "**G2 controller, fake target:** deterministic traces —
append; first-word change; identical update and final; retraction; Unicode; rejected/lost final;
repeated cancel; timeout-after-apply; held key; out-of-order results; stop + immediate re-arm; child
death; focus change mid-operation. Assert exact text/caret, bounded queue, zero legacy-backend calls,
no duplicates, no extra writes, no post-takeover mutations. **Necessary, never sufficient.**" The item
contract adds: "Evidence bounded in tests/" + "OUTPUT: G2 pass recorded as the gate artifact" +
"DOCS: gate record file only."

---

## §0 WHAT EXISTS WHEN THIS TASK STARTS (the consumed contracts)

Per the parallel-execution rule, S1 and S2 are BOTH treated as landed exactly per their PRPs
(verified 2026-11-23: neither `voice_typing/bulk_controller.py` nor `tests/test_bulk_controller.py`
exists yet — both land before this task runs; this task's gate module is TDD-RED until then, same
coordination S2's PRP used against S1):

1. **`voice_typing/bulk_delivery.py` (LANDED, commit `2a0032e`, read-only)** — `ShowResult`
   (APPLIED/UNCHANGED/REFUSED/UNKNOWN, str-valued), `AcquireResult(ok,handle,revision,reason)`,
   `DeliveryTarget` Protocol (`acquire/show/finalize/leave/cancel`; show/finalize take
   `(session,utterance,seq,expected_revision,span)`), `rendered_equal` (whitespace-only fold),
   `map_span`, `TargetUnits`.
2. **`voice_typing/bulk_controller.py` (S1+S2, assumed landed)** — `BulkController(target, *,
   queue_size=32, on_stopped=None, op_deadline=0.25)`: `acquire/start/stop(*,leave=True)/arm(gen)/
   on_partial/on_final/on_final_dropped/is_active/stats()/_process_next(blocking=False,timeout=None)/
   drain(max_items=None)`; S2 adds `_dispatch_epoch` give-up guard, stop reasons
   (`queue-overflow|op-deadline|refused|unknown|target-error`), `on_stopped` fired once, three-value
   accessors `latest_recognized()/accepted_final()/confirmed_visible()`, retention across a failure
   stop, extended `stats()` (`stop_reason/stopped_at_ms/deadline_exceeded/target_errors/
   late_results_discarded`).
3. **`tests/test_bulk_controller.py` (S1's ~25 + S2's ~13 appended)** — the unit suites this gate
   RE-RUNS but never edits.
4. **The G1 baseline (d3_defects_g1_baseline.md)** — the no-new-failures reference:
   `test_streaming_commit.py` 22 passed / **10 failed** (pre-existing), `test_zero_diff_rewind.py`
   3/0, `test_textproc.py` 31/0, `test_typing_backends.py` 36/0, `test_key_listener.py` 32/0,
   `test_control_socket.py` 27/0, `test_config.py` 54/0.

**GAP FOUND (this task's one code allowance):** neither S1's nor S2's PRP adds a controller-level
`cancel()` entry — S1's API has `on_final_dropped` (boundary close) but NO cancel, and the daemon-side
cancel intercept is explicitly P1.M6.T2.S1's (d2 map §2: branch at top of `daemon.cancel()`
:1754-1798, BEFORE the legacy press_backspace call). But R.7's G2 matrix REQUIRES the "repeated
cancel" trace to run **through the controller** ("G2 *controller*, fake target"). R.5/R.3 pin the
semantics: "discards the fragment's recognition, removes only a verified owned range, and leaves the
mic armed on success; nothing pending ⇒ no edit; uncertain range ⇒ stop, never attempt repair."
⇒ **Task 2 of this PRP adds a MINIMAL `cancel()` entry to BulkController, preflight-gated** (only if
the landed S1+S2 class lacks it — check `grep -n "def cancel" voice_typing/bulk_controller.py`).
Design in §3.

---

## §1 THE G2 FAKE TARGET (richer than S1/S2's — the exact-text/caret model)

S1/S2's `_FakeTarget` records calls; the GATE fake must additionally model the FIELD, because the
matrix asserts **exact text/caret** and **edit counts** (the R.1 event-count law: insertion = 1,
correction = 1, zero-diff = 0). Model (mirrors what the R.2 GTK probe asserted — text, caret,
edit-count):

```python
class G2FakeTarget:
    """Field-modeling fake: owned-range replacement, visible edit counting, programmable faults.

    Field model: `text` (the whole field), `owned` (start,end char span we own — only this range
    is ever mutated), `caret` (char index; after an APPLIED show/finalize = owned end), `edit_count`
    (VISIBLE edits — the event-count law's counter: +1 per mutation, +0 for unchanged/refused/unknown
    no-ops). Op log: `ops` = [(method, span, expected_revision, result)] — for no-duplicates /
    no-extra-writes / zero-legacy assertions. Thread ids: `thread_ids` set (one-writer corroboration).
    """
    text: str = ""; owned: tuple[int,int] = (0,0); caret: int = 0; edit_count: int = 0
    ops: list; thread_ids: set
    # programmable faults (S2's variants, reused): result_overrides, gate (threading.Event for the
    # timeout-after-apply trace), delay, raise_exc (child death), refuse_after (focus change).
    def acquire(self): -> AcquireResult(ok=True, handle="g2", revision=0)
    def show(self, session, utterance, seq, expected_revision, span):
        # fault injection first (gate/refuse/raise per trace);
        # mutation-time ownership check: session != current session -> REFUSED (stale);
        # replace self.text[owned_start:owned_end] with span; owned=(start, start+len(span));
        # caret = owned_end; edit_count += 1; return APPLIED
    def finalize(...)  # same replacement semantics; render-equal span -> UNCHANGED, edit_count += 0
    def leave(self): record; never mutates (leave = preserve, zero writes — assert edit_count flat)
    def cancel(self):
        # nothing owned -> UNCHANGED (+0 edits); owned -> delete owned range, caret=owned_start,
        # edit_count += 1, owned=(0,0), return APPLIED
```

Ownership rule: `show`/`finalize` replace EXACTLY the owned range (R.3: "the complete rendered span
replaces the adapter's OWN verified range") — adjacent user text untouched (seed the field with
prefix/suffix user text in some traces and assert they survive byte-exact).

---

## §2 THE 13-TRACE MATRIX → MECHANISMS (every trace's drive + assert)

All deterministic: drive via `ctl.acquire(); ctl.arm(1); entries; ctl.drain()` (S1's seam); fakes
block on `threading.Event` (bounded `wait(1.0)`); `op_deadline=0.02`; NO bare sleeps. Unicode spans
flow verbatim (the controller never normalizes — S1 Critical).

| # | Trace | Drive | Assert (beyond green) |
|---|---|---|---|
| 1 | append | partials "Hello"→"Hello world"→final "Hello world" | text ends "Hello world"; edits: 2 (2 shows) + 0 (finalize UNCHANGED); caret = owned_end; revision +1 per APPLIED |
| 2 | first-word change | "Hello world"→"Hi world" | ONE show with the COMPLETE new span (not char retype); text exact; edit 1 |
| 3 | identical update AND final | same partial twice; identical final | 2nd partial: ZERO target calls (controller zero-diff skip); final: finalize called once → UNCHANGED, edit 0; **no duplicates**: final text contains the span exactly once |
| 4 | retraction | "hello world"→"hello" | one show; owned range SHRINKS; caret correct; edit 1 |
| 5 | Unicode | spans "naïve café 😀 猫" | byte/codepoint-exact text; caret char-index exact; no mojibake |
| 6 | rejected/lost final | on_final_dropped(utt) after shown partial | NO finalize call; shown tail PRESERVED (rejected final never auto-erases); boundary closed (late partial for that utt discarded); queue drains to empty |
| 7 | repeated cancel | ctl.cancel(); ctl.cancel() | 1st: pending utterance discarded + ONE target.cancel APPLIED (owned range removed, edit 1, text back to pre-utterance) + **still active** (mic armed); 2nd: nothing pending ⇒ NO target call, edit flat; (§3 design) |
| 8 | timeout-after-apply | show gated on Event, op_deadline=0.02 | stop "op-deadline"; ONE target call; after gate.set(): late APPLIED DISCARDED — text may show it in the fake but revision/confirmed_visible/stats-late_results_discarded prove the controller never consumed it |
| 9 | held key | target returns REFUSED on next show | stop "refused"; on_stopped once; NO retry (one op); queued items never dispatched; ZERO post-stop mutations (edit_count frozen at the refusal) |
| 10 | out-of-order results | stale future resolves after stop+re-arm(gen2) | gen2 partial APPLIES; stale gen1 result cannot touch gen2 (epoch+gen); no duplicate writes |
| 11 | stop + immediate re-arm | stop(); arm(2); gen2 entries | leave() exactly once (pre-re-arm); gen2 flows; gen1 straggler discarded at enqueue AND dispatch |
| 12 | child death | target.show raises ConnectionError | stop "target-error"; exception never escapes drain(); stop()'s leave() on the dead target safe (wrapped); no further calls |
| 13 | focus change mid-operation | target flips to REFUSED mid-flight (focus lost between accept and apply) | stop "refused"; the op already queued behind it is re-checked at mutation time ⇒ NEVER dispatched; no post-takeover mutations |

## §2b THE SIX ASSERTION FAMILIES (woven through EVERY trace — the G2-specific layer)

1. **Exact text/caret** — `fake.text == expected` and `fake.caret == expected` after every drain;
   user prefix/suffix text around the owned range survives byte-exact.
2. **Bounded queue** — after every enqueue step `len(ctl._dq) <= queue_size`; the overflow variant
   (S1 unit) is re-asserted here as STOP-not-drop; `stats()` queue counters consistent.
3. **ZERO legacy-backend calls** — a module-scoped pytest fixture monkeypatches
   `voice_typing.typing_backends` (`type_text`, `press_backspace`, `make_backend`, every backend
   class) with sentinel recorders that FAIL the test if invoked; every trace asserts `calls == []`.
   This is the runtime form of d2 §3's law (S1's source-scan guards stay; the gate adds behavioral
   proof "no type_text/press_backspace reachable in bulk mode").
4. **No duplicates** — the op log has no repeated mutation of the same content twice; finalize-
   matching-visible leaves the text with the span exactly once (the R.2 duplicate-final incident
   class).
5. **No extra writes** — `fake.edit_count == exactly the event-count-law number` per trace
   (insertion 1, correction 1, zero-diff 0); `leave()` never mutates; no calls after stop/on_stopped.
6. **No post-takeover mutations** — after any REFUSED/stop/epoch-bump: `fake.edit_count` frozen;
   the one-writer thread id set never grows; `drain()` after stop → zero target calls.

Plus the **gate-verdict summary test** (`test_g2_gate_summary`): recomputes the matrix coverage —
asserts the module executed one test per trace name (a frozen list of the 13) — so the gate record's
"13/13 green" is machine-checked, not hand-claimed.

## §3 THE MINIMAL `cancel()` GAP-FILL (Task 2; ONLY if preflight shows it absent)

```python
def cancel(self, *, gen: int | None = None) -> bool:
    """R.5/R.3 cancel semantics at the controller seam: discard the pending utterance's
    recognition, remove ONLY the verified owned range (ONE target.cancel op), keep listening.
    Nothing pending => NO target call, no edit (idempotent). Uncertain (not _active / stalled)
    => refuse the removal, never attempt repair. (Daemon-side intercept is P1.M6.T2.S1.)"""
    # under _cond: if not _active or gen mismatch -> return False (uncertain — never mutate)
    #   pending = utterances in _dq/_shown_span with an unclosed boundary
    #   purge their queued _Partial/_Final items; mark them in _closed (late strays discard)
    # ONE target.cancel() OUTSIDE _cond (writer-side op; same discipline as show/finalize —
    #   keep one-op-in-flight; may go through the op runner so the 250 ms deadline applies):
    #   APPLIED -> owned range removed; stay _active (mic stays armed); UNCHANGED -> fine (nothing
    #   pending); REFUSED/UNKNOWN -> S2's stop path (no retry, one reason).
```
Pinned: NO physical-character compensation (the len(tail)-1 backspace law is legacy-only); stays
active on success; honors S2's deadline + no-retry. ~30 lines. If preflight finds S1/S2 already
shipped a cancel seam, USE theirs — do not duplicate (the tests target the semantics, not the name).

## §4 DELIVERABLES + THE GATE RECORD (the OUTPUT artifact)

1. `tests/test_g2_bulk_gate.py` — NEW (~20 tests: 13 traces + families woven + summary + legacy-
   sentinel fixtures). Evidence bounded: the module IS the evidence; no /tmp dumps; any captured
   pytest output in the record = summary lines only (AGENTS.md Rule 3).
2. `voice_typing/bulk_controller.py` — CONDITIONAL minimal modify (§3; preflight-gated).
3. `plan/008_a47116bb2b79/architecture/g2_gate_record.md` — NEW gate record (mirrors
   d3_defects_g1_baseline.md's tabular style): date/HEAD; the matrix table (trace → test → verdict
   → assertion families exercised); the live pass counts (`test_g2_bulk_gate.py`,
   `test_bulk_controller.py`, `test_bulk_delivery.py`, `test_zero_diff_rewind.py` 3/0,
   `test_streaming_commit.py` no-new-failures vs 22/10 baseline); the six families each confirmed;
   the cancel gap-fill note (added-or-preexisting); and the mandatory caveat in bold:
   **"G2 is necessary, NEVER sufficient — this pass marks NO field row verified; G3 (P1.M4.T5) is the
   real-field gate and a G2 pass never flips any R.2 row to 'passed'."**

## §5 TOOLING / COORDINATION / BOUNDARIES

- `.venv/bin/python` (zsh aliases bare python); `timeout 60` inner + bash-tool timeout outer
  (AGENTS.md Rule 1). The gate suite is pure-stdlib threads — seconds, no CUDA/daemon/Wayland.
- Do NOT touch: S1/S2's tests (append-free — the gate is a NEW file), `bulk_delivery.py`,
  streaming/typing_backends/daemon/config/feedback (d2 §3/§4: config surface = P1.M3.T3; daemon
  wiring = P1.M6.T2; adapters = P1.M4).
- Do NOT "fix" the 10 pre-existing `test_streaming_commit.py` reds (G1 baseline; Gotcha in S2's PRP).
- Determinism: Event-bounded fakes, op_deadline=0.02, drain()-driven; re-run the gate 3× — identical
  counts. `mypy` NOT installed; ruff optional.
