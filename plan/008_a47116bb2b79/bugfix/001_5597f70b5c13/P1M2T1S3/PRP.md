# PRP — P1.M2.T1.S3: Align changed-span field observations and expose attribution gaps

## Goal

**Feature Goal**: Upgrade the pure G5 metrics engine (`tests/g5_timing_support.py`) from
positional-block / next-callback-window matching to a **bounded changed-span attribution
contract**. Every update observation gets a calibrated label (`matched` / `missing` /
`superseded` / `no_op` / `ambiguous`; orphan frames: `unpaired`); word first-visibility is decided
by **changed-span alignment against independent field snapshots** (fixing the three defects the
architecture doc names: late frames charged to the next callback, lost previous-state snapshots,
positional matching overstating Pi delay on rewrites); `aggregate`/report expose **coverage, miss
and ambiguity counters + provenance** (partial source, clock/cap failures). Floors, latency caps,
backlog and dump rules are **byte-preserved**; the zero-edit oracle survives with the
delayed-frame carve-out. All work is mock-clock synthetic traces — **no live GUI, no daemon, no
CUDA**.

**Deliverable** (2 code files + 1 doc append):
1. `tests/g5_timing_support.py` — (a) new `ReadyEvent` dataclass + legacy-tuple coercion;
   `ReplayRecord` gains optional provenance fields (`partial_source`, `anchor_text`, `capped`,
   `heartbeats`); (b) changed-span core: `changed_spans(old, new)`, span-aware
   `resolve_visibility_detailed()` (write-once first appearance, anchor/reset exclusion, ambiguity
   marking) with `resolve_visibility()` kept as its `.ts` projection; (c)
   `attribute_updates(update_ready, field_events)` returning labeled observations via the
   oldest-pending span-match rule, with `ready_to_frame()` reimplemented as a thin projection of it
   (signature and behavior preserved on all currently-defined cases); (d) `RouteMetrics`,
   `render_report_row`, `render_markdown` gain **additive** counters/keys; (e) docstrings for every
   changed type/function (Mode A).
2. `tests/test_g5_timing_support.py` — additive synthetic section: lost frames, revisions/repeats,
   burst inputs, unpaired events, anchor/reset, ambiguity, the zero-diff delayed-frame carve-out,
   producer/daemon stage + gen/utt/seq matching, clock/cap failure counters, and the compat
   contract (the 14 existing tests stay green, untouched).
3. `tests/G5_TIMING_EVIDENCE.md` — **append-only** "Measurement method" section documenting the
   labels, counters and defect fixes; historical numbers untouched; no route-verdict-shaped table.

**Success Definition**:
- (a) All 14 existing tests in `tests/test_g5_timing_support.py` pass **unchanged** (they are the
  historical-comparability contract; do not edit them to fit new code).
- (b) The new defect-pinning tests pass: a delayed frame is charged to the **older** pending
  update (never to a newer identical callback ⇒ no false zero-diff); a superseded (coalesced-away)
  update is `superseded`, not `missing`; an `unpaired` frame is counted, never a fast sample; a
  rewrite keeps a word's FIRST appearance without overstating delay; genuinely ambiguous
  repeats are counted, not guessed.
- (c) Verdict semantics unchanged: `aggregate()` over legacy tuple-shaped records yields the same
  verdict/failures as before for every existing test scenario (floors `MIN_COUNT=100`, caps
  `SPEECH_MED_MS/SPEECH_P95_MS/READY_P95_*`, `SUSTAIN_*`, `DUMP_*`, zero-edit law — all constants
  and rules byte-identical).
- (d) Consumers get the contract: S4 (route runner) can populate
  stage/gen/utt/seq/disposition/ack_ts; S6 (paired A/B) gets calibrated labels + `partial_source`
  provenance; T2.S3 (qualification) gets coverage/miss counters in the report rows.
- (e) `git status` shows ONLY those 3 files.

## User Persona

Not applicable (internal measurement engine; no operator-facing surface). DOCS: Mode A — update
docstrings of every changed support type/function and append the measurement-method note to
`tests/G5_TIMING_EVIDENCE.md`.

## Why

