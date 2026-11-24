# PRP — P1.M2.T1.S5: Qualify a private Pi prompt frame observation

## Goal

**Feature Goal**: Close the G5 "editor read ≠ Ghostty paint" gap for the pi-ghostty route with two
landed capabilities: (1) **Pi agent/config/state isolation** — the route's ghostty+pi child runs
under a disposable `HOME`/XDG tree so operator extensions/sessions/config are never loaded (binary
discovery stays in the parent via `PI_BIN`/`shutil.which`; NO fallback to real HOME, ever); and
(2) a **bounded route-local frame observer** — a `grim` window-region digest loop over the
disposable Ghostty window, correlated with the independently sampled 10 ms editor read-poll and
the S3/S4 ack/anchor data, with clock and observer resolution calibrated by boot-time probes.
The observer must provably distinguish `visible_insert` / `visible_correction` from `ack_only`,
`unchanged`, `cursor_redraw`, `reset` and `missed_below_resolution` (mocked window/process/event
feeds in unit tests). If display observation cannot be verified, the editor poll stays a
**labelled proxy** and every frame metric is marked `unverified`/`blocked` — never a synthetic
passing timing. Never touch the live window/session (R.7).

**Deliverable** (2 new files, 2 edited files):
1. `tests/g5_frame_observer.py` — NEW pure-stdlib module: `FrameEvent`, `FrameObserver`
   (injected `capture_fn`, ~50 ms cadence, bounded deque + JSONL, capture-latency stamps),
   `window_geometry(env, allowed_pids)` (swaymsg get-tree, exactly-one ghostty node with
   tracked pid), `grim_capture(geo, env)` (PNG bytes → sha256 digest, no pixels persisted),
   `correlate_frames(...)` (the 8-class classifier, reusing `g5_timing_support.changed_spans`
   read-only), `calibrate(...)` (text probes + cursor-redraw probes via wtype), and the
   `frame_observer` artifact-block builder. Mode A docstrings.
2. `tests/test_g5_frame_observer.py` — NEW hermetic unit file: classifier matrix (all 8
   classes), bounded-rings/caps, geometry guard (0 nodes / >1 node / untracked pid → blocked),
   env-isolation helper assertions, calibration with a fake clock and scripted captures,
   miss-rule honesty (a miss is a miss, never imputed).
3. `tests/g5_timing_lab.py` — EDIT, Pi route only + additive artifact wiring:
   `_pi_window_env()` disposable-HOME env helper used by `boot()`; observer
   start/calibrate/stop in the Pi route lifecycle; `self._log_path` initialized eagerly
   (mirrors GtkRoute) so pi smoke stops crashing; `run_inner` gains the additive
   `frame_observer` block + per-record bounded `frame_qualified` list on the pi route;
   `preflight_note()` updated; module docstring note. **Zero** changes to `_G5PiBundle`,
   `_CancelOnLeaveTarget`, `bulk_target_factory`, `_poll_loop` semantics, or any
   voice_typing/** file.
4. `tests/G5_TIMING_EVIDENCE.md` — EDIT, append `## Pi frame observer qualification
   (P1.M2.T1.S5)`: Pi preflight tools, disposable-HOME inputs, measured observer resolution,
   proxy limits. NOT route+verdict shaped (the g6 parser owns the one verdict table);
   historical rows untouched.

**Success Definition**:
- (a) The pi child env provably contains `HOME=<lab.root>/home` + XDG overrides under it, PATH
      preserved, `LD_LIBRARY_PATH` stripped, private `SWAYSOCK`/`WAYLAND_DISPLAY`/
      `XDG_RUNTIME_DIR` passed explicitly; pi boots under it (socket appears) or the route
      honestly fails — never a real-HOME fallback.
- (b) With grim + a resolvable tracked window, the observer runs a bounded digest loop, and the
      qualification output classifies each correlated field change; unit tests prove every class
      boundary with mocked feeds; boot calibration measures (and records) frame-detect vs
      poll-detect latency for text and cursor-redraw probes.
- (c) Without grim / with a geometry miss / with an env-identity mismatch: observer `blocked`,
      route still measures (editor poll labelled proxy), artifact carries the explicit Pi
      coverage block, exit semantics unchanged.
- (d) `timeout 200 .venv/bin/python -m pytest tests/test_g5_frame_observer.py -q` green (new);
      `timeout 200 … tests/test_g5_timing_lab.py -q` green (S4 contract intact);
      `timeout 120 … tests/test_g5_timing_support.py -q` green (S3 engine untouched); pi smoke
      no longer crashes; `git status` shows exactly the 4 files.

## User Persona

Not applicable (internal acceptance instrumentation; no operator-facing surface). DOCS: Mode A —
module docstrings + `tests/G5_TIMING_EVIDENCE.md` record the observer's scope and limits. **No
production extension or config claims**: `.pi/extensions/voice-editor.ts` stays harness-owned
lab fixture; nothing in `voice_typing/`, `config.py`, `config.toml`, README changes.

## Why

- **The architecture doc mandates it** (`architecture/bulk_delivery_gate.md` § G5): "field state
  is not actual Ghostty rendering. Record instrument precision/scope; get qualified independent
  changed-frame evidence in the private route if feasible, otherwise explicitly mark any
  frame-specific gate unverified and BUG-002 open. No invented frame or cross-route pass."
  And: "Before measuring Pi, isolate its agent/config/state and restrict extensions to the
  harness-owned fixture; a real HOME used only to locate binaries must not load live operator
  sessions/extensions. If that can't be safely arranged, block that route and record it."
- **BUG-002 acceptance depends on it**: S6 (paired comparison + lag localization) and T2.S3
  (production-source qualification on both routes) need to know whether pi-ghostty "visible"
  timings are paint or editor-model truth. Without S5 their numbers inherit an unlabelled proxy.
- **Privacy/safety**: today's route inherits real HOME into the pi child — operator sessions,
  agent config and global extensions load inside a scratch measurement. Isolation is a
  precondition to measuring this route at all.

## What

Route-local instrumentation + isolation, defaulting to today's behavior when the observer is
unavailable (labelled, additive output only). The live paired route RUNS are S6's task; S5
delivers the qualified observer and runs at most one private qualification pass to populate the
evidence section.

### Success Criteria

- [ ] `_pi_window_env()` returns the disposable env; `boot()` uses it for the ghostty spawn;
      unit test asserts every key (HOME/XDG_*/PATH/LD_LIBRARY_PATH/SWAYSOCK/WAYLAND_DISPLAY/
      XDG_RUNTIME_DIR) and that `lab.root/"home"` is created.
