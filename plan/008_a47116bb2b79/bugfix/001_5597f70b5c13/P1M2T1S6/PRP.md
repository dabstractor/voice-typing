# PRP — P1.M2.T1.S6: Run the paired callback comparison and localize visible lag

## Goal

**Feature Goal**: Execute the R.8 paired A/B measurement that everything since S1 has been built
for: run the S4 private runner **four times** — im-gtk × {plain, default(stabilized)} and
pi-ghostty × {plain, default(stabilized)} — with matched paced clips, ASR version/model/device/
cadence/context, comparable replay budget and the built-in one-discarded-warmup, each under
per-route GNU `timeout -k 2 1500` (bash-tool timeout strictly larger) with the runner's guaranteed
private teardown. Then **localize the visible lag**: decompose speech-end→word-visible per arm
into recognizer/callback (speech→first-useful-update), relay+queue+dispatch+adapter
(update→ACK), field paint (ACK→field change) and — on pi-ghostty, when S5's observer verified —
frame paint (field→frame), and publish a **dated route-by-source result and stage diagnosis**
that names the dominant stage per route, explicitly **distinguishes an early callback from early
field visibility**, and states candidate selection/repair criteria for P1.M2.T2.S1 and
P1.M2.T2.S2. Missing prerequisites or inconclusive clocks are reported as blocked/unverified —
never a pass, never imputed numbers. Unit-level checks use mocked records/artifacts/clock only;
measured samples come exclusively from the real private route runs — never the live desktop,
never fakes.

**Deliverable** (2 new files, 2 edited files, plus the four recorded runs):
1. `tests/g5_ab_compare.py` — NEW pure-stdlib analysis module (no voice_typing imports; imports
   `g5_timing_support` read-only like the S3/S4/S5 modules do): `stage_summary(records)` (the
   per-run additive stage decomposition computed from `ReplayRecord`s), artifact loading +
   `check_comparable` (fail-closed cross-arm provenance gate: clips/device/versions/budget/warm/
   effective-source labels, heartbeat/clock sanity), `compare` (the route-by-source assembly
   with measured / not-run / unverified-clock labelling), and `render_markdown` (the dated
   evidence section — non-verdict vocabulary only).
2. `tests/test_g5_ab_compare.py` — NEW hermetic unit file: stage math on synthetic records
   (fake clock), ACK-split behaviour when `ack_ts` present/absent, frame-split consumption of
   S5's `frame_qualified`, comparability gate matrix, missing/corrupt artifact → blocked (never
   numbers), and the **g6 non-interference proof** (`g6_assessment.parse_route_verdicts` output
   unchanged when the rendered section is appended to a doc fixture).
3. `tests/g5_timing_lab.py` — EDIT, additive only: artifact gains `"stage_summary":
   ab.stage_summary(records)`; `provenance` gains `realtimestt_version`
   (`importlib.metadata.version("RealtimeSTT")`), `replay_budget` (`g5.REPLAY_BUDGET`) and a
   cadence note string. **Zero** changes to thresholds, the replay loop semantics, the frozen Pi
   seams (`_G5PiBundle`, `_CancelOnLeaveTarget`, `bulk_target_factory`, `_poll_loop`) or S5's
   `frame_observer` wiring.
