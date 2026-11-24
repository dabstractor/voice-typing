---
name: "P1.M6.T3.S1 — Bulk-mode prompt source decision + implementation (decouple the rolling context prompt from StreamingOutput in bulk mode)"
description: "In bulk-text mode the rolling context prompt push (`_refresh_context_prompt`) currently never fires after commits (the bulk branch of on_final returns ahead of the streaming block) and, if it did, would read `_stream.committed` — which the bulk path never feeds (stays \"\" all session). This item makes the explicit decision risk #7 demands and implements it: in bulk mode the prompt source is the BulkController's own mirror of target-CONFIRMED text (`confirmed_visible()`, R.5 three-value law #3), read-only; `_stream` is never written by the bulk path; context still trims at the sentence boundary via the unchanged `prompt_engine.rolling_context_prompt`; both modes keep working with no cross-mode state bleed; the decision is documented in a code comment (no user-facing surface). Daemon-only changes + one new pure-python test file."
---

# PRP — P1.M6.T3.S1: Bulk-mode prompt source decision + implementation

## Goal

**Feature Goal**: Make the rolling context prompt (PRD §4.2quater) correct in
`output.delivery="bulk-text"` mode. Today the bulk path performs NO prompt push after commits
(`_bulk_handle_final` returns before the streaming block; its trailing comment defers the
decoupling to THIS item), so after the arm-time clear the child decodes every utterance
context-free — mid-paragraph fragments come out capitalized with spurious trailing periods,
the exact defect the prompt exists to fix. Decide and implement: **in bulk mode the prompt
source is the bulk controller's last target-CONFIRMED text** (`BulkController.confirmed_visible()`
— the controller's OWN mirror of screen truth), never `_stream.committed` (which the bulk path
never feeds) and never written back into `_stream`. Trigger the push at the bulk commit
checkpoints: accepted-final enqueue (covers UNCHANGED finals — no `on_applied` fires there) and
finalize-APPLIED (corrects context after a revised finalize), plus a context-free clear after a
bulk cancel (a removed fragment must never become decode context). Stream-edit behavior is
byte-identical (G1 discipline).

**Deliverable** (1 MODIFY + 1 CREATE):
1. `voice_typing/daemon.py` — MODIFY (adds-only within existing bodies + one behavior-identical
   extraction):
   - `_refresh_context_prompt()` (:2403): a bulk source branch FIRST (`_bulk_wired()` ⇒
     `source = self._bulk_ctrl.confirmed_visible()`; bulk mode but not wired ⇒ early return),
     ahead of the unchanged streaming/rev1 branches; docstring documents the DECISION.
   - `_bulk_handle_final()` (:1951): accepted path calls `self._refresh_context_prompt()` right
     after `ctrl.on_final(...)` (~:1987), inside the existing `is_active()` guard; REPLACE the
     trailing "NO prompt refresh … out of scope here" comment (~:2025-2028) with the new reality.
   - `_on_bulk_applied()` (:2153): `if kind == "finalize":` → `self._refresh_context_prompt()`
     (own try/except, never raises); `kind == "show"` deliberately does NOT push.
   - `_bulk_cancel()` (~:2196): after the out-of-lock `ctrl.cancel(gen)`, push the context-free
     clear via a new `_clear_context_prompt()` helper.
   - `_arm()` (:1707): extract the inline prompt-clear block (:1742-1755) into
     `_clear_context_prompt()` and call it — behavior-identical (the FIFO pin
     set_prompt("")-before-set_microphone(True) must hold exactly); `_bulk_cancel` reuses it.
2. `tests/test_bulk_context_prompt.py` — CREATE: pure-python unit tests pinning BOTH modes'
   prompt content (no CUDA, no subprocess, no live desktop; fake bundle over a fake
   DeliveryTarget + real `BulkController`, mirroring `tests/test_bulk_dispatch.py` doubles).

**Success Definition**:
- (a) Bulk accepted final → TWO pushes in the steady state: at enqueue,
  `rolling_context_prompt(confirmed_visible-at-enqueue)` (= the current utterance's last
  APPLIED show span); at finalize-APPLIED, `rolling_context_prompt(final span)` when the
  finalize revised the visible text.