- [ ] No real-HOME path can reach the pi child; a boot failure under disposable HOME surfaces
      as the existing honest `RuntimeError` path (socket/`_editor_ready` never appears).
- [ ] `FrameObserver`: injected `capture_fn`, stop-event, bounded deque + JSONL
      (`field_frames.jsonl`, cap ≈ `g5.MAX_REPORT_LINES * 200` like the poll loop), per-sample
      `(t_mono, t_wall, digest, changed, capture_ms)`, digests only — zero pixel bytes stored.
- [ ] `window_geometry` blocks (returns None + reason) on 0 ghostty nodes, >1 ghostty node, or
      pid ∉ lab-tracked set; observer subprocesses always receive the explicit private
      `SWAYSOCK`/`WAYLAND_DISPLAY`/`XDG_RUNTIME_DIR` env captured at boot.
- [ ] `correlate_frames` produces exactly the 8 classes with S3's miss rule (misses counted,
      never latency-imputed); `reset` requires anchor equality and is excluded from dictation
      counts; classification uses `g5.changed_spans` for insert-vs-correction.
- [ ] Calibration probes: plain chars + Backspace (text/revert), ArrowLeft/Right (redraw, no
      text), pre-warmup (outside every measured window), No Enter ever; per-probe latencies +
      p50/p95 recorded; wtype absent → calibration skipped, status degrades honestly.
- [ ] Artifact + final stdout line gain the additive `frame_observer` block (status
      `verified|unverified|blocked`, reason, proxy label, cadence/capture/resolution stats,
      calibration, samples, class counts) and per-record bounded `frame_qualified` (≤20).
- [ ] Pi `--smoke` no longer crashes (`_log_path` eager init); S3/S4 suites green unedited;
      evidence doc appended (Mode A), no new verdict-shaped table; exactly 4 files changed.

## All Needed Context

### Context Completeness Check

_Pass._ The route's full surface, the S3/S4 contracts it consumes, the capture/probe mechanics,
the isolation design, the 8-class classifier semantics, the miss/labeling laws and the evidence
discipline are all specified below with verified anchors; the research note carries the verified
details.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S5/research/pi_frame_observer.md
  why: "All verified facts behind this PRP: the gap, in-tree contracts with line anchors, the
        grim/swaymsg/wtype mechanics (tools verified present at /usr/bin), isolation design,
        the 8-class contract, the artifact interface for S6/T2.S3, external doc URLs."
  section: "all"
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/bulk_delivery_gate.md
  why: "§ G5 — the verbatim mandates S5 implements (frame-vs-render qualification, isolation,
        block-if-unsafe, per-route timeout, smoke≠measurement). § 'Gate and evidence handoff' —
        one verdict table law, append-only evidence."
