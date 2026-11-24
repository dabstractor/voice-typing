---
name: "P1.M6.T4.S1 — G5 harness + per-route timing evidence (word-aligned real-voice replay, warm GPU, monotonic clocks)"
description: "Build the bounded G5 measurement harness and produce per-route timing evidence for the wired bulk path (P1.M6.T2.S1). The speech clock is word-aligned replay of the real-voice clips in tools/asr-lab/voice/ (offline faster-whisper word-timestamp fixtures, paced at 1× with zero-slice silence); the GPU is warm (resident recorder, one discarded warmup); all clocks are CLOCK_MONOTONIC. Visibility is read from the FIELD's own change events inside a private disposable compositor — automation never touches the live desktop, real clipboard, default microphone, or active service. Publish per-route counts, median, p95, worst gap, max words outstanding; misses are misses; a sustained five-word backlog or a sentence-end dump fails the route regardless of medians. Deliverables: inert feed seam (recorder_host + daemon pass-through), pure-python metrics engine + tests, alignment-fixture generator, env-gated route-pluggable lab (im-gtk + pi-ghostty first), and the committed bounded timing report."
---

# PRP — P1.M6.T4.S1: G5 harness + per-route timing evidence

## Goal

**Feature Goal**: Stand up the G5 timing gate (PRD §4.2sexies R.7 "G5 timing") as a bounded,
repeatable measurement harness, and use it to publish per-route timing evidence for the
**wired bulk path** (P1.M6.T2.S1: mic → reader thread → `BulkController` → TargetAdapter →
field). G5's rules, verbatim from the PRD, are the contract:

- **Warm GPU, monotonic clocks, word-aligned replay of real voice** — callback cadence and
  the silence detector are NOT the speech clock.
- speech-end→word-visible: **median ≤ 500 ms, p95 < 1 s**.
- update-ready→first-changed-frame: **p95 ≤ 100 ms (insertion) / ≤ 50 ms (correction)**.
- unchanged ⇒ **no edit** (zero field events).
- **≥ 100 insertions and ≥ 100 corrections per claimed route**; publish counts, median,
  p95, worst gap, max words outstanding.
- **Missing words are misses, not zero-latency samples.**
- **A sustained five-word backlog or a sentence-end dump fails regardless of medians.**
- asr-lab's turbo@float16 = 382 ms median word lag is an **external timing reference** (engine
  word lag on these clips), never the delivery clock and never a pass bar.

**Deliverable** (2 MODIFY + 4 CREATE + 1 committed report):

1. `voice_typing/recorder_host.py` — MODIFY (additive, inert): ctor kwarg `feed_input=False`;
   when set, the child constructs the recorder with `use_microphone=False`; new child-loop
   command `('feed', {'pcm': ..., 'sr': int})` → `recorder.feed_audio(pcm,
   original_sample_rate=sr)`; host-side proxy `feed(pcm, sr)` = non-blocking cmd-queue put.
   Default path byte-identical (no feed commands are ever sent in production).
2. `voice_typing/daemon.py` — MODIFY (additive, inert): ctor kwarg `feed_input=False`,
   forwarded to the REAL `RecorderHost` only, exactly like the existing extra-kwarg
   pass-through in `_load_host` (:1115-1120, "Test fakes keep the old surface"). No other
   change; P1.M6.T3.S1's sites are untouched.
3. `tests/g5_timing_support.py` — CREATE: pure-stdlib metrics engine (alignment-fixture IO,
   event-log parsing, word-visibility resolution, per-route metric/verdict computation,
   bounded report rendering). No CUDA, no desktop, no subprocess.
4. `tests/test_g5_timing_support.py` — CREATE: pure-python unit tests for (3) on synthetic
   event streams (pytest-collected).
5. `tests/g5_make_alignments.py` — CREATE: offline word-alignment fixture generator —
   faster-whisper `word_timestamps=True` over `tools/asr-lab/voice/*.wav` (daemon venv +
   CUDA `LD_LIBRARY_PATH` recipe from the asr-lab README) → committed
   `tools/asr-lab/voice/<name>.words.json`.
6. `tests/g5_timing_lab.py` — CREATE: the env-gated harness (`G5_TIMING_LAB=1`, NOT
   pytest-collected) with a route registry; ships `im-gtk` and `pi-ghostty` routes reusing
   the G3 boot recipes; drives an **in-process real daemon** (private `XDG_RUNTIME_DIR`,
   real control socket, real `RecorderHost` with `feed_input=True`,
   route-specific `bulk_target_factory`), warmup pass, paced word-aligned replays with
   stop/start re-arms, field event-log collection, metric computation, bounded JSON
   artifacts + report rows.
7. `tests/G5_TIMING_EVIDENCE.md` — CREATE (committed, the DOCS deliverable): the bounded
   timing report — per-route numbers, thresholds, failure register, environment provenance.

**Success Definition**:

- (a) The harness runs the **real wired bulk path end-to-end** — real CUDA recorder child
  (real models, real decode), real daemon dispatch, real `BulkController`, real adapter,
  real field in a private compositor — with synthetic input only at the two sanctioned
  seams: `feed_audio` audio in, private-desktop field out.
- (b) The speech clock is the alignment fixture mapped through the pacer's monotonic
  replay clock; no G5 number derives from callback cadence or VAD/silence timing.
- (c) Per claimed route the harness publishes: insertion/correction counts, per-metric
  median + p95, worst gap, max words outstanding (+ sustain flag), misses count,
  unchanged-zero-edit check, sentence-end-dump check — and a pass/fail verdict where any
  hard-fail rule (sustained ≥5-word backlog, sentence-end dump, threshold breach,
  count shortfall after the replay budget) fails the route **without averaging it away**.
- (d) Automation hygiene proven: zero contact with the live desktop, real clipboard,
  default microphone, or active service; scratch confined to ONE bounded TemporaryDirectory
  with guaranteed teardown; only fixtures + the markdown report enter git.