- **The architecture doc mandates it** (bulk_delivery_gate.md § G5, verbatim): "`ready_to_frame`
  windowing can charge a late change to the next callback or disappear unpaired; its
  previous-state tracking can lose the prior snapshot. `resolve_visibility` assumes
  position/contiguous blocks and can overstate Pi delay on rewrites. Use changed-span aware
  alignment against independent field snapshots; preserve first genuine visibility for
  repeated/corrected words, distinguish initial anchored text from new insertions, and expose
  misses, ambiguous matches, superseded/no-op updates, clock/cap failures."
- **S4/S6/T2.S3 cannot run honestly without it**: the paired callback comparison (S6) will fire
  rapid update/repeat/revision patterns precisely where today's engine misattributes; qualifying
  the production source (T2.S3) requires distinguishing "lost during coalescing" from "late
  upstream partial" from "late field visibility" — impossible without labeled observations.
- **R.5/R.7 discipline**: `FieldEvent` stays the ONLY visibility truth; an ACK (target `APPLIED`)
  is a cross-check, never a frame ("No sample may be credited merely because target ACKs"); an
  unobserved edit does not become a fast event.
- **The identity plumbing already exists** (recorder_host `_RelayIds` gen/utterance stamping,
  daemon `_bulk_next_seq`, S1's `partial_callback` provenance) — only the engine's contract lacks
  the fields to receive it.

## What

### The attribution contract (normative)

**ReadyEvent** (coerced from legacy `(ts, text, kind)` tuples — coercion is total and lossless for
tuples): `t: float` (monotonic), `text: str`, `kind: str` ("partial"|"final"), `stage: str =
"daemon"` ("producer" stamps arrive before IPC — a separate checkpoint, never mixed),
`gen: int | None = None`, `utt: int | None = None`, `seq: int | None = None` (identity where
available; match by it when present), `disposition: str = ""` (""|"dispatched"|"coalesced"|"dropped"
— controller fate, where recorded), `ack_ts: float | None = None` (target APPLIED cross-check only).

**Changed spans**: `changed_spans(old_text, new_text) -> list[AddedSpan]` over normalized tokens —
the added/replaced regions of consecutive INDEPENDENT field snapshots (anchor text counts as the
initial baseline; the first event's additions are measured against `anchor_text`/`""`). A
reference word becomes first-visible when its normalized token first appears in an AddedSpan —
presence in pre-existing text never counts.

**Visibility (span-aware)**: `resolve_visibility_detailed(words, field_events, anchor=0,
anchor_text="", ...) -> VisibilityResult` with `.ts: list[float|None]` (the exact current
`resolve_visibility` return), plus `.ambiguous: list[int]` (reference words whose appearance is
genuinely indeterminate — e.g. the same token appears in multiple candidate AddedSpan positions),
plus reset handling: an event whose text reverts to/below the anchor baseline is a **reset** — it
never un-sees (write-once `seen`), never generates phantom misses, and re-added copies after a
reset are matched by ordered position within the bounded window else marked ambiguous. Retain:
first-appearance across revisions/repeats, one-word substitution rescue, the bounded
`window_fwd=12` / `window_back=24` scan, and the anchor token-position floor (a rewrite can render
following words up to `window_back` early). `resolve_visibility(...)` becomes exactly
`resolve_visibility_detailed(...).ts`.

**Attribution**: `attribute_updates(update_ready, field_events, anchor_text="") ->
AttributionResult` — `.observations: list[Observation]` (one per ReadyEvent), `.frames_unpaired:
int`, plus the existing `(FrameSample, violations)` projection. Core rules:
1. Build the changed-frame series from consecutive field snapshots (`a.text != b.text` ⇒ frame at
   `b.t` with its AddedSpans) — the previous snapshot is never lost (rolling last-text, seeded
   with `anchor_text`, not `""`).
2. A frame is charged to the **oldest pending** update whose expected added content matches the
   frame's AddedSpans (content matching over normalized tokens, bounded look-back), where "pending"
   = not yet matched and not superseded — NOT merely "the update whose [ts, next-ts) window
   contains the frame". A late frame therefore lands on its true (older) update; a burst's single
   frame may satisfy several pending updates whose combined span it paints (all matched, one ts).
3. `no_op`: an update whose text is normalized-equal to the current observed field state. Any
   frame attributable to it violates the zero-diff law — EXCEPT a frame matching an older pending
   update's span (the delayed-frame carve-out: "do not charge a delayed frame to a newer identical
   callback").
4. `superseded` (explicit when `disposition` says coalesced/replaced; inferred otherwise when a
   later same-gen/utt update's text subsumes the older's new content as a normalized prefix): the
   update's span was never required to paint — not `missing`, no sample, counted.
5. `missing`: dispatched, not superseded, no matching frame before end-of-record — counted, never
   a zero-latency sample (Gotcha #7).
6. `ambiguous`: a frame/word that could belong to multiple updates (rapid/repeated frames the span
   rule cannot separate) — excluded from latency samples, counted.
7. `unpaired`: a changed frame with no attributable pending update (before the first update, or
  after all are settled) — counted, never a fast sample.
8. `ready_to_frame(update_ready, field_events)` = the `(FrameSamples, violations)` projection of
   `attribute_updates`; identical results on every case the current tests define.

**Counters/provenance (additive)**: `RouteMetrics` gains
`updates_total, updates_matched, updates_missing, updates_superseded, updates_no_op,
updates_ambiguous, frames_unpaired, words_ambiguous, clock_failures, cap_failures` (ints, default
0). `ReplayRecord` gains `partial_source: str = ""`, `anchor_text: str = ""`, `capped: bool =
False`, `heartbeats: list[tuple[float, float]] = field(default_factory=list)`.
`aggregate()` folds the counters; a record whose `heartbeats` fail `heartbeat_ok` or whose `capped`
is True increments the failure counters and appends a REPORTED failure string (a clock/cap failure
must not be averaged away — it's evidence, and per the doc you "report unverifiable metrics rather
than imputing a pass"; it does NOT auto-fail the route by itself unless samples were lost — the
misses/count floors already handle that). `render_report_row` gains the new JSON keys additively;
`render_markdown` keeps its existing columns and may append trailing counter columns (route +
verdict columns stay first — `g6_assessment.py:parse_route_verdicts` compatibility).

### Success Criteria

- [ ] `ReadyEvent` exists; `ReplayRecord.update_ready` accepts both legacy tuples and `ReadyEvent`s
      (all existing tuple-based tests green without edits).
- [ ] `changed_spans`, `resolve_visibility_detailed`, `attribute_updates` exist and are pure
      stdlib (no `voice_typing` import).
- [ ] The 14 existing tests pass unchanged; new tests cover every rule above (see Task 1 list).
- [ ] `aggregate()` verdict + `failures` on existing scenarios byte-identical to today.
- [ ] Report row JSON/markdown carry the new counters; existing keys/columns unchanged.
- [ ] `tests/G5_TIMING_EVIDENCE.md` gains an appended measurement-method section; `git diff` on
      the historical tables is empty.
- [ ] Only the 3 files change.

## All Needed Context

### Context Completeness Check

_Pass._ The three defects, the replacement algorithm, the label taxonomy, the identity fields the
plumbing already provides, the compat contract (14 tests + tuple shape + thresholds), the evidence
append constraints (parser-safe), and the downstream consumer handoffs are all specified below
with file:line anchors.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/bulk_delivery_gate.md
  why: "§ G5 — the verbatim defect list + prescription this PRP implements (quoted in Why/What).
        § seams 1-3 — the gen/utterance/seq + coalescing disposition sources; 'Target APPLIED is
        not a frame'; 'producer ready and daemon receipt are separate checkpoints'; the gate rules
        that must stay byte-preserved."
  critical: "The whole item is the doc's sentence: 'Use changed-span aware alignment against
             independent field snapshots… expose misses, ambiguous matches, superseded/no-op
             updates, clock/cap failures. An unobserved edit does not become a fast event.'"
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S3/research/changed_span_attribution.md
  why: "Distilled evidence: current engine anatomy with defect locations, the landed identity
        plumbing (recorder_host _RelayIds/relay_identity, daemon _bulk_next_seq, S1's
        partial_callback provenance), consumer map (S4 populates / S6 compares / T2.S3 qualifies),
        parser constraint, purity rule."
  section: "all"
- file: tests/g5_timing_support.py
  why: "THE file to edit. ReplayRecord @~68; FieldEvent @~57; resolve_visibility @~168 (the
        positional matcher to re-base on spans); classify_pair/classify_events @~280; ready_to_frame
        @~300 (the window matcher with the lost-snapshot/late-frame defects — rolling cursor `ei`,
        `prev_text` starts \"\" for the first update); speech_to_visible/outstanding_series/
        sentence_end_dump/aggregate @~330-480; render_report_row/render_markdown @~520-616."
  pattern: "dataclass-per-concept + small pure functions + module-constant thresholds + honest
            failure strings; dual-import discipline documented in the module docstring."
  gotcha: "Pure stdlib only — do NOT import voice_typing (re-implement normalized equality locally
           via normalize_tokens; bulk_delivery.rendered_equal is reference semantics, not an import)."
- file: tests/test_g5_timing_support.py
  why: "The 14-test compat contract (median/p95 math, miss-not-zero, backlog sustain/transient,
        dump/no-dump, zero-edit, insert/correct split, shortfall, first-visibility retention,
        renderer bounds, anchor exclusion, heartbeat, shrinking correction). New section mirrors
        its helpers: FEED=1000.0, mk_words, mk_events, mk_record, growing_events."
  gotcha: "Do NOT edit existing tests; add an additive section. Header command:
           timeout 120 .venv/bin/python -m pytest tests/test_g5_timing_support.py -v"
- file: tests/g5_timing_lab.py
  why: "READ-ONLY reference for how records are built today (:929-990: anchor=flog.anchor(),
        events/updates filtered to [fs-0.5,end_t], update_ready tuples from wrap_ready :741-763 =
        daemon-receipt stamps; FieldLog cap=4000 @:161). S4 owns every edit here — none in this item."
  gotcha: "NEVER run the lab in this task (live desktop); never edit it either."