- file: tests/g5_timing_lab.py
  why: "THE integration file. PiGhosttyRoute :401-633 (boot :416, _focus_ghostty :460,
        _log_editor_state :477, _editor_ready :506, _poll_loop :526, field_log :559,
        bulk_target_factory/_G5PiBundle/_CancelOnLeaveTarget :562-629, preflight_note :631);
        PI_EXT_SRC :85; _Lab spawn/kill/kill_all :232-277; boot_sway :279-292 (exports private
        SWAYSOCK/WAYLAND_DISPLAY); FieldLog :159; start_daemon :719; _resolve_partial_source
        :746; run_inner :766 (record assembly ~:975-1035, artifact ~:1035-1065); desktop_env
        ~:1070; ROUTES :635."
  pattern: "log() JSONL stdout lines; until() bounded polls; own-process-group spawn bookkeeping;
            counts-only diagnostics."
  gotcha: "Line numbers drift — locate by named symbols. The Pi route is YOURS to edit now
           (S4 froze it only for S4); _G5PiBundle/_CancelOnLeaveTarget/bulk_target_factory/
           _poll_loop stay untouched anyway (S6 depends on them verbatim)."
- file: tests/g5_timing_support.py
  why: "READ-ONLY consumption: changed_spans (insert-vs-correction), FieldEvent.t semantics,
        ReadyEvent.ack_ts ('never a frame'), ReplayRecord.anchor_text, the miss rule,
        MAX_REPORT_LINES=120 :1019, additive report-key tolerance."
- file: tests/test_g5_timing_lab.py
  why: "S4's suite — MUST stay green unedited. It asserts PiGhosttyRoute(...).
        bulk_target_factory() returns a callable WITHOUT invoking it; keep that true."
- file: voice_typing/pi_editor.py
  why: "READ-ONLY: PiEditorClient (:158, closed op set insert|replace|cancel|read :259),
        PiEditorTarget (:352, ACK≠paint law in module docstring :30-49), PiEditorTakeoverWatch
        (:720). The route already builds these via bulk_target_factory — S5 adds no client of
        its own except the existing _poll_client pattern for probes."
  gotcha: "insert/replace REFUSE when range not owned ('range not owned'/'dirty') — you cannot
           manufacture text changes through the socket; probes go through wtype keystrokes."
- file: .pi/extensions/voice-editor.ts
  why: "The harness-owned fixture boot() copies into proj/.pi/extensions. setTimeout(0) render
        scheduling, no render-completed callback — WHY the observer is needed and why ACK/model
        writes are not paint."
- file: tests/G5_TIMING_EVIDENCE.md
  why: "Append target. Headings today: Verdict table :14, Run commands :28, Provenance :50,
        Thresholds :81, Failure register :103, Lab-side bridges :128, Open items :148,
        Hygiene :167, Measurement method :177 (S3). New section goes after :177."
- url: https://gitlab.freedesktop.org/wayland/grim
  why: "grim(1): `grim -g \"X,Y WxH\" -` crops geometry, `-` = PNG to stdout; needs
        wlr-screencopy (sway implements it on every backend)."
- url: https://man.archlinux.org/man/sway-ipc.7.en
  why: "swaymsg -t get_tree JSON: nodes carry app_id, pid, rect{x,y,width,height} — the
        geometry + identity source for the window guard."
- url: https://github.com/atx/wtype
  why: "wtype(1): Wayland virtual-keyboard typing bound to the target WAYLAND_DISPLAY — the
        calibration probe mechanism."