- (e) `tests/test_g5_timing_support.py` green; G1 watch set + bulk suites green untouched;
   default-config daemon behavior byte-identical (feed seam inert).
- (f) `tests/G5_TIMING_EVIDENCE.md` contains real measured numbers for ≥1 claimed route
  (target: `im-gtk` AND `pi-ghostty`), each row honestly labeled
  `pass | fail(reason) | blocked(reason)` — no over-claiming (a lab that never ran is
  "not run", never "passed").

## User Persona

**Target User**: internal — three consumers: (1) **P1.M7.T1.S1** (G6 graduation assessment):
its default-flip decision consumes this evidence verbatim; (2) the **operator**: the numbers
tell them whether bulk dictation will feel live (words appear while speaking) or like the
rev-1 wait-for-silence experience; (3) future maintainers re-running the gate after adapter/
model changes (drift re-measurement, same as the P1.M4.T5.S2 matrix re-run discipline).

**Use Case**: developer runs the harness per route under a timeout; it boots a private
desktop, loads the real models, warms up, replays the real-voice clips at 1× pace through
the wired bulk path, timestamps every field change, and prints/writes the per-route G5
verdict with every threshold and failure flag explicit.

**User Journey**: `timeout -k 2 1500 env G5_TIMING_LAB=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk`
→ private Sway boots → daemon arms → warmup replay (discarded) → N measured replays → field
log + metrics → JSON artifact in scratch + printed verdict → report rows appended to
`tests/G5_TIMING_EVIDENCE.md` by the developer from the artifact.

