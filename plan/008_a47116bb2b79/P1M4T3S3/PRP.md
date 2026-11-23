# PRP — P1.M4.T3.S3: `finalize()` / `leave()` / `cancel()` semantics — ownership ends, stop preserves, one-op cancel (`voice_typing/ime/target.py` completes)

## Goal

**Feature Goal**: Ship the **lifecycle half** of the IM-v2 adapter (PRD §4.2sexies R.3, research
note R.3): `finalize()`, `leave()`, `cancel()` on `ImeTarget`, plus the wire `cancel` command the
protocol RESERVED for this task. This completes the `DeliveryTarget` protocol implementation
(acquire ✓ T2.S1, show ✓ T3.S1/S2) — **the adapter is then complete for takeover work (P1.M4.T4)**.

Contract branches (each implemented AND unit-tested):

1. **finalize** — a final matching the visible text ⇒ **NO further edit** (ownership ends; no
   request at all, so composition-protocol commit side effects cannot visibly change or duplicate
   the text); a differing final ⇒ **ONE replacement** (delegates to the landed insert/correction
   paths); a final with no preceding partial ⇒ **inserts once** and is logged `live=false` (the
   missed-live-update hook — counting it in latency evidence is M6.T4/G5, fenced); a **rejected
   final never auto-erases visible words** (the controller never calls finalize on rejection —
   `on_final_dropped` is a no-target-call boundary; the adapter self-heals via the
   utterance-switch guard so the next utterance INSERTS, never corrects the abandoned words).
2. **leave** — stop preserves the last visible words where they are; **NO post-stop writes
   anywhere, including a newly focused field** (binding cleared; every later show/finalize/cancel
   REFUSES "not acquired" until a fresh acquire); best-effort host `leave` request, never raises,
   idempotent.