- file: voice_typing/recorder_host.py
  why: "READ-ONLY: module docstring :37-62 — relay payloads carry (session_gen, utterance_id);
        session_gen bumps at 'arm'; utterance id rotates at on_speech (late events keep their
        utterance's id); host.relay_identity valid inside on_final/on_partial. These are the
        gen/utt semantics the ReadyEvent fields must be able to carry."
- file: tests/G5_TIMING_EVIDENCE.md
  why: "The append target. Historical verdict table @14-19, thresholds table @81-92, failure
        registers @103+ — append a NEW '## Measurement method — changed-span attribution
        (P1.M2.T1.S3)' section AFTER the existing content; historical numbers untouched."
  gotcha: "g6_assessment.py:parse_route_verdicts scans verdict tables and overwrites duplicate
           route keys — the appended section must contain NO table with route+verdict columns
           (prose/bullets/label-definition lists only). Grep the parser before finalizing."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S1/PRP.md
  why: "The landed effective-source item: partial_source selector + 'partial_callback' in the
        spawn-ready payload — the provenance ReplayRecord.partial_source echoes for S6's A/B."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S2/PRP.md
  why: "The parallel in-flight item (daemon _BulkTargetBundle.start/_arm_work, README,
        test_daemon.py) — fully disjoint from this item's 3 files; do not touch its regions."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── tests/