- file: AGENTS.md  # two-timeout law; never foreground the daemon; lab only via its env gate;
                   # voicectl under timeout; smoke vs full-route discipline
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── .pi/extensions/voice-editor.ts   # harness-owned fixture (PI_EXT_SRC) — READ-ONLY
├── tests/
│   ├── g5_timing_lab.py             # EDIT: Pi route isolation + observer wiring + artifact
│   ├── g5_timing_support.py         # READ-ONLY (S3 engine: changed_spans, miss rule, caps)
│   ├── test_g5_timing_support.py    # READ-ONLY (S3 contract — must stay green)
│   ├── test_g5_timing_lab.py        # READ-ONLY (S4 contract — must stay green)
│   ├── G5_TIMING_EVIDENCE.md        # EDIT: append qualification section (Mode A)
│   ├── g5_frame_observer.py         # CREATE
│   └── test_g5_frame_observer.py    # CREATE
└── voice_typing/                    # READ-ONLY (pi_editor.py consumed as-is)
```

### Desired Codebase tree with files to be added and responsibility of file

```bash
tests/
├── g5_frame_observer.py      # NEW: FrameEvent/FrameObserver (injected capture, bounded,
│                             #     digest-only), window_geometry (identity-guarded),
│                             #     grim_capture, correlate_frames (8 classes, S3 miss rule),
│                             #     calibrate (text + cursor-redraw probes), build_frame_block
├── test_g5_frame_observer.py # NEW: full mock matrix — classifier classes, bounds, guards,
│                             #     env isolation, calibration honesty
├── g5_timing_lab.py          # +_pi_window_env(); boot(): disposable HOME + observer start +
│                             #     calibration; _log_path eager init (smoke fix); run_inner():
│                             #     additive frame_observer block + frame_qualified records;
│                             #     preflight_note updated
└── G5_TIMING_EVIDENCE.md     # + "## Pi frame observer qualification (P1.M2.T1.S5)"
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DEPENDENCY GATE. S4's seams must be in-tree before editing (they are at
#   research time): grep -n '_resolve_partial_source\|partial-source' tests/g5_timing_lab.py.
#   grep -n 'def changed_spans' tests/g5_timing_support.py (S3). If absent, STOP and report.
# CRITICAL #2 — NO REAL-HOME FALLBACK. If pi fails to boot under the disposable HOME, the
#   route FAILS honestly (existing until()/RuntimeError path). Never "fix" it by restoring
#   operator HOME — the architecture doc says block and record, not measure anyway.
# CRITICAL #3 — NEVER TOUCH THE LIVE WINDOW/SESSION. Every observer subprocess (swaymsg, grim,
#   wtype) gets an EXPLICIT env= with the private SWAYSOCK/WAYLAND_DISPLAY/XDG_RUNTIME_DIR
#   captured at boot_sway time — never a bare inherit. Geometry must resolve EXACTLY ONE
#   ghostty node whose pid is in the lab's tracked set, else observer=blocked. grim crops the
#   private output's region; no path can reach the operator's display.
# CRITICAL #4 — DIGESTS ONLY, BOUNDED. No PNG bytes persisted anywhere; frames JSONL capped
#   like the poll loop (g5.MAX_REPORT_LINES * 200 writes); capture loop bounded by stop event
#   + max samples + per-call timeout (2 s). /tmp discipline (AGENTS.md Rule 3) applies to all
#   scratch — the lab root is already bounded scratch with G5_KEEP_SCRATCH escape hatch.
# CRITICAL #5 — A MISS IS A MISS (S3 law). field change with no correlated frame within the
#   attribution window ⇒ counted missed_below_resolution; NEVER impute a frame ts, never let
#   it become a fast sample, never subtract observer resolution from latencies (conservative:
#   report resolution alongside, let S6 interpret).
# CRITICAL #6 — ACK IS NOT A FRAME (R.5 #3). ack_only classification requires the observer to
#   be demonstrably alive (other frames seen in the run) — an ack_only label from a dead
#   observer is just 'blocked', not evidence.
# CRITICAL #7 — DO NOT SILENCE CURSOR BLINK. No --cursor-blink=false / ghostty render-config
#   changes: the item requires DISTINGUISHING cursor redraw (period-stable frame changes, no
#   field change), not eliminating the discriminandum. Classifier handles it.
# GOTCHA #8 — PROBES: wtype only, boot-time (pre-warmup, outside every measured window), a few
#   chars + Backspace + Arrow keys, NEVER Enter (no submission), no ownership risk (owned is
#   null before first acquire; insert/replace refuse unowned anyway). If wtype is missing ⇒
#   calibration skipped, resolution degrades to in-run statistical only — recorded honestly.
# GOTCHA #9 — SMOKE FIX IS ONE LINE OF INTENT: initialize self._log_path in __init__
#   (GtkRoute :319 pattern) so field_log() works pre-boot; do NOT restructure boot for smoke.
# GOTCHA #10 — S4's Pi test asserts bulk_target_factory() returns a callable UNINVOKED; keep
#   _G5PiBundle/_CancelOnLeaveTarget byte-identical (S6's seam). _poll_loop stays exactly as
#   is — the observer is a SECOND independent loop with its own JSONL.
# GOTCHA #11 — EVIDENCE DOC IS PARSER-SCANNED (g6_assessment.parse_route_verdicts overwrites
#   duplicate route keys): the new section must not contain a route×verdict table. Historical
#   commands/numbers untouched and attributed.
# GOTCHA #12 — Two-timeout law on EVERY command; lab runs only as `timeout -k 2 1500 env
#   G5_TIMING_LAB=1 …` (architecture: per-route budget); never the systemd unit, never a
#   foreground daemon, never untimed voicectl. Unit tests pure-mock (no CUDA, no compositor,
#   no sockets). No ruff/mypy in this repo; pytest>=9.1.1.
```

## Implementation Blueprint

### Data models and structure

```python
# tests/g5_frame_observer.py (all new, pure stdlib + hashlib + subprocess + json + threading)
@dataclasses.dataclass
class FrameEvent:
    seq: int; t_mono: float; t_wall: float
    digest: str          # sha256 hex of the cropped PNG bytes — NEVER the bytes
    changed: bool        # digest != previous
    capture_ms: float    # wall time spent in capture_fn (latency component)