**Pain Points Addressed**: (1) G5 has never been measured — R.2's evidence table lists
"speech-to-visible latency … NOT VERIFIED anywhere", so G6 cannot even be assessed; (2) the
only existing real-audio E2E (`tests/e2e_virtual_mic.sh`) rebinds the system default source —
unusable for G5 by R.7's own rule; (3) without a word-aligned clock, "latency" measured from
callback cadence would silently launder engine pacing into delivery timing (the exact
confusion the work item's research note forbids).

## Why

- **PRD §4.2sexies R.7 G5** is a hard gate before G6 graduation; R.2's evidence table marks
  speech-to-visible latency, throughput, and backlog behavior as NOT VERIFIED. This item is
  the gate's instrument AND its first reading.
- **The work item contract**: INPUT = bulk path from P1.M6.T2.S1 + ≥1 verified route
  (P1.M5.T2.S1 or P1.M4.T5 rows — both exist and are Complete). LOGIC = bounded harness,
  private compositor + synthetic input, per-route metrics, failures reported never averaged.
  OUTPUT = G5 evidence per claimed route. DOCS = bounded timing report.
- **Everything the harness drives is landed and contract-stable**: dispatch wiring +
  `bulk_target_factory` + `host_factory` (P1.M6.T2.S1), identity relay (P1.M6.T1.S1),
  IM adapter + G3 labs (P1.M4.*), pi-editor adapter + Ghostty row (P1.M5.T1/T2), clipboard
  fallback + G4 lab (P1.M5.T3.S1). The only missing piece is the audio-in seam — and PRD
  §4.4 already sanctions `use_microphone=False # False + feed_audio() in tests`, with
  `tests/test_feed_audio.py` as the proven in-repo pattern.
- **Sequencing**: P1.M6.T3.S1 (bulk prompt source) lands in parallel and is a CONTRACT —
  the harness measures the path WITH context prompts active; its daemon sites
  (`_refresh_context_prompt`, `_bulk_handle_final`, `_on_bulk_applied`, `_bulk_cancel`,
  `_arm`) are disjoint from this item's (`__init__` ctor kwargs, `_load_host`). No conflicts;
  re-grep before editing (Task 0).

## What

A measurement lab, not a feature: no user-facing surface changes, no config-key additions
(no key-set pin churn), no CLI additions, no state.json changes. The two production-file
changes are additive and inert unless a harness-only ctor kwarg is explicitly passed.

### Success Criteria

- [ ] Feed seam: `RecorderHost(cfg, ..., feed_input=True)` child runs `use_microphone=False`
      and accepts `feed()`; default `feed_input=False` constructs the child exactly as today
      (asserted by existing suites staying green).
- [ ] Alignment fixtures: `tools/asr-lab/voice/{natural,jargon,pauses,noisy}.words.json` in
      git, each an array of `{"word", "start", "end"}` covering its `.txt` reference (word
      count reconciled within alignment tolerance; mismatches recorded, not fudged).
- [ ] Harness runs both shipped routes end-to-end on demand; a `--route` flag selects;
      unknown route exits 2.
- [ ] Per-route artifact (bounded JSON in the scratch dir) + printed verdict contain ALL of:
      counts (insertions, corrections, misses), speech-end→word-visible median/p95/worst,
      update-ready→first-changed-frame p95 split insertion/correction, max words outstanding,
      sustained-backlog flag, sentence-end-dump flag, unchanged-zero-edit check, warm/GPU +
      model + versions provenance.
- [ ] Verdict logic proven by unit tests on synthetic streams: threshold pass/fail, miss
      accounting (never zero-latency), backlog sustain window, sentence-end dump,
      count-shortfall-after-budget, unchanged ⇒ zero events.
- [ ] R.7 hygiene: no live-desktop/clipboard/default-mic/active-service contact; bounded
      logs; trap teardown verified; only fixtures + report enter git.
- [ ] `tests/G5_TIMING_EVIDENCE.md` written with real numbers, honest row labels, run
      commands, and the failure register.

## All Needed Context

### Context Completeness Check

_Pass._ The audio-in gap and its sanctioned fix, the exact daemon/child seams, the G3 boot
recipes per route, the clock strategy, the metric definitions with thresholds, and the
executable validation commands are all below with verified anchors (re-verified at
dd0bd5b; P1.M6.T2.S3 and P1.M6.T3.S1 may shift daemon line numbers — re-grep shapes, not
offsets).

### Documentation & References

```yaml
# MUST READ — this item's verified research (seam audit, clock strategy, metric defs).
- file: plan/008_a47116bb2b79/P1M6T4S1/research/g5_harness_research.md
  why: "§2 the feed-seam decision (what was rejected and why); §3 the in-process daemon +
        control-socket isolation pattern; §4 the speech-clock design; §9 metric definitions;
        §10 safety/boundedness checklist."

# MUST READ — the PRD clauses this item is the instrument for.
- docfile: plan/008_a47116bb2b79/prd_snapshot.md
  why: "§4.2sexies R.7 G5 paragraph (the thresholds and the 'NOT the speech clock' rule),
        R.7 preamble ('automation MUST NOT exercise the live desktop, real clipboard,
        default microphone, or active service — private compositor + synthetic input +
        isolated app instances; evidence stays bounded, only fixtures enter version
        control'), R.2 evidence table (what is NOT VERIFIED — never flip a row without a
        run), R.5 three-value law (latest recognized ≠ accepted final ≠ target-CONFIRMED
        — the field log is value #3 and the only visibility truth), R.3 show()/finalize
        semantics (insertion vs correction classification)."
  critical: "G5 is judged on VISIBLE words (field events), never on wire/bytes/callback
             timestamps; 'unknown' is not 'delivered'."

# MUST READ — the input contract (the wired path being measured).
- file: plan/008_a47116bb2b79/P1M6T2S1/PRP.md
  why: "The dispatch/lifecycle/cancel-intercept contract + the bulk_target_factory +
        host_factory ctor seams + the precondition triple (bulk-text requires
        streaming=true, graceful_stop=false, keypress_action='disarm')."

# MUST READ — the parallel contract (assume landed exactly as specified).
- file: plan/008_a47116bb2b79/P1M6T3S1/PRP.md
  why: "Bulk-mode context-prompt source (confirmed_visible) + triggers A/B/D4 — the harness
        measures WITH this active; do not touch its sites; expect arm-time set_prompt(\"\")
        traffic on the FIFO."

# MUST READ — the proven audio-feed pattern (the child-side reference implementation).
- file: tests/test_feed_audio.py
  why: "G-ORDER (arm/consume thread BEFORE first feed), feed_audio semantics
        (non-blocking, re-slices to 32 ms frames), silence MUST be fed as zero slices at
        natural pace (:194-226), use_microphone=False override (:276)."

# MUST READ — the paced-replay clock reference (asr-lab = the external timing reference).
- file: tools/asr-lab/paced_poll.py
  why: ":18-39 the monotonic paced-feed loop (sleep to target, never drift-accumulate) —
        the G5 pacer generalizes this to word-aligned chunking."
- file: tools/asr-lab/common.py
  why: "wav_duration :70, wav_chunks :76, pcm_float_chunks :91 (16 kHz float32 slicing —
        check feed_audio's expected dtype against test_feed_audio's slices and reuse
        whichever form that test feeds), norm_words :111 (word-matching normalization for
        visibility resolution)."
- file: tools/asr-lab/README.md
  why: "The CUDA LD_LIBRARY_PATH recipe for daemon-venv python (the alignment generator
        reuses it); the 382 ms turbo@float16 number and its meaning (engine word lag,
        external reference only)."
  gotcha: "asr-lab summarize_emissions approximates word offsets by LINEAR SPREAD — G5
           must NOT do that; the alignment fixture replaces the approximation."

# MUST READ — the G3 boot recipes the routes reuse (copy, do not reinvent).
- file: tests/ime_g3_lab.py
  why: "The full private-desktop boot pattern (xvfb-run -a + dbus-run-session private bus
        + sway x11 backend + disposable HOME/XDG_RUNTIME_DIR/TMPDIR; system-python3 field
        app; venv-python adapter; ONE TemporaryDirectory; EventLogWriter 64 KiB cap;
        killpg teardown; env-gating; exit codes 0/1/2) — the G5 lab's skeleton."
- file: tests/pi_g3_row_lab.py
  why: "The pi-in-Ghostty recipe (tools/paste-lab/ghostty_probe.py base + THE DOCUMENTED
        HOME DELTA pi needs) + the no-pi scaffold-smoke pattern (PI_G3_ROW_NO_PI=1) —
        mirror as G5_NO_DESKTOP=1."
- file: tests/ime_g3_field_gtk.py
  why: "The GTK field app (its own text/caret/edit-count assertions; cseq deltas) — extend
        additively with an env-gated bounded timing log rather than forking logic."
- file: tests/ime_g3_support.py
  why: "EventLogWriter (bounded) + the payload/status vocabulary + the frame-oracle
        vocabulary — reuse for the field timing log."

# MUST READ — the daemon/child seams being modified.
- file: voice_typing/recorder_host.py
  why: "Ctor signature; the child cmd loop :843-903 (text|arm|disarm|abort|prompt|shutdown
        — add 'feed' in the same style); where the child builds AudioToTextRecorder kwargs
        (add use_microphone=False under feed_input); the mp-queue put convention for
        non-blocking host methods (set_prompt :304 is the model)."
  gotcha: "feed slices must be small (32 ms-ish) and NON-blocking puts only — the pacer's
           pacing, not the queue, controls timing."
- file: voice_typing/daemon.py
  why: "__init__ ctor kwargs region (:788 host_factory precedent), _load_host :1115-1120
        (the 'only the real RecorderHost takes it' extra-kwarg pass — copy verbatim for
        feed_input)."
  critical: "Test fakes keep the old ctor surface — do NOT add required kwargs anywhere."

# MUST READ — what the harness wraps/observes in-process.
- file: voice_typing/bulk_controller.py
  why: "READ ONLY. on_applied elapsed_ms (:454/:738 t0 stamps) = cross-check column only;
        confirmed_visible() = three-value law #3 (never the visibility source — the FIELD
        log is)."
- file: voice_typing/ime/ime_host.py   # + manager.py/target.py/wlwire.py
  why: "READ ONLY. How a route's bulk bundle binds a private seat (env inheritance — the
        harness sets WAYLAND_DISPLAY/XDG_RUNTIME_DIR before constructing the daemon so
        _build_default_bulk_target/route factories inherit the private session)."
- file: voice_typing/pi_editor.py
  why: "READ ONLY. The pi-prompt TargetAdapter (socket path config) for the pi-ghostty
        route's bulk_target_factory."

# Hard rules.
- file: AGENTS.md
  why: "Two timeouts on every non-trivial command (inner GNU timeout + bash-tool backstop
        above it); never foreground the daemon; /tmp is RAM — every scratch/log bounded;
        cleanup recipe if anything wedges."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── daemon.py            # ctor seams :788/:829; _load_host :1115-1120  ← MODIFY (feed_input pass-through)
├── recorder_host.py     # child loop :843-903; recorder kwargs site     ← MODIFY (feed seam, inert)
├── bulk_controller.py   # READ ONLY (on_applied elapsed_ms cross-check)
├── ime/                 # READ ONLY (route adapter: private-seat binding)
├── pi_editor.py         # READ ONLY (pi-prompt route adapter)
└── feedback.py, config.py, session_recovery.py, ...   # untouched
tests/
├── ime_g3_lab.py / ime_g3_support.py / ime_g3_field_gtk.py / pi_g3_row_lab.py ...
├── test_feed_audio.py                    # the feed_audio reference
├── test_bulk_dispatch.py                 # the daemon-ctor seam reference (:324-342)
└── (G1 watch set + bulk suites — must stay green untouched)
tools/asr-lab/voice/{natural,jargon,pauses,noisy}.wav + .txt   # tracked real-voice fixtures
```

### Desired Codebase tree with files to be added

```bash
voice_typing/recorder_host.py            # + ~25 lines: feed_input ctor kwarg, 'feed' cmd, host feed()
voice_typing/daemon.py                   # + ~6 lines: feed_input ctor kwarg + _load_host pass-through
tools/asr-lab/voice/<clip>.words.json    # + 4 committed alignment fixtures
tests/g5_make_alignments.py              # + offline alignment generator (env-gated, CUDA, bounded)
tests/g5_timing_support.py               # + pure-stdlib metrics engine + report rendering
tests/test_g5_timing_support.py          # + unit tests for the engine (pytest-collected)
tests/g5_timing_lab.py                   # + THE env-gated harness (route registry: im-gtk, pi-ghostty)
tests/ime_g3_field_gtk.py                # + additive env-gated bounded timing log (default off)
tests/G5_TIMING_EVIDENCE.md              # + committed bounded timing report (DOCS deliverable)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE SPEECH CLOCK. Word i's speech-end is feed_start + words[i].end from the
#   ALIGNMENT FIXTURE. NEVER derive timing from partial-callback arrival, VAD events, or
#   post_speech_silenceDuration trips (work item + R.7). The 382 ms asr-lab number is engine
#   word lag (external reference) — do not subtract it, do not compare against it as a bar.

# CRITICAL #2 — Silence must be FED, not skipped. feed_audio with use_microphone=False gets
#   audio ONLY from you; natural pauses must be zero-slice feeds at pace so VAD segmentation
#   behaves like live speech (test_feed_audio.py :194-226 G-silence). The pacer owns timing:
#   sleep-to-target on time.monotonic() (paced_poll.py pattern), never sleep(chunk) drift.

# CRITICAL #3 — Warm GPU discipline. First arm pays the model load; the harness does ONE
#   discarded warmup replay after the first arm before any measured sample, keeps
#   auto_unload_idle_seconds=0 so the recorder stays resident, and re-arms via stop/start
#   (instant once resident). Any sample taken during a (re)load is discarded, not averaged.

# CRITICAL #4 — Clocks: time.monotonic() (CLOCK_MONOTONIC) shares one epoch across ALL
#   processes on this host, so harness/daemon/field timestamps intercompare directly.
#   Mandate monotonic everywhere (never time.time() for deltas) and assert it with a
#   heartbeat: every participant logs (monotonic, wall) pairs; fail the run if pairwise
#   deltas disagree beyond tolerance.

# CRITICAL #5 — Visibility truth is the FIELD app's own change events (R.5 value #3). Wire
#   timestamps (commit acks) and on_applied elapsed_ms are cross-check columns ONLY. A field
#   event with IDENTICAL rendered text is not a change (zero-diff) — the unchanged row
#   asserts ZERO field events for identical updates.

# CRITICAL #6 — Insertion vs correction classification comes from the FIELD log's
#   old→new pair: insertion = new extends old at the cursor; correction = anything else
#   (retraction, mid-string change, shrink). Do not classify from controller intent.

# CRITICAL #7 — Misses are misses: a reference word never visible in any hypothesis nor
#   any final is counted in a misses column and EXCLUDED from latency stats; it must never
#   enter a median as 0 ms. Recognition misses are R.8's problem — but the report SHOWS them.

# CRITICAL #8 — Fail rules override medians: sustained backlog = words-outstanding ≥ 5 held
#   ≥ SUSTAIN_WINDOW_S (2.0 s); sentence-end dump = an utterance (alignment pause ≥ 0.6 s
#   or clip boundary) of ≥ 5 words with < 2 of them visible before its finalize-class field
#   event. Either ⇒ route FAIL regardless of every median.

# CRITICAL #9 — Count floors need a budget, not a fudge: loop replays (fresh stop/start
#   arm per replay) until insertions ≥ 100 AND corrections ≥ 100, or REPLAY_BUDGET (20)
#   replays exhaust; a shortfall is REPORTED as a failure. Never synthesize corrections.

# CRITICAL #10 — R.7 hygiene is non-negotiable: private XDG_RUNTIME_DIR for the daemon
#   (isolates control socket + state file); feedback.hypr_notify=false; output.backend="null"
#   (belt-and-suspenders: bulk must never call the backend anyway); cancel.devices pointed
#   at a nonexistent path so the evdev listener takes its sanctioned "log once at arm"
#   fallback (REAL keyboards are live surfaces; a stray human keypress would HALT mid-run);
#   auto_stop_idle_seconds=0 (pause-heavy clips must not disarm the run). NEVER pactl /
#   set-default-source / hyprctl / voicectl against live sessions; NEVER systemctl.

# CRITICAL #11 — Bounded everything (AGENTS.md Rule 3): scratch in ONE TemporaryDirectory
#   (tmpfs = RAM) with EXIT/INT trap that killpg's OWN session groups (never pattern-sweeps)
#   and removes the dir; field timing logs capped (EventLogWriter 64 KiB / 2000-write
#   precedents); artifacts are metrics-only JSON (raw event logs die with the temp dir);
#   no unguarded >> anywhere.

# CRITICAL #12 — Feed seam inertness: 'feed' cmds are never sent in production and
#   use_microphone stays True unless feed_input — the G1 watch set must be byte-identical.
#   The daemon pass-through must NOT change the fake-host ctor contract (host_factory
#   fakes keep the old surface — mirror the :1119-1120 comment's discipline).

# CRITICAL #13 — Env-gating: the lab is NOT pytest-collected (no test_ prefix; requires
#   G5_TIMING_LAB=1; without it: print skipped, exit 0). Exit codes 0 pass / 1 any route
#   failed / 2 env-or-usage misuse. The alignment generator likewise requires an env var.

# CRITICAL #14 — Parallel-item drift: P1.M6.T3.S1 (daemon prompt sites) and P1.M6.T2.S3
#   (ctl.py/_dispatch) may land before you start — re-grep anchors (Task 0); your daemon
#   diff must touch only the ctor-kwarg region + _load_host pass-through.
```

## Implementation Blueprint

### Data models and structure

No production data models change. New harness-side structures (all in
`tests/g5_timing_support.py`, stdlib dataclasses):

```python
@dataclass
class WordAlign:            # one row of <clip>.words.json
    word: str; start: float; end: float   # seconds into the clip

@dataclass
class FieldEvent:           # one field text-change observation
    t: float                # time.monotonic() at the field's own change callback
    text: str               # full rendered text after the change
    kind: str               # "insert" | "correct" | "final"   (classified by producer or pairwise)

@dataclass
class ReplayRecord:         # one measured replay
    route: str; clip: str; feed_start: float
    words: list[WordAlign]; field_events: list[FieldEvent]
    update_ready: list[tuple[float, str]]   # (monotonic ts at daemon dispatch entry, text)

@dataclass
class RouteMetrics:         # the published per-route aggregate
    insertions: int; corrections: int; misses: int
    speech_to_visible_med_ms: float | None; speech_to_visible_p95_ms: float | None
    worst_gap_ms: float                     # max single speech-end→word-visible sample
    ready_to_frame_p95_insert_ms: float | None; ready_to_frame_p95_correct_ms: float | None
    max_words_outstanding: int; backlog_sustained: bool
    sentence_end_dump: bool; unchanged_zero_edit_ok: bool
    verdict: str; failures: list[str]       # every breach, spelled out — never averaged away
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: RE-GREP the anchors (parallel-item drift guard)
  - RUN: grep -n "def __init__\|def _load_host\|host_factory\|feed_input" voice_typing/daemon.py
         grep -n "kind == \|def set_prompt\|use_microphone\|AudioToTextRecorder(" voice_typing/recorder_host.py
  - NOTE: P1.M6.T3.S1/P1.M6.T2.S3 may have shifted daemon lines; adjust offsets, not shapes.

Task 1: MODIFY voice_typing/recorder_host.py — the inert feed seam
  - ADD ctor kwarg feed_input: bool = False (after the existing kwargs; never required).
  - CHILD: where the child builds AudioToTextRecorder kwargs, when feed_input: set
    kwargs["use_microphone"] = False (the tests/test_feed_audio.py :276 override — PRD §4.4
    sanctions it) and carry feed_input to the child (spawn args/queue hello, however the
    existing ctor flags travel — follow set_prompt's channel conventions).
  - CHILD LOOP: elif kind == "feed": recorder.feed_audio(payload["pcm"],
    original_sample_rate=payload["sr"]) — same style as the existing cmds (:843-903);
    defensive: missing/inactive recorder → log one line, never raise.
  - HOST: def feed(self, pcm, sr) → cmd-queue put (('feed', {...})), non-blocking
    (model: set_prompt :304).
  - VERIFY: timeout 600 .venv/bin/python -m pytest tests/test_ime_host.py tests/test_recorder_host*.py -q
    (whichever exist; plus the daemon suites in Task 2's verify) — all green unchanged.

Task 2: MODIFY voice_typing/daemon.py — inert pass-through
  - ADD ctor kwarg feed_input: bool = False beside host_factory (:788); store
    self._feed_input = feed_input.
  - IN _load_host (:1115-1120): pass feed_input=self._feed_input to the REAL RecorderHost
    ONLY, inside the existing "only the real RecorderHost takes it" branch — fakes keep the
    old surface. Extend that comment by one clause.
  - VERIFY: timeout 600 .venv/bin/python -m pytest tests/test_bulk_dispatch.py tests/test_daemon.py -q
    (test_daemon is CUDA-heavy: only if its existing gates allow; else the dispatch suite +
    ruff suffice for this inert diff).

Task 3: CREATE tests/g5_make_alignments.py — the alignment-fixture generator
  - ENV-GATED (G5_ALIGN=1), NOT pytest-collected; runs under the DAEMON venv with the CUDA
    LD_LIBRARY_PATH recipe from tools/asr-lab/README.md (document the export in the header).
  - FOR each tools/asr-lab/voice/*.wav: faster-whisper transcribe(word_timestamps=True,
    the configured final model, float16, language="en") → normalize/clip segments → write
    tools/asr-lab/voice/<name>.words.json ([{word, start, end}, ...], 2-space JSON, stable).
  - CROSS-CHECK each against the .txt reference (tools/asr-lab/common.py norm_words):
    print word-count reconciliation; do NOT edit fixtures by hand to force parity.
  - BOUNDED: prints + the small JSONs only. timeout 900 inner.
  - OUTPUT IS A COMMITTED FIXTURE (R.7: "only fixtures enter version control").

Task 4: CREATE tests/g5_timing_support.py — the pure metrics engine
  - PURE STDLIB, no CUDA/desktop/subprocess. Functions:
    load_alignments(path) -> list[WordAlign]
    parse_field_log(path|dict) -> list[FieldEvent]
    resolve_visibility(words, field_events) -> per-word first-visible ts (longest-prefix
      positional match via common.norm_words-style normalization; a word visible only in a
      LATER corrected hypothesis keeps its FIRST appearance time)
    classify_events(field_events) -> insert/correct pairwise labels
    speech_to_visible(words, visibility, feed_start) -> samples_ms + misses list
    ready_to_frame(update_ready, field_events) -> per-update first-changed-frame delta + class
    outstanding_series(words, visibility, feed_start) -> max words outstanding + sustain flag
      (sample at every word speech-end and every field event; SUSTAIN ≥5 for ≥2.0 s)
    sentence_end_dump(words, visibility, field_events, finalize_ts) -> bool per utterance
      (utterance = inter-word gap ≥0.6 s or clip boundary; dump = ≥5 words, <2 pre-finalize)
    aggregate(records) -> RouteMetrics + verdict (thresholds as named constants:
      MED_MS=500, P95_MS=1000, READY_P95_INSERT_MS=100, READY_P95_CORRECT_MS=50,
      MIN_COUNT=100, SUSTAIN_WORDS=5, SUSTAIN_WINDOW_S=2.0, DUMP_MIN_WORDS=5,
      DUMP_MAX_PRE_FINALIZE=1)
    render_report_row(m) / render_markdown(metrics_per_route) -> bounded strings.
  - Unit-test targets are synthetic streams (Task 5) — design for that (functions take
    data, never touch files when given parsed inputs).

Task 5: CREATE tests/test_g5_timing_support.py — the engine's tests (pytest-collected)
  - PATTERN: pure-python like tests/test_g3_matrix_support.py / test_ime_g3_support.py
    (header docstring with run command; no CUDA; fast).
  - CASES (naming test_<subject>_<scenario>):
    1. test_speech_to_visible_basic_median_and_p95 — synthetic 100-word stream, exact stats.
    2. test_missing_word_is_miss_not_zero — one word never visible: misses==1, sample count
       drops, median unchanged-by-miss (no 0 ms sample).
    3. test_backlog_sustain_fails — 6 words outstanding held 2.5 s → backlog_sustained,
       verdict FAIL even with perfect medians.
    4. test_backlog_transient_does_not_fail — 5 outstanding for 0.5 s → no flag.
    5. test_sentence_end_dump_fails — 8-word utterance, all words appear at the finalize
       event → dump flag, FAIL regardless of medians.
    6. test_live_stream_no_dump — same utterance streamed word-by-word → no flag.
    7. test_unchanged_zero_edit — identical update with zero field events → check passes;
       a spurious no-change event → FAIL (zero-diff law).
    8. test_ready_to_frame_split — insertion vs correction classification + separate p95s.
    9. test_count_shortfall_after_budget — 40 insertions/12 corrections after budget →
       reported failure, verdict FAIL.
    10. test_correction_word_keeps_first_visibility — word shown, hypothesis retracts and
        re-adds it → first-appearance ts retained.
    11. test_render_markdown_bounded — report string contains every metric; length sane.

Task 6: CREATE tests/g5_timing_lab.py — THE harness (env-gated, route-pluggable)
  - SKELETON: copy tests/ime_g3_lab.py's boot/teardown/env-gating/exit-code discipline
    verbatim (xvfb-run -a + dbus-run-session private bus + sway x11 backend; disposable
    HOME/XDG_RUNTIME_DIR/TMPDIR; ONE TemporaryDirectory; EXIT/INT trap killpg's OWN groups;
    without G5_TIMING_LAB=1 print skipped exit 0; 0 pass / 1 route fail / 2 misuse).
  - ROUTE REGISTRY: routes = {"im-gtk": ImGtkRoute, "pi-ghostty": PiGhosttyRoute} — each
    provides boot_private_desktop() (G3 recipe: ime_g3_lab.py / pi_g3_row_lab.py), a
    field-log drain path, and a bulk_target_factory closure binding the route adapter to
    the private seat (env inherited; ImeProcess/ImeTarget for im-gtk; pi_editor.PiEditorTarget
    socket for pi-ghostty). --route selects; later rows (editor/browser/clipboard) just
    register.
  - DAEMON (in-process): build cfg for the measured path (Gotcha #10 values: delivery=
    "bulk-text", streaming=true, graceful_stop=false, keypress_action="disarm",
    backend="null", hypr_notify=false, private state_file, auto_stop=0, auto_unload=0,
    context_prompt default true) → construct VoiceTypingDaemon(cfg, host_factory=<real
    RecorderHost>, bulk_target_factory=<route closure>, feed_input=True) with the harness
    env already pointing XDG_RUNTIME_DIR at the private dir (control socket + state file
    isolated). CONTROL: speak JSON-lines to the private control socket (start/stop/status)
    — the real command surface, no daemon internals for control.
  - UPDATE-READY WRAP: wrap the instance's on_final/_on_partial entries with
    time.monotonic() + text captures into a lock-guarded list (in-process lab-only;
    document that the append is ns-scale).
  - PACER: load clip PCM (16 kHz mono float32 — match test_feed_audio's slice form) +
    alignments; feed 32-ms-ish slices sleep-to-target on time.monotonic() so audio-time t
    hits feed_start + t; inter-clip and trailing silence = zero slices at pace (≥1.5 s
    trailing so the final lands inside the replay window).
  - WARMUP: first arm + ONE discarded clip replay (models load here); then measured
    replays: stop → start (instant re-arm, recorder resident) → feed one clip → drain →
    repeat until count floors met or REPLAY_BUDGET (20) replays exhausted (clip order
    cycles).
  - COLLECTION: field app writes its bounded timing log ((monotonic, full_text) per
    change, drained at replay end via the route's channel); assemble ReplayRecords →
    g5_timing_support.aggregate() → per-route verdict printed (one JSON line) + bounded
    artifact in the scratch dir.
  - SCAFFOLD SMOKE: G5_NO_DESKTOP=1 boots only the daemon+fake-field path and exits 0
    (the PI_G3_ROW_NO_PI pattern) so CI-ish checks can run without a compositor.
  - RUNTIME BOUNDS: inner `timeout -k 2 1500` per route (cold cuDNN can be minutes);
    never foreground-block beyond it; every subprocess the lab spawns is under its own
    timeout in the G3 style.
  - MODIFY tests/ime_g3_field_gtk.py ADDITIVELY: env-gated timing log (G5_FIELD_TIMING=1;
    bounded 2000 writes; default off — G3 behavior byte-identical). The pi route's
    extension gets the same additive treatment in its support file.

Task 7: RUN the evidence + WRITE tests/G5_TIMING_EVIDENCE.md (the DOCS deliverable)
  - GENERATE fixtures: run Task 3 once; commit the .words.json files.
  - RUN: both routes (im-gtk, pi-ghostty) under their timeouts, scratch dir preserved only
    for the run's duration.
  - WRITE the committed report from the artifacts: per-route sections with the FULL metric
    set, thresholds vs measured, failure register (every breach listed), provenance (GPU,
    models + compute_type, field/adapter/compositor versions, warm status, clip list,
    replay counts, date), run commands, and honest row labels (pass | fail(reason) |
    blocked(reason) | not-run). Mirror the tone/format of tests/G1_BASELINE.md and
    tests/D1_DUCK_EVIDENCE.md. If a route cannot run (e.g., no Ghostty/pi scaffold), the
    row says blocked(reason) — never silently omitted, never claimed passed.
```

### Implementation Patterns & Key Details

```python
# Pacer (the speech clock's enforcer) — generalizes paced_poll.py:
def paced_feed(host, pcm, sr, align, chunk_s=0.032):
    feed_start = time.monotonic()
    for offset, slice_ in slices(pcm, chunk_s):        # audio-time offset per slice
        target = feed_start + offset
        now = time.monotonic()
        if target > now:
            time.sleep(target - now)                   # sleep-to-target, never drift-accumulate
        host.feed(slice_, sr)                          # non-blocking; the QUEUE never paces
    return feed_start                                   # word i speech-end = feed_start + align[i].end

# Update-ready wrap (in-process, lab-only):
orig_partial = daemon._on_partial
def wrapped_partial(text, *a, **kw):
    update_ready.append((time.monotonic(), text))
    return orig_partial(text, *a, **kw)
daemon._on_partial = wrapped_partial                    # same shape for on_final

# Verdict assembly — failures accumulate, medians never veto them:
failures = []
if med_ms is None or med_ms > 500: failures.append(f"speech→visible median {med_ms} > 500 ms")
if p95_ms is None or p95_ms >= 1000: failures.append(...)
if ins_ready_p95 is None or ins_ready_p95 > 100: failures.append(...)
if cor_ready_p95 is None or cor_ready_p95 > 50: failures.append(...)
if m.backlog_sustained: failures.append(f"backlog ≥5 words sustained ≥2.0 s (max {m.max_words_outstanding})")
if m.sentence_end_dump: failures.append("sentence-end dump (utterance delivered as one final edit)")
if m.insertions < 100 or m.corrections < 100: failures.append(f"counts {m.insertions}/{m.corrections} < 100 after budget")
if not m.unchanged_zero_edit_ok: failures.append("zero-diff violation: unchanged update produced a field event")
# misses are always REPORTED (a column), and count toward no median
verdict = "pass" if not failures else "fail"
```

### Integration Points

```yaml
NO production integration points change:
  - no config keys (key-set pin untouched), no state.json fields, no CLI, no README
  - recorder_host 'feed' cmd + use_microphone=False exist ONLY under feed_input=True
  - daemon feed_input kwarg defaults False; G1 watch set byte-identical
FIXTURES (committed):
  - tools/asr-lab/voice/<name>.words.json × 4
REPORT (committed):
  - tests/G5_TIMING_EVIDENCE.md
SCRATCH (never committed, bounded, trap-torn-down):
  - one TemporaryDirectory per lab run: private bus/sway sockets, field logs, artifacts
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# After each file; fix before proceeding. Expected: zero errors.
.venv/bin/ruff check voice_typing/recorder_host.py voice_typing/daemon.py tests/g5_timing_support.py tests/test_g5_timing_support.py tests/g5_timing_lab.py tests/g5_make_alignments.py --fix
.venv/bin/ruff format voice_typing/recorder_host.py voice_typing/daemon.py tests/g5_*.py
# mypy if the repo's existing gate includes it for touched paths (follow ruff-only precedent if so)
```

### Level 2: Unit Tests (Component Validation)

```bash
# The engine — fast, pure-python, must be green before any lab run:
timeout 120 .venv/bin/python -m pytest tests/test_g5_timing_support.py -v
# Inertness of the feed seam (no CUDA needed):
timeout 300 .venv/bin/python -m pytest tests/test_bulk_dispatch.py tests/test_g2_bulk_gate.py -q
# G1 watch set spot-check (streaming/zero-diff untouched):
timeout 300 .venv/bin/python -m pytest tests/test_zero_diff_rewind.py tests/test_streaming_commit.py -q
# G3 support suites still green after the additive field-log change:
timeout 300 .venv/bin/python -m pytest tests/test_ime_g3_support.py tests/test_pi_g3_row_support.py -q
```

### Level 3: Integration (the harness itself — private desktops only)

```bash
# Alignment fixtures (once; CUDA — inner timeout, bash-tool timeout 960+):
timeout -k 2 900 env G5_ALIGN=1 .venv/bin/python tests/g5_make_alignments.py
# Scaffold smoke (no compositor needed):
timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk
# The real routes (inner timeout; bash-tool timeout 1560+; NEVER interrupt mid-run —
# the trap does teardown; if you must abort, run the AGENTS.md cleanup recipe after):
timeout -k 2 1500 env G5_TIMING_LAB=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk
timeout -k 2 1500 env G5_TIMING_LAB=1 .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty
# Expected: exit 0 = all rows pass; exit 1 = honest failure (read the failure register —
# a FAIL with real numbers is a SUCCESSFUL harness run); exit 2 = misuse.
# Hygiene check after every run: no stray sway/xfvfb/daemon children of the lab remain
# (pgrep against the private runtime dir path, not a broad pattern-sweep).
```

### Level 4: Domain-Specific Validation (evidence quality)

```bash
# Sanity-audit the artifacts (bounded greps, never cat whole logs):
#  1. every claimed route's JSON artifact has all RouteMetrics fields non-null
#     (or an explicit blocked/not-run reason);
#  2. counts ≥ 100/100 OR a recorded shortfall failure;
#  3. misses column present; no 0 ms samples in the latency arrays (grep '"0.0' sanity);
#  4. provenance block (GPU string, model+compute_type, versions, warm=true) present;
#  5. heartbeat check passed (monotonic/wall consistency);
#  6. git status shows ONLY: the 2 source MODIFYs, the new tests/g5_* files, the 4
#     .words.json fixtures, tests/G5_TIMING_EVIDENCE.md, the additive field-app change —
#     nothing else (no scratch, no artifacts).
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 1 clean (ruff check/format on all touched files).
- [ ] `tests/test_g5_timing_support.py` green; bulk/dispatch/G1 spot suites green untouched.
- [ ] Feed seam inert by default proven (suites above + no behavior diff with
      `feed_input=False` — the only production-code change is the additive kwarg/cmd).
- [ ] Harness runs both shipped routes end-to-end with real models, warm GPU, and exits
      0/1 honestly (a measured FAIL is a working harness; report it, do not chase it away).

### Feature Validation

- [ ] Per-route published: counts, median, p95, worst gap, max words outstanding (+ sustain
      flag), misses, unchanged-zero-edit check, sentence-end-dump check, provenance.
- [ ] All G5 thresholds encoded as named constants and unit-tested (Gotcha #8/#9).
- [ ] `tests/G5_TIMING_EVIDENCE.md` committed with real numbers and honest labels.
- [ ] R.7 hygiene: no live desktop/clipboard/default-mic/active-service contact anywhere
      in the lab path; scratch bounded + trap-torn-down; only fixtures + report in git.

### Code Quality Validation

- [ ] G3 lab conventions followed (env-gating, exit codes, bounded logs, killpg teardown,
      no pytest collection of labs).
- [ ] No new patterns where G3/asr-lab/feed_audio patterns exist (boot, pacing, feeding).
- [ ] No daemon lock held by anything the harness adds; wraps are append-only observers.

### Documentation & Deployment

- [ ] `tests/G5_TIMING_EVIDENCE.md` self-contained: run commands, thresholds, definitions,
      failure register, provenance, drift-re-run instructions (for P1.M4.T5.S2-style
      re-measurement).
- [ ] No README/config/AGENTS changes (out of scope; P1.M7.T2 owns docs sync).

## Anti-Patterns to Avoid

- ❌ Measuring "latency" from callback arrival, VAD events, or the silence gate — the
  alignment fixture is the speech clock (CRITICAL #1).
- ❌ Skipping silence instead of feeding zero slices — segmentation desyncs from the
  replay clock (CRITICAL #2).
- ❌ Counting misses as 0 ms samples, or averaging away backlog/dump failures (CRITICAL
  #7/#8).
- ❌ Accepting wire/adapter timestamps as "visible" — only the field's own change events
  count (CRITICAL #5).
- ❌ Fudging counts or fixtures to hit the 100/100 floor — shortfall is a reported failure
  (CRITICAL #9).
- ❌ Rebinding the system default source (e2e_virtual_mic route) or touching the live
  service/clipboard/keyboards (CRITICAL #10, R.7).
- ❌ Unbounded scratch/logs under /tmp (tmpfs = RAM), or reading a giant log before
  deleting it (AGENTS.md Rule 3).
- ❌ Running the daemon or any lab stage without inner GNU timeout + bash-tool backstop.
- ❌ Modifying P1.M6.T3.S1's sites or adding config keys/CLI surface — this is a
  measurement item; the production diff is the inert feed seam only.
- ❌ Claiming a route "passed" from a scaffold smoke or a partial run — honest labels only
  (pass | fail(reason) | blocked(reason) | not-run).
