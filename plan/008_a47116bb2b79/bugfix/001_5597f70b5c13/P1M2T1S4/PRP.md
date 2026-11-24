# PRP — P1.M2.T1.S4: Wire the isolated route runner to compare real recorder builds

## Goal

**Feature Goal**: Turn `tests/g5_timing_lab.py` into the **paired real-build comparison runner** the
R.8 mandate requires: a lab-only `--partial-source plain|stabilized` CLI flag (omitted = the
production default) threaded through both argparse levels → `run_route` → `run_inner` →
`start_daemon` → `VoiceTypingDaemon(partial_source=…)` (the landed S1 spawn-boundary selector), with
the **selected vs effective source recorded after spawn and fail-closed on mismatch**; the GTK route
switched to the **default production factory** (S2's `_BulkTargetBundle.start()` — the lab bridge
deleted), the Pi route's **injected adapter / instrument reset / independent observation seam kept
verbatim** for S5; stage observations upgraded to the S3 **ReadyEvent replay contract**
(stage/gen/utt/seq stamped at the daemon-receipt boundary, bounded, no raw speech in committed
diagnostics); preflight misses become honest **blocked** outcomes; truncated evidence and unsafe
environments fail closed — all proven with **mocked daemon/control/process-runner/field-trace unit
tests** (never the live systemd unit), plus an end-to-end scaffold-smoke validation.