class FrameObserver:     # thread; injected capture_fn() -> bytes keeps it unit-testable
    def __init__(self, capture_fn, *, cadence_s=0.05, max_samples=4000, clock=time.monotonic): ...
    def start(self); def stop(self)   # stop event + join(timeout=5)
    def events(self) -> list[FrameEvent]
    def stats(self) -> dict           # cadence p50/p95, capture_ms p50/p95, samples, capped

def window_geometry(env: dict, allowed_pids: set[int]) -> tuple[str, str] | None
    # swaymsg -t get_tree; exactly one node app_id=="ghostty" with pid in allowed_pids;
    # returns ("X,Y WxH", reason|"ok") — None + reason on any miss (guard CRITICAL #3)

def grim_capture(geo: str, env: dict, timeout: float = 2.0) -> bytes
    # sp.run(["grim", "-g", geo, "-"], env=env, capture_output=True, timeout=timeout)

def correlate_frames(field_events, frame_events, acks, anchor_text, *,
                     attrib_window_s, period_tol=0.35, min_period_s=0.15) -> dict
    # 8 classes per research §5; uses g5.changed_spans for insert-vs-correction;
    # attribution_window = max(2 * observed_cadence_p50, 0.15) recorded in the block

def calibrate(observer_probe_ctx) -> dict   # text probes + arrow-key redraw probes → latencies

def build_frame_block(...) -> dict          # the additive artifact interface (research §6)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: VERIFY DEPENDENCIES (blocking gate).
  - grep -n '_resolve_partial_source' tests/g5_timing_lab.py        # S4 in-tree
  - grep -n 'def changed_spans' tests/g5_timing_support.py          # S3 in-tree
  - command -v grim swaymsg wtype ghostty                            # record availability
  - If an S3/S4 seam is missing: STOP and report (S5 cannot proceed).