3. **cancel** — deliberate cancel removes the owned fragment in **ONE operation** (one atomic
   delete+commit), drops its buffered audio (controller-side, already landed), keeps listening;
   nothing pending ⇒ `UNCHANGED`, no request; uncertain range ⇒ REFUSED (stop, never attempt
   repair); **NO `len(tail)−1` physical-character compensation** — that is legacy-path-only
   (`daemon.py:1966`, routed around by M6.T2.S1's intercept): bulk cancel sends
   `before == len(owned.encode())` **exactly**.

**Deliverable** (3 evolved source files + 3 evolved test files + 1 optional lab; everything else
fenced):
1. `voice_typing/ime/target.py` — **EVOLVE**: `show()` gains the utterance-switch + closed-set
   guards; `_owned_region_intact`'s anchor generalizes; the correction advance becomes
   suffix-aware; **add** `finalize()`, `leave()`, `cancel()` + two state fields. All three edits
   to S2's landed code are **byte-identical in S2's single-utterance world** (proof in Gotchas)
   — S1/S2 tests stay green.
2. `voice_typing/ime/protocol.py` — **EVOLVE**: lift the `cancel` reservation (`REQUEST_CMDS` +
   `validate_request` requires `before` int ≥ 0 + docstring line).
3. `voice_typing/ime/ime_host.py` — **EVOLVE**: add the `_cancel` handler + one dispatch line
   (mirrors `_show` minus the text payload).
4. `tests/test_ime_target.py` — **APPEND** ~20 lifecycle cases (S1/S2 bodies untouched).
5. `tests/test_ime_protocol.py` — **APPEND** cancel-validation cases.
6. `tests/test_ime_host.py` — **REPLACE** `test_cancel_reserved` (it pins the reservation this
   task lifts) + **APPEND** `_cancel` cases. This is the ONLY existing test body this task may
   change.
7. `tests/ime_finalize_lab.py` — **CREATE** (optional evidence, NON-collected): env-gated GTK row
   (`IME_FINALIZE_LAB=1`) covering finalize-match (zero edits), finalize-differ (one correction),
   cancel (one edit, caret back), leave (no writes after).

**Success Definition**:
- (a) `timeout 180 .venv/bin/python -m pytest tests/test_ime_target.py tests/test_ime_host.py
  tests/test_ime_protocol.py tests/test_ime_wlwire.py tests/test_ime_manager.py
  tests/test_bulk_delivery.py tests/test_bulk_controller.py tests/test_g2_bulk_gate.py -q` →
  all green (S1 insert + S2 correction + controller/G2 consumers — zero regression);
  `git status --porcelain` shows ONLY the files above.
- (b) finalize ordering pinned: not-acquired ⇒ REFUSED; closed utterance ⇒ REFUSED
  "utterance closed", NO request; render-equal final ⇒ `UNCHANGED`, **zero requests**, ownership
  ends; differing final ⇒ exactly ONE show-family request (insert delta or
  `before=owned_bytes`+full-span correction — S2's branches, delegated); settled
  (APPLIED/UNCHANGED) ⇒ `_last_applied_span=""`, `_owned_utterance=None`, utterance added to the
  closed set, `_inserted_bytes` **unchanged** (committed text stays; caret math survives).
- (c) leave pinned: one bounded host `leave` request (timeout 0.25), binding cleared BEFORE it,
  returns `None`, never raises (dead/raising proc tolerated), second call = pure no-op, and every
  post-leave mutating call REFUSES "not acquired" with NO request.
- (d) cancel pinned: unbound ⇒ REFUSED "not acquired"; empty owned ⇒ `UNCHANGED` "nothing
  pending", NO request (the queued-but-undispatched-partial case — load-bearing, G2 trace_07);
  owned ⇒ recheck(caret at end of owned range) + `_owned_region_intact`, then **ONE**
  `request("cancel", timeout=0.25, before=owned_bytes)` with `before == len(owned.encode())`
  EXACTLY (UTF-8; astral = 4; **never −1**); applied ⇒ owned reset, utterance closed,
  `_inserted_bytes -= owned_bytes`, and a FOLLOW-UP insert still passes recheck (accounting
  round-trip); refused/unknown ⇒ state untouched, identical retry recomputes the same `before`.
- (e) Multi-utterance pins: after a settled finalize, a new utterance's partial INSERTS
  (`before=0`); a new utterance's CORRECTION deletes anchored at
  `caret − owned_bytes` (NOT the binding caret) and leaves
  `_inserted_bytes = prior_bytes − owned_bytes + span_bytes`; a DROPPED final (no finalize call)
  followed by a new utterance's show INSERTS — the abandoned words are never deleted.
- (f) Every REFUSED/UNKNOWN records machine-readable `self.last_reason` (taxonomy:
  `not acquired` / `utterance closed` / `nothing pending` / `recheck:<reason>` /
  `owned region diverged` / `host refused` / `host result <r>` / `ime no reply`); logs carry
  counts/times/flags ONLY — `session, seq, result, live` / `before, remaining_bytes, t_ms` —
  never recognition text (R.5).

## User Persona

**Target User**: Internal — **bulk_controller** (landed, M3) is the caller: `_process_next`
dispatches `target.finalize` for finals through the op runner; `stop(leave=True)` calls
`target.leave()` directly outside the runner; `cancel()` submits `target.cancel` through the
runner. **P1.M4.T4** (takeover) builds on the completed adapter; **P1.M6.T2.S1** constructs
`ImeTarget(ImeProcess(...))` in the daemon and routes `voicectl cancel` to the bulk path BEFORE
`daemon.cancel`'s legacy backspace. No end-user surface changes.

**Use Case**: Bulk mode armed on a GTK field. Partials `"helllo w"` applied (utterance u1). The
silence trips → the correction pass finalizes `"hello world"` → `finalize(u1, span="hello
world")` → delegates to show()'s correction branch → ONE atomic replacement → ownership ends
(committed; no longer revisable). Utterance u2's partial `"yes"` → INSERT at the caret with the
cumulative byte accounting intact. The user hits the cancel keybind mid-u3 → `cancel()` → recheck
proves the caret ends u3's owned `"wait no"` → ONE `delete_surrounding_text(7,0)`+commit removes
exactly those 7 bytes (no −1) → mic stays hot, `"just say it again"`. Stop → `leave()` → the last
visible words stay; focusing another field writes nothing.

**Pain Points**: (1) Without finalize, every final REFUSES at the adapter (not-implemented) and
disarms delivery — dictation cannot complete a single sentence. (2) A finalize that re-sends a
matching span would emit a spurious commit — the exact "visibly change or duplicate" defect R.3
forbids. (3) A cancel that compensates `len−1` (copying the legacy evdev rule) deletes one byte
too few; a cancel with a stale anchor deletes USER text. (4) A leave that writes after stop
(including into a newly focused field) is the classic post-stop-mutation bug R.5 bans.

## Why

- **The controller is landed and demands all three**: `bulk_controller.py:678` (finalize
  dispatch), `:361` (leave at stop), `:418` (cancel through the runner) — every one currently
  hits an unimplemented/no-op adapter surface, so bulk delivery cannot survive its first final.
- **The PRD pins the semantics verbatim** (R.3 finalize/leave/cancel model; R.5 "a dropped or
  filtered final still closes its utterance boundary", "never retry", "validate deadlines … in
  the RECEIVER"). The controller already enforces its half; this task is the adapter half.
- **The wire machinery is landed**: host `_leave` exists (releases grab, keeps serving); host
  `_show` proves the atomic delete+commit pattern cancel reuses; the protocol explicitly
  RESERVED `cancel` for this task (`protocol.py:81-82`, pinned by `test_cancel_reserved`).
- **Ownership-end is a state-machine insight, not new wire**: controller spans are PER-UTTERANCE
  (`_shown_span.get((gen, utterance), "")`) while committed bytes are cumulative — the adapter
  needs exactly two new fields and three byte-identical-in-S2's-world anchor fixes to express
  "ownership ends, bytes remain".

## What

Per the research note §2 (pinned state machine). Exact source in the Blueprint.

### Success Criteria

- [ ] All 7 files as specified; the combined suites green under `timeout 180`; scope guard clean.
- [ ] finalize: match ⇒ UNCHANGED zero-request + ownership ends; differ ⇒ ONE replacement;
      no-partial ⇒ one insert + `live=false` log; rejected-final ⇒ next utterance inserts
      (abandoned words never deleted).
- [ ] leave: preserves visible words, no post-stop writes anywhere, never raises, idempotent.
- [ ] cancel: one op, `before == owned_bytes` exactly (no −1), uncertain ⇒ refuse, accounting
      round-trip after an applied cancel.
- [ ] `cancel` lifted in protocol + host (validation, dispatch, confirm mapping); the reserved
      test replaced.
- [ ] `last_reason` taxonomy + text-free logs pinned; lab driver not collected by default.

## All Needed Context

### Context Completeness Check

_Pass._ The caller contracts are landed-and-anchored (finalize dispatch `bulk_controller.py:678`;
leave-at-stop `:331-366` outside the runner; cancel `:368-451` with the UNCHANGED-stays-active
rule; per-utterance spans `:672`; revision +1 only on applied `:721`); the host halves exist
(`_show` `ime_host.py:174-197` incl. the `before>0` triple; `_leave` `:214-221`;
`SHOW_CONFIRM_WAIT=0.22` `:38`; `_SNAPSHOT_HEAD_BYTES=64 KiB` `:41`); the reservation to lift is
pinned (`protocol.py:37,81-82`; `tests/test_ime_host.py:101`); S2's guards/state are the pinned
base with a hard preflight STOP gate; the state-machine derivation (per-utterance owned span,
cumulative bytes, suffix-anchored deletes) is proven in the research note and pinned verbatim
below; the test matrix is case-enumerated against the existing `_FakeProc`/`_snap`/`_verify`/
`_bound` helpers and the host `_FakeWire`/`_make_host` pattern.

### Documentation & References

```yaml
# MUST READ — this task's design record (anchors, state-machine derivation, fences).
- docfile: plan/008_a47116bb2b79/P1M4T3S3/research/finalize_leave_cancel_design.md
  section: "ALL. §1 consumed-surface anchors (live-verified), §2 the state machine + the three
            byte-identical-in-S2's-world edits, §3 host/protocol cancel design, §4 test pins,
            §5 fences."

# MUST READ — the two sibling PRPs this task builds on (ASSUME LANDED; preflight verifies).
- docfile: plan/008_a47116bb2b79/P1M4T3S2/PRP.md
  section: "Implementation Blueprint — show() with BOTH branches + _owned_region_intact (our
            base); Known Gotchas #1-#14 (backward-delete anchor; SET-vs-+=; unchunkable; UTF-8;
            zero-diff-first; no-text logs)."
  critical: "S2's correction advance `_inserted_bytes = span_bytes` and its
             `_owned_region_intact` anchor `binding.cursor_bytes` are SINGLE-UTTERANCE-world
             correct; this task generalizes both (Gotchas #2/#3) — in S2's world
             `_inserted_bytes == owned_bytes` always, so the generalized forms are byte-identical
             there and S2's tests must stay green."
- docfile: plan/008_a47116bb2b79/P1M4T3S1/PRP.md
  section: "Goal (b)-(e) — the insert-path ordering, state-advance-only-on-APPLIED, and
            last_reason taxonomy this task PRESERVES; the _FakeProc test pattern."

# MUST READ — the files being EVOLVED.
- file: voice_typing/ime/target.py
  why: "show() (S1+S2 landed) gains the utterance-switch + closed-set guards at the TOP;
        _owned_region_intact's anchor becomes caret-anchored; the correction advance becomes
        suffix-aware; APPEND finalize()/leave()/cancel(); __init__ gains _owned_utterance/
        _closed_utterances; acquire() resets them. recheck/to_bytes_span/binding_caret_after and
        the refusal taxonomy are test-pinned — do not alter."
  gotcha: "Never reset _inserted_bytes on settle/cancel-switch — only the owned-span bookkeeping
           resets; bytes are the caret arithmetic."
- file: voice_typing/ime/protocol.py
  why: "REQUEST_CMDS :37 += 'cancel'; validate_request :79-93 — replace the reserved-error branch
        with: cancel requires 'before' present and int >= 0; docstring :18-19 updated."
- file: voice_typing/ime/ime_host.py
  why: "_dispatch :135-148 gains the cancel entry; _cancel mirrors _show :174-197 (same
        not-activated/exception/dones-confirm posture) minus the text payload:
        delete_surrounding_text(before,0) + commit_string('') + commit(dones)."
  gotcha: "Do NOT touch _show/_acquire/_verify/_leave/SHOW_CONFIRM_WAIT — S1/S2/T2.S1 test-pinned."

# MUST READ — the vocabulary + the caller (read-only).
- file: voice_typing/bulk_delivery.py
  why: "DeliveryTarget.finalize/leave/cancel docstrings = the contract verbatim; ShowResult
        semantics (UNCHANGED keeps delivery active; UNKNOWN never retried)."
- file: voice_typing/bulk_controller.py
  why: ":672 per-utterance prev_span; :678 finalize dispatch; :721 +1 only on applied; :331-366
        stop→leave outside the runner; :368-451 cancel (UNCHANGED stays active; purges queue +
        closes boundaries controller-side). FENCED — if a controller test fails, the adapter's
        mapping/state is wrong."

# MUST READ — the test files to APPEND to (reuse helpers verbatim).
- file: tests/test_ime_target.py
  why: "_FakeProc :21 (records (cmd, timeout, fields); scripted replies; None = dead), _snap
        :33, _verify :40, _bound :47. APPEND only — S1/S2 bodies untouched."
- file: tests/test_ime_host.py
  why: "_FakeWire :19, _make_host :52, _feed :59 — the pattern for the _cancel cases;
        test_cancel_reserved :101 is the ONE body this task REPLACES."
- file: tests/test_ime_protocol.py
  why: "existing validate_request cases — APPEND the cancel-validation matrix."

# READ — grounding + PRD + discipline.
- docfile: PRD.md
  section: "§4.2sexies R.3 (finalize/leave/cancel model — the task's contract verbatim), R.5
            (dropped final still closes its utterance boundary; never retry; receiver-side
            deadlines; logs w/o text; 'uncertain range ⇒ stop, never attempt repair'), R.2
            (evidence — do not re-derive)."
- url: https://wayland.app/protocols/input-method-unstable-v2#zwp_input_method_context_v2:request:delete_surrounding_text
  why: "Wire legality of the cancel commit cycle (delete_surrounding_text + commit_string +
        commit in one state sequence; the XML Hyprland vendors — wlwire sends it via the
        generic request())."
- docfile: AGENTS.md
  section: "Rules 1-3 (GNU timeout everywhere; .venv/bin/python; bounded scratch; never the
            live desktop)."
```

### Current Codebase tree (excerpt, state at task start — S2 assumed landed)

```bash
voice_typing/ime/target.py             # EVOLVE: +finalize/leave/cancel, +utterance tracking, 3 anchor fixes
voice_typing/ime/protocol.py           # EVOLVE: lift the cancel reservation
voice_typing/ime/ime_host.py           # EVOLVE: +_cancel handler + dispatch line
voice_typing/bulk_delivery.py          # READ-ONLY vocabulary (finalize/leave/cancel contract)
voice_typing/bulk_controller.py        # READ-ONLY caller (all three call sites landed)
tests/test_ime_target.py               # APPEND ~20 lifecycle cases
tests/test_ime_protocol.py             # APPEND cancel-validation cases
tests/test_ime_host.py                 # REPLACE test_cancel_reserved + APPEND _cancel cases
tests/ime_acquire_lab.py               # pattern reference for the optional lab (untouched)
# NOT YET: tests/ime_finalize_lab.py
```

### Desired Codebase tree

```bash
voice_typing/ime/target.py          # the COMPLETE DeliveryTarget implementation (ready for T4)
voice_typing/ime/protocol.py        # cancel live in the vocabulary
voice_typing/ime/ime_host.py        # cancel dispatched + confirmed
tests/test_ime_target.py            # full lifecycle matrix
tests/test_ime_protocol.py          # cancel validation
tests/test_ime_host.py              # cancel dispatch/confirm
tests/ime_finalize_lab.py           # optional env-gated GTK lifecycle row
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — OWNERSHIP ENDS, BYTES REMAIN. finalize's settle and the utterance-switch reset
#   clear _last_applied_span (and _owned_utterance) but NEVER _inserted_bytes: the caret sits
#   PAST everything we committed, and recheck's math is binding.cursor_bytes + _inserted_bytes.
#   Resetting bytes after a settle breaks the very next recheck ("caret moved" ⇒ delivery stops).
# CRITICAL #2 — THE OWNED SPAN IS A SUFFIX OF OUR COMMITTED RANGE. Anchor every verified delete
#   at [binding.cursor_bytes + _inserted_bytes − owned_bytes, +owned_bytes) — i.e. the
#   owned_bytes immediately BEFORE the expected caret — NOT at binding.cursor_bytes. In S2's
#   single-utterance world _inserted_bytes == owned_bytes so the two coincide (S2's tests stay
#   green); after a settled finalize they differ and the binding-caret anchor would verify (and
#   delete) USER/prior-utterance text. Same fix inside show()'s correction branch via the
#   generalized _owned_region_intact.
# CRITICAL #3 — THE CORRECTION ADVANCE BECOMES SUFFIX-AWARE: _inserted_bytes =
#   _inserted_bytes − owned_bytes + span_bytes (S2's `= span_bytes` is the one-utterance special
#   case). Cancel is the span_bytes=0 case: _inserted_bytes -= owned_bytes. One invariant, three
#   call sites — never hand-roll a fourth.
# CRITICAL #4 — NO len(tail)−1 COMPENSATION. The legacy evdev path subtracts the physical
#   keystroke (daemon.py:1966); bulk cancel has NO physical key — before == owned_bytes EXACTLY.
#   Test-pinned (a −1 would leave one owned character stranded in the field).
# CRITICAL #5 — ZERO-DIFF FINALIZE SENDS NOTHING. rendered_equal ⇒ UNCHANGED with ZERO requests:
#   a commit that "re-confirms" matching text is the visibly-change-or-duplicate defect R.3
#   forbids. No request ⇒ no side effects, period.
# CRITICAL #6 — REJECTED FINAL = SELF-HEAL, NEVER ERASE. The controller never calls finalize on
#   a rejected/dropped final (on_final_dropped: boundary only). The adapter's utterance-switch
#   guard resets the owned span when a DIFFERENT utterance arrives, so the next partial INSERTS —
#   the abandoned words are never deleted by us. Test: partial u1 applied → no finalize →
#   show(u2) ⇒ before=0.
# CRITICAL #7 — LEAVE RUNS OUTSIDE THE OP RUNNER. Controller stop() calls target.leave()
#   directly (bulk_controller.py:361) — the adapter must bound its own host request
#   (timeout=_SHOW_TIMEOUT_S), never raise (wrap the request; a dead proc is a logged warning),
#   and clear the binding FIRST so even a wedged call cannot leave us writing after stop.
#   Return None; second call = pure no-op; NO field writes, and nothing may be written into a
#   newly focused field later (post-leave everything refuses "not acquired").
# CRITICAL #8 — UNCHANGED-FOR-EMPTY-OWNED IS LOAD-BEARING. The controller calls target.cancel
#   only when a partial was QUEUED — it may not yet be DISPATCHED, so the adapter's owned span
#   can still be "". UNCHANGED keeps delivery active (G2 trace_07 repeated-cancel pin);
#   REFUSED would stop it for no reason. Unbound (post-leave) ⇒ REFUSED "not acquired".
# CRITICAL #9 — STATE ADVANCES ONLY ON APPLIED (S1's rule, unchanged). refused/unknown leave
#   every field untouched; a repeated cancel recomputes the same before vs the last APPLIED span.
# CRITICAL #10 — UTF-8 BYTES EVERYWHERE, ORIGINAL STRINGS. before, _inserted_bytes, and the
#   intact-slice all use .encode("utf-8") on ORIGINAL strings (astral char = 4 — test-pinned).
# CRITICAL #11 — UNCERTAIN RANGE ⇒ STOP. A cancel whose recheck or _owned_region_intact fails
#   REFUSES (the controller disarms) — never attempt repair, never delete a best guess
#   (R.5). No explicit cancel byte cap: the delete carries only a count; the 64 KiB verify
#   snapshot bounds what is verifiable (truncated past the range end ⇒ refuse).
# GOTCHA #12 — the closed-set is DEFENSIVE: the controller already discards duplicate finals and
#   late post-final partials at enqueue (_closed). The adapter's _closed_utterances turns a leak
#   into an honest refusal ("utterance closed") instead of a second mutation. Bounded by
#   utterances-per-arm; cleared on acquire.
# GOTCHA #13 — LOGS: counts/times/flags ONLY (session, seq, result, live / before,
#   remaining_bytes, t_ms) — never span text (R.5).
# GOTCHA #14 — the empty commit_string('') in the host _cancel is the ONE mechanism not
#   lab-proven (R.2 proved the triple with non-empty text). The optional GTK lab row verifies;
#   if GTK misbehaves, drop the commit_string request (one line; delete+commit is still a legal
#   commit cycle per the vendored XML). Record honestly either way.
# GOTCHA #15 — the lab driver: no test_ prefix, IME_FINALIZE_LAB=1 gate, timeout 300, private
#   seat (xvfb-run + dbus-run-session + sway), mktemp scratch + EXIT trap (AGENTS.md Rule 3).
# GOTCHA #16 — GNU timeout + .venv/bin/python on EVERY command (AGENTS.md Rule 1; zsh aliases).
```

## Implementation Blueprint

### Data models and structure

No new dataclasses/enums. Adapter state additions (`__init__`):

```python
self._owned_utterance: "str | None" = None   # utterance owning _last_applied_span (None ⇒ none open)
self._closed_utterances: set[str] = set()    # settled by finalize/cancel (defensive late-stray refusal)
```

`acquire()` success path additions (alongside S1's three lines):
`self._owned_utterance = None; self._closed_utterances.clear()`.

Constants: none new (`_SHOW_TIMEOUT_S`/`_ACQUIRE_TIMEOUT_S`/`_COMMIT_CAP_BYTES` reused).

### `show()` top-of-method guard (the ONLY insert into S2's landed body)

```python
        # (P1.M4.T3.S3) utterance bookkeeping — ownership is per-utterance, bytes are not.
        if utterance in self._closed_utterances:
            self.last_reason = "utterance closed"      # settled final/cancel — never a 2nd op
            return ShowResult.REFUSED
        if self._owned_utterance is not None and utterance != self._owned_utterance:
            # The previous utterance's final never came (dropped/rejected — the controller's
            # on_final_dropped makes NO finalize call): its visible words STAY on screen; we
            # merely stop owning them. NEVER a delete here (rejected finals never auto-erase).
            self._last_applied_span = ""               # ownership ends; _inserted_bytes KEEPS
        self._owned_utterance = utterance
```

### `_owned_region_intact` anchor generalization (1-line change inside S2's helper)

```python
        # (P1.M4.T3.S3) the owned span is the SUFFIX of our committed range: the owned_bytes
        # immediately before the expected caret. In the single-utterance world
        # (_inserted_bytes == owned_bytes) this is exactly S2's binding.cursor_bytes anchor.
        end = binding.cursor_bytes + self._inserted_bytes
        start = end - len(owned.encode("utf-8"))
        ...
        return raw[start:end] == owned.encode("utf-8")
```

### Correction-branch advance (inside S2's correction path; behavior-identical in S2's world)

```python
            advance = lambda: (setattr(self, "_last_applied_span", span),
                               setattr(self, "_inserted_bytes",
                                       self._inserted_bytes - owned_bytes + span_bytes))
```

### `finalize()` / `leave()` / `cancel()` (implement verbatim)

```python
    def finalize(self, session: int, utterance: str, seq: int,
                 expected_revision: int, span: str) -> ShowResult:
        """R.3 finalize (P1.M4.T3.S3): settle the utterance.

        Matching final ⇒ NO further edit (zero requests — commit side effects cannot change or
        duplicate text that is already visible); ownership ends. Differing final ⇒ ONE
        replacement (the landed insert/correction paths, delegated). No preceding partial ⇒
        inserts once (logged live=false — the missed-live-update evidence hook; counting is
        M6.T4/G5). _inserted_bytes NEVER resets here: committed text stays, caret math survives.
        """
        if self._binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        if utterance in self._closed_utterances:
            self.last_reason = "utterance closed"       # duplicate final — never a 2nd op
            return ShowResult.REFUSED
        live = bool(self._last_applied_span) and self._owned_utterance == utterance
        result = self.show(session, utterance, seq, expected_revision, span)
        if result in (ShowResult.APPLIED, ShowResult.UNCHANGED):
            self._last_applied_span = ""                # ownership ENDS (R.3); bytes remain
            self._owned_utterance = None
            self._closed_utterances.add(utterance)
            logger.info("ime finalize settled: session=%s seq=%s result=%s live=%s",
                        session, seq, result.value, live)
        return result

    def leave(self) -> None:
        """R.3 leave (P1.M4.T3.S3): stop preserving the last visible words — NO post-stop
        writes anywhere, including a newly focused field. Never raises; idempotent; the host
        request is best-effort (releases any grab; the host keeps serving)."""
        binding = self._binding
        self._binding = None                            # FIRST: nothing may write after this
        self._last_applied_span = ""
        self._owned_utterance = None
        if binding is None:
            return                                      # already left — pure no-op
        try:
            self._proc.request("leave", timeout=_SHOW_TIMEOUT_S)
        except Exception:                               # dead/raising proc must not propagate
            logger.warning("ime leave: host request raised")   # one line, no text (R.5)

    def cancel(self) -> ShowResult:
        """R.3 cancel (P1.M4.T3.S3): remove the owned fragment in ONE operation; keep
        listening. NO len(tail)-1 physical-key compensation (legacy-only, daemon.py) —
        before == owned_bytes EXACTLY. Uncertain range ⇒ REFUSED (stop, never repair)."""
        binding = self._binding
        if binding is None:
            self.last_reason = "not acquired"
            return ShowResult.REFUSED
        if rendered_equal(self._last_applied_span, ""):
            self.last_reason = "nothing pending"        # queued-but-undispatched partial ⇒ fine
            return ShowResult.UNCHANGED                 # NO request (G2 trace_07 pin)
        owned = self._last_applied_span
        owned_bytes = len(owned.encode("utf-8"))        # wire units; ORIGINAL string
        ok, reason, _rev = self.recheck(binding, inserted_bytes=self._inserted_bytes)
        if not ok:                                      # caret must END the owned range —
            self.last_reason = f"recheck: {reason}"     # the delete counts backward from it
            return ShowResult.REFUSED
        if not self._owned_region_intact(binding, owned):
            self.last_reason = "owned region diverged"  # uncertain range ⇒ stop (R.5)
            return ShowResult.REFUSED
        r = self._proc.request("cancel", timeout=_SHOW_TIMEOUT_S, before=owned_bytes)
        if r is None:
            self.last_reason = "ime no reply"
            logger.warning("ime cancel: no reply (before=%d)", owned_bytes)
            return ShowResult.UNKNOWN
        result = r.get("result")
        if result == "applied":
            u, self._owned_utterance = self._owned_utterance, None
            if u is not None:
                self._closed_utterances.add(u)
            self._last_applied_span = ""
            self._inserted_bytes -= owned_bytes         # caret moved BACK by owned_bytes
            self.last_reason = ""
            logger.info("ime cancel applied: before=%d remaining_bytes=%d t_ms=%s",
                        owned_bytes, self._inserted_bytes, r.get("t_ms"))
            return ShowResult.APPLIED
        if result == "refused":
            self.last_reason = "host refused"
            return ShowResult.REFUSED
        self.last_reason = f"host result {result!r}"
        logger.warning("ime cancel unknown: result=%r", result)
        return ShowResult.UNKNOWN
```

### Host `_cancel` + protocol lift

```python
# protocol.py
REQUEST_CMDS = ("acquire", "show", "verify", "leave", "ping", "cancel")  # cancel live (T3.S3)
# validate_request: DELETE the `if cmd == "cancel": return None, "cancel reserved..."` branch; ADD:
    if cmd == "cancel":
        before = obj.get("before")
        if not isinstance(before, int) or isinstance(before, bool) or before < 0:
            return None, "cancel requires 'before' as a non-negative int"

# ime_host.py — dispatch entry + handler (mirrors _show's posture; NO text payload):
    if cmd == "cancel":
        return self._cancel(rid, obj)

    def _cancel(self, rid, obj: dict) -> dict:
        if not self.activated:
            return protocol.make_reply(rid, "cancel", result="refused", t_ms=0.0)
        t0 = time.monotonic()
        dones_before = self.dones
        try:
            before = int(obj.get("before", 0) or 0)
            self.c.request(self.im, IFACE, "delete_surrounding_text", before, 0)
            self.c.request(self.im, IFACE, "commit_string", "")   # Gotcha #14 — lab-proven triple,
            self.c.request(self.im, IFACE, "commit", self.dones)  # empty-text variant
        except Exception:                               # wire send failed ⇒ unknown; never retry
            return protocol.make_reply(rid, "cancel", result="unknown",
                                       t_ms=round((time.monotonic() - t0) * 1000, 3))
        deadline = time.monotonic() + SHOW_CONFIRM_WAIT  # same bounded confirm loop as _show
        while True:
            self._drain_events()
            if self.dones > dones_before:
                return protocol.make_reply(rid, "cancel", result="applied",
                                           t_ms=round((time.monotonic() - t0) * 1000, 3))
            if self.stopped or time.monotonic() >= deadline:
                return protocol.make_reply(rid, "cancel", result="unknown",
                                           t_ms=round((time.monotonic() - t0) * 1000, 3))
            time.sleep(0.01)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT (no mutation) — STOP if the base is missing
  - RUN:
      grep -q "_owned_region_intact" voice_typing/ime/target.py && echo "S2 landed" \
        || echo "PREFLIGHT FAIL: P1.M4.T3.S2 not landed — STOP"
      ! grep -q "correction not implemented" voice_typing/ime/target.py || echo "PREFLIGHT FAIL"
      grep -n "SHOW_CONFIRM_WAIT\s*=" voice_typing/ime/ime_host.py   # RECORD (expect 0.22)
      timeout 180 .venv/bin/python -m pytest tests/test_ime_target.py tests/test_ime_host.py \
        tests/test_ime_protocol.py tests/test_ime_wlwire.py tests/test_ime_manager.py \
        tests/test_bulk_delivery.py tests/test_bulk_controller.py tests/test_g2_bulk_gate.py -q | tail -1
  - EXPECTED: S2 landed + all green (record any pre-existing red and proceed only if unrelated).

Task 1: tests/test_ime_protocol.py + tests/test_ime_host.py FIRST (TDD RED).
  protocol: cancel now VALID (no reserved error); missing 'before' → error; before="7" (str) /
    negative / boolean → error; before=0 → valid; SHOW_FIELDS unchanged for show.
  host: REPLACE test_cancel_reserved with the live-dispatch matrix — scripted dones increment →
    result applied + t_ms; not-activated → refused with ZERO wire sends; wire exception →
    unknown; missing before → error reply, host keeps serving (the _feed/_make_host pattern).

Task 2: EVOLVE voice_typing/ime/protocol.py + voice_typing/ime/ime_host.py per the Blueprint
        → the Task 1 suites GREEN.

Task 3: tests/test_ime_target.py — APPEND the lifecycle matrix (reuse _FakeProc/_snap/_verify/
        _bound; script the verify replies with cursor == binding.cursor + _inserted_bytes so
        recheck passes unless the case says otherwise). Cases:
        finalize-matching: insert "hello world" (u1, applied) → finalize(span="hello world") →
          UNCHANGED, ZERO new requests, _last_applied_span=="" , _owned_utterance is None,
          "u1" in _closed_utterances, _inserted_bytes UNCHANGED (the bytes-remain pin);
        finalize-differing: owned "helllo w" → finalize("hello world") → ONE show request
          before==8 text=="hello world" → applied → owned reset, _inserted_bytes == 11 (fresh
          acquisition: prior==0), closed;
        finalize-multi-utterance-bytes: u1 settled at B1 bytes → u2 partial applied → u2
          correction finalize → _inserted_bytes == B1 + len(span.encode()) (NOT span_bytes —
          the suffix-aware advance pin), verify slicing anchored at caret−owned_bytes;
        finalize-no-partial: fresh acquire, finalize(span="ok") → ONE insert before==0
          text=="ok" → APPLIED (caplog contains "live=False");
        post-finalize-new-utterance: u1 settled → show(u2, "yes") → INSERT before==0
          delta=="yes", recheck passes against cumulative bytes;
        rejected-final: show(u1,"abc") applied → NO finalize → show(u2,"x") → INSERT before==0
          — never a delete of u1's words (the auto-erase pin);
        closed-utterance: finalize(u1) settled → show(u1,...) and finalize(u1,...) again →
          REFUSED "utterance closed", zero requests;
        finalize not-acquired (leave first) → REFUSED;
        leave: after an applied show → ONE request cmd=="leave" timeout==0.25 → binding None →
          show/finalize REFUSE "not acquired", cancel REFUSES too; NO show/cancel requests
          after the leave (proc.calls tail pin); leave() returns None; second leave → no
          request;
        leave-dead-proc: _FakeProc whose request raises → leave() still returns None, binding
          cleared, nothing raised;
        cancel-nothing-owned: bound, no span → UNCHANGED, zero requests, last_reason
          "nothing pending";
        cancel-owned: insert "wait no" (7 B) → cancel → ONE request cmd=="cancel"
          before==7 (EXACTLY — the no−1 pin) timeout==0.25 → applied → owned reset, utterance
          closed, _inserted_bytes reduced by 7; THEN show(u2,"again") → insert passes recheck
          (the accounting round-trip pin);
        cancel-utf8: owned "héllo 😀" → before == len(b"h\xc3\xa9llo \xf0\x9f\x98\x80") == 10;
        cancel-owned-diverged: verify text mismatched in the owned slice → REFUSED "owned
          region diverged", zero cancel requests, state untouched;
        cancel-recheck-caret-moved → REFUSED "recheck: caret moved";
        cancel-reply-None → UNKNOWN, state untouched; retry recomputes before==same;
        cancel-host-refused → REFUSED;
        cancel-after-leave → REFUSED "not acquired";
        show-utterance-switch does NOT reset _inserted_bytes (assert via a follow-up recheck
          passing with cumulative bytes).

Task 4: EVOLVE voice_typing/ime/target.py per the Blueprint (show-top guards + anchor fix +
        suffix-aware advance + the three methods + state) → the WHOLE combined suites GREEN
        (incl. S1/S2 — the three edits must be byte-identical in their world).

Task 5: CREATE tests/ime_finalize_lab.py (optional evidence; mirror tests/ime_acquire_lab.py):
        gate IME_FINALIZE_LAB=1 (else print "skipped" exit 0); private seat (xvfb-run +
        dbus-run-session + sway), mktemp + EXIT trap; rows: (a) insert "hel" → finalize
        "hello world" → field text ends "hello world", caret at end, edit_count grew by ≤2;
        (b) finalize the SAME span again → edit_count grew by 0 (zero events); (c) partial
        applied → cancel → fragment gone, caret back to pre-utterance position, ONE edit;
        (d) leave → refocus/re-activate → assert ZERO further text changes. ONE verdict line
        per row; record the empty-commit_string behavior honestly (Gotcha #14). timeout 300.

Task 6: VALIDATE (below). Commit if directed:
        "P1.M4.T3.S3: IM adapter lifecycle — finalize/leave/cancel; ownership ends, one-op
         cancel, no legacy compensation; protocol cancel live".
```

### Integration Points

```yaml
PACKAGE SEAM (consumed downstream; nothing wired here):
  - P1.M4.T4: "takeover revocation composes with leave() (binding cleared) and the closed-set;
               the adapter is COMPLETE — takeover is the remaining half"
  - P1.M5.T1: "the cooperating-editor adapter implements the same finalize/leave/cancel contract"
  - P1.M6.T2.S1: "constructs ImeTarget(ImeProcess(...)); routes voicectl cancel to
                  controller.cancel() BEFORE daemon.cancel's legacy backspace (the no−1 rule's
                  enforcement point)"
NOT WIRED: "no daemon/feedback/ctl/manager/wlwire/bulk_controller/bulk_delivery/config edits;
            no session recovery, no voicectl session, no G5 counting (M6.T4), no recorder
            abort (the controller's cancel purge + the daemon's host abort own 'drops buffered
            audio')."
```

## Validation Loop

```bash
cd /home/dustin/projects/voice-typing
# L1 syntax + purity
timeout 60 .venv/bin/python -m py_compile voice_typing/ime/target.py voice_typing/ime/protocol.py \
  voice_typing/ime/ime_host.py tests/test_ime_target.py tests/test_ime_protocol.py \
  tests/test_ime_host.py tests/ime_finalize_lab.py && echo "L1 OK"
env -u WAYLAND_DISPLAY .venv/bin/python -c "from voice_typing.ime.target import ImeTarget; \
  assert all(hasattr(ImeTarget, m) for m in ('finalize','leave','cancel')); print('pure import ok')"

# L2 the gate (S1+S2+protocol+host+controller+G2 consumers — zero regression)
timeout 180 .venv/bin/python -m pytest tests/test_ime_target.py tests/test_ime_host.py \
  tests/test_ime_protocol.py tests/test_ime_wlwire.py tests/test_ime_manager.py \
  tests/test_bulk_delivery.py tests/test_bulk_controller.py tests/test_g2_bulk_gate.py -q | tail -1
# Expected: 0 failed. A bulk_controller/G2 failure ⇒ the adapter's mapping/state is wrong.

# L3 fake duplex smoke (no compositor) — the full lifecycle end-to-end
timeout 60 .venv/bin/python - <<'EOF'
from voice_typing.ime.target import ImeTarget
from voice_typing.bulk_delivery import ShowResult
state = {"text": "hi ", "cursor": 3, "dones": 5}
class P:
    def __init__(s): s.calls = []
    def request(s, cmd, timeout=None, **f):
        s.calls.append(cmd)
        if cmd == "acquire": return {"ok": True, "handle": "im", "revision": 2,
            "text": state["text"], "cursor": state["cursor"], "anchor": state["cursor"],
            "snapshot_truncated": False}
        if cmd == "verify": return {"ok": True, "activated": True, "dones": state["dones"],
            "text": state["text"], "cursor": state["cursor"], "anchor": state["cursor"],
            "snapshot_truncated": False}
        if cmd in ("show", "cancel"):
            if cmd == "show":
                delta, before = f["text"], f.get("before", 0)
                cut = len(state["text"].encode()) - before
                state["text"] = state["text"].encode()[:cut].decode() + delta
            else:
                cut = len(state["text"].encode()) - f["before"]
                state["text"] = state["text"].encode()[:cut].decode()
            state["cursor"] = len(state["text"].encode())
            state["dones"] += 1
            return {"result": "applied", "t_ms": 12.0}
        return {"ok": True}
p = P(); t = ImeTarget(p); assert t.acquire().ok
assert t.show(1, "u1", 1, 2, "helllo w") is ShowResult.APPLIED
assert t.finalize(1, "u1", 2, 3, "hello world") is ShowResult.APPLIED      # correction settle
assert t.show(1, "u2", 1, 4, "yes") is ShowResult.APPLIED                 # post-finalize insert
assert t.finalize(1, "u2", 2, 5, "yes") is ShowResult.UNCHANGED           # match ⇒ 0 events
assert state["text"] == "hi hello world yes"
assert t.show(1, "u3", 1, 6, "wait no") is ShowResult.APPLIED
assert t.cancel() is ShowResult.APPLIED                                   # ONE op, before==7
assert t.cancel() is ShowResult.UNCHANGED                                 # nothing pending
assert state["text"] == "hi hello world yes" and state["cursor"] == 18    # exact removal
t.leave()
assert t.show(1, "u4", 1, 8, "x") is ShowResult.REFUSED                   # no post-stop writes
print("L3 OK", p.calls)
EOF
# Expected: L3 OK — acquire, verify, show, [verify, verify,] show, show, verify, show,
# verify, verify, cancel, leave — zero writes after the leave.

# L4 scope guards + optional evidence
git status --porcelain   # ONLY: target.py(M) protocol.py(M) ime_host.py(M) test_ime_target.py(M)
                         #        test_ime_protocol.py(M) test_ime_host.py(M) ime_finalize_lab.py
git diff --stat voice_typing/ime/wlwire.py voice_typing/ime/manager.py voice_typing/bulk_delivery.py \
  voice_typing/bulk_controller.py voice_typing/daemon.py voice_typing/feedback.py voice_typing/ctl.py \
  tools/im-lab | wc -l   # 0
timeout 120 .venv/bin/python -m pytest tests/ -q --collect-only 2>/dev/null | grep -c ime_finalize_lab || echo "ok: not collected"
timeout 300 env IME_FINALIZE_LAB=1 .venv/bin/python tests/ime_finalize_lab.py || echo "lab row failed/skipped — record honestly (Gotcha #14)"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1–L4 green; the combined suites pass (S1 insert + S2 correction + protocol + host +
      controller + G2 — zero regression); scope guard clean (fenced files untouched).
- [ ] finalize: match ⇒ UNCHANGED with zero requests + ownership ends; differ ⇒ ONE replacement
      (delegated, anchored correctly post-finalize); no-partial ⇒ one insert + `live=false`;
      rejected-final ⇒ next utterance inserts (never deletes the abandoned words).
- [ ] leave: binding cleared before the host request; never raises; idempotent; NO post-stop
      writes (post-leave calls all refuse "not acquired").
- [ ] cancel: one op; `before == len(owned.encode())` exactly (UTF-8, astral = 4, NO −1);
      uncertain ⇒ refused; applied ⇒ accounting round-trip (follow-up insert passes recheck);
      empty-owned ⇒ UNCHANGED (stays active).
- [ ] The three S2-world edits verified byte-identical there (S2's correction tests green).
- [ ] Protocol cancel validated (int ≥ 0); host dispatch/confirm mirrors `_show`; the reserved
      test replaced; lab not collected by default.
- [ ] `last_reason` taxonomy pinned; logs = counts/times/flags only.

### Feature Validation
- [ ] All success criteria from "What" met; L3 lifecycle smoke exercises the exact PRD
      narrative (settle → new utterance → match-finalize → cancel → leave).
- [ ] Error cases handled with proper taxonomy; no retries of unknown; no text in logs.

### Code Quality Validation
- [ ] Follows the existing adapter patterns (guard-first, honest mapping, state-only-on-applied);
      file placement matches the desired tree; no scope creep into T4/M5/M6.

## Anti-Patterns to Avoid

- ❌ Don't reset `_inserted_bytes` on settle/switch/cancel-switch — only the owned-span
      bookkeeping resets; the bytes ARE the caret arithmetic (Critical #1).
- ❌ Don't anchor a verified delete at `binding.cursor_bytes` once a finalize has settled — the
      owned span is the suffix before the caret; the binding-caret anchor eats prior/user text
      (Critical #2).
- ❌ Don't copy the legacy `len(tail)−1` compensation into bulk cancel — no physical key fires
      here (Critical #4).
- ❌ Don't send ANY request for a matching final, and don't "re-confirm" after cancel — zero
      events means zero requests (Critical #5, event-count law).
- ❌ Don't erase a dropped final's words — ownership ends by RESET, never by deletion
      (Critical #6).
- ❌ Don't let leave() raise, hang, or write — it runs outside the op runner (Critical #7).
- ❌ Don't reimplement the insert/correction logic inside finalize — delegate to show() (drift
      between the two IS the duplicate-visible-edit bug class).
- ❌ Don't retry an unknown cancel, don't log span text, don't touch the fenced files, don't
      run anything without GNU timeout + `.venv/bin/python`, don't let pytest collect the lab.
- ❌ Don't chase takeover detection, session recovery, or latency counting here — T4/M6 own
      them; record, don't implement.