**Deliverable** (1 edited source, 1 new test file, 1 edited doc):
1. `tests/g5_timing_lab.py` — (a) `--partial-source` on the outer and inner `"run"` parsers
   (`choices=("plain","stabilized")`, default `None`; `None` ⇒ pass nothing ⇒ production default);
   (b) an extracted `build_inner_argv(folder, route_name, smoke, partial_source)` used by
   `run_route`; (c) `start_daemon(smoke, factory, partial_source=None)` → daemon kwarg;
   (d) `_resolve_partial_source(host, requested)` (requested vs `host.partial_callback`, reverse
   `voice_typing.daemon._PARTIAL_SOURCES` lookup, `RuntimeError` on mismatch/unknown — never
   measure a mislabeled arm) + provenance in the warm log, every `ReplayRecord.partial_source`, the
   artifact JSON and the final metrics line; (e) `wrap_ready` appends `g5.ReadyEvent`s
   (`stage="daemon"`, `gen`/`utt` via `d._bulk_identity()` inside the callback window, `seq` read
   from `d._bulk_seq` after the orig call, `None` fields on degrade) and the run_inner
   tuple-iteration sites switch to attribute access; (f) `FieldLog.anchor_text()` + records gain
   `anchor_text`/`capped`/`heartbeats`; ready-deque truncation raises, field-log cap sets `capped`;
   (g) raw-speech snippets (`first_partial`) removed from the warm and replay log lines (counts
   only); (h) `preflight(route_name) -> str | None` checked in `run_route` before ANY spawn →
   `{"stage":"preflight","verdict":"blocked",…}` + rc 1; (i) `GtkRoute.bulk_target_factory` deleted
   (inherits `_Route`'s `None` = default route) with the class docstring NOTE removed;
   `PiGhosttyRoute` untouched; (j) run-command docstring updated.
2. `tests/test_g5_timing_lab.py` — NEW hermetic unit file (sys.path insert + `import
   g5_timing_lab as lab`): CLI parsing at both levels, argv threading, `start_daemon` pass-through,
   `wrap_ready` ReadyEvent stamping, `_resolve_partial_source` fail-closed matrix, GTK-factory-is-
   None / Pi-factory-is-callable, record assembly fields, log scrubbing, preflight matrix, `_Lab`
   own-process bookkeeping, and a mocked `run_inner` smoke path (fake daemon/control/feed/clips).
3. `tests/G5_TIMING_EVIDENCE.md` — Mode A: run instructions gain the per-source commands (plain +
   default arms per route) and blocked semantics; instrumentation notes (stage observations,
   effective-source provenance, truncation flags, no raw speech); isolation notes updated (GTK
   bridge GONE — default production factory + 2 s activation pump + arm-retry; `ime_host.jsonl`
   capture lost on that route; Pi HOME delta unchanged). Historical commands/numbers/provenance
   stay attributed and untouched. NO new verdict-shaped table (the g6 parser owns the one current
   table).

**Success Definition**:
- (a) `--partial-source plain` reaches the recorder child (S1 seam) and the warm log + artifact +
  every record prove it: `partial_callback_effective == "on_realtime_transcription_update"`;
  omitting the flag yields `"on_realtime_transcription_stabilized"` with requested shown as
  default; a requested≠effective situation refuses to measure (RuntimeError → honest harness-fail
  line, exit 1).
- (b) The GTK route measures through the **default** daemon factory (`bulk_target_factory() is
  None`): production `_build_default_bulk_target` + `_BulkTargetBundle.start()` on the arm worker,
  with the arm-retry loop compensating the 2 s activation pump — no lab spawn/activation bridge
  remains on that path.
- (c) The Pi route is byte-preserved (injected `_G5PiBundle`, `_CancelOnLeaveTarget` reset,
  10 ms poll, `preflight_note`); reset edits are excluded via `anchor_text` + S3's reset rules —
  never counted as dictation edits.
- (d) Stage observations are the S3 contract: `update_ready` entries are `ReadyEvent`s with
  `stage="daemon"` and gen/utt/seq where the boundary provides them; captures stay bounded
  (deque 20000 / FieldLog 4000); truncated captures fail closed or flag `capped`.
- (e) No raw speech in any default stdout log line (warm/replay/verdict lines carry counts and
  provenance only).
- (f) Missing preflight (no PI_BIN/ghostty/sway/xvfb-run/clips) → blocked JSON + exit 1 with
  nothing spawned; the disposable-env refusal and the guaranteed own-process teardown
  (`kill_all`, `G5_KEEP_SCRATCH` escape hatch) are preserved.
- (g) `timeout 200 .venv/bin/python -m pytest tests/test_g5_timing_lab.py -q` green (new file);
  `timeout 120 .venv/bin/python -m pytest tests/test_g5_timing_support.py -q` green (S3 contract
  untouched); scaffold smoke with and without `--partial-source plain` completes honestly under
  `timeout -k 2 240` (exit 0, provenance correct); only the 3 files change.

## User Persona

Not applicable (internal acceptance harness; no operator-facing surface). DOCS: Mode A — the lab's
module/run-command docstrings and `tests/G5_TIMING_EVIDENCE.md` document the flag, the
instrumentation and the isolation limits. No public config, no README change (P1.M2.T3.S2 owns
overview claims).

## Why

- **R.8 is mandated and unperformed** (PRD §4.2sexies; BUG-002): "compare the earliest usable
  update callback against the stabilized one and choosing by VISIBLE word lag". S1 landed the
  spawn-boundary selector; S3 defines the replay contract — nothing RUNS the comparison yet. This
  item makes each (route, source) a single reproducible private CLI run with paired fixture
  settings and honest provenance, consumed by S5 (Pi frame observation), S6 (the paired runs +
  lag localization) and T2.S3 (qualification).
- **The architecture doc prescribes it** (`architecture/bulk_delivery_gate.md` § G5): "Record
  source actually installed in the spawn child. Compare plain vs stabilized on each route; do not
  claim plain is earlier until measured"; "producer ready (before IPC) and daemon receipt are
  separate clocks/checkpoints"; "no transcript/diagnostics in routine production logs";
  "Before measuring Pi, isolate its agent/config/state… a real HOME used only to locate binaries
  must not load live operator sessions/extensions. If that can't be safely arranged, block that
  route and record it"; "Do not count lab smoke as a measurement"; per-route `timeout -k 2 1500`;
  the Pi `_CancelOnLeaveTarget` harness reset "is not production behavior and does not count as a
  dictation edit".
- **The GTK lab bridge must die** (gate doc §4 "Production GTK parity gap confirmed" + S2):
  route acceptance must exercise the REAL startup path (`_build_default_bulk_target` +
  `bundle.start()`), not the lab's own spawn/60 s-activation loop that masked the production gap.
- **Fail-closed honesty**: a mislabeled arm (requested≠installed), truncated capture, unsafe
  environment or missing preflight must never produce a plausible-looking measurement.

## What

A lab-only CLI seam + provenance discipline + contract wiring, defaulting to today's behavior
(omitted flag ⇒ the production stabilized source; identical fixture settings). Unit-proven with
mocks; validated end-to-end at scaffold-smoke level (private, no compositor). The **live paired
route runs are S6's task** (per the plan: S6 "Run the paired callback comparison and localize
visible lag") — S4 delivers the ready runner, not the recorded comparison data.

### Success Criteria

- [ ] Both parsers accept `--partial-source {plain,stabilized}`; invalid value exits 2; omission
      threads `None` end-to-end and the daemon is constructed without an override (production
      default).
- [ ] `start_daemon` passes `partial_source` (None→"stabilized" materialization happens at the
      daemon seam, never `None` into `RecorderHost`).
- [ ] `_resolve_partial_source`: requested + installed-key match ⇒ selector name; requested +
      mismatch ⇒ RuntimeError; no-request + unknown installed key ⇒ RuntimeError; no-request +
      stabilized key ⇒ `"stabilized"`.
- [ ] Warm log / artifact / records / final metrics line carry requested + effective source.
- [ ] `wrap_ready` emits `g5.ReadyEvent`s (stage="daemon", gen/utt from `_bulk_identity()` inside
      the window, seq from `_bulk_seq` post-orig, degraded to `None` fields); orig callbacks still
      run; deque stays bounded; installation still precedes the first arm.
- [ ] `update_ready`/`finals_ts` assembly uses ReadyEvent attributes; records populate
      `partial_source`, `anchor_text` (FieldLog last text at drain), `capped` (field-log cap hit),
      `heartbeats` (the run's (mono,wall) pairs); ready-cap hit raises RuntimeError.
- [ ] No `first_partial` or any transcript text in stdout log lines.
- [ ] `preflight()` blocks (JSON + rc 1, zero spawns) on missing sway/xvfb-run/python3, missing
      PI_BIN/ghostty for `needs_pi`, missing clips/alignments; returns None when all present.
- [ ] `GtkRoute().bulk_target_factory() is None`; `PiGhosttyRoute().bulk_target_factory()` returns
      a callable (uninvoked in tests); no Pi-route code changes.
- [ ] `tests/G5_TIMING_EVIDENCE.md` updated per Deliverable 3 with historical content intact;
      `git status` shows exactly the 3 files.

## All Needed Context

### Context Completeness Check

_Pass._ The lab's full anatomy (every function to touch, with markers), the three sibling
contracts (S1 landed / S2 in-worktree / S3 PRP-as-contract), the identity seams at the daemon
boundary (`_bulk_identity` validity window, `_bulk_seq`), the fail-closed design, the test-import
pattern, the g6 parser constraint and the smoke-run quirk are all specified below with anchors;
the research note carries the verified table.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S4/research/lab_runner_wiring.md
  why: "§1 the verified lab anatomy table (anchor → S4 relevance for every function);
        §2 the three sibling contracts' exact landed surfaces; §3 the identity/seq stamping proof
        at the daemon boundary; §4 the fail-closed/blocked design; §5 consumer handoffs;
        §6 test-file facts."
  section: "all"
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/bulk_delivery_gate.md
  why: "§ G5 'G5 experiment and instrumentation' — the verbatim mandates: record the installed
        source in the spawn child; compare plain vs stabilized on each route; separate
        producer/daemon checkpoints; no transcripts in routine logs; Pi isolation + block-if-
        unsafe; disposable runtime isolation list; 'Do not count lab smoke as a measurement'.
        §4 — the production GTK startup prescription S2 landed (this task consumes it)."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S1/PRP.md
  why: "The landed selector contract: `_PARTIAL_SOURCES` map (daemon.py), keyword-only
        `partial_source` on `VoiceTypingDaemon.__init__`, spawn-args carry, ready-payload
        `partial_callback` + host property. THE seam this runner drives."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S2/PRP.md
  why: "The production GTK startup (bundle.start spawn + 2 s read-only activation pump on the arm
        worker; failures → unsupported + stays armed). The lab bridge this task deletes was its
        motivation; the arm-retry loop is the compensating control."
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S3/PRP.md
  why: "The replay contract consumed: ReadyEvent fields/coercion, ReplayRecord provenance fields
        (partial_source/anchor_text/capped/heartbeats), RouteMetrics counters, reset/anchor
        exclusion rules (why reset edits don't count), additive report keys."
  critical: "S4 DEPENDS ON S3 — if ReadyEvent/fields are absent, S3 has not landed; stop and
             report rather than re-implementing the engine."
- file: tests/g5_timing_lab.py
  why: "THE file. main() ~:1210 (outer parser); inner run parser ~:1212; run_route ~:1129 (argv
        build ~:1149, smoke branch, teardown); run_inner ~:766 (env guard, warmup block
        ~:903-935, measured loop record build ~:975-1035, artifact ~:1035-1065, finally teardown);
        start_daemon ~:719; wrap_ready ~:741; build_cfg ~:641; FieldLog ~:159; GtkRoute ~:297
        (bridge NOTE ~:303-311, bulk_target_factory ~:363-400); PiGhosttyRoute ~:401 (factory
        ~:562-637, preflight_note ~:631); desktop_env ~:1070; ROUTES ~:639; constants ~:73-89."
  pattern: "env-gated private lab; log() JSONL stdout lines; until() bounded polls; _Lab killpg
            own-groups teardown; counts-only diagnostics."
  gotcha: "Line numbers drift with S2/S3 landings — locate by the named symbols/grep markers
           (e.g. 'first_partial', 'lab-side bridge', 'Refusing to run outside')."
- file: voice_typing/daemon.py
  why: "_PARTIAL_SOURCES ~:232 (the reverse map for provenance); VoiceTypingDaemon.__init__
        keyword-only partial_source ~:904/:951; _load_host pass-through ~:1254;
        _build_default_bulk_target ~:861 (pure; ImeProcess(on_delivery_state=…) — NO log_path);
        _bulk_identity ~:2070 ('Valid INSIDE on_final/_on_partial ONLY'); _bulk_next_seq ~:2092
        (the _bulk_seq dict keyed (gen,uid))."
  gotcha: "READ-ONLY for this task — zero voice_typing/ edits."
- file: voice_typing/recorder_host.py
  why: "partial_callback property ~:247 ('' until ready; additive ready-payload key ~:540-543) —
        the EFFECTIVE source ground truth the runner records."
- file: tests/test_g5_timing_support.py
  why: "The import pattern to copy (:22-24 sys.path insert + module import) and the S3 contract
        suite this task must keep green (unedited)."
- file: tests/g6_assessment.py
  why: "parse_route_verdicts ~:289 (regex accepts pass|fail|blocked ~:80) — why the evidence edit
        adds no second verdict-shaped table."
- file: tests/G5_TIMING_EVIDENCE.md
  why: "Run commands :28-47 (append the per-source commands; keep historical attribution); verdict
        table :14-19 (DO NOT duplicate); 'Lab-side bridges' :128 (GTK bridge note must be updated
        to 'removed'); Hygiene :167."
- file: AGENTS.md  # the two-timeout law; never foreground the daemon; voicectl under timeout 30;
                   # smoke vs full-route discipline
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── tests/
│   ├── g5_timing_lab.py           # EDIT (the runner: CLI, provenance, ReadyEvent wiring, preflight,
│   │                              #       GTK default route, scrubbing, truncation)
│   ├── g5_timing_support.py       # READ-ONLY (S3's engine — consumed, never edited here)
│   ├── test_g5_timing_support.py  # READ-ONLY (S3's contract suite — must stay green)
│   ├── test_g5_timing_lab.py      # CREATE (hermetic unit coverage, mocked daemon/control/runner/trace)
│   ├── G5_TIMING_EVIDENCE.md      # EDIT (Mode A run/instrumentation/isolation notes)
│   └── g6_assessment.py           # READ-ONLY (parser constraint)
└── voice_typing/                  # READ-ONLY (S1 selector + S2 startup already landed)
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
tests/
├── g5_timing_lab.py           # +--partial-source (both parsers) + build_inner_argv + threaded
│                              #  run_route/run_inner/start_daemon; +_resolve_partial_source
│                              #  fail-closed provenance; wrap_ready→ReadyEvent(gen/utt/seq);
│                              #  FieldLog.anchor_text(); records carry partial_source/
│                              #  anchor_text/capped/heartbeats; truncation fail-closed;
│                              #  first_partial scrubbed; preflight()→blocked; GTK bridge deleted
├── test_g5_timing_lab.py      # NEW: parser/argv/start_daemon/wrap_ready/resolve/factories/
│                              #      records/logs/preflight/_Lab/run_inner-smoke (all mocked)
└── G5_TIMING_EVIDENCE.md      # +run commands per source; +instrumentation & isolation notes;
                               #  historical rows/commands preserved & attributed
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — S4 DEPENDS ON S1+S2 LANDED AND S3's CONTRACT. Verify before editing:
#   grep -n '_PARTIAL_SOURCES' voice_typing/daemon.py (S1); grep -n 'def start(' voice_typing/daemon.py
#   inside _BulkTargetBundle (S2); grep -n 'class ReadyEvent' tests/g5_timing_support.py (S3 —
#   if absent, S3 hasn't landed: STOP and report the blocker, do not re-implement the engine).
# CRITICAL #2 — NEVER PASS None INTO THE SELECTOR CHAIN. Materialize at the daemon seam:
#   start_daemon does partial_source or "stabilized" (S1's chain ValueErrors on None deep in the
#   child — the failure would surface only after spawn).
# CRITICAL #3 — FAIL CLOSED ON THE WRONG ARM. The ONLY ground truth for the effective source is
#   host.partial_callback (the child's ready payload). requested≠installed, or an installed key
#   that reverse-maps to nothing in _PARTIAL_SOURCES, raises RuntimeError BEFORE any measured
#   replay. A mislabeled arm must never produce numbers.
# CRITICAL #4 — wrap_ready STILL INSTALLS BEFORE THE FIRST ARM (its docstring law: _load_host
#   captures d.on_final/d._on_partial at spawn time). Keep the install point; only the appended
#   payload changes. The identity call d._bulk_identity() is valid INSIDE the wrapper (same reader
#   thread, inside _dispatch) — call it BEFORE orig; read d._bulk_seq.get((gen,uid)) AFTER orig
#   (seq is assigned inside _bulk_handle_partial/_bulk_handle_final). Degrade to None fields via
#   getattr — never crash the reader thread (wrap the stamping in try/except Exception → None).
# CRITICAL #5 — NO RAW SPEECH IN COMMITTED DIAGNOSTICS. The warm/replay log lines lose
#   first_partial (x[:60]/x[:50] snippets). Text still lives in the internal records (metrics
#   input) and the scratch JSONL (deleted with the tmpdir) — stdout stays pasteable into evidence.
# CRITICAL #6 — TRUNCATION IS EVIDENCE, NOT NOISE. ready deque (maxlen 20000) at cap ⇒ raise
#   (unattributable); FieldLog deque (cap 4000) at cap ⇒ record.capped=True (S3 reports it;
#   never impute). Check AFTER each replay window, before appending the record.
# CRITICAL #7 — THE GTK ROUTE RUNS PRODUCTION STARTUP NOW. The default ImeProcess carries NO
#   log_path ⇒ no ime_host.jsonl diagnostic on that route (daemon INFO + set_delivery_state
#   reasons remain), and bundle.start's pump is 2 s (the old bridge allowed 60 s) — the lab's
#   3-attempt arm() retry is the compensating control (cold GTK-loop stalls are exactly what it
#   exists for). A persistent activation failure is an HONEST route fail — do NOT re-add any
#   lab-side spawn/activation bridge.
# GOTCHA #8 — PI ROUTE IS FROZEN. bulk_target_factory/_CancelOnLeaveTarget/poll loop/preflight_
#   note are S5's seam — zero edits. Reset edits are excluded by data (anchor_text + S3 reset
#   rules), not by new code.
# GOTCHA #9 — SMOKE PATH QUIRK: pi-ghostty smoke crashes today (field_log() touches _log_path,
#   set only in boot()) — smoke tests and smoke validation use --route im-gtk (as the evidence
#   doc's command #1 already does). Do not "fix" Pi smoke here.
# GOTCHA #10 — NEVER run the live systemd unit, never foreground the daemon, never an untimed
#   voicectl; the lab itself is env-gated (GATE_ENV) and boots its own disposable desktop — only
#   ever invoke it exactly as documented (timeout -k 2 … env G5_TIMING_LAB=1 …). Unit tests are
#   pure-mock (no CUDA, no compositor, no sockets). pytest>=9.1.1; full paths + functional
#   `timeout` on EVERY command (AGENTS.md two-timeout discipline). No ruff/mypy in this repo.
# GOTCHA #11 — THE EVIDENCE DOC IS PARSER-SCANNED: exactly one current verdict table
#   (g6_assessment.parse_route_verdicts overwrites duplicate route keys); the new sections carry
#   no route+verdict table columns. Historical commands/numbers/provenance stay attributed.
```

## Implementation Blueprint

### Data models and structure

None new in production. The lab consumes S3's model:

```python
# tests/g5_timing_lab.py (conceptual — the shapes consumed, not new types)
g5.ReadyEvent(t=…, text=…, kind="partial"|"final", stage="daemon",
              gen=int|None, utt=int|None, seq=int|None, disposition="", ack_ts=None)
g5.ReplayRecord(..., partial_source="plain"|"stabilized", anchor_text=str, capped=bool,
                heartbeats=list[tuple[float, float]])
# lab-local helpers:
build_inner_argv(folder, route_name, smoke, partial_source) -> list[str]
_resolve_partial_source(host, requested) -> str        # selector name; RuntimeError on mismatch
preflight(route_name) -> str | None                     # blocked reason or None
FieldLog.anchor_text() -> str                           # last event text ("" when empty)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: VERIFY THE DEPENDENCIES (blocking gate).
  - grep -n '_PARTIAL_SOURCES' voice_typing/daemon.py | head -2          # S1 landed
  - grep -n 'def start(' voice_typing/daemon.py                          # S2's bundle.start
  - grep -n 'class ReadyEvent\|partial_source' tests/g5_timing_support.py | head -5   # S3 landed
  - If ANY is missing: STOP and report (S4 cannot proceed without the contracts).

Task 1: CREATE tests/test_g5_timing_lab.py FIRST (RED) — the hermetic unit matrix.
  - Header mirrors tests/test_g5_timing_support.py (:22-24): sys.path.insert(tests dir);
    import g5_timing_lab as lab; import g5_timing_support as g5. NO env gate needed at import
    (module-level imports are stdlib + g5_timing_support only).
  - FAKES: _FakeDaemon (on_final/_on_partial callables, _bulk_identity() scripted snapshot,
    _bulk_seq dict, _host with .device/.partial_callback, shutdown()); _FakeControl (scripted
    control_send replies via monkeypatch of lab.control_send); _FakeProc (poll()/pid for _Lab);
    tiny wav fixture (wave module, a few frames) + words.json in tmp_path for VOICE_DIR monkey-
    patch; monkeypatch lab.paced_feed/lab.until/lab.start_daemon/lab.boot_sway as needed.
  - CASES (all under `timeout 200`):
    (1) outer parser: --partial-source plain|stabilized parsed; invalid → SystemExit 2; omitted →
        None (drive lab.main's argparse via monkeypatched sys.argv + a stubbed run_route capturing
        (route, smoke, partial_source) — do NOT let main loop real routes).
    (2) inner run parser: same matrix on the "run <root> --route …" form.
    (3) build_inner_argv: flag present only when set; order stable.
    (4) start_daemon: monkeypatch voice_typing.daemon.{VoiceTypingDaemon,ControlServer,LatencyLog}
        + voice_typing.feedback.Feedback with fakes → ctor receives partial_source="plain" when
        given, "stabilized" when None (NEVER None).
    (5) wrap_ready: fake daemon → ReadyEvents appended with stage="daemon", gen/utt from the
        identity snapshot, seq read AFTER orig (fake _bulk_seq mutated by the orig), kind/text/t
        correct; identity degrade (None) → None fields; orig still called exactly once; bounded
        deque respected.
    (6) _resolve_partial_source matrix: match → selector; requested-vs-installed mismatch →
        RuntimeError naming both; unknown installed key → RuntimeError; no-request + stabilized
        key → "stabilized"; host without the property → RuntimeError (fail closed, not guess).
    (7) GtkRoute(fake_lab).bulk_target_factory() is None; PiGhosttyRoute(fake_lab).
        bulk_target_factory() returns a callable (DO NOT invoke — PiEditorClient connects).
    (8) record assembly (drive the measured-loop record construction via its extracted helper or
        the mocked run_inner): record.partial_source/anchor_text/capped/heartbeats populated;
        ready-cap → RuntimeError; field-cap → capped=True.
    (9) log scrubbing: the warm/replay log dicts built by the lab contain NO text-bearing keys
        (assert "first_partial" absent; assert every str value is not the fixture transcript).
    (10) preflight matrix: monkeypatch shutil.which/lab.VOICE_DIR → each miss returns a reason;
         all-present → None.
    (11) _Lab bookkeeping: fake spawn (monkeypatch sp.Popen) → procs tracked; kill_all kills
         exactly the own groups (fake killpg via os.killpg monkeypatch).
    (12) run_inner smoke capstone: monkeypatch env (XDG_RUNTIME_DIR=tmp g5-timing-lab-* dir),
         start_daemon→(fake d,srv,thread), control_send scripted, paced_feed→fixed feed_start,
         until→truthy, VOICE_DIR→fixture; assert exit 0, the warm log line carries
         partial_source_requested/partial_callback_effective, and (with requested="plain" +
         fake host partial_callback="on_realtime_transcription_update") no raise — and the
         mismatch variant raises before returning.
  - RUN (RED): timeout 200 .venv/bin/python -m pytest tests/test_g5_timing_lab.py -q → failures
    name the missing lab features.

Task 2: EDIT tests/g5_timing_lab.py — CLI threading (GREEN part 1).
  - 2a: outer parser (main): ap.add_argument("--partial-source", choices=("plain","stabilized"),
        default=None, help="lab-only R.8 arm selector; omit for the production source").
  - 2b: inner run parser: same argument; run_inner signature gains partial_source: str | None.
  - 2c: extract build_inner_argv(folder, route_name, smoke, partial_source) building the current
        argv + conditional ["--partial-source", ps]; run_route signature gains partial_source and
        uses it (both the xvfb argv and — for symmetry/safety — asserts the smoke in-place path
        passes it through to run_inner).
  - 2d: main passes ns.partial_source into run_route.
  - 2e: module docstring run-commands: add the per-source examples (plain + default per route).
  - DO NOT: default the flag to "stabilized" (None must mean "production source, unoverridden").

Task 3: EDIT tests/g5_timing_lab.py — daemon seam + provenance (GREEN part 2).
  - 3a: start_daemon(smoke, factory, partial_source=None); pass partial_source=(partial_source
        or "stabilized") into VoiceTypingDaemon (never None — Gotcha #2).
  - 3b: add _resolve_partial_source(host, requested) per Gotcha #3 (reverse map from
        voice_typing.daemon._PARTIAL_SOURCES — import inside the function).
  - 3c: run_inner: after the warmup arm (host resident), call it once; stash the result; add
        "partial_source_requested" (requested or "default") and "partial_callback_effective"
        (host.partial_callback) to the warm log line; carry both into the artifact provenance and
        the final metrics log line; each record gets partial_source=<resolved selector>.
  - DO NOT: log any transcript text while doing it (Gotcha #5).

Task 4: EDIT tests/g5_timing_lab.py — wrap_ready → ReadyEvent (GREEN part 3).
  - Replace the tuple appends with g5.ReadyEvent(t=time.monotonic(), text=text, kind=…,
    stage="daemon", gen=…, utt=…) stamping identity via d._bulk_identity() BEFORE orig (guarded
    try/except → None fields), and seq via getattr(d, "_bulk_seq", {}).get((gen, uid)) AFTER orig
    (guarded the same). Keep: install-before-first-arm law, the lock, append-only ns-scale cost,
    the docstring (updated to the ReadyEvent contract).
  - Update run_inner's iteration sites: got_final/quiet/win/fp-block switch from (t,x,k) tuple
    unpacking to attribute access (.t/.text/.kind); finals_ts=[r.t for r in win if r.kind=="final"].
  - DO NOT: change recorder_host, daemon, or the relay payload (read-only consumption).

Task 5: EDIT tests/g5_timing_lab.py — records, truncation, scrubbing, anchor (GREEN part 4).
  - 5a: FieldLog.anchor_text() (last event text, "" when empty); run_inner captures it at the
        pre-feed drain and passes anchor_text=… into each ReplayRecord.
  - 5b: truncation: after each replay window — if len(ready) >= ready.maxlen: raise RuntimeError
        (honest harness fail); if len(flog.events) >= flog.events.maxlen: capped=True on the
        record. heartbeats=hb (the run's pairs — bounded, ~6 entries).
  - 5c: scrub: delete first_partial from the warm and replay log dicts (keep counts: ready_kinds/
        kinds, events, updates).
  - DO NOT: touch thresholds, aggregate, or any g5_timing_support logic.

Task 6: EDIT tests/g5_timing_lab.py — preflight blocked + GTK default route (GREEN part 5).
  - 6a: preflight(route_name) -> str | None: shutil.which checks (sway, xvfb-run, SYSTEM_PY;
        ghostty + PI_BIN-or-which("pi") when ROUTES[route_name].needs_pi); VOICE_DIR has ≥1 *.wav
        each with a .words.json sibling. Return a concise reason string naming the miss.
  - 6b: run_route calls it FIRST; a reason → log({"stage":"preflight","verdict":"blocked",
        "route":…, "reason":…}) and return 1 (nothing spawned, tmpdir still cleaned).
  - 6c: DELETE GtkRoute.bulk_target_factory (inherit _Route's None default); rewrite the GtkRoute
        docstring NOTE: the route now exercises the production default factory +
        _BulkTargetBundle.start() (P1.M2.T1.S2); drop host_log/ime-host-log mentions that imply
        the bridge (the attribute may stay only if still referenced — prefer removing it).
  - DO NOT: touch PiGhosttyRoute at all (Gotcha #8).

Task 7: EDIT tests/G5_TIMING_EVIDENCE.md (Mode A).
  - Run commands: append the R.8 paired commands (per route: `--partial-source plain` AND the
    unflagged default run), the smoke validation commands, and the blocked semantics (preflight
    miss → "verdict":"blocked" JSON + exit 1, nothing spawned). Attribute the historical commands
    (stabilized-only wiring, pre-S4) in place — do not rewrite them.
  - Instrumentation notes: stage observations are daemon-receipt ReadyEvents (gen/utt/seq where
    available; producer-stage stamps remain a future seam); requested-vs-effective source
    provenance on every run; truncation flags (ready cap aborts; field cap flags); no raw speech
    in stdout lines; ACK is not a frame (S3).
  - Isolation notes: GTK bridge REMOVED (default production factory; 2 s activation pump; arm
    retry compensates; ime_host.jsonl capture lost on that route); Pi route unchanged (injected
    adapter + cancel-on-leave instrument reset + 10 ms read-poll; reset edits excluded from
    counts; real-HOME delta for binary discovery only); disposable XDG/DBus/Xvfb/sway, no mic,
    duck off, null typing, fake keys, bounded scratch, own-process killpg teardown — unchanged.
  - NO new verdict-shaped table (Gotcha #11); historical numbers untouched.

Task 8: VALIDATE (see the loop below). If committed: "P1.M2.T1.S4: route runner compares real
  recorder builds (--partial-source arms, effective-source provenance, ReadyEvent stages, GTK
  default route, blocked preflight, scrubbed diagnostics)".
```

### Implementation Patterns & Key Details

```python
# PATTERN — the effective-source resolution (fail closed; the child's ready payload is ground truth):
def _resolve_partial_source(host, requested: str | None) -> str:
    from voice_typing.daemon import _PARTIAL_SOURCES            # {selector: callback key}
    installed = getattr(host, "partial_callback", "")           # "" until ready
    if not installed:
        raise RuntimeError("recorder host never reported partial_callback (not ready?)")
    rev = {key: sel for sel, key in _PARTIAL_SOURCES.items()}
    effective = rev.get(installed)
    if effective is None:
        raise RuntimeError(f"unknown partial_callback {installed!r} installed in the spawn child")
    if requested is not None and _PARTIAL_SOURCES.get(requested) != installed:
        raise RuntimeError(f"partial_source={requested!r} requested but {installed!r} installed — "
                           "refusing to measure a mislabeled arm")
    return effective

# PATTERN — the ReadyEvent stamping wrapper (install BEFORE first arm; never crash the reader thread):
def wrapped_partial(text, *a, **kw):
    ident = None
    try:
        ident = d._bulk_identity()          # valid HERE: reader thread inside _dispatch
    except Exception:
        ident = None
    gen = getattr(ident, "session_gen", None); utt = getattr(ident, "utterance_id", None)
    try:
        out = orig_partial(text, *a, **kw)  # orig assigns _bulk_seq[(gen, utt)] on the bulk path
    finally:
        seq = None
        try:
            seq = (d._bulk_seq.get((gen, utt)) if gen is not None and utt is not None else None)
        except Exception:
            seq = None
        with lock:
            ready.append(g5.ReadyEvent(t=time.monotonic(), text=text, kind="partial",
                                       stage="daemon", gen=gen, utt=utt, seq=seq))
    return out

# PATTERN — blocked preflight (nothing spawned; tmpdir still cleaned by run_route's finally):
reason = preflight(route_name)
if reason:
    log({"stage": "preflight", "verdict": "blocked", "route": route_name, "reason": reason})
    return 1

# GOTCHA — build_inner_argv keeps the flag OPTIONAL in the argv (omitted = production arm):
argv = [sys.executable, str(Path(__file__).resolve()), "run", folder, "--route", route_name]
if smoke: argv.append("--smoke")
if partial_source: argv += ["--partial-source", partial_source]
```

### Integration Points

```yaml
CONSUMES (landed): S1's daemon/recorder_host partial_source seam + host.partial_callback;
  S2's _BulkTargetBundle.start() default-route startup; S3's ReadyEvent/ReplayRecord contract.
FEEDS — P1.M2.T1.S5: the frozen Pi route seams (bulk_target_factory/_CancelOnLeaveTarget/
  poll loop/field_log/preflight_note) + anchor_text-based reset exclusion.
FEEDS — P1.M2.T1.S6: one CLI invocation per (route, source) with provenance on stdout+artifact;
  paired fixture settings (build_cfg untouched).
FEEDS — P1.M2.T2.S3: the S3 counters the runner now populates (coverage/misses/clock/cap).
UNTOUCHED: voice_typing/**, g5_timing_support.py, test_g5_timing_support.py, g6_assessment.py,
  config.py/config.toml, ctl.py, README.md (P1.M2.T3.S2 owns it), thresholds/constants.
```

## Validation Loop

> Full paths + functional `timeout` on every command (AGENTS.md two-timeout law). Run from
> `/home/dustin/projects/voice-typing`. Unit level is pure-mock; the scaffold smoke is the
> sanctioned env-gated private run (real models, NO compositor, NO live desktop, NO systemd unit).

### Level 1: Syntax & shape (immediate)

```bash
cd /home/dustin/projects/voice-typing
timeout 30 .venv/bin/python -m py_compile tests/g5_timing_lab.py tests/test_g5_timing_lab.py
timeout 30 .venv/bin/python -c "import sys; sys.path.insert(0,'tests'); import g5_timing_lab"  # import-safe
grep -n 'partial-source' tests/g5_timing_lab.py | head            # both parsers + docstring
grep -cn 'first_partial' tests/g5_timing_lab.py                   # EXPECTED: 0
grep -n 'def bulk_target_factory' tests/g5_timing_lab.py          # EXPECTED: exactly 2 (base + Pi)
# Expected: compile clean; flag wired; snippets gone; only _Route + PiGhosttyRoute factories.
```

### Level 2: Unit contract

```bash
cd /home/dustin/projects/voice-typing
timeout 200 .venv/bin/python -m pytest tests/test_g5_timing_lab.py -q        # NEW file green
timeout 120 .venv/bin/python -m pytest tests/test_g5_timing_support.py -q    # S3 contract intact
# Expected: both green. A test_g5_timing_support failure means the engine contract broke — you
# edited g5_timing_support.py, which is forbidden here.
```

### Level 3: End-to-end scaffold smoke (private; real models; no compositor)

```bash
cd /home/dustin/projects/voice-typing
# default arm (omitted flag ⇒ production source):
timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 \
    .venv/bin/python tests/g5_timing_lab.py --route im-gtk
# plain arm (the R.8 comparison seam, end-to-end through the spawn child):
timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 \
    .venv/bin/python tests/g5_timing_lab.py --route im-gtk --partial-source plain
# misuse exits 2:
timeout 30 env G5_TIMING_LAB=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk --partial-source loud; echo "rc=$?"
# Expected: both smoke runs print the warm line with partial_source_requested +
# partial_callback_effective matching the arm (default→on_realtime_transcription_stabilized;
# plain→on_realtime_transcription_update) and {"stage":"smoke","pass":true}; rc=0. The invalid
# flag exits 2. NEVER interrupt a smoke mid-model-load; let the timeout own it.
```

### Level 4: Docs & scope guard

```bash
cd /home/dustin/projects/voice-typing
git diff tests/G5_TIMING_EVIDENCE.md | grep -c '^-'                # minimal; historical rows intact
grep -n 'partial-source' tests/G5_TIMING_EVIDENCE.md | head        # new run commands present
grep -n 'Lab-side bridges' tests/G5_TIMING_EVIDENCE.md             # section updated (GTK bridge removed)
git status --short
# Expected: ONLY tests/g5_timing_lab.py, tests/test_g5_timing_lab.py, tests/G5_TIMING_EVIDENCE.md.
# NO voice_typing/, NO g5_timing_support.py, NO g6_assessment.py, NO README.md, NO config.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: compile + import clean; flag on both parsers; zero `first_partial`; exactly 2 factories.
- [ ] L2: new unit file green; S3's suite green unedited.
- [ ] L3: both scaffold smokes honest (provenance correct, pass:true); invalid flag exits 2.
- [ ] L4: exactly 3 files changed; evidence historical content preserved.

### Feature Validation
- [ ] `--partial-source plain` installs the update callback in the child and the run proves it
      (requested/effective recorded; mismatch refuses to measure).
- [ ] Omitted flag = production source (nothing overridden anywhere).
- [ ] GTK route measures via the default production factory (bridge deleted; no re-added seam).
- [ ] Pi route byte-preserved; reset edits excluded via anchor_text + S3 rules.
- [ ] ReadyEvents carry stage/gen/utt/seq where available; captures bounded; truncation aborts or
      flags; no raw speech on stdout; preflight misses → blocked, zero spawns; teardown intact.
- [ ] Isolation preserved end-to-end: no mic, duck off, null typing, fake keys, private
      XDG/DBus/Xvfb/sway, bounded logs, own-process killpg cleanup, env-gate, exit 0/1/2.

### Code Quality Validation
- [ ] Lab docstrings + module run-commands reflect the new flag/limits (Mode A).
- [ ] Helpers extracted (build_inner_argv, _resolve_partial_source, preflight) are unit-covered.
- [ ] No new thresholds, no engine edits, no production-code edits, no config knob.

### Scope Boundary Validation
- [ ] voice_typing/**, g5_timing_support.py, test_g5_timing_support.py, g6_assessment.py, README,
      config untouched; no overlap with S3's files; live systemd unit never exercised.

## Anti-Patterns to Avoid

- ❌ Don't default `--partial-source` to "stabilized" in argparse — `None` must mean "production
  source"; materialize to "stabilized" only at the daemon seam.
- ❌ Don't trust the requested selector as provenance — record the child's installed
  `partial_callback` and fail closed on any disagreement (a mislabeled arm is worse than no run).
- ❌ Don't re-add any GTK lab bridge (spawn/activation/log_path) to "make activation reliable" —
  the production path + arm retry is the point of the exercise; a persistent failure is honest.
- ❌ Don't touch the Pi route, the engine, the thresholds, or production code; don't count reset
  edits (data-level exclusion only).
- ❌ Don't log transcript text on stdout, don't run the lab un-gated/untimed, don't exercise the
  live systemd unit or the live desktop (R.7), don't foreground the daemon.
- ❌ Don't invoke the Pi factory in unit tests (PiEditorClient connects); don't add a second
  verdict-shaped table to the evidence doc; don't rewrite historical commands/numbers.
- ❌ Don't proceed if S1/S2/S3 seams are absent — report the blocker instead of re-implementing.

---

## Confidence Score

**8/10** — every edit site is verified in the current worktree with the three sibling contracts
read in full (S1 landed, S2 visible in-tree, S3's PRP treated as the binding contract); the
identity/seq stamping is proven available at the exact hook (reader-thread window,
`_bulk_identity` docstring); the fail-closed matrix, blocked semantics, scrubbing and truncation
rules all trace to verbatim architecture-doc mandates; and the unit-test design reuses the
repo's established import/mock patterns with no live surfaces. The −2: (a) S3 lands in parallel —
its final ReadyEvent/field shapes could shift slightly from the PRP (mitigated by the dependency
gate in Task 0 and by consuming only documented, defaulted fields); (b) the mocked `run_inner`
smoke capstone needs careful fake wiring (control_send/until/paced_feed monkeypatches) and may
need one iteration to pin timing-insensitive assertions — the per-helper tests (1)-(11) already
carry the contract if the capstone proves brittle.