- (b) UNCHANGED finalize (final renders equal to the shown span — the common
  stabilized-partial-equals-final case): the enqueue push fired; NO finalize-APPLIED push
  (`on_applied` does not fire) — context is still correct (the show span renders equal to the
  final).
- (c) Bulk cancel → exactly one `set_prompt("")` clear; the cancelled fragment NEVER appears in
  any pushed prompt text.
- (d) Rejected final (blocklist/min_chars) in bulk → ZERO pushes (parity with the stream-edit
  deliberate no-op).
- (e) Partial shows (`kind == "show"`) → ZERO prompt pushes (no mid-utterance
  self-conditioning).
- (f) Stream-edit mode: `tests/test_context_prompt_refresh.py` green UNTOUCHED — source stays
  `_stream.committed` (streaming) / `_rev1_committed` (Rev 1); the bulk branch is unreachable
  there (`_bulk_wired()` False).
- (g) No cross-mode state bleed: across a full bulk arm→speak→cancel→re-arm→speak session,
  `self._stream.committed` stays `""` (never written), the arm-time clear still fires in bulk
  mode (FIFO before the arm cmd), and every pushed prompt derives solely from
  `confirmed_visible()` (or the explicit ""-clears).
- (h) Gates preserved in bulk mode: `asr.context_prompt=false` ⇒ zero pushes; degraded child
  (`_context_prompt_active is not True`) ⇒ zero pushes; a host without `set_prompt` ⇒ silent
  DEBUG no-op; a raising `set_prompt` is swallowed (never kills reader/writer/cancel threads).
- (i) No `bulk_controller.py` changes; G1 watch set + bulk suites green untouched.

## User Persona

**Target User**: internal — (1) the **operator** dictating in bulk mode: mid-paragraph
fragments continue lowercase without spurious trailing periods (the §4.2quater defect class);
(2) **P1.M6.T4.S1** (G5 timing) — the wired bulk path it measures now decodes with proper
context; (3) **P1.M7.T1.S1** (G6 graduation) — recognition-quality evidence assumes the prompt
conditioning works in the mode being graduated.

**Use Case**: arm in bulk mode → speak sentence 1 → partials show live → final 1 enqueues →
enqueue push conditions on sentence 1's visible text → finalize applies (revised) → APPLIED
push conditions on the exact final text → the decoder decodes sentence 2's partials as a
CONTINUATION (lowercase first word, no spurious period). Backspace mid-utterance → cancel →
prompt cleared → the re-spoken sentence is NOT conditioned on the cancelled fragment.

**Pain Points Addressed**: (1) bulk mode silently loses the §4.2quater context fix (no push
after commits — context-free decoding degrades WER on fragments); (2) risk #7
(d2_bulk_delivery_map.md §9): if someone "fixes" it naively, `_refresh_context_prompt` would
read `_stream.committed` = "" forever (bulk never feeds it) — silently inert, or worse a future
change could feed `_stream` from bulk and break the G1 keystroke-parity contract; this item
makes the source decision explicit, documented, and unit-pinned per mode.

## Why