Task 1: CREATE tests/test_g5_frame_observer.py FIRST (RED).
  - Import pattern: sys.path.insert(0, str(Path(__file__).parent)); import
    g5_frame_observer as fo; import g5_timing_support as g5 (mirror
    tests/test_g5_timing_support.py :22-24).
  - FAKES: scripted capture_fn returning ordered PNG-ish blobs on a controllable fake clock;
    synthetic FieldEvent/ReadyEvent/ack streams; monkeypatched sp.run for swaymsg (canned
    get_tree JSON: one/zero/two ghostty nodes, tracked/untracked pids) and grim (bytes);
    fake wtype runner.
  - CASES (all under timeout 200):
    (1) FrameObserver: bounded deque/JSONL; stop() joins; digests only (assert no raw-bytes
        key anywhere in the file it writes); capture_ms stamped; changed flag correct.
    (2) window_geometry matrix: one tracked node → ("X,Y WxH","ok"); zero → None+reason;
        two → None+reason; untracked pid → None+reason; malformed JSON → None+reason.
    (3) correlate_frames classifier matrix — one test per class: visible_insert (span grew +
        frame in window), visible_correction (span rewritten + frame), ack_only (ack, no
        field, no frame, observer alive), unchanged, cursor_redraw (period-stable frames, no
        field), reset (text == anchor + frame; NOT counted as dictation), missed_below_
        resolution (field, no frame in window — counted, never latency-imputed),
        unpaired_frame (frame, no field, not periodic).
    (4) window-edge: frame just outside attribution window ⇒ miss; frame inside ⇒ correlated;
        attribution window derived from cadence (2×p50 clamp 150 ms).
    (5) calibrate with fake clock + scripted captures: per-probe latencies recorded; wtype
        failure/absence ⇒ calibration {"skipped": reason} (no fabricated numbers).
    (6) build_frame_block: status transitions verified|unverified|blocked with reasons;
        proxy label present; all count keys present; bounded frame_qualified (≤20).
    (7) _pi_window_env (import from g5_timing_lab — mirror S4's lab-test import discipline):
        HOME under lab.root, XDG_* under it, PATH preserved, LD_LIBRARY_PATH absent,
        SWAYSOCK/WAYLAND_DISPLAY/XDG_RUNTIME_DIR explicit; home dir created.
  - RUN (RED): timeout 200 .venv/bin/python -m pytest tests/test_g5_frame_observer.py -q.

Task 2: CREATE tests/g5_frame_observer.py (GREEN) — the module per the data models above.
  - Pure stdlib; NO voice_typing imports; g5_timing_support imported only for changed_spans
    (read-only use). Every public function Mode A docstring'd (scope + limits, esp. "digest
    observation is a lower bound on paint time; resolution never subtracted").

Task 3: EDIT tests/g5_timing_lab.py — Pi isolation (CRITICAL #2/#3).
  - 3a: _pi_window_env() on PiGhosttyRoute: HOME=lab.root/"home" (mkdir parents), XDG_CONFIG_
        _HOME/XDG_CACHE_HOME/XDG_DATA_HOME/XDG_STATE_HOME under it, copy PATH, drop
        LD_LIBRARY_PATH, explicit SWAYSOCK/WAYLAND_DISPLAY/XDG_RUNTIME_DIR from os.environ.
  - 3b: boot(): ghostty spawn uses env=_pi_window_env(); log({"stage":"pi-isolation",
        "home": "<scratch path>", "xdg": "<scratch path>"}). pi_bin resolution stays in the
        parent BEFORE env construction. Everything else in boot unchanged.
  - 3c: __init__: self._log_path = lab.root / "field_timing.jsonl" (smoke fix, Gotcha #9).

Task 4: EDIT tests/g5_timing_lab.py — observer lifecycle in the Pi route.
  - 4a: boot(): after the poll thread starts — resolve geometry (window_geometry(explicit
        env, allowed_pids=lab-tracked); grim presence via shutil.which). Available ⇒ create
        FrameObserver(capture_fn=partial(grim_capture, geo, explicit_env)) + start; else
        observer_state="blocked" with reason; log one {"stage":"frame-observer"} line either
        way (counts/status only).
  - 4b: boot(): calibration probes when wtype present (pre-warmup; chars+Backspace;
        ArrowLeft/Right; NEVER Enter) via a small bounded helper using the route's
        _poll_client reads + observer events; store results on the route.
  - 4c: teardown (route close/stop path wherever _poll_stop is set): observer.stop();
        frames JSONL left in scratch (deleted with the tmpdir unless G5_KEEP_SCRATCH).
  - 4d: preflight_note(): "10 ms editor read-poll (proxy; extension exposes no render
        callback) + grim frame observer @ ~50 ms (status per run)".
  - DO NOT touch _G5PiBundle, _CancelOnLeaveTarget, bulk_target_factory, _poll_loop.

Task 5: EDIT tests/g5_timing_lab.py — artifact wiring (additive only).
  - run_inner (pi route only): after replays, correlate_frames(field_events=FieldLog.drain()
        transitions, frame_events=observer.events(), acks=record ReadyEvent ack_ts,
        anchor_text per record); artifact gains "frame_observer": build_frame_block(...);
        final stdout metrics line gains "frame_observer":"verified|unverified|blocked";
        per-record additive "frame_qualified" (≤20 entries: field_t/ack_ts/frame_t/class/
        latency_ms). Observer blocked ⇒ explicit Pi coverage block (proxy label, frame
        metrics "unverified"). No thresholds touched; no S3/S4 keys renamed.

Task 6: EDIT tests/G5_TIMING_EVIDENCE.md (Mode A append after :177 section).
  - "## Pi frame observer qualification (P1.M2.T1.S5)": tools preflight (grim/swaymsg/wtype
        verified paths), disposable-HOME isolation (what the pi child sees; harness extension
        from proj/.pi/extensions; no operator state), observer method (window-region digest,
        cadence, capture latency), calibration + measured resolution numbers from the
        qualification run (Task 7), class counts summary, proxy limits (editor poll remains
        the visibility truth when unverified; resolution bounds interpretation; S6/T2.S3
        consume the block). NO route×verdict table; historical content untouched.

Task 7: QUALIFICATION RUN (private, one pass, default source — NOT the S6 comparison).
  - timeout -k 2 1500 env G5_TIMING_LAB=1 PI_BIN=<pi> .venv/bin/python tests/g5_timing_lab.py
        --route pi-ghostty   (exactly as the evidence doc's command #2; never interrupt
        mid-run). Read the frame_observer block; transcribe status/resolution/counts into the
        evidence section. An honest timing FAIL is expected and fine (S6 owns remediation);
        S5 qualifies the OBSERVER. If the environment cannot run it (no ghostty/pi/compositor
        time), the evidence section records the unit-qualification + blocked/unverified label
        and the artifact interface stands — never fabricate numbers.
  - Also: pi smoke check (timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 … --route
        pi-ghostty) completes without the old field_log crash (observer correctly absent).

Task 8: VALIDATE (the loop below). If committed: "P1.M2.T1.S5: private Pi frame observer
  (disposable HOME isolation, grim digest observer + calibration, 8-class correlation,
  additive frame_observer artifact block, labelled proxy fallback)".
```

### Implementation Patterns & Key Details

```python
# PATTERN — identity-guarded geometry (CRITICAL #3; refuse, never guess):
def window_geometry(env, allowed_pids):
    r = sp.run(["swaymsg", "-t", "get_tree"], env=env, capture_output=True, timeout=3)
    tree = json.loads(r.stdout)
    hits = [n for n in _walk(tree) if n.get("app_id") == "ghostty"]
    tracked = [n for n in hits if n.get("pid") in allowed_pids]
    if len(tracked) != 1:
        return None, f"ghostty nodes={len(hits)} tracked={len(tracked)} (refusing)"
    rect = tracked[0]["rect"]
    return f"{rect['x']},{rect['y']} {rect['width']}x{rect['height']}", "ok"

# PATTERN — the explicit-env law for EVERY observer subprocess (never bare inherit):
_priv = {k: os.environ[k] for k in ("SWAYSOCK", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR") if k in os.environ}
env = {**_pi_window_env(), **_priv}          # spawn/lab env + private compositor identity

# PATTERN — attribution + miss rule (CRITICAL #5; conservative, additive):
window = max(2 * cadence_p50, 0.15)
# field change at t: frame change in [t - window, t + window] ⇒ qualified with frame_t;
# none ⇒ missed_below_resolution += 1   (counted; NEVER a latency sample; NEVER imputed)

# PATTERN — status semantics (research §6):
# verified   = observer ran AND ≥1 text-correlated frame (calibration probe or in-run)
# unverified = ran, zero detections (record cadence/capture stats + reason)
# blocked    = never ran (grim missing / geometry miss / env guard) → Pi coverage block,
#              editor poll stays the labelled proxy, frame metrics unverified
```

### Integration Points

```yaml
CONSUMES (in-tree, read-only): S3 changed_spans/FieldEvent/ReadyEvent.ack_ts/anchor_text/miss
  rule/MAX_REPORT_LINES; S4 --partial-source runner, preflight() blocked semantics,
  FieldLog.anchor_text(); _Lab spawn/kill_all pid tracking; boot_sway's exported private
  SWAYSOCK/WAYLAND_DISPLAY.
FEEDS — P1.M2.T1.S6: the additive frame_observer block + per-record frame_qualified as an
  input to lag localization (editor-model vs paint split); the frozen Pi seams verbatim.
FEEDS — P1.M2.T2.S3: the explicit Pi coverage contract (status/reason/resolution/classes)
  that qualification must cite; proxy labelling law when unverified.
UNTOUCHED: voice_typing/**, .pi/extensions/voice-editor.ts (fixture source), g5_timing_
  support.py, test_g5_timing_support.py, test_g5_timing_lab.py, g6_assessment.py, config.py/
  config.toml, README.md (P1.M2.T3.S2 owns it), thresholds/constants, the live desktop.
```

## Validation Loop

> Full paths + functional `timeout` on every command (AGENTS.md two-timeout law); run from
> `/home/dustin/projects/voice-typing`. Unit level is pure-mock; the qualification run is the
> sanctioned env-gated private lab invocation — never the systemd unit, never the live desktop.

### Level 1: Syntax & shape (immediate)

```bash
cd /home/dustin/projects/voice-typing
timeout 30 .venv/bin/python -m py_compile tests/g5_frame_observer.py tests/test_g5_frame_observer.py tests/g5_timing_lab.py
timeout 30 .venv/bin/python -c "import sys; sys.path.insert(0,'tests'); import g5_frame_observer, g5_timing_lab"
grep -n '_pi_window_env\|FrameObserver\|frame_observer' tests/g5_timing_lab.py | head
grep -c 'os.environ\["HOME"\]\|environ.get("HOME")' tests/g5_frame_observer.py   # EXPECTED: 0 (no real-HOME reads)
# Expected: compile/import clean; seams present; the observer module never reads real HOME.
```

### Level 2: Unit contract

```bash
cd /home/dustin/projects/voice-typing
timeout 200 .venv/bin/python -m pytest tests/test_g5_frame_observer.py -q        # NEW file green
timeout 200 .venv/bin/python -m pytest tests/test_g5_timing_lab.py -q            # S4 intact
timeout 120 .venv/bin/python -m pytest tests/test_g5_timing_support.py -q        # S3 intact
# Expected: all three green. An S3/S4 failure means a contract broke — you edited a
# read-only file, which is forbidden here.
```

### Level 3: Private smoke + qualification (env-gated; never interrupt mid-run)

```bash
cd /home/dustin/projects/voice-typing
# pi smoke no longer crashes (observer correctly absent without a compositor):
timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty
# one qualification pass (default source; honest timing FAIL is fine — S5 qualifies the observer):
timeout -k 2 1500 env G5_TIMING_LAB=1 PI_BIN="$(command -v pi)" .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty | tail -5
# Expected: smoke completes (rc 0); the qualification run's final line carries
# "frame_observer":"verified|unverified|blocked" consistent with what actually happened, and
# the pi-isolation log line shows the scratch HOME. Exit 0/1 per the gate; rc 124 = wedged →
# AGENTS.md cleanup before anything else.
```

### Level 4: Docs & scope guard

```bash
cd /home/dustin/projects/voice-typing
grep -n 'Pi frame observer qualification' tests/G5_TIMING_EVIDENCE.md    # new section present
git diff tests/G5_TIMING_EVIDENCE.md | grep -c '^-'                      # append-only-ish; history intact
git status --short
# Expected: ONLY tests/g5_frame_observer.py, tests/test_g5_frame_observer.py,
# tests/g5_timing_lab.py, tests/G5_TIMING_EVIDENCE.md. No voice_typing/, no S3/S4 test
# files, no g6_assessment.py, no README, no config, no .pi/extensions edits.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: compile/import clean; seams grep-present; observer module reads no real HOME.
- [ ] L2: new unit file green; S4's and S3's suites green unedited.
- [ ] L3: pi smoke clean; one qualification pass recorded with an honest frame_observer status.
- [ ] L4: exactly 4 files changed; evidence history preserved; no verdict-shaped table added.

### Feature Validation
- [ ] Pi child runs under disposable HOME/XDG; operator extensions/sessions/config never load;
      no real-HOME fallback exists in code; boot failure under isolation is honest.
- [ ] Observer: identity-guarded geometry, explicit-env subprocesses, digest-only bounded
      capture, calibration recorded; all 8 classes unit-proven incl. miss and reset rules.
- [ ] Artifact/final line carry the additive frame_observer block + bounded frame_qualified;
      blocked ⇒ explicit Pi coverage block with the proxy label; no synthetic timing anywhere.
- [ ] Frozen seams intact: _G5PiBundle/_CancelOnLeaveTarget/bulk_target_factory/_poll_loop;
      S4's callable-not-invoked Pi test still passes; pi smoke fixed exactly per Gotcha #9.

### Code Quality Validation
- [ ] Mode A docstrings on every new public function (scope + limits stated).
- [ ] No new thresholds; no production code/config edits; no pixels persisted; scratch bounded.
- [ ] Every observer subprocess constructed with the explicit private env (grep-verifiable).

### Scope Boundary Validation
- [ ] voice_typing/**, g5_timing_support.py, test_g5_timing_support.py, test_g5_timing_lab.py,
      g6_assessment.py, README.md, config, .pi/extensions/voice-editor.ts untouched.
- [ ] Live desktop/systemd unit/daemon never exercised; lab invoked only through its env gate
      under functional timeouts.

## Anti-Patterns to Avoid

- ❌ Don't fall back to real HOME when pi misbehaves under isolation — block and record (the
  architecture mandate), never measure with operator state loaded.
- ❌ Don't capture anything outside the identity-guarded private window, don't inherit env into
  observer subprocesses, don't persist pixel data, don't leave unbounded frame logs.
- ❌ Don't impute frame timestamps for misses, don't subtract observer resolution from
  latencies, don't upgrade unverified to verified because "the ACK came back" (ACK ≠ frame).
- ❌ Don't disable cursor blink or otherwise tune ghostty rendering to make classification
  easy — distinguish, don't sanitize.
- ❌ Don't touch the frozen Pi seams, the S3 engine, S4's tests, thresholds, or production
  code; don't add a second verdict-shaped table; don't rewrite historical evidence rows.
- ❌ Don't run the lab un-gated/untimed, don't interrupt a qualification run mid-model-load,
  don't exercise the live systemd unit or foreground the daemon.

---

## Confidence Score

**8/10** — the gap, the S3/S4 contracts and the route's full surface are verified in-tree with
named anchors; grim/swaymsg/wtype/ghostty are verified present on this machine; the capture,
guard, calibration and classification designs are all mock-testable pure logic with the exact
class semantics fixed by the item text and the S3 miss/ack laws. The −2: (a) grim-over-headless-
sway capture of the GL-rendered ghostty window is strongly expected to work (wlr-screencopy is
backend-independent; the GTK field already proves GL under this lab's compositor) but is only
provable in the Task-7 qualification run — which is precisely why the PRP hard-wires the honest
blocked/unverified fallback; (b) S4 is finishing in parallel — its landed surface is what S5
consumes, and any late S4 reshape of the artifact assembly region would need the integration
anchors re-grepped (named-symbol discipline covers this).