4. `tests/G5_TIMING_EVIDENCE.md` — EDIT, Mode A append (after S5's section): `## Paired callback
   comparison and stage diagnosis (P1.M2.T1.S6)` — dated provenance (commit, RealtimeSTT
   version, model/device, cadence, context, budget, warmup policy), the four arm rows under a
   **non-verdict-shaped** table header, the stage decomposition, the early-callback vs
   early-visibility verdict, the dominant-stage diagnosis, candidate criteria for T2.S1/T2.S2,
   and instrumentation limits (replay counts, misses, caps, pi observer status). Historical
   rows and the authoritative two-route verdict table (`:14`) stay untouched.
5. The four run transcripts + copied artifacts under
   `plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S6/research/` (renamed per arm —
   the scratch tmpdir is otherwise deleted), scratch removed after each copy.

**Success Definition**:
- (a) All four arms produce a dated, provenance-complete result row — or an honest not-run/
      unverified row if a prerequisite (e.g. PI_BIN/ghostty) is unavailable; no arm is ever
      marked with a passing verdict by S6's tables, and no number exists without a matching
      real run (or a synthetic, labelled unit fixture).
- (b) Every new artifact carries `stage_summary` + the expanded provenance; the four copied
      artifacts pass `check_comparable` (or every mismatch is listed as a limit, never
      silently ignored).
- (c) The evidence section presents, per route and arm: first-useful-word and first-visible-word
      timings, misses, edit churn (insertions/corrections/superseded/no-op/unpaired), backlog/
      dump flags, and the stage decomposition with shares — plus an explicit statement of
      whether plain's advantage (if any) is at the callback boundary or at field visibility,
      and which stage dominates the lag.
- (d) `timeout 200 .venv/bin/python -m pytest tests/test_g5_ab_compare.py -q` green (new);
      `timeout 200 … tests/test_g5_timing_lab.py -q` green (S4 contract); `timeout 120 …
      tests/test_g5_timing_support.py -q` green (S3 contract); `timeout 200 …
      tests/test_g5_frame_observer.py -q` green (S5 contract); `git status` shows exactly the
      4 repo files (+ research notes).

## User Persona

Not applicable (internal acceptance measurement; no operator-facing surface). DOCS: Mode A —
module docstrings + the evidence section record the method, provenance and limits. No production
code, config, README (P1.M2.T3.S2 owns it) or `.pi/extensions` changes.

## Why

- **R.8 is mandated and still unperformed** (PRD §4.2sexies; BUG-002, PRD h3.1): "compare the
  earliest usable update callback against the stabilized one and choosing by VISIBLE word lag".
  S1 landed the selector, S3 the attribution engine, S4 the runner + commands, S5 the Pi
  observer — **nothing has recorded the comparison yet**. This item is the measurement itself.
- **The architecture doc prescribes it** (`architecture/bulk_delivery_gate.md`): "Compare plain
  vs stabilized on **each** route; do not claim plain is earlier until measured"; § Gate:
  "Append paired A/B data and final candidate verdict separately, with commit, versions,
  selected source, exact commands, sample counts, misses and instrumentation limits. Diagnose
  the dominant stage (recognizer/processing cadence, relay, writer, or adapter before paint)
  before tuning; do not lower thresholds."
- **external_deps.md warns the naive expectation is wrong**: RealtimeSTT 1.0.2 fires both
  legacy callbacks in the same eligible decode, stabilized first inline — plain may not arrive
  first; the plausible delta is content granularity and revision churn. Only isolated same-clip
  replays can establish which callback wins (and § Gate: the historical failed baseline "has
  different route instrumentation and does not prove where delivery stalls").
- **T2 needs the diagnosis to aim**: T2.S1 (dispatch promptness + burst fail-closed) consumes
  the winning arm's update-rate/burst profile; T2.S2 (source-to-field bottleneck remediation)
  consumes the dominant-stage verdict. Without S6 they would be tuning blind.

## What

An analysis module + additive artifact block + the four real private runs + a dated evidence
section. The lab runner itself is NOT restructured — S6 consumes it exactly as the evidence
doc's "R.8 paired arms" commands prescribe. Exploratory A/B rows stay visually and parser-wise
distinct from the authoritative two-route verdict table (which T2.S3 owns refreshing).

### Success Criteria

- [ ] `tests/g5_ab_compare.py`: `stage_summary(records)` returns medians (and p95 where sample
      count ≥ 5) for speech_end→first_useful_update, first_useful_update→ack, ack→first_field
      (or the merged update→field, labelled, when `ack_ts` absent), field→frame (pi, only when
      S5's `frame_qualified`/`frame_observer.status=="verified"`; else `"frame": null` +
      proxy/unverified label), plus per-arm churn/backlog scalars and sample counts; misses and
      `capped`/clock flags are carried, never averaged away.
- [ ] `check_comparable(artifacts)` verifies per route-pair: identical `clips` set, `device`
      dict, `realtimestt_version`, `python`/`kernel`, `replay_budget`, `warm` policy, distinct
      `partial_callback_effective` per arm (plain vs stabilized), `heartbeat_ok` true; every
      violation is returned as a reason string and surfaces in the rendered limits.
- [ ] `compare`/`render_markdown` label arms `measured` / `not-run` / `unverified-clock` —
      the tokens pass/fail/blocked never appear as cell values; a missing or corrupt artifact
      yields a not-run row with the reason, never zeros.
- [ ] g6 non-interference: `parse_route_verdicts(current_doc_text)` equals
      `parse_route_verdicts(current_doc_text + rendered_section)` — unit-proven and re-checked
      live after the doc edit.
- [ ] `tests/g5_timing_lab.py` artifact edit is purely additive (`stage_summary`, provenance
      keys); S4's suite passes unedited; frozen Pi seams and S5's `frame_observer` block are
      byte-preserved.
- [ ] The four runs executed exactly per the documented commands (sequential, never parallel,
      never interrupted); artifacts copied per arm into the work item's `research/` and the
      scratch dirs removed (AGENTS.md Rule 3/5).
- [ ] Evidence section appended with dated provenance, four arm rows, stage diagnosis,
      early-callback-vs-early-visibility distinction, T2.S1/T2.S2 candidate criteria, limits;
      historical content and the `:14` verdict table untouched; `git status` shows exactly the
      4 files.

## All Needed Context

### Context Completeness Check

_Pass._ The runner commands, the data model feeding the stage split (`ReplayRecord` fields
verified in-tree), the artifact shape, the S3/S4/S5 contracts to preserve, the g6 parser
constraint, the external-contract facts that shape the diagnosis, and the run discipline
(timeouts, teardown, scratch bounding) are all specified below with anchors; the research note
carries the verified table.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S6/research/ab_comparison.md
  why: "§1 what-exists table (S1-S4 landed, S5 contract); §2 the verified ReplayRecord/artifact
        anatomy the stage decomposition computes from; §3 external-contract facts (both
        callbacks fire in the same decode — plain may not be earlier); §4 gate constraints incl.
        the g6 parser regex; §5 runbook facts (commands, budgets, teardown, scratch lifecycle);
        §6 the T2.S1/T2.S2 consumer handoff."
  section: "all"
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/bulk_delivery_gate.md
  why: "§ 'Gate and evidence handoff' — the verbatim mandates: append paired A/B separately
        with commit/versions/source/commands/counts/misses/limits; diagnose dominant stage
        BEFORE tuning; don't lower thresholds; exactly one parser-compatible current table,
        comparison rows under a different header. § 'G5 experiment and instrumentation' —
        matched arms, one discarded warmup, per-route timeout -k 2 1500, record installed
        source, no credit on ACK alone."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/external_deps.md
  why: "RealtimeSTT 1.0.2 contract: plain update + stabilized both fire per eligible decode,
        stabilized first inline; difference is content/revisions, not invocation order; only
        isolated same-clip replays establish the winner; exactly one callback per build."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S5/PRP.md
  why: "The S5 CONTRACT consumed in parallel-then-predecessor order: the additive
        `frame_observer` artifact block (status verified|unverified|blocked, resolution,
        classes) and per-record `frame_qualified` (≤20) that stage_summary's field→frame split
        reads; the frozen Pi seams (_G5PiBundle/_CancelOnLeaveTarget/bulk_target_factory/
        _poll_loop) that S6 must keep verbatim; the G5_KEEP_SCRATCH escape hatch."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S4/PRP.md
  why: "The runner contract: --partial-source at both parser levels, _resolve_partial_source
        fail-closed provenance, preflight→blocked, the artifact/final-line keys, and the exact
        four run commands (already transcribed into the evidence doc)."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S3/PRP.md
  why: "The attribution contract consumed read-only: ReadyEvent fields (t/text/kind/stage/
        gen/utt/seq/disposition/ack_ts), changed_spans/normalize_tokens semantics, the miss law
        (misses counted, never imputed), reset/anchor exclusion."
- file: tests/g5_timing_lab.py
  why: "EDIT target (additive only). Verified anchors: preflight :634; build_inner_argv :668;
        start_daemon :771; _resolve_partial_source :799; wrap_ready :825; run_inner :938 (warm
        log :1092, measured loop :1106-1188, artifact assembly :1191-1228, final line :1230,
        finally teardown :1240); run_route :1320 (preflight blocked, timeout_s 240/1440);
        ROUTES :631; paced_feed :144; FieldLog :183."
  pattern: "log() JSONL stdout lines; until() bounded polls; counts-only diagnostics; _Lab
            killpg own-groups teardown."
  gotcha: "Locate by named symbol — S5's landing shifts lines. Do NOT touch the replay loop,
           thresholds, or the frozen Pi seams; add stage_summary where the artifact dict is
           assembled."
- file: tests/g5_timing_support.py
  why: "READ-ONLY consumption: ReplayRecord :109 (feed_start/words/field_events/update_ready/
        anchor_text/partial_source/capped/heartbeats), FieldEvent :75, ReadyEvent :84
        (disposition/ack_ts semantics), changed_spans :234, normalize_tokens :186, aggregate
        :911, render_report_row :1022 (the metric keys the A/B table cites verbatim),
        REPLAY_BUDGET/MIN_COUNT constants, SPEECH_*_MS/READY_P95_* bars."
- file: tests/G5_TIMING_EVIDENCE.md
  why: "EDIT target (append) + command source. Headings: Verdict table :14 (DO NOT TOUCH),
        Run commands :28, '### R.8 paired arms' :50 (the exact commands), '### S4
        instrumentation notes' :93, Provenance :113, Thresholds :144, Failure register :166,
        Lab-side bridges :191, Open items :218, Hygiene :237, '### Measurement method' :247
        (S3); S5 appends its section after :247 — S6 appends after S5's."
- file: tests/g6_assessment.py
  why: "READ-ONLY: parse_route_verdicts (~:289) scans verdict tables and overwrites duplicate
        route keys; _ROUTE_VERDICT_RE = \\*{0,2}(pass|fail|blocked)\\*{0,2} IGNORECASE — why the
        A/B tables avoid those tokens entirely and why the non-interference test exists."
- file: tools/asr-lab/voice/*.words.json
  why: "The four paced clips (jargon/natural/noisy/pauses) + alignments ([{word,start,end},…])
        consumed by the runner — identical across arms; cited in provenance."
- url: https://pypi.org/project/RealtimeSTT/1.0.2/
  why: "The pinned ASR version recorded into provenance (uv.lock:698-717) — the A/B is only
        valid within one engine version."
- url: https://docs.python.org/3/library/statistics.html
  why: "Median/quantile semantics for stage_summary (pure stdlib; no numpy in this lab layer);
        report n alongside every percentile, skip p95 when n<5 rather than extrapolate."
- file: AGENTS.md  # two-timeout law on EVERY command; never foreground the daemon; never
                   # interrupt a lab run mid-model-load; voicectl under timeout 30; /tmp is
                   # RAM — copy artifacts out then delete scratch immediately
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── tests/
│   ├── g5_timing_lab.py             # EDIT (additive stage_summary + provenance keys)
│   ├── g5_timing_support.py         # READ-ONLY (S3 engine — consumed)
│   ├── g5_frame_observer.py         # S5's module (verify present; consume read-only)
│   ├── test_g5_timing_support.py    # READ-ONLY (must stay green)
│   ├── test_g5_timing_lab.py        # READ-ONLY (must stay green)
│   ├── test_g5_frame_observer.py    # READ-ONLY (must stay green)
│   ├── g6_assessment.py             # READ-ONLY (parser — non-interference proof)
│   ├── G5_TIMING_EVIDENCE.md        # EDIT (append the A/B + diagnosis section)
│   ├── g5_ab_compare.py             # CREATE
│   └── test_g5_ab_compare.py        # CREATE
└── voice_typing/                    # READ-ONLY
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
tests/
├── g5_ab_compare.py        # NEW: stage_summary(records) — per-replay decomposition
│                           #     (speech→update, update→ack, ack→field, field→frame) with
│                           #     medians/p95 + n; artifact loader + check_comparable
│                           #     (provenance/heartbeat fail-closed); compare (measured/
│                           #     not-run/unverified-clock labels); render_markdown (dated
│                           #     non-verdict section); pure stdlib, g5 imported read-only
├── test_g5_ab_compare.py   # NEW: synthetic-record stage math (fake clock), ack-present/
│                           #     absent split, frame consumption + unverified labelling,
│                           #     comparability matrix, corrupt/missing artifact → not-run,
│                           #     g6 non-interference, no-fabrication invariants
├── g5_timing_lab.py        # + artifact["stage_summary"]; +provenance realtimestt_version/
│                           #  replay_budget/cadence_note — additive only
└── G5_TIMING_EVIDENCE.md   # + "## Paired callback comparison and stage diagnosis
│                           #    (P1.M2.T1.S6)" — dated provenance, 4 arm rows (non-verdict
│                           #    header), stage shares, early-callback vs early-visibility,
│                           #    dominant stage, T2.S1/T2.S2 criteria, limits
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DEPENDENCY GATE (Task 0): S3/S4/S5 seams must be in-tree before editing:
#   grep -n 'class ReadyEvent' tests/g5_timing_support.py          (S3)
#   grep -n '_resolve_partial_source' tests/g5_timing_lab.py       (S4)
#   grep -n 'frame_observer\|_pi_window_env' tests/g5_timing_lab.py; ls tests/g5_frame_observer.py
#   (S5 — if absent, S5 has not landed: STOP and report; S6's INPUT names S5 as a prerequisite)
#   grep -n 'def parse_route_verdicts' tests/g6_assessment.py      (confirm signature for the test)
#   command -v pi ghostty sway xvfb-run grim                        (record; absence ⇒ honest not-run rows)
# CRITICAL #2 — THE G6 PARSER OWNS VERDICTS. parse_route_verdicts overwrites duplicate route
#   keys and _ROUTE_VERDICT_RE matches pass|fail|blocked (any emphasis, IGNORECASE). The A/B
#   tables use ONLY measured / not-run / unverified-clock; the authoritative :14 table is not
#   edited; the non-interference test is mandatory (unit + live re-check after the doc edit).
# CRITICAL #3 — NEVER FABRICATE OR UPGRADE. A missing artifact, failed preflight, heartbeat
#   failure (heartbeat_ok false) or clock_failures>0 ⇒ not-run / unverified-clock rows and a
#   limits note — never zeros, never a borrowed number from another arm, never averaging a
#   miss away. p95 only when n ≥ 5; always print n. Misses are counted, never imputed (S3 law).
# CRITICAL #4 — RUNS ARE SEQUENTIAL, SANCTIONED, UNINTERRUPTIBLE. One arm at a time (one CUDA
#   model per run; parallel arms corrupt cadence and contend the GPU). Exactly the documented
#   commands: timeout -k 2 1500 env G5_TIMING_LAB=1 [PI_BIN=…] .venv/bin/python
#   tests/g5_timing_lab.py --route <r> [--partial-source plain]; bash-tool timeout ≥ 1560.
#   NEVER interrupt mid-run; rc 124 ⇒ AGENTS.md cleanup (voicectl quit under timeout 30, unit
#   stop, pkill tree) BEFORE any retry. Never the systemd unit, never a foreground daemon,
#   never the live desktop.
# CRITICAL #5 — SCRATCH IS RAM (/tmp tmpfs) AND EPHEMERAL. Artifacts land in the run's
#   mkdtemp dir which teardown DELETES. Per arm: run with G5_KEEP_SCRATCH=1, immediately copy
#   artifact-<route>.json to research/artifact-<route>-<arm>.json (rename — same filename
#   across arms!), then rm -rf that scratch dir. Never tail/cat a stray giant file; never
#   leave scratch behind (AGENTS.md Rule 3/5).
# CRITICAL #6 — THE PI FRAME SPLIT IS CONDITIONAL. field→frame numbers exist ONLY when S5's
#   frame_observer.status == "verified" AND frame_qualified entries exist for the record;
#   otherwise frame: null + "editor read-poll proxy" label. ACK is never a frame (R.5 #3);
#   ack_ts is a cross-check for the update→ack vs ack→field split only.
# CRITICAL #7 — PLAIN MAY NOT BE EARLIER (external_deps): both callbacks fire in the same
#   eligible decode, stabilized first inline. The diagnosis MUST NOT assume invocation-order
#   advantage; measure first-useful-update per arm and report the delta with its sign. The
#   interesting question is granularity (updates_total, superseded/no_op shares, per-update
#   span sizes) and its effect on VISIBLE lag.
# GOTCHA #8 — COMPARABILITY IS PER ROUTE-PAIR. plain vs default arms must agree on clips,
#   device, realtimestt_version, python/kernel, replay_budget, warm policy; effective source
#   must differ exactly as labelled. Unequal `replays` counts (early break at ≥100/≥100) are a
#   DISCLOSED limit, not a disqualifier. Cross-ROUTE rows are never pooled into one verdict.
# GOTCHA #9 — DON'T RECOMPUTE WHAT aggregate() OWNS. Insertions/corrections/misses/speech
#   medians/backlog/dump come verbatim from artifact["metrics"]; stage_summary only adds the
#   decomposition the metrics don't carry. Reuse g5.normalize_tokens/changed_spans read-only.
# GOTCHA #10 — FIRST "USEFUL" HAS A PRECISE MEANING: the first partial ReadyEvent after
#   feed_start whose normalized text grows beyond anchor_text/running hypothesis (changed span
#   non-empty). A same-text repeat or no-op is NOT a useful word (S3 no_op law).
# GOTCHA #11 — TIME BASE: everything is time.monotonic() in the lab's clocks (feed_start,
#   ReadyEvent.t, FieldEvent.t, ack_ts); words.json start/end are AUDIO seconds mapped by the
#   pacer (speech_end = feed_start + words[-1].end). Never mix time.time() in. Heartbeat
#   (mono↔wall) sanity is already checked by the runner — cite heartbeat_ok, don't re-derive.
# GOTCHA #12 — No ruff/mypy here; pytest>=9.1.1 via .venv/bin/python -m pytest. Unit tests
#   are pure-mock (no CUDA, no compositor, no sockets, no daemon import beyond g5 modules).
#   The lab runs ONLY through its G5_TIMING_LAB gate under functional timeouts.
```

## Implementation Blueprint

### Data models and structure

```python
# tests/g5_ab_compare.py (all new; pure stdlib; imports g5_timing_support as g5 read-only)
@dataclasses.dataclass
class StageRow:
    """One arm's stage decomposition (medians ms, p95 ms when n>=5, n per stage)."""
    route: str
    arm: str                    # "plain" | "stabilized" (from partial_callback_effective)
    status: str                 # "measured" | "not-run" | "unverified-clock"
    reason: str = ""            # preflight miss / heartbeat fail / parse error — never ""
            #                     when status != "measured"
    speech_to_useful_med_ms: float | None = None   # recognizer+callback stage
    useful_to_ack_med_ms: float | None = None      # relay+queue+dispatch+adapter
    ack_to_field_med_ms: float | None = None       # adapter paint (None when acks absent
                                                    #  → merged useful_to_field, labelled)
    useful_to_field_med_ms: float | None = None
    field_to_frame_med_ms: float | None = None     # pi only; None ⇒ proxy/unverified
    frame_verified: bool = False                   # mirrors S5 frame_observer.status
    n_replays: int = 0; n_updates: int = 0; n_acks: int = 0
    # churn/backlog scalars copied VERBATIM from artifact["metrics"] (Gotcha #9)

def stage_summary(records: list[g5.ReplayRecord], *, frame_observer: dict | None = None) -> dict
    # per-replay: speech_end = feed_start + words[-1].end (Gotcha #11);
    # first useful update via changed_spans(anchor_text → running) over partial ReadyEvents;
    # first visible field event likewise; ack split only where ack_ts present and coherent
    # (ack within [update.t, field.t] sanity); frame ts from the record's frame_qualified
    # (S5) only when frame_observer["status"] == "verified". capped/clock flags carried.

def load_artifact(path) -> dict                     # JSON parse; OSError/JSONDecodeError → {}
def check_comparable(arts: dict[tuple[str, str], dict]) -> list[str]
    # per-route pairwise provenance equality + heartbeat_ok + distinct effective source;
    # returns reason strings (every one must surface in the rendered limits)

def compare(artifact_paths: dict[tuple[str, str], Path]) -> list[StageRow]
def render_markdown(rows, *, meta: dict) -> str     # dated, provenance block, non-verdict
                                                    # vocabulary, limits section (Gotcha #8)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: VERIFY DEPENDENCIES (blocking gate — Gotcha #1). Run every grep/command-v listed
  there; record availability (esp. `command -v pi` and ghostty). If an S3/S4/S5 seam is
  missing: STOP and report the blocker (S6 cannot run honestly without its INPUT contracts).

Task 1: CREATE tests/test_g5_ab_compare.py FIRST (RED).
  - Import pattern: sys.path.insert(0, str(Path(__file__).parent)); import g5_ab_compare as
    abc; import g5_timing_support as g5 (mirror tests/test_g5_timing_support.py :22-24).
  - FIXTURES: synthetic ReplayRecords on a fake monotonic clock (words from a small inline
    [{word,start,end}] list; ReadyEvents with controlled t/text/kind/disposition/ack_ts;
    FieldEvents; anchor_text seeds); minimal artifact dicts (real key names from run_inner
    :1191-1228); tmp_path artifact files incl. a corrupt JSON and a missing path; a doc
    fixture = the first ~30 lines of tests/G5_TIMING_EVIDENCE.md (read at test time).
  - CASES (all under timeout 200):
    (1) stage math: known timestamps ⇒ exact stage medians; p95 skipped when n<5 with n
        reported; speech_end uses feed_start + words[-1].end.
    (2) first-useful rule: no-op/repeat partials are skipped (Gotcha #10); the first
        content-growing partial after feed_start wins.
    (3) ack split: ack_ts present ⇒ useful_to_ack + ack_to_field; absent ⇒ merged
        useful_to_field with the merged label; ack outside [update, field] sanity window ⇒
        ack ignored + counted as a provenance warning, never a negative latency.
    (4) frame split: frame_observer.status=="verified" + frame_qualified entry ⇒
        field_to_frame; status "unverified"/"blocked"/absent ⇒ None + proxy label (S5 law).
    (5) capped/clock flags propagate into the row's limits; misses never imputed.
    (6) check_comparable matrix: matched pair ⇒ []; clip/device/version/budget/warm mismatch,
        heartbeat_ok false, same effective source in both arms ⇒ each a distinct reason.
    (7) compare labels: missing file / corrupt JSON / empty artifact ⇒ status "not-run" with
        reason, all numeric fields None — NEVER zeros; heartbeat fail ⇒ "unverified-clock".
    (8) g6 non-interference: render_markdown output appended to the doc fixture leaves
        g6_assessment.parse_route_verdicts output byte-identical (import via sys.path insert;
        if the signature needs a path/doc, adapt per the Task-0 grep).
    (9) render invariants: no cell equals pass/fail/blocked (regex
        r'(?i)\*{0,2}(pass|fail|blocked)\*{0,2}' over table rows — only the prose may quote
        the historical verdicts, and even then avoid the bare tokens in tables); every number
        row carries n; provenance block keys present.
  - RUN (RED): timeout 200 .venv/bin/python -m pytest tests/test_g5_ab_compare.py -q.

Task 2: CREATE tests/g5_ab_compare.py (GREEN) — the module per the data models above.
  - Mode A docstrings (scope + limits: "stage shares are medians over replays; single-replay
    arms carry n=1 and no p95; frame stage is paint-qualified only under S5 verification").
  - Percentiles: pure stdlib (sorted + index math or statistics.quantiles); no numpy.

Task 3: EDIT tests/g5_timing_lab.py — additive artifact block ONLY.
  - Near the artifact assembly (:1191-1228): artifact["stage_summary"] =
    ab.stage_summary(records, frame_observer=<S5's block if present else None>) — consume S5's
    variable/block by its landed name (Task-0 grep); import as `import g5_ab_compare as ab`
    alongside the existing g5 import.
  - provenance: "realtimestt_version": importlib.metadata.version("RealtimeSTT"),
    "replay_budget": g5.REPLAY_BUDGET, "cadence_note": short string citing paced_feed's
    real-time pacing constants.
  - NOTHING else: no threshold, loop, log-line, preflight or frozen-Pi-seam changes; S4's and
    S5's suites must stay green unedited.

Task 4: RUN THE FOUR ARMS (the measurement; Gotchas #4/#5/#7).
  - Order (sequential, one at a time, from /home/dustin/projects/voice-typing):
      1) timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 \
           .venv/bin/python tests/g5_timing_lab.py --route im-gtk --partial-source plain
      2) same --route im-gtk            (default/stabilized arm)
      3) timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 PI_BIN="$(command -v pi)" \
           .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty --partial-source plain
      4) same --route pi-ghostty        (default/stabilized arm)
    (bash-tool timeout ≥ 1560 each; expect honest FAIL exits 1 on the timing gate — that is
    the measurement, not an error; capture each stdout to research/run-<route>-<arm>.log via
    tee, bounded by the timeout itself.)
  - After EACH run: locate the retained scratch dir (its path is in the run's first JSON
    lines), copy artifact-<route>.json → research/artifact-<route>-<arm>.json, then
    rm -rf that scratch dir. Never read large scratch files into context.
  - If a run exits 124 or wedges: AGENTS.md cleanup FIRST, then decide whether to re-run once;
    a second failure ⇒ honest not-run row with the reason.
  - If PI_BIN/ghostty absent (Task 0): the pi arms are executed anyway to capture the honest
    preflight-blocked line, recorded as not-run rows — never fabricated.

Task 5: BUILD THE COMPARISON.
  - timeout 120 .venv/bin/python - <<'PY' style one-shot (or a tiny __main__ in
    g5_ab_compare.py): load the four research/artifact-*.json, compare(), render_markdown()
    with meta {date, HEAD commit, realtimestt version, device, cadence, budget, warm policy,
    observer status}; write research/ab_section.md; print the table.
  - Re-run the non-interference check live: append ab_section.md to a copy of the current
    evidence doc, assert parse_route_verdicts unchanged (one-off python -c; Task-0 signature).
  - Sanity-read the four artifact metrics against the historical baseline rows (Provenance
    :113, Failure register :166): new numbers are expected to differ (new instrumentation —
    the old baseline "does not prove where delivery stalls"); attribute, don't reconcile.

Task 6: EDIT tests/G5_TIMING_EVIDENCE.md — append after S5's section (Mode A).
  - "## Paired callback comparison and stage diagnosis (P1.M2.T1.S6)":
    * Provenance: date, HEAD commit, RealtimeSTT version, model/device, cadence note, context
      (build_cfg fixed), replay budget + actual replays per arm, one-discarded-warmup policy,
      the four exact commands, PI_BIN provenance, pi frame_observer status.
    * The route-by-source table (from Task 5; non-verdict header, e.g. "Route | Arm | Status |
      1st useful (ms, med) | 1st visible (ms, med) | speech→visible med/p95 | updates
      matched/superseded/no-op | ins/cor | backlog max | dump | n").
    * Stage decomposition table + shares per arm (speech→update / update→ack / ack→field /
      field→frame; merged-cell labelled where acks absent; frame row labelled proxy when
      S5 unverified).
    * **Early callback vs early field visibility**: per route, the sign and size of plain's
      delta at the callback boundary vs at first-visible; the explicit sentence stating
      whether an early callback exists at all (external_deps prediction tested).
    * Dominant-stage diagnosis per route (largest median share) + candidate criteria:
      - for P1.M2.T2.S1: the winning arm's update volume/burst profile (updates_total,
        superseded/no_op shares, worst_gap_ms) that its dispatch-promptness + burst
        fail-closed design must hold under;
      - for P1.M2.T2.S2: the named bottleneck stage + the numbers a remediation must move
        (e.g. "update→ack dominates at X ms med ⇒ writer/coalescing, not ASR cadence").
    * Limits: unequal replay counts, misses, capped records, clock failures, pi observer
      status, single-machine/single-session scope, comparability-gate reasons (if any).
  - DO NOT touch the :14 verdict table, historical rows, or S3/S4/S5 sections.

Task 7: VALIDATE (the loop below). If committed: "P1.M2.T1.S6: paired callback A/B + stage
  diagnosis (g5_ab_compare stage decomposition, four dated private runs, evidence section,
  T2 selection/repair criteria)".
```

### Implementation Patterns & Key Details

```python
# PATTERN — per-replay decomposition (pure; fake-clock testable):
def _replay_stages(rec, anchor_text):
    speech_end = rec.feed_start + rec.words[-1].end if rec.words else None
    useful_t, vis_t, ack_t = None, None, None
    running = rec.anchor_text or anchor_text
    for ev in rec.update_ready:                      # ReadyEvent (S3 coercion if tuple)
        if ev.kind != "partial" or ev.t < rec.feed_start:
            continue
        if g5.changed_spans(running, ev.text):       # content growth ⇒ useful (Gotcha #10)
            useful_t, ack_t = ev.t, ev.ack_ts
            break
        running = ev.text                            # no-op/repeat: not useful, keep rolling
    for fe in rec.field_events:
        if fe.t >= rec.feed_start and g5.changed_spans(running, fe.text):
            vis_t = fe.t; break                      # first VISIBLE change
    # sanity (Gotcha #11/#3): ack only splits when update.t <= ack_t <= (vis_t or +inf)
    return speech_end, useful_t, ack_t, vis_t        # all monotonic-clock floats

# PATTERN — status semantics (never a verdict; Gotcha #3):
# measured        = artifact parsed, heartbeat_ok, clock_failures == 0 (flags still listed)
# unverified-clock= heartbeat_ok false OR clock_failures > 0 (numbers shown, labelled)
# not-run         = missing/corrupt artifact OR preflight-blocked run (numbers all None)

# PATTERN — comparability (per route-pair, fail-closed into limits):
for (route, arm1), (route2, arm2) in pairs:
    for key in ("clips", "device", "realtimestt_version", "python", "kernel",
                "replay_budget", "warm"):
        if arts[a1]["provenance"].get(key) != arts[a2]["provenance"].get(key):
            reasons.append(f"{route}: {key} differs across arms")
    if eff(a1) == eff(a2): reasons.append(f"{route}: both arms report {eff(a1)!r}")
```

### Integration Points

```yaml
CONSUMES (read-only): S3 g5.ReplayRecord/ReadyEvent/FieldEvent/changed_spans/normalize_tokens/
  aggregate metrics keys; S4 runner (--partial-source both parsers, _resolve_partial_source
  provenance, preflight→blocked, artifact shape, the documented commands); S5 frame_observer
  block + per-record frame_qualified + G5_KEEP_SCRATCH hatch; g6_assessment.parse_route_verdicts
  (the non-interference oracle); tools/asr-lab/voice clips+alignments (via the runner).
EDITS: tests/g5_timing_lab.py (additive artifact block ONLY — stage_summary + 3 provenance
  keys), tests/G5_TIMING_EVIDENCE.md (append-only section).
FEEDS — P1.M2.T2.S1: winning-arm update/burst profile (updates_total, superseded/no-op
  shares, worst_gap_ms) sizing the dispatch-prompt + burst fail-closed design.
FEEDS — P1.M2.T2.S2: dominant-stage verdict with numbers (which of speech→update /
  update→ack / ack→field / field→frame must move, by how much).
FEEDS — P1.M2.T2.S3: the A/B provenance format + limits discipline its qualification
  section will extend when it refreshes the authoritative verdict table.
UNTOUCHED: voice_typing/**, g5_timing_support.py, test_g5_timing_support.py,
  test_g5_timing_lab.py, g5_frame_observer.py, test_g5_frame_observer.py, g6_assessment.py,
  config.py/config.toml, README.md, .pi/extensions/voice-editor.ts, thresholds/constants,
  the :14 verdict table, the live desktop/systemd unit.
```

## Validation Loop

> Full paths + functional `timeout` on every command (AGENTS.md two-timeout law); run from
> `/home/dustin/projects/voice-typing`. Unit level is pure-mock; the four arms are the
> sanctioned env-gated private lab invocations — never the systemd unit, never the live
> desktop, never interrupted mid-run.

### Level 1: Syntax & shape (immediate)

```bash
cd /home/dustin/projects/voice-typing
timeout 30 .venv/bin/python -m py_compile tests/g5_ab_compare.py tests/test_g5_ab_compare.py tests/g5_timing_lab.py
timeout 30 .venv/bin/python -c "import sys; sys.path.insert(0,'tests'); import g5_ab_compare, g5_timing_lab"
grep -n 'stage_summary\|realtimestt_version' tests/g5_timing_lab.py | head
git diff tests/g5_timing_lab.py | grep -c '^-[^-]'   # EXPECTED: 0 — the lab edit is additive only
# Expected: compile/import clean; seams present; zero deleted lines in the lab file.
```

### Level 2: Unit contract (all four suites)

```bash
cd /home/dustin/projects/voice-typing
timeout 200 .venv/bin/python -m pytest tests/test_g5_ab_compare.py -q        # NEW file green
timeout 200 .venv/bin/python -m pytest tests/test_g5_timing_lab.py -q        # S4 intact
timeout 200 .venv/bin/python -m pytest tests/test_g5_frame_observer.py -q    # S5 intact
timeout 120 .venv/bin/python -m pytest tests/test_g5_timing_support.py -q    # S3 intact
# Expected: all green. An S3/S4/S5 failure means a read-only contract broke — forbidden.
```

### Level 3: The four measured arms (env-gated; NEVER interrupt mid-run)

```bash
cd /home/dustin/projects/voice-typing
# sequential, one at a time (bash-tool timeout >= 1560 each); capture with tee into research/:
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 \
  .venv/bin/python tests/g5_timing_lab.py --route im-gtk --partial-source plain 2>&1 | tee <log>
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 \
  .venv/bin/python tests/g5_timing_lab.py --route im-gtk 2>&1 | tee <log>
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 PI_BIN="$(command -v pi)" \
  .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty --partial-source plain 2>&1 | tee <log>
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 PI_BIN="$(command -v pi)" \
  .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty 2>&1 | tee <log>
# After each: copy artifact-<route>.json → research/artifact-<route>-<arm>.json, then
#   rm -rf <that run's scratch dir>. rc 1 = honest timing FAIL (expected pre-T2) — record it;
#   rc 124 = wedged → AGENTS.md cleanup BEFORE anything else; preflight-blocked JSON = not-run.
# Then build + live-verify the section:
timeout 120 .venv/bin/python -m tests.g5_ab_compare 2>/dev/null || \
  timeout 120 .venv/bin/python tests/g5_ab_compare.py   # per your __main__; writes ab_section.md
# Expected: 4 dated rows (or honest not-run rows); comparability reasons empty or listed;
# parse_route_verdicts unchanged with the section appended.
```

### Level 4: Docs & scope guard

```bash
cd /home/dustin/projects/voice-typing
grep -n 'Paired callback comparison and stage diagnosis' tests/G5_TIMING_EVIDENCE.md  # section present
git diff tests/G5_TIMING_EVIDENCE.md | grep -c '^-'        # append-only; the :14 table untouched
grep -n '^| ' tests/G5_TIMING_EVIDENCE.md | sed -n '1,5p' # historical tables intact
git status --short
ls plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S6/research/              # artifacts + logs + section
# Expected repo diff: ONLY tests/g5_ab_compare.py, tests/test_g5_ab_compare.py,
# tests/g5_timing_lab.py, tests/G5_TIMING_EVIDENCE.md. No voice_typing/, no sibling test
# files, no g6_assessment.py, no README, no config, no .pi/extensions, no leftover scratch.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: compile/import clean; lab diff additive-only (zero deletions); seams grep-present.
- [ ] L2: new suite green; S3/S4/S5 suites green UNEDITED.
- [ ] L3: four arms run (or honestly not-run) with dated artifacts copied out; scratch removed;
      no run interrupted; rc semantics recorded (1 = honest fail, 124 = wedged + cleaned).
- [ ] L4: evidence section present, append-only; exactly 4 repo files changed; research/ holds
      the artifacts, run logs and the rendered section.

### Feature Validation
- [ ] Route-by-source table complete: first useful word, first visible word, misses, churn,
      backlog, dump — per arm, with n.
- [ ] Stage decomposition with shares; ack split labelled where absent; frame stage present
      only under S5 verification (else labelled proxy/unverified).
- [ ] Early-callback vs early-field-visibility explicitly distinguished per route (sign +
      size of the plain delta at each boundary; the external_deps prediction tested, not
      assumed).
- [ ] Dominant stage named per route with numbers; candidate criteria stated for T2.S1
      (burst profile to survive) and T2.S2 (stage + magnitude to move).
- [ ] Blocked/unverified outcomes honestly labelled; no zeros-for-missing; no p95 without n≥5;
      misses counted, never imputed; limits section discloses replay counts, caps, clocks,
      observer status, comparability reasons.

### Code Quality Validation
- [ ] Mode A docstrings on every new public function (scope + limits stated).
- [ ] g5_ab_compare is pure stdlib + read-only g5 imports; no recomputation of aggregate-owned
      metrics; no verdict tokens in any rendered table (regex-proven).
- [ ] The non-interference property proven in unit tests AND re-checked live after the doc edit.

### Scope Boundary Validation
- [ ] voice_typing/**, all sibling suites, g6_assessment.py, README, config, .pi/extensions,
      thresholds and the authoritative verdict table untouched.
- [ ] No live desktop/systemd interaction; lab invoked only via G5_TIMING_LAB under functional
      timeouts; scratch bounded and removed; no daemon foregrounded anywhere.

## Anti-Patterns to Avoid

- ❌ Don't merge A/B rows into the authoritative verdict table, don't add a second
  route×verdict-shaped table, don't let pass/fail/blocked tokens near table cells — the g6
  parser overwrites duplicate route keys.
- ❌ Don't run arms in parallel, don't interrupt a mid-run model load, don't retry a wedged run
  before the AGENTS.md cleanup, don't "borrow" a number from another arm to fill a gap.
- ❌ Don't recompute insertions/misses/medians the S3 engine already owns; don't invent a
  producer-stage clock that doesn't exist (daemon-receipt is the stamped boundary — S4 notes).
- ❌ Don't assume plain is earlier (external_deps: same decode, stabilized fires first inline);
  don't credit visibility on ACK; don't upgrade an unverified frame split to verified.
- ❌ Don't leave scratch dirs or stray logs in /tmp (RAM), don't read giant scratch files into
  context, don't edit read-only sibling contracts to make a test pass.
- ❌ Don't lower thresholds, don't hide zero-edit violations, don't let an exploratory row
  masquerade as the two-route verdict.

---

## Confidence Score

**8/10** — the runner, commands, data model, artifact shape and every consumer contract are
verified in-tree with named anchors (S3/S4 landed at HEAD 86ba158; S5 specified as contract and
gated by Task 0); the analysis module is pure logic over verified dataclasses, fully
mock-testable; the g6 non-interference risk is fenced by a mandated unit + live check. The −2:
(a) the four real runs depend on machine conditions (CUDA residency, PI_BIN/ghostty presence)
and honest-fail exits — the PRP's not-run/blocked paths cover every degradation but cannot
guarantee measurement richness; (b) S5 lands in parallel — if its `frame_observer` block or
`frame_qualified` shape shifts late, the frame-split consumption anchors must be re-grepped
(Task 0 + named-symbol discipline covers this, and the split degrades to a labelled proxy
rather than breaking).