- **PRD §4.2sexies R.5** keeps recognition quality in scope for bulk mode ("Keep the configured
  … path and its lifecycle guarantees"); §4.2quater's rolling context prompt is the
  mid-paragraph-fragment fix and applies to "EVERY decode" — bulk mode is not exempt.
- **The item contract (this work item)**: "in bulk mode the prompt push reads the bulk
  controller's last-confirmed text (its own mirror; read-only from _stream, never writing it);
  context still trims at the sentence boundary; both modes keep working; no cross-mode state
  bleed (unit-test both modes' prompt content)."
- **Risk #7** (d2_bulk_delivery_map.md §9 row 7): "`_stream.committed` coupling — the
  context-prompt push reads it; bulk mode must not redefine it implicitly; prompt source for
  bulk mode needs an explicit decision."
- **Everything needed already landed**: the dispatch wiring (`_bulk_handle_final`,
  `_on_bulk_applied`, `_bulk_cancel`, `_bulk_wired` — P1.M6.T2.S1, the INPUT), the controller's
  three-value mirror (`confirmed_visible()`), the child-side executor
  (`prompt_engine.PromptedExecutor` + `host.set_prompt` cmd, read between utterances), and the
  arm-time FIFO clear. This item is a source-branch + three trigger calls + tests.

## What

User-visible behavior: in bulk mode, dictation quality on mid-sentence continuations matches
stream-edit (lowercase continuation, no spurious trailing punctuation). No config, no status,
no CLI, no state.json changes — the decision is documented as a code comment/docstring only.

### Success Criteria

- [ ] (a)-(i) from the Success Definition, each pinned by a test in
      `tests/test_bulk_context_prompt.py` or an existing untouched suite.
- [ ] The decision comment exists on `_refresh_context_prompt` (source choice + why
      confirmed_visible, why not _stream, the UNCHANGED-final double-trigger rationale, the
      cancel-clear divergence from stream-edit) and at each trigger site.
- [ ] G1 watch set + `tests/test_bulk_dispatch.py` + `tests/test_bulk_controller.py` +
      `tests/test_g2_bulk_gate.py` + `tests/test_context_prompt_refresh.py` +
      `tests/test_prompt_engine.py` all green, untouched.

## All Needed Context

### Context Completeness Check

_Pass._ The exact modification sites with current line cites, the controller's
`confirmed_visible()` semantics (including the UNCHANGED/cancel subtleties that dictate the
trigger design), the thread/lock audit for each new call, the test-double patterns, and
executable validation commands are all below. Line cites were re-verified live this session;
P1.M6.T2.S3 lands in parallel (session_reply/`_dispatch`/ctl.py — disjoint sites) — re-grep
before editing (Task 0).

### Documentation & References

```yaml
# MUST READ — this item's verified research (the decision analysis D1-D4 + timing/lock audit).
- file: plan/008_a47116bb2b79/P1M6T3S1/research/bulk_prompt_source_decision.md
  why: "§2 why confirmed_visible() + why the enqueue trigger is REQUIRED (UNCHANGED finals
        never fire on_applied); §3 the trigger sites; §4 timing safety (silence gate 0.8 s vs
        ~250 ms apply — both pushes land before the next decode); §5 thread/lock audit;
        §6-7 test landscape + parallel-conflict check."

# MUST READ — the grounding map (risk #7 = §9 row 7; §3 the _stream.committed coupling law).
- file: plan/008_a47116bb2b79/architecture/d2_bulk_delivery_map.md
  why: "§9 row 7 (this item's reason to exist); §1 prompt_engine summary + 'Bulk relevance'
        (read-only; do not couple); §3 'bulk code must NOT call' list + the shared-mutable-state
        traps (b) is exactly the coupling this item resolves."
  critical: "Map line cites are @ 2335a9e and DRIFTED — use this PRP's cites."

# MUST READ — the PRD clauses.
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: "§4.2quater Rolling context prompt (committed back to last sentence boundary, ~200-token
        cap, dynamic executor, degrade-never-crash) + deterministic guards; §4.2sexies R.5
        three-value law (confirmed_visible is value #3) + 'bulk mode MUST enqueue and return'
        reader-thread law; R.8 (recognition quality separate work — this item is the prompt
        half of that integration)."

# MUST READ — the files being modified/consumed.
- file: voice_typing/daemon.py
  why: "(1) _refresh_context_prompt :2403-2449 — the ONE push funnel: gates (context_prompt
        config + _context_prompt_active), source branch :2436-2440 (streaming/rev1 — insert
        the bulk branch FIRST), defensive set_prompt getattr, never-raise. (2) on_final :1401,
        bulk branch :1516-1519 (returns into _bulk_handle_final BEFORE the streaming block that
        contains the legacy refresh). (3) _bulk_handle_final :1951 — accepted path
        ctrl.on_final ~:1987 inside the is_active guard (insert trigger A right after); the
        trailing 'NO prompt refresh … P1.M6.T3.S1' comment ~:2025-2028 (REPLACE).
        (4) _on_bulk_applied :2153 (add the kind=='finalize' trigger B after the
        record_confirmed_op try/except). (5) _bulk_cancel ~:2196 (add the D4 clear AFTER the
        out-of-lock ctrl.cancel(gen), BEFORE `with self._lock:`). (6) _arm :1707 — the inline
        clear block :1742-1755 to extract into _clear_context_prompt() (behavior-identical;
        FIFO pin). (7) _bulk_mode :1913 / _bulk_wired :1917 (the gates for the source branch).
        (8) module docstring :1-140 (add one Mode A line under the existing bulk note)."
  critical: "NEVER take a daemon lock inside the new calls (none needed — audited); NEVER call
             ctrl mutators from _refresh_context_prompt/_clear_context_prompt (confirmed_visible
             is a read); keep the extraction in _arm byte-identical in behavior."

- file: voice_typing/bulk_controller.py
  why: "READ ONLY. confirmed_visible() :650 (three-value law #3, thread-safe, retained across
        fault stops, cleared by _reset_session_locked at arm); _process_next APPLIED branch
        :773-776 (_confirmed_visible = item.span — INCLUDING partial shows); on_applied fire
        :782-793 (APPLIED only, outside _cond, exception-wrapped — kinds 'show'|'finalize');
        UNCHANGED branch (:778-780) updates _shown_span but NOT _confirmed_visible and fires NO
        hook; cancel() :398-500 (APPLIED :483-487 does NOT touch _confirmed_visible — the
        stale-fragment window D4 closes)."
  critical: "Do NOT modify this file. The UNCHANGED/cancel semantics are what dictate the
             daemon-side trigger design — read §2 of the research notes before coding."

- file: voice_typing/prompt_engine.py
  why: "READ ONLY. rolling_context_prompt(committed) — sentence-boundary trim + 200-token cap,
        PURE, never raises; the child caps again in set_prompt (defense in depth). The bulk
        path reuses it UNCHANGED ('context still trims at the sentence boundary')."

- file: voice_typing/recorder_host.py
  why: "READ ONLY. set_prompt :304 — ('prompt', {'text'}) mp-queue put, non-blocking; :636 the
        child applies prompt cmds BETWEEN utterances (FIFO with arm/text cmds) — the timing
        argument for why both triggers are safe."

# MUST READ — the test patterns to mirror.
- file: tests/test_bulk_dispatch.py
  why: "The bulk-side doubles: _FakeHost :139 (settable relay_identity; add a prompts list +
        set_prompt recorder), _FakeTarget :197, _FakeBundle :246, _make_bulk_daemon :314 (cfg
        satisfies the delivery precondition triple; host_factory seam), _wait_until :368.
        Real BulkController over _FakeTarget ⇒ writer thread drains async; drive with
        ctrl.drain() or _wait_until."
- file: tests/test_context_prompt_refresh.py
  why: "The both-modes regression anchor + the gate-test patterns (config-off, degraded child,
        no-set_prompt host, raising set_prompt, rejected final, arm-clear FIFO). Its _FakeHost
        ready payload carries the context_prompt flag :110-117 — mirror that in the bulk fake."
  critical: "This file must pass UNTOUCHED — it pins stream-edit; the new file pins bulk."

# Hard rules.
- file: AGENTS.md
  why: "Two timeouts on every non-trivial command (inner GNU timeout + bash-tool timeout);
        pytest under timeout 600; no CUDA/no daemon in these tests (they are pure-python)."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── daemon.py            # ← MODIFY: _refresh_context_prompt bulk branch + _clear_context_prompt
│                        #   extraction + 3 trigger calls (A/B/D4) + comment updates
├── bulk_controller.py   # READ ONLY (confirmed_visible semantics drive the design)
├── prompt_engine.py     # READ ONLY (rolling_context_prompt reused unchanged)
├── recorder_host.py     # READ ONLY (set_prompt cmd, between-utterance application)
├── streaming.py         # READ ONLY (never written by the bulk path — the whole point)
└── bulk_delivery.py ime/ pi_editor.py feedback.py config.py  # READ ONLY
tests/
├── test_bulk_context_prompt.py  # ← CREATE (all new tests)
└── (test_bulk_dispatch, test_bulk_controller, test_g2_bulk_gate,
    test_context_prompt_refresh, test_prompt_engine, test_streaming_commit,
    test_zero_diff_rewind, ...)  # must stay green untouched
```

### Desired Codebase tree with files to be added

```bash
voice_typing/daemon.py            # + ~45 lines: bulk source branch in _refresh_context_prompt
                                  #   (+ docstring decision), _clear_context_prompt() extraction,
                                  #   trigger A in _bulk_handle_final, trigger B in
                                  #   _on_bulk_applied, D4 clear in _bulk_cancel, comment swaps,
                                  #   1 module-docstring line
tests/test_bulk_context_prompt.py # + ~10 tests (fake bundle + real controller + prompt-spy host)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — UNCHANGED finals are the COMMON case, and on_applied does NOT fire for them
#   (APPLIED only; _confirmed_visible is not updated either). A finalize-APPLIED-only trigger
#   would leave the context an utterance behind forever. The enqueue-time trigger (A) is what
#   covers them: at enqueue, confirmed_visible = this utterance's last APPLIED show span,
#   which renders equal to the final exactly when the finalize will be UNCHANGED.

# CRITICAL #2 — confirmed_visible() updates on PARTIAL shows too. That is fine ONLY because the
#   prompts are read exclusively at the two final-tied triggers + the cancel clear; partial
#   shows (kind == "show") must NEVER trigger a push (mid-utterance self-conditioning — the
#   executor runs condition_on_previous_text=False precisely because the daemon owns
#   cross-utterance context).

# CRITICAL #3 — cancel() does NOT reset _confirmed_visible: after cancelling utterance N it
#   transiently holds N's removed fragment. Without the D4 clear, a later accepted final with
#   zero shows of its own could push that removed text as context. D4's set_prompt("") closes
#   the window; the next finalize-APPLIED rebuilds proper context. Note the deliberate
#   divergence: stream-edit KEEPS pre-cancel context (committed unchanged); bulk goes
#   context-free (no cumulative mirror exists — conservative degrade, PRD philosophy).

# CRITICAL #4 — branch ORDER in _refresh_context_prompt: the bulk check must come FIRST.
#   Bulk requires streaming=true, so the existing branch would pick _stream.committed ("" all
#   session). Gate on _bulk_wired() (mode AND controller exists); bulk-but-unwired (no arm yet,
#   acquire-failed 'unsupported', torn down) => EARLY RETURN, no push — there is no source of
#   truth and the arm-time clear already left the child context-free.

# CRITICAL #5 — reader-thread law (R.5): trigger A runs on the host reader thread inside
#   _bulk_handle_final. _refresh_context_prompt is non-blocking (mp-queue put + pure function)
#   and never raises — enqueue-and-return is preserved. Trigger B runs on the controller writer
#   thread (on_applied is fired outside _cond and exception-wrapped); D4 runs on the cancel
#   caller's thread (control socket / evdev). NONE of the new calls takes a daemon lock or
#   calls a ctrl mutator — the bulk lock law (G1, daemon.py bulk-section comment) holds.

# CRITICAL #6 — the _arm extraction must be behavior-identical: same gates
#   (cfg.asr.context_prompt AND _context_prompt_active is True), same set_prompt("") put BEFORE
#   set_microphone(True) (the FIFO pin in test_context_prompt_refresh.py), same DEBUG fallbacks.
#   Extract, do not "improve".

# CRITICAL #7 — per-utterance, not cumulative: confirmed_visible() is the LAST confirmed span
#   (R.3 spans are per-utterance), so a multi-utterance unpunctuated sentence conditions only
#   on the newest confirmed utterance (stream-edit's committed would carry the whole run).
#   ACCEPTED divergence — document it in the decision comment; do NOT build a daemon-side
#   accumulator (that is a second source of truth; the contract names the controller's mirror).

# CRITICAL #8 — G8 log law: keep the existing DEBUG-only push logs (word counts, never the
#   prompt TEXT above DEBUG — it is user dictation). No new text-bearing logs.

# CRITICAL #9 — scope walls: do NOT touch bulk_controller.py / streaming.py /
#   typing_backends.py / ime/ / pi_editor.py / feedback.py / config.py / ctl.py (T2.S3 owns
#   ctl.py + _dispatch in parallel). No config keys, no state.json, no README — the DOCS
#   deliverable is the in-code decision comment only.
```

## Implementation Blueprint

### Data models and structure

No new data models. The design reuses: `BulkController.confirmed_visible() -> str` (read-only),
`prompt_engine.rolling_context_prompt(committed: str) -> str` (pure, unchanged), and the
`host.set_prompt(text)` cmd seam. The only new daemon state is none — the source branch reads
existing fields (`self._bulk_ctrl` via `_bulk_wired()`).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: RE-GREP the anchors (parallel-item drift guard)
  - RUN: grep -n "def _refresh_context_prompt\|def _bulk_handle_final\|def _on_bulk_applied\|
         def _bulk_cancel\|def _arm\|NO prompt refresh" voice_typing/daemon.py
  - NOTE: P1.M6.T2.S3 lands session_reply/_dispatch lines in parallel; the cites above were
    verified this session — adjust offsets, not shapes.

Task 1: MODIFY voice_typing/daemon.py — extract _clear_context_prompt() from _arm
  - MOVE the inline clear block (:1742-1755) into `def _clear_context_prompt(self) -> None`
    (same docstring content + the reuse note), called from _arm at the SAME position.
  - BEHAVIOR-IDENTICAL: gates, put order (before set_microphone(True)), DEBUG fallbacks.
  - VERIFY: timeout 120 .venv/bin/python -m pytest tests/test_context_prompt_refresh.py -q

Task 2: MODIFY _refresh_context_prompt — the bulk source branch + the DECISION docstring
  - INSERT at the top of the try-body (after the existing gate check, before the source pick):
      if self._bulk_mode():
          if not self._bulk_wired():
              return  # no controller -> no source of truth; arm-clear already context-free
          source = self._bulk_ctrl.confirmed_visible()
      elif self._cfg.output.streaming:
          source = self._stream.committed
      else:
          source = self._rev1_committed
    (restructure the existing ternary into this if/elif — same stream-edit semantics).
  - DOCSTRING: document the decision (see Success Criteria): bulk source =
    confirmed_visible() — the controller's OWN mirror of target-CONFIRMED text (R.5 value #3);
    _stream is read-only everywhere and NEVER written by the bulk path; per-utterance span
    divergence (Gotcha #7); triggers A/B/D4 and why (UNCHANGED-final coverage, correction,
    cancel hygiene); deliberate no-ops preserved (rejected finals, dropped finals, unload
    teardown).
  - NAMING/PLACEMENT: no new methods here; keep the never-raise + DEBUG-only-text laws.

Task 3: MODIFY _bulk_handle_final — trigger A (enqueue-time push)
  - INSIDE the existing `if ctrl is not None and ctrl.is_active():` guard, immediately after
    `ctrl.on_final(cleaned, utterance=str(uid), seq=seq, gen=gen)` (~:1987):
    `self._refresh_context_prompt()  # P1.M6.T3.S1 trigger A — covers UNCHANGED finals`.
  - REPLACE the trailing comment block "NO _stream.commit, NO backend.type_text, NO
    text-bearing latency line, NO prompt refresh (… out of scope here)" — keep every clause
    except the prompt one; the prompt refresh now happens at trigger A above.
  - NOTE: rejected finals return EARLIER (the `if not cleaned:` branch) — zero pushes there
    (parity pinned by test).

Task 4: MODIFY _on_bulk_applied — trigger B (finalize-APPLIED push)
  - AFTER the existing record_confirmed_op try/except, add:
      if kind == "finalize":
          try:
              self._refresh_context_prompt()  # P1.M6.T3.S1 trigger B — post-correction context
          except Exception:
              logger.debug("bulk finalize prompt refresh failed (ignored)", exc_info=True)
  - kind == "show" and kind == "cancel": NO push (cancel's clear is D4, in _bulk_cancel).

Task 5: MODIFY _bulk_cancel — D4 (post-cancel context-free clear)
  - AFTER the out-of-lock `ctrl.cancel(gen=self._bulk_gen)` block (before `with self._lock:`):
    `self._clear_context_prompt()  # P1.M6.T3.S1 D4 — a cancelled fragment is never context`.
  - Rationale comment: stream-edit keeps pre-cancel context (committed unchanged); bulk has no
    cumulative mirror — context-free until the next finalize-APPLIED rebuilds it.
  - Update the module docstring's bulk section with ONE line (Mode A): bulk-mode prompt source
    = controller confirmed text; triggers A/B/D4; _stream untouched.

Task 6: CREATE tests/test_bulk_context_prompt.py
  - HEADER: pure-python docstring (no CUDA/no subprocess/no live desktop) + run command,
    mirroring tests/test_bulk_dispatch.py's conventions.
  - DOUBLES: copy _FakeHost/_FakeTarget/_FakeBundle/_make_bulk_daemon/_wait_until from
    tests/test_bulk_dispatch.py; EXTEND the fake host with `self.prompts: list[str]` +
    `set_prompt(text)` recorder and a ready payload `context_prompt=True` flag (the
    test_context_prompt_refresh.py _FakeHost pattern :110-117/:137) so _context_prompt_active
    resolves True.
  - TESTS (naming: test_<subject>_<scenario>):
    1. test_bulk_final_enqueues_then_applies_two_pushes — partial show (APPLIED) → final
       (revised) → drain/_wait_until → prompts == [arm-clear "", enqueue-context, finalize-
       context] where contexts == rolling_context_prompt of the respective confirmed spans.
    2. test_bulk_unchanged_finalize_single_push — final renders equal to the shown span →
       prompts end at the enqueue push; NO finalize push (on_applied never fired); context ==
       rolling_context_prompt(last show span).
    3. test_bulk_partial_shows_never_push — several APPLIED shows, no final → prompts stay
       [arm-clear ""].
    4. test_bulk_cancel_clears_prompt — shown span + Backspace/cancel() → prompts gain exactly
       one ""; the fragment text appears in NO pushed prompt (scan all non-"" prompts).
    5. test_bulk_rejected_final_no_push — blocklist final → zero pushes beyond the arm clear.
    6. test_bulk_never_reads_or_writes_stream — across arm/partials/finals/cancel/re-arm:
       `d._stream.committed == ""` (spy stream if the double has one; else assert the field)
       AND the spy backend recorded zero calls (R.1 law, copied from test_bulk_dispatch).
    7. test_bulk_config_off_zero_pushes — cfg.asr.context_prompt=False → set_prompt never
       called (not even the arm clear).
    8. test_bulk_degraded_child_zero_pushes — ready payload context_prompt=False → zero pushes.
    9. test_bulk_rearm_clears_first — after confirmed spans exist, re-arm → first prompt is ""
       (FIFO before the arm cmd) even in bulk mode.
    10. test_stream_edit_source_unchanged — delivery="stream-edit" daemon (existing
        test_context_prompt_refresh pin) + one explicit new assertion: with streaming=true and
        delivery="stream-edit", commits still push rolling_context_prompt(_stream.committed)
        (guards the branch-order regression where the bulk branch could shadow stream-edit).
    11. test_bulk_fault_stopped_no_stale_push — controller stopped (fault) → a subsequent
        accepted final fires NO push (trigger A sits inside the is_active guard; confirmed
        text retained but never read).
  - COVERAGE: every Success Definition item (a)-(i) maps to ≥1 test.

### Implementation Patterns & Key Details

```python
# Task 2 — the source branch (bulk FIRST; stream-edit semantics unchanged):
def _refresh_context_prompt(self) -> None:
    try:
        if not self._cfg.asr.context_prompt or self._context_prompt_active is not True:
            return
        # P1.M6.T3.S1 DECISION (risk #7, d2 map §9): in bulk mode the committed checkpoint
        # lives in the BULK CONTROLLER (its own mirror of target-CONFIRMED text — R.5
        # three-value law #3), NOT in StreamingOutput: the bulk path never feeds _stream, so
        # its .committed stays "" all session and would silently disable conditioning.
        # _stream stays READ-ONLY in every mode; the bulk path NEVER writes it.
        if self._bulk_mode():
            if not self._bulk_wired():
                return  # no controller (pre-arm / unsupported / torn down): no source of truth
            source = self._bulk_ctrl.confirmed_visible()
        elif self._cfg.output.streaming:
            source = self._stream.committed
        else:
            source = self._rev1_committed
        text = prompt_engine.rolling_context_prompt(source)  # sentence-boundary trim, 200-token cap
        ...  # unchanged: defensive set_prompt getattr + DEBUG logs (word counts only)

# Task 3 — trigger A (reader thread; inside the is_active guard, after ctrl.on_final):
        if ctrl is not None and ctrl.is_active():
            ctrl.on_final(cleaned, utterance=str(uid), seq=seq, gen=gen)
            self._refresh_context_prompt()  # trigger A: covers UNCHANGED finals (no on_applied)

# Task 4 — trigger B (writer thread; on_applied fires outside _cond, after _confirmed_visible
# was updated under it — confirmed_visible() here returns the finalize's exact span):
        if kind == "finalize":
            try:
                self._refresh_context_prompt()  # trigger B: post-correction context
            except Exception:
                logger.debug("bulk finalize prompt refresh failed (ignored)", exc_info=True)
```

### Integration Points

```yaml
NONE. No config keys, no state.json fields, no feedback/ctl surfaces, no docs beyond in-code
comments (the contract: "code comment documenting the decision (no user-facing surface)").
The child-side seam (host.set_prompt -> ("prompt", {"text"}) -> PromptedExecutor.set_prompt,
applied between utterances) is consumed as-is.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m py_compile voice_typing/daemon.py tests/test_bulk_context_prompt.py
# (repo uses ruff if configured: .venv/bin/ruff check voice_typing/daemon.py tests/test_bulk_context_prompt.py --fix)
# Expected: zero errors.
```

### Level 2: Unit Tests (Component Validation)

```bash
# The new suite (pure-python, seconds):
timeout 300 .venv/bin/python -m pytest tests/test_bulk_context_prompt.py -q
# The both-modes anchor + the untouched bulk suites:
timeout 600 .venv/bin/python -m pytest tests/test_context_prompt_refresh.py \
    tests/test_bulk_dispatch.py tests/test_bulk_controller.py tests/test_g2_bulk_gate.py \
    tests/test_prompt_engine.py -q
# Expected: all green; the five existing files UNTOUCHED (git diff --stat shows only
# daemon.py + the new test file).
```

### Level 3: Integration Testing (System Validation)

```bash
# G1 watch set (the regression gate — numbers must match the recorded baseline):
timeout 900 .venv/bin/python -m pytest tests/test_streaming_commit.py \
    tests/test_zero_diff_rewind.py tests/test_control_socket.py tests/test_config.py -q
# NOTE: test_streaming_commit has recorded legacy-red rows at HEAD (G1 baseline) — compare
# against tests/G1_BASELINE.md, do NOT "fix" or skip them; only NEW failures block.
# No daemon/E2E run in this item (AGENTS.md: unit tests only; the E2E scripts rebind audio).
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Reasoning-level check (no live desktop): re-read the decision comment against the contract
# clauses — "reads the bulk controller's last-confirmed text", "read-only from _stream, never
# writing it", "trims at the sentence boundary", "both modes keep working", "no cross-mode
# state bleed" — each clause maps to a code site + a test. Optional smoke (ONLY if a daemon is
# already running under systemd and the operator asks): journalctl --user -u voice-typing -f |
# grep context-prompt — pushes log word counts at DEBUG.
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 1-3 commands run clean; new suite green; the five existing suites green UNTOUCHED.
- [ ] `git diff --stat` touches ONLY `voice_typing/daemon.py` + `tests/test_bulk_context_prompt.py`.

### Feature Validation

- [ ] (a)-(i) each pass; the decision comment exists on `_refresh_context_prompt` + trigger sites.
- [ ] Stream-edit prompt content byte-identical (test_context_prompt_refresh untouched & green).
- [ ] `_stream.committed` never written by the bulk path; every bulk prompt derives from
      `confirmed_visible()` or an explicit ""-clear.

### Code Quality Validation

- [ ] No new locks taken, no ctrl mutators called from the prompt path, never-raise preserved.
- [ ] No config/state/CLI/README surface added (contract: no user-facing surface).
- [ ] Log law: word counts at DEBUG, never prompt text above DEBUG.

## Anti-Patterns to Avoid

- ❌ Don't "fix" `_refresh_context_prompt` by feeding `_stream` from the bulk path — that
  redefines `committed` implicitly (exactly risk #7) and breaks the G1 keystroke-parity contract.
- ❌ Don't trigger pushes from partial shows (`kind == "show"`) — mid-utterance
  self-conditioning; the executor's `condition_on_previous_text=False` exists so the daemon
  owns cross-utterance context only.
- ❌ Don't build a daemon-side cumulative committed accumulator — a second source of truth; the
  contract names the controller's mirror.
- ❌ Don't modify `bulk_controller.py` to fire `on_applied` on UNCHANGED — that corrupts the
  record_confirmed_op event accounting (R.1: zero-diff = 0 ops); the enqueue trigger covers it.
- ❌ Don't reorder/rewrite `_arm`'s clear beyond the behavior-identical extraction — the FIFO
  pin (set_prompt("") before set_microphone(True)) is load-bearing for warm re-arm.
- ❌ Don't log prompt text, don't add config knobs, don't touch the parallel T2.S3 surfaces.
```