│   ├── g5_timing_support.py        # EDIT: the engine (spans, ReadyEvent, attribution, counters, docstrings)
│   ├── test_g5_timing_support.py   # EDIT: additive synthetic section (existing 14 tests untouched)
│   ├── g5_timing_lab.py            # READ-ONLY (S4 owns; imports the support module — keep API compat)
│   ├── G5_TIMING_EVIDENCE.md       # EDIT: append measurement-method section only
│   └── g6_assessment.py            # READ-ONLY (parser constraint on the evidence append)
└── voice_typing/                   # READ-ONLY (S2 in flight; identity plumbing already landed)
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
tests/
├── g5_timing_support.py        # +ReadyEvent, +AddedSpan/changed_spans, +VisibilityResult/
│                               #  resolve_visibility_detailed, +Observation/AttributionResult/
│                               #  attribute_updates, +RouteMetrics counters, +ReplayRecord
│                               #  provenance fields, Mode-A docstrings
├── test_g5_timing_support.py   # +synthetic attribution section (lost/revision/burst/unpaired/
│                               #  anchor-reset/ambiguous/zero-diff-carveout/stage-identity/
│                               #  clock-cap counters/compat)
└── G5_TIMING_EVIDENCE.md       # +appended "Measurement method — changed-span attribution" section
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — PURE STDLIB, DUAL-IMPORT: no voice_typing imports (the module is imported by unit
#   tests AND the live lab). Normalized equality = local normalize_tokens comparison.
# CRITICAL #2 — COMPAT IS THE CONTRACT: the 14 existing tests, the legacy (ts,text,kind) tuple shape,
#   resolve_visibility's return type, ready_to_frame's signature/returns, every threshold constant,
#   and aggregate's verdict/failures on existing scenarios stay IDENTICAL. Additive only.
# CRITICAL #3 — WRITE-ONCE FIRST APPEARANCE: a retraction/repeat/reset never un-sees and never
#   overwrites a word's first ts (existing tests #10/#14 pin this).
# CRITICAL #4 — AN UNOBSERVED EDIT IS NOT A FAST EVENT: missing/superseded/ambiguous/unpaired
#   produce counters, never latency samples, never 0 ms laundering (Gotcha #7 lineage).
# CRITICAL #5 — OLDEST-PENDING MATCH, NOT WINDOW OWNERSHIP: a frame is charged by span content to
#   the oldest pending update; "do not charge a delayed frame to a newer identical callback" is a
#   TESTED rule, not a comment.
# CRITICAL #6 — BOUNDED SCAN: keep the window_fwd/window_back bounds (O(frontier×fwd) per event
#   across ~1k-token accumulating texts); ambiguity is the bounded honest answer, not deep search.
# CRITICAL #7 — ACK IS NOT A FRAME: ack_ts is recorded and reported as a cross-check only; FieldEvent
#   stays the only visibility truth (R.5 #3).
# CRITICAL #8 — STAGE SEPARATION: producer vs daemon stamps are distinct checkpoints (gen/utt/seq
#   matching when both exist); never average across stages.
# GOTCHA #9 — EVIDENCE APPEND: no route-verdict-shaped table in the new section (the g6 parser
#   overwrites duplicate route keys); never touch historical numbers.
# GOTCHA #10 — DISCIPLINE: full paths + functional `timeout` on every command (AGENTS.md); no live
#   GUI/daemon/CUDA anywhere in this task; pytest>=9.1.1; no ruff/mypy in this repo's flow.
```

## Implementation Blueprint

### Data models and structure

```python
@dataclass
class ReadyEvent:          # coerced from (ts, text, kind) tuples — lossless for legacy shape
    t: float; text: str; kind: str
    stage: str = "daemon"              # "producer" = pre-IPC checkpoint (separate clock)
    gen: int | None = None; utt: int | None = None; seq: int | None = None
    disposition: str = ""              # "" | "dispatched" | "coalesced" | "dropped"
    ack_ts: float | None = None        # target APPLIED cross-check — NEVER a frame

@dataclass
class AddedSpan:           # one added/replaced region between consecutive field snapshots
    pos: int; tokens: list[str]        # normalized-token slice + its position in the new text

@dataclass
class VisibilityResult:
    ts: list[float | None]             # EXACTLY today's resolve_visibility return
    ambiguous: list[int] = field(default_factory=list)   # reference-word indexes left honest-unmatched

@dataclass
class Observation:
    index: int; label: str             # matched|missing|superseded|no_op|ambiguous
    frame_ts: float | None = None      # first attributable changed-frame ts (matched only)
    detail: str = ""                   # calibrated why (e.g. "superseded by seq=7 (prefix)")

@dataclass
class AttributionResult:
    observations: list[Observation]; frames_unpaired: int
    samples: list[FrameSample] = field(default_factory=list); violations: int = 0
```

`ReplayRecord` adds `partial_source: str = ""`, `anchor_text: str = ""`, `capped: bool = False`,
`heartbeats: list[tuple[float, float]] = field(default_factory=list)` (all defaulted ⇒ every
existing constructor call and the lab's build site stay valid). `RouteMetrics` adds the 10 counter
ints (default 0).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: CREATE the failing tests FIRST (RED) — additive section in tests/test_g5_timing_support.py.
  - REUSE the file's helpers (FEED, mk_words, mk_events, mk_record, growing_events); new helpers
    for ReadyEvent streams (with gen/utt/seq/stage/disposition) and revision-trace builders.
  - CASE LIST (each asserts label + counter + sample-exclusion, using mock-clock synthetic traces):
    (1) lost frame: dispatched update, no field change ⇒ missing, no sample;
    (2) revision keeps first visibility WITHOUT overstatement (word re-added later keeps first ts;
        a positional matcher would have credited the late re-add);
    (3) repeat disambiguation: identical token in multiple AddedSpans ⇒ words_ambiguous, no guessed ts;
    (4) burst: 3 rapid updates (changed+identical interleaved), one late frame ⇒ charged to the
        OLDEST pending update; the newer identical callback gets NO zero-diff violation;
    (5) superseded explicit (disposition="coalesced") and inferred (later same gen/utt subsumes
        prefix) ⇒ superseded, not missing;
    (6) unpaired frame before first update / after all settled ⇒ frames_unpaired, no sample;
    (7) anchor/reset: pre-existing anchor_text excluded; mid-replay reset never un-sees, no
        phantom misses; re-added-after-reset follows the ordered-window/ambiguous rule;
    (8) zero-edit oracle preserved: rendered-identical update + attributable frame ⇒ violation;
        same frame matching an older pending span ⇒ carve-out (no violation);
    (9) producer/daemon stages: two ReadyEvents same (gen,utt,seq) different stages ⇒ paired as one
        logical update (daemon stage pairs frames; producer→daemon delta reported, not mixed);
    (10) clock/cap: heartbeats failing heartbeat_ok ⇒ clock_failures; capped=True ⇒ cap_failures;
         both appear in failures/report row;
    (11) compat: aggregate() over legacy tuple records equals today's verdict/failures strings;
         resolve_visibility(...) on the existing scenarios returns identical lists;
    (12) renderer: report row JSON gains the new keys; markdown stays ≤ MAX_REPORT_LINES and keeps
         route/verdict first columns.
  - RUN (RED): timeout 120 .venv/bin/python -m pytest tests/test_g5_timing_support.py -q \
      -k 'attribution or span or superseded or unpaired or carve'  → fails (no ReadyEvent today).

Task 2: EDIT tests/g5_timing_support.py — data model + spans (GREEN part 1).
  - ReadyEvent + _to_ready_events() coercion (tuples → ReadyEvent); ReplayRecord provenance fields;
    AddedSpan + changed_spans(old, new) over normalize_tokens (difflib.SequenceMatcher on token
    lists is acceptable stdlib; keep it bounded and deterministic); Mode-A docstrings.
  - RUN: the coercion/compat slices of Task 1 go green; existing 14 still green.

Task 3: EDIT tests/g5_timing_support.py — span-aware visibility (GREEN part 2).
  - resolve_visibility_detailed: per event, diff vs previous text (seeded with anchor_text); a
    reference word first-visible when its token first appears in an AddedSpan (token-position floor
    anchor, window_fwd/window_back retained, substitution rescue retained, write-once seen); reset
    detection (text reverts to/below anchor baseline) ⇒ no un-seeing, no phantom misses; ordered
    matching for repeated tokens within the bounded window else ambiguous.
  - resolve_visibility = resolve_visibility_detailed(...).ts (one-line projection — cannot drift).

Task 4: EDIT tests/g5_timing_support.py — attribution + aggregate/report (GREEN part 3).
  - attribute_updates per rules 1-8 in What; ready_to_frame = projection (same signature/returns);
    RouteMetrics counters; aggregate folds labels/counters + clock/cap failure strings;
    render_report_row/render_markdown additive keys/columns.
  - RUN: full file green: timeout 120 .venv/bin/python -m pytest tests/test_g5_timing_support.py -v

Task 5: EDIT tests/G5_TIMING_EVIDENCE.md (append-only) + final validation.
  - Append '## Measurement method — changed-span attribution (P1.M2.T1.S3)': the label taxonomy,
    the counters, the three fixed defects, the delayed-frame carve-out, the producer/daemon
    checkpoint separation, the purity/limits (ACK≠frame; pi-ghostty polled read ≠ rendering);
    explicit note that historical rows above predate this method and are NOT recomputed.
  - Validate per the loop below; git status shows only the 3 files.
```

### Implementation Patterns & Key Details

```python
# PATTERN — the attribution core (oldest-pending span match; NOT window ownership):
def attribute_updates(update_ready, field_events, anchor_text=""):
    evs = _to_ready_events(update_ready)
    frames = _changed_frames(field_events, anchor_text)   # (t, added_spans) from consecutive diffs
    pending: list[int] = []                               # unmatched, un-superseded update indexes
    for f in frames:
        # pass 1: explicit/inferred supersession prunes pending (later same gen/utt subsumes prefix,
        #          or disposition == "coalesced"/"dropped")
        # pass 2: oldest pending whose expected-added content matches f.spans → matched(f.t);
        #          one frame may satisfy several pending updates (burst coalesce) — all matched
        # pass 3: no pending matched ⇒ unpaired += 1 (never a fast sample)
        ...
    # end-of-record: pending left ⇒ missing; rendered-identical ⇒ no_op (violations counted only
    # for frames GENUINELY attributable to them — the delayed-frame carve-out lives in pass 2)

# GOTCHA — "expected added content" of an update = normalize_tokens(update.text) MINUS the tokens
# already observed in the field at its dispatch (the rolling snapshot), so append-only routes and
# rewrite routes reduce to the same comparison space.
```

### Integration Points

```yaml
DOWNSTREAM — P1.M2.T1.S4 (route runner): populates ReadyEvent stage/gen/utt/seq/disposition/ack_ts
  (relay_identity read inside on_final/on_partial; disposition from the controller seam) and
  re-wires the lab capture. This PRP only defines the receiving fields.
DOWNSTREAM — P1.M2.T1.S6 (paired comparison): reads labels + partial_source provenance for the
  plain-vs-stabilized verdict.
DOWNSTREAM — P1.M2.T2.S3 (qualification): cites the coverage/miss counters in evidence rows.
PARALLEL — P1.M2.T1.S2 (in flight): voice_typing/daemon.py + README + test_daemon.py — disjoint.
UNTOUCHED: g5_timing_lab.py, g6_assessment.py, voice_typing/**, config, thresholds/constants.
```

## Validation Loop

> Full paths + functional `timeout` on every command (AGENTS.md). Run from
> `/home/dustin/projects/voice-typing`. Pure synthetic only — no live GUI/daemon/CUDA (R.7).

### Level 1: Syntax & shape (immediate)

```bash
cd /home/dustin/projects/voice-typing
timeout 30 .venv/bin/python -m py_compile tests/g5_timing_support.py tests/test_g5_timing_support.py
grep -cE 'class (ReadyEvent|AddedSpan|VisibilityResult|Observation|AttributionResult)' tests/g5_timing_support.py  # ≥5
grep -n 'import voice_typing\|from voice_typing' tests/g5_timing_support.py   # EXPECTED: no matches (purity)
# Expected: compile clean; new types present; zero voice_typing imports.
```

### Level 2: The contract (unit)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python -m pytest tests/test_g5_timing_support.py -v
# Expected: ALL pass — the 14 existing tests UNEDITED (compat) + the new attribution section.
# A failure in an EXISTING test means compat broke (tuple shape, write-once, thresholds) — fix the
# new code, never the old test.
```

### Level 3: Compat equivalence & consumers

```bash
cd /home/dustin/projects/voice-typing
# aggregate on legacy-shaped inputs must produce identical verdict/failures as before the change —
# pinned by Task 1 case (11); re-run the full file once more to confirm no order dependence:
timeout 120 .venv/bin/python -m pytest tests/test_g5_timing_support.py -q
# the lab still imports the engine unchanged (API compat proof — import only, NEVER run the lab):
timeout 30 .venv/bin/python -c "import sys; sys.path.insert(0, 'tests'); import g5_timing_support as g5; \
  r = g5.ReplayRecord(route='x', clip='c', feed_start=0.0, words=[], field_events=[], \
  update_ready=[(1.0, 'a', 'partial')], finals_ts=[], anchor=0); \
  print(g5.ready_to_frame(r.update_ready, r.field_events))"
# Expected: prints ([], 0) — legacy tuple shape + ready_to_frame signature still work verbatim.
```

### Level 4: Docs & scope guard

```bash
cd /home/dustin/projects/voice-typing
git diff --stat tests/G5_TIMING_EVIDENCE.md | tail -1     # append-only: additions dominate
git diff tests/G5_TIMING_EVIDENCE.md | grep -c '^-'       # EXPECTED: 0 removed lines
grep -n 'Measurement method' tests/G5_TIMING_EVIDENCE.md  # the new section present, after old content
git status --short
# Expected: ONLY tests/g5_timing_support.py, tests/test_g5_timing_support.py,
# tests/G5_TIMING_EVIDENCE.md. No g5_timing_lab.py, no voice_typing/, no g6_assessment.py.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: py_compile clean; new dataclasses present; zero `voice_typing` imports.
- [ ] L2: full test file green (14 existing unedited + new section).
- [ ] L3: legacy-tuple + `ready_to_frame` smoke prints `([], 0)`; compat equivalence case green.
- [ ] L4: evidence diff is append-only; exactly 3 files changed.

### Feature Validation
- [ ] Delayed frame → oldest pending update; newer identical callback gets no zero-diff violation.
- [ ] missing / superseded / ambiguous / unpaired all distinguished with counters, never samples.
- [ ] Rewrite visibility keeps first appearance; repeats resolve ordered-or-ambiguous (bounded).
- [ ] Anchor text + resets excluded; no phantom misses; no un-seeing.
- [ ] Floors/caps/backlog/dump/zero-edit verdict semantics byte-preserved on existing scenarios.
- [ ] Producer vs daemon stages + gen/utt/seq matching supported; ack_ts cross-check only.

### Code Quality Validation
- [ ] Pure stdlib; dual-import discipline; bounded scans; deterministic (no wall clock in engine).
- [ ] Mode-A docstrings on every changed type/function; evidence section documents method + limits.
- [ ] Report row/markdown additive only; route+verdict columns first (g6 parser compatible).

### Scope Boundary Validation
- [ ] `g5_timing_lab.py`, `g6_assessment.py`, `voice_typing/**`, config untouched.
- [ ] No overlap with S2's in-flight files (daemon.py/README/test_daemon.py).
- [ ] No new thresholds, no re-labeled historical numbers, no live-desktop anything.

## Anti-Patterns to Avoid

- ❌ Don't edit the 14 existing tests, the tuple shape, or a threshold constant to make new code
  pass — compat IS the contract; additive only.
- ❌ Don't charge frames by window ownership ("it landed in this update's window") — charge by
  oldest-pending span match; never bill a delayed frame to a newer identical callback.
- ❌ Don't turn a miss/supersede/ambiguity/unpair into a latency sample or a 0 ms credit.
- ❌ Don't un-see words on retraction/reset/rewrite — first appearance is write-once.
- ❌ Don't import `voice_typing` into the support module or run/edit the live lab (S4 owns it).
- ❌ Don't credit an ACK (target APPLIED) as visibility — FieldEvent is the only truth.
- ❌ Don't add a route-verdict-shaped table to the evidence append (g6 parser overwrites keys);
  don't rewrite historical numbers.
- ❌ Don't run commands without functional `timeout`; no live GUI, no daemon, no CUDA (R.7).

## Confidence Score

**8/10** — the defect list, replacement algorithm, label taxonomy, identity fields, compat
constraints, test matrix and consumer handoffs are all pinned to verbatim architecture-doc
mandates and read code (with line anchors), and the whole change is pure synthetic TDD in two
files plus an append. The −2: (a) `changed_spans` matching quality on pathological traces (dense
repeats + rewrites interleaved) needs the bounded ambiguity escape hatch tuned against the
synthetic cases — the taxonomy guarantees honesty but exact `ambiguous` counts may need one
iteration; (b) S4's real captured streams may exercise shapes the synthetic matrix didn't
anticipate — the contract's defaulted optional fields and the calibrated `detail` strings leave
room to extend labels without breaking compat again.
