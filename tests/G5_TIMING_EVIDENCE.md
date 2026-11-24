# G5 TIMING EVIDENCE — per-route timing gate (P1.M6.T4.S1)

- Date: 2026-11-23  |  HEAD: c9a0a45 (working tree: + feed seam, + G5 harness)
- Gate: PRD §4.2sexies **R.7 G5** — speech clock = word-aligned replay of the
  real-voice clips at 1× with zero-slice silence; warm GPU (resident recorder,
  ONE discarded warmup, `auto_unload_idle_seconds=0`); all clocks
  `time.monotonic()` with a (mono, wall) heartbeat check.
- **A G5 pass never marks a row verified.** These rows are the gate's FIRST
  reading: every claimed route is labeled `pass | fail(reason) | blocked(reason)`
  — misses are misses, a sustained backlog or a sentence-end dump fails the
  route regardless of medians, and a count shortfall after the replay budget is
  a reported failure (Gotchas #7/#8/#9).

## Verdict table

| route | verdict | ins | cor | miss | speech med/p95 ms | worst ms | ready ins/cor p95 ms | max out | flags |
|---|---|---|---|---|---|---|---|---|---|
| im-gtk | **fail** (backlog sustained; counts 20/0 < 100; correction p95 unexercised) | 20 | 0 | 870 | 195.1/318.6 ✓ | 318.6 ✓ | 4.4 / — | 57 | backlog-sustained |
| pi-ghostty | **fail** (speech→visible 12.6 s median; backlog sustained; sentence-end dump) | 108 | 169 ✓ | 231 | 12616.2/13203.1 ✗ | 13203.1 ✗ | 11.5 / 11.7 ✓ | 57 | backlog-sustained, dump |

Both routes **FAIL G5**. The dominant finding is identical on both: with the
shipped bulk path, words become visible only at **utterance granularity**
(the controller's newest-partial-wins coalescing applies at most one live op
per utterance, and each utterance's text lands as one visible edit at its end)
— so the field accumulates a multi-second, multi-word backlog for the whole
utterance duration. No route streams words live at speaking pace.

## Run commands (drift re-run; P1.M4.T5.S2-style re-measurement)

```sh
# 0. one-time alignment fixtures (daemon venv + CUDA LD recipe, asr-lab README):
CUDA_LIBS="$(.venv/bin/python -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b
def _d(m):
    f=getattr(m,"__file__",None)
    return os.path.dirname(f) if f else next(iter(m.__path__))
print(_d(a)+":"+_d(b))')" && export LD_LIBRARY_PATH="$CUDA_LIBS"
timeout -k 2 900 env G5_ALIGN=1 .venv/bin/python tests/g5_make_alignments.py

# 1. scaffold smoke (feed seam + real models + control socket, no compositor):
timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 \
    .venv/bin/python tests/g5_timing_lab.py --route im-gtk

# 2. the routes (private compositor; ~4-20 min each; NEVER interrupt mid-run):
timeout -k 2 1500 env G5_TIMING_LAB=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk
timeout -k 2 1500 env G5_TIMING_LAB=1 PI_BIN=~/.local/bin/pi \
    .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty
# Exit 0 pass / 1 honest fail / 2 misuse. One JSON verdict line per route on stdout.
```

### R.8 paired arms (P1.M2.T1.S4 — the runner; the recorded comparison is S6)

Per route, ONE private CLI run per arm: `--partial-source plain` (the spawn
child installs `on_realtime_transcription_update`) and the UNFLAGGED default
arm (the production source — stabilized today; the daemon seam materializes
it, argparse never does). The S6 paired runs + lag localization consume
these commands as-is:

```sh
# im-gtk — plain arm, then the default arm:
timeout -k 2 1500 env G5_TIMING_LAB=1 .venv/bin/python tests/g5_timing_lab.py \
    --route im-gtk --partial-source plain
timeout -k 2 1500 env G5_TIMING_LAB=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk

# pi-ghostty — plain arm, then the default arm (PI_BIN for binary discovery only):
timeout -k 2 1500 env G5_TIMING_LAB=1 PI_BIN=~/.local/bin/pi .venv/bin/python tests/g5_timing_lab.py \
    --route pi-ghostty --partial-source plain
timeout -k 2 1500 env G5_TIMING_LAB=1 PI_BIN=~/.local/bin/pi .venv/bin/python tests/g5_timing_lab.py \
    --route pi-ghostty

# misuse exits 2 (argparse validates the choice at BOTH parser levels):
timeout 30 env G5_TIMING_LAB=1 .venv/bin/python tests/g5_timing_lab.py \
    --route im-gtk --partial-source loud; echo "rc=$?"
```

Scaffold-smoke validation (NOT a measurement — wiring only; both arms, no
compositor):

```sh
timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 \
    .venv/bin/python tests/g5_timing_lab.py --route im-gtk
timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 \
    .venv/bin/python tests/g5_timing_lab.py --route im-gtk --partial-source plain
```

Blocked semantics: a missing preflight binary/fixture (sway, xvfb-run,
python3; ghostty or PI_BIN for pi-ghostty; clips or alignments) prints one
`{"stage":"preflight","verdict":"blocked","route":…,"reason":…}` line and
exits 1 with NOTHING spawned. A requested-vs-installed source mismatch
refuses to measure (honest harness-fail line, exit 1); a truncated
update-ready capture aborts (unattributable); a field-log cap hit flags
the record `capped` (never imputed).

### S4 instrumentation notes (P1.M2.T1.S4)

- Stage observations are daemon-receipt `g5.ReadyEvent`s (`stage="daemon"`;
  gen/utt stamped inside the reader-thread window via `_bulk_identity()`,
  seq read from `_bulk_seq` after the orig dispatch; degraded to None where
  the boundary provides nothing). Producer-stage stamps remain a future
  seam; ACK is not a frame (S3).
- Provenance: every run records `partial_source_requested` vs
  `partial_callback_effective` (the child's ready payload is the ONLY
effective-source truth) on the warm line, in the artifact provenance, on
  every replay record, and on the final metrics line.
- No raw speech in any default stdout line: warm/replay/verdict lines carry
  counts and provenance only (the `first_partial` snippets were removed in
  S4); transcript text stays in the internal records and the scratch JSONL,
  which is deleted with the tmpdir.
- Pi route unchanged: injected adapter + `_CancelOnLeaveTarget` instrument
  reset + 10 ms read-poll; the real-HOME delta stays binary-discovery-only;
  reset edits are excluded from counts via `anchor_text` + S3's reset rules
  (data-level — no new code on that route).

## Provenance (both runs)

- GPU: NVIDIA GeForce RTX 3080 Ti (12 GiB) — device=cuda compute_type=float16
  model=small.en (the configured final path; context_prompt on, prompt empty
  throughout — confirmed-visible never advanced past the replay window).
- Compositor: private sway (WLR_BACKENDS=x11, pixman, xvfb-run -a) +
  dbus-run-session private bus; disposable HOME/XDG_RUNTIME_DIR/TMPDIR; ONE
  TemporaryDirectory; killpg teardown of OWN session groups; the live systemd
  unit was never touched; no pactl/hyprctl/voicectl against any live session.
- Daemon: in-process `VoiceTypingDaemon(delivery="bulk-text", backend="null",
  hypr_notify=false, duck off, cancel.devices=[nonexistent], auto_stop=0,
  auto_unload=0, feed_input=True)` behind its REAL private control socket
  (start/stop/status only — no daemon internals for control).
- Speech input: `use_microphone=False` child + `feed` seam — the default
  microphone is NEVER captured (R.7); 32 ms slices sleep-to-target on
  time.monotonic(); trailing silence fed as zero slices at pace.
- Clips (cycled): jargon 17.6 s / natural 13.2 s / noisy 7.8 s / pauses 13.5 s
  (16 kHz mono; aligned by faster-whisper word_timestamps=True, same model —
  `tools/asr-lab/voice/<name>.words.json`, committed; natural reconciles 49/49
  with its reference, jargon/noisy/pauses carry honest mismatches that surface
  as misses, never fudged).
- im-gtk field instrument: tests/ime_g3_field_gtk.py with G5_FIELD_TIMING=1
  (the field's own changed/frame events, JSONL, 2000-line cap) on system
  python3, GTK 4.24.1. pi-ghostty instrument: the editor's own read op polled
  at 10 ms (the extension exposes no render callback — granularity noted).
- Heartbeat: every run checks pairwise (monotonic, wall) deltas of the field
  log and the harness; all reported runs passed the check (a violation fails
  the run — Gotcha #4).
- Warm status: resident recorder across replays (`auto_unload_idle_seconds=0`);
  ONE discarded warmup replay before any measured sample.

## Thresholds vs measured (PRD R.7 numbers)

| metric | bar | im-gtk | pi-ghostty |
|---|---|---|---|
| speech-end→word-visible median | ≤ 500 ms | 195.1 ms ✓ | 12616.2 ms ✗ |
| speech-end→word-visible p95 | < 1 s | 318.6 ms ✓ | 13203.1 ms ✗ |
| update-ready→first-changed-frame p95 (insertion) | ≤ 100 ms | 4.4 ms ✓ | 11.5 ms ✓ |
| update-ready→first-changed-frame p95 (correction) | ≤ 50 ms | not exercised ✗ | 11.7 ms ✓ |
| unchanged ⇒ zero field events | must hold | ✓ | ✓ |
| ≥ 100 insertions AND ≥ 100 corrections | floors | 20/0 ✗ | 108/169 ✓ |
| sustained ≥5-word backlog (≥2.0 s) | must not | ✗ (max 57 words) | ✗ (max 57 words) |
| sentence-end dump | must not | ✓ none | ✗ dump |

Note on the two speech→visible readings: im-gtk's 195 ms median is measured
over the words visible at each replay's single commit (the commit lands right
after the utterance's silence gate, so its words read as "fast"), while the
BACKLOG column shows the truth — 57 words outstanding for the whole clip.
pi-ghostty streams more updates (counts pass; 76 field changes per replay on
the revising prompt buffer), but its words' first-visibility clusters at
utterance rewrites seconds after they were spoken. Read BOTH columns together;
the backlog flag is the gate's verdict carrier on both routes.

## Failure register (every breach, spelled out)

### im-gtk (20 measured replays, budget 20)
- backlog ≥5 words sustained ≥2.0 s (max outstanding 57)
- counts 20/0 < 100 after replay budget (one visible commit per replay: the
  final; the controller's per-utterance coalescing never let a partial op
  paint before its final superseded it)
- ready→frame correction p95 unexercised (0 correction ops reached the field)

### pi-ghostty (5 measured replays — budget loop broke early on the count floors)
- speech→visible median 12616 ms > 500 ms
- speech→visible p95 13203 ms ≥ 1000 ms
- backlog ≥5 words sustained ≥2.0 s (max outstanding 57)
- sentence-end dump (an utterance delivered as one final edit)

## Defect found and fixed on the way (production, P1.M6.T2.S1 seam)

`Daemon._bulk_identity` degraded to None for the REAL RecorderHost:
`relay_identity` is a `@property` on the host (returns the snapshot value) but
the seam called it only when `callable()` — the method-shaped test fakes passed
while every real event was dropped as id-less (`dropped_no_id`). Fixed to
accept both shapes (daemon.py; the fakes' method shape still works). Until this
fix the wired bulk path had never delivered a real event — P1.M6.T2.S1's
validation exercised the seam through fakes only.

## Lab-side bridges (zero production change beyond the feed seam)

- im-gtk lab bridge REMOVED (P1.M2.T1.S4): the route now exercises the
  PRODUCTION default factory — `daemon._build_default_bulk_target` +
  `_BulkTargetBundle.start()` (landed in P1.M2.T1.S2): the daemon spawns its
  own IM child and runs the 2 s read-only activation pump on the arm worker,
  and the lab's 3-attempt arm() retry compensates cold GTK-loop stalls (a
  persistent activation failure is an HONEST route fail — no lab-side
  spawn/activation seam may be re-added). Consequence: the default
  ImeProcess carries no log_path, so the ime_host.jsonl capture is lost on
  this route (daemon INFO + set_delivery_state reasons remain).
  Historical note (pre-S4): the route's factory used to perform the G3
  start_adapter recipe itself — spawn → seat-bound globals → ping-pump
  activation (pings pump the host's event loop; a log-only wait deadlocks
  because activate is processed only around request handling) — and return
  the daemon's own `_BulkTargetBundle`, so attach/teardown wiring was
  exactly the production default.
- pi-ghostty: the delivery lifetime ends with `target.leave()` (binding
  cleared) — the extension's owned range persists until an explicit cancel op
  (the trace_07 pin skips cancel when the span bookkeeping is empty). The lab's
  instrument reset sends the raw cancel op at leave so each measured lifetime
  starts from a clean prompt; the measured commit path itself is unchanged.
- Serialization: each replay's stop waits for the stopper's post-teardown
  status (`delivery != active`) before re-arming, and feeding starts only once
  status reports `delivery_state == "active"` (updates dispatched before
  acquire are dropped by the controller — by design).

## Open items

- The visibility matcher (`g5_timing_support.resolve_visibility`) matches
  reference words as contiguous blocks against the field's normalized text
  (positional, bounded windows, single-word substitution rescue). On the
  revising pi prompt buffer its positional assumptions degrade (words first
  visible at rewrite bursts), which likely inflates pi's speech→visible beyond
  the route's true perceptual latency; the backlog/dump findings do not depend
  on it. A per-op diff-based matcher (walking each field change's edit span)
  would remove the assumption — left as the follow-up for the next G5 pass.
- The im-gtk route's partial streaming collapse (3-4 dispatched updates per
  replay vs ~100 during the warmup arm) reproduces only with delivery ACTIVE;
  worth a dedicated look before the next measurement (the backlog verdict does
  not depend on it).
- Both routes fail G5 as shipped; G6 (default-flip) must NOT proceed on this
  evidence. The fix direction the numbers point at: stream partial updates at
  word granularity (per-op coalescing at the field, not per-utterance), then
  re-measure with this exact harness.

## Hygiene (R.7)

Zero contact with the live desktop, real clipboard, default microphone, or
active service anywhere in the lab path: private XDG_RUNTIME_DIR isolates the
control socket + state file; the recorder child runs `use_microphone=False`
(the sanctioned PRD §4.4 feed path); no pactl/pw-cat/hyprctl/voicectl against
live sessions; scratch confined to ONE bounded TemporaryDirectory with killpg
teardown of OWN session groups; field logs capped (2000 lines); only the
alignment fixtures (`*.words.json`) and this report enter version control.

## Measurement method — changed-span attribution (P1.M2.T1.S3)

Appended after the historical content above; every number above predates
this method and is NOT recomputed. This section is prose and bullets only —
deliberately no verdict-shaped table — because
tests/g6_assessment.py:parse_route_verdicts scans pipe tables and overwrites
duplicate route keys; the verdict table at the top of this file must remain
the single parser-compatible current one.

- Truth and units. Field change events (FieldEvent) remain the ONLY
  visibility truth; update-ready stamps are checkpoints. A target ACK
  (ReadyEvent.ack_ts) is recorded for cross-checks and is never a frame: no
  sample may be credited merely because the target ACKs (R.5 value 3).
- Changed frames. A frame is a field snapshot that differs from the previous
  one; its added content is the changed span between two independent
  snapshots (changed_spans over the shared normalized token space). The
  rolling previous snapshot is seeded with the replay's anchor text, so the
  pre-replay field state is never lost (defect fix: the old window matcher
  started from an empty string and could lose the prior snapshot).
- Observation labels (one per ReadyEvent, from attribute_updates):
  - matched — a changed frame charged to this update by content (the frame's
    added spans equal the update's expected added content); one FrameSample
    (ready-to-frame delta) per matched update.
  - missing — dispatched but never painted before end of record; counted,
    never a latency sample, never a 0 ms credit (Gotcha 7 lineage).
  - superseded — its span was never required to paint: explicit controller
    disposition (coalesced, dropped, replaced) or, when (gen, utterance)
    identity is present, a later same-identity update whose text subsumes
    the older's expected added content as a proper normalized prefix. A
    coalesced-away update is superseded, NOT missing.
  - no_op — the update announced nothing new over the observed field state
    (an identical callback); a raw-changed, content-identical frame in its
    watch is a zero-diff violation. The delayed-frame carve-out: a frame
    matching an OLDER pending update's span charges the older update, so the
    newer identical callback generates no false zero-diff violation (defect
    fix: the old next-callback windowing billed a late frame to the newer
    identical callback).
  - ambiguous — the same normalized token added in multiple distinct spans
    of one frame while several pending updates match: genuinely
    indeterminate; counted (updates_ambiguous, words_ambiguous) and excluded
    from latency samples — never guessed.
  - unpaired frames — a changed frame no pending update claims (before the
    first update or after all settled): counted in frames_unpaired, never a
    fast sample. An unobserved edit does not become a fast event.
- Attribution rule. Frames charge to the OLDEST PENDING update whose expected
  added content matches (content matching over normalized tokens, bounded
  look-back) — never by window ownership. A burst's single frame may satisfy
  several pending updates whose combined span it paints (all matched, one
  frame ts). Expected added content = the update's normalized tokens minus
  the multiset already observed at its dispatch, so append-only and rewrite
  routes reduce to the same comparison space.
- Visibility. resolve_visibility is now exactly the .ts projection of
  resolve_visibility_detailed: changed-span alignment against independent
  field snapshots with write-once first appearance (a rewrite or re-add
  never un-sees a word and never overstates its delay), the anchor
  token-position floor (a previous replay's copy can never match), the
  bounded window_fwd=12 / window_back=24 scan, reset handling (a revert
  to/below the anchor baseline adds nothing: no phantom misses, no
  un-seeing; re-added copies resolve ordered-or-ambiguous), and ambiguity as
  the bounded honest answer on dense repeat/rewrite interleavings.
- Producer vs daemon. Producer-ready (before IPC) and daemon-receipt are
  separate checkpoints (R.7): only daemon-stage events pair frames; a
  producer event is paired to its daemon twin by (gen, utterance, seq) and
  its observation carries the producer-to-daemon relay delta in its detail;
  an unpaired producer event is a relay loss (missing) — which is how late
  upstream partials are distinguished from loss during coalescing and from
  late field visibility.
- Clock and coverage. A record whose heartbeat pairs fail heartbeat_ok, or
  that hit the field-log cap, increments clock_failures / cap_failures and
  appends a provenance warning: unverifiable metrics are reported, never
  imputed as a pass and never averaged away; the flag alone does not flip
  the verdict — the miss/count floors already fail honestly when samples
  are lost.
- Counters (additive on RouteMetrics and the JSON verdict row; one trailing
  markdown column, with route and verdict kept as the first two columns):
  updates_total, updates_matched, updates_missing, updates_superseded,
  updates_no_op, updates_ambiguous, frames_unpaired, words_ambiguous,
  clock_failures, cap_failures, provenance_warnings.
- Limits. The engine is pure stdlib and deterministic (no wall clock). The
  pi-ghostty field read is polled (about 10 ms) and is NOT actual Ghostty
  rendering, so frame-specific numbers remain instrument-scoped. Relay
  identity and disposition are used only where the plumbing records them:
  legacy tuple streams behave exactly as before this method (the 14
  pre-existing tests in tests/test_g5_timing_support.py are unchanged and
  green — the historical-comparability contract).

## Pi frame observer qualification (P1.M2.T1.S5)

Appended after the historical content above; every number above predates
this section and is NOT recomputed. Prose and bullets only — deliberately
no route×verdict table (the parser-owned verdict table at the top of this
file remains the single current one).

- Tools preflight (verified present on this machine before the run):
  /usr/bin/grim, /usr/bin/swaymsg, /usr/bin/wtype, /usr/bin/ghostty; pi
  resolved in the PARENT via PI_BIN (a missing binary is the existing
  honest blocked outcome — preflight() was not changed).
- Disposable-HOME isolation (what the ghostty+pi child sees):
  HOME = <lab-root>/home (fresh scratch tree), XDG_CONFIG_HOME/CACHE/DATA/
  STATE under it (created), PATH preserved, LD_LIBRARY_PATH stripped (the
  GL/CUDA-LD recipe), and SWAYSOCK/WAYLAND_DISPLAY/XDG_RUNTIME_DIR passed
  EXPLICITLY from the private session. Operator sessions, agent config and
  global extensions NEVER load; the harness-owned extension still loads
  project-locally from proj/.pi/extensions (cwd=proj; its socket derives
  from XDG_RUNTIME_DIR, so it lands in the disposable root). One addition
  was required to boot unattended: pi's first-run "Trust project folder?"
  gate blocks extension loading under a fresh HOME (the old real-HOME runs
  inherited the operator's existing trust record instead). The route now
  pre-seeds ONLY the scratch project paths into the DISPOSABLE home's
  trust store (<scratch-home>/.pi/agent/trust.json) — nothing is copied
  from the real HOME. NO real-HOME fallback exists in code; a pi boot
  failure under isolation surfaces as the existing honest RuntimeError
  (observed twice during bring-up: the socket never appears, the route
  exits 1, nothing is measured).
- Observer method: after the editor read-poll starts, the route resolves
  the private Ghostty window via swaymsg get_tree under an identity guard
  — EXACTLY ONE node with a known ghostty app_id ("ghostty" or
  "com.mitchellh.ghostty", the form this ghostty 1.4.0 actually maps as)
  whose pid is in the lab's tracked spawn set; any other count is a
  refusal (observer blocked, reason recorded). grim crops that region to a
  PNG on stdout, which is sha256-digested in memory — no pixel bytes are
  ever persisted; field_frames.jsonl carries digests only, capped like the
  poll loop (g5.MAX_REPORT_LINES * 200 writes), in-RAM events bounded by a
  4000-sample deque. Every observer subprocess (swaymsg/grim/wtype) gets
  the explicit private compositor env — never a bare inherit.
- Qualification run (the sanctioned env-gated private lab invocation,
  `timeout -k 2 1500 env G5_TIMING_LAB=1 PI_BIN=… tests/g5_timing_lab.py
  --route pi-ghostty`; 20 measured replays, G5_KEEP_SCRATCH=1 for
  transcription, scratch deleted after): the run's final line carried
  frame_observer=verified alongside an honest route timing FAIL (BUG-002
  remains open; S6 owns remediation — S5 qualifies the OBSERVER, not the
  route). Measured observer numbers from that run's artifact:
  - digest loop cadence p50 69.8 ms / p95 87.4 ms (nominal 50 ms + grim
    spawn cost), per-capture grim latency p50 19.6 ms / p95 37.3 ms
    (window region 0,27 1024x741), 4000 in-RAM samples / 777 changed
    digests, 0 capture errors, JSONL write cap not hit.
  - Boot calibration (wtype into the focused private window, pre-warmup,
    outside every measured window; chars + Backspace + Arrow keys, NEVER
    Enter): 5 probes, 3/3 text-or-revert probes detected by BOTH the poll
    and the observer, 2/2 arrow-key redraws detected as frame-only changes
    (no text change — the cursor-redraw discriminandum). Resolution
    (frame-detect minus poll-detect, text/revert probes): p50 35.2 ms,
    p95 96.1 ms. This is the observer's resolution RELATIVE TO the poll
    instrument; it is reported alongside latencies and NEVER subtracted
    from them.
  - Correlation classes across the run (attribution window 0.15 s =
    2×cadence clamped to the 150 ms floor): visible_insert 399,
    visible_correction 487, unchanged 121, unpaired_frame 22,
    cursor_redraw 1, missed_below_resolution 0, ack_only 0, reset 0.
    Every correlated field change painted within the window in this run —
    but the CLASSES are per-run data, not a guarantee; a miss is a miss
    wherever it occurs (counted, never latency-imputed).
  - Per-record frame_qualified (≤20 entries: field_t/ack_ts/frame_t/
    class/latency_ms) rides the artifact for S6's lag localization.
- Proxy limits (the honesty contract): the editor read-poll remains the
  ONLY visibility truth whenever the observer is blocked or unverified —
  a blocked observer (grim missing, geometry-guard refusal, env guard) is
  an explicit Pi coverage block in the artifact and the final line, and
  frame metrics are then unverified, never synthetic. Digest observation
  at ~70 ms cadence is a LOWER BOUND on paint time: it cannot certify the
  ≤100/50 ms frame bars alone, and an ACK never upgrades a status (R.5 #3
  — ack_only is only labeled when the observer demonstrably saw other
  frames). The frozen S4 seams (_G5PiBundle/_CancelOnLeaveTarget/
  bulk_target_factory/_poll_loop) are byte-identical; the observer is a
  SECOND independent loop. S6 (paired comparison) and T2.S3 (production
  qualification) consume the additive frame_observer block as recorded
  here.
- Defects found and fixed on the way (lab-side, all unit-proven now):
  pi smoke crashed on field_log before boot (eager _log_path init, the
  GtkRoute pattern); the geometry guard initially matched only app_id
  "ghostty" and correctly refused this machine's com.mitchellh.ghostty
  (allowlist widened, refusal behavior unchanged and still tested); the
  observer's capture_ms aggregate was double-scaled ×1000 (the run's own
  raw frames log exposed it — stats fixed, ms-scale regression test
  added); the G5_KEEP_SCRATCH escape hatch never actually kept the root
  (TemporaryDirectory deleted unconditionally — now mkdtemp + guarded
  teardown).
## Paired callback comparison and stage diagnosis (P1.M2.T1.S6)

### Provenance

- Date: 2026-11-24
- HEAD commit: 9ffc54b
- RealtimeSTT version: 1.0.2
- Model / device: {"compute_type": "float16", "context_prompt": true, "device": "cuda", "model": "small.en", "partial_callback": "on_realtime_transcription_stabilized"}
- Cadence: audio fed in real time: 32 ms chunks sleep-to-target on time.monotonic() + 1.6 s trailing silence (paced_feed)
- Replay budget: g5.REPLAY_BUDGET=20 (actual replays — im-gtk/stabilized: 20, pi-ghostty/plain: 20, pi-ghostty/stabilized: 20)
- Warm policy: resident (auto_unload_idle_seconds=0; one discarded warmup)
- Pi frame observer: {'pi-ghostty': 'verified'}

Exact commands (sequential, one arm at a time):

```bash
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk --partial-source plain
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 PI_BIN="$(command -v pi)" .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty --partial-source plain
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 PI_BIN="$(command -v pi)" .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty
```

### Route-by-source result

| Route | Arm | Status | 1st useful (med ms) | 1st useful (p95 ms) | 1st visible (med ms) | word lag med/p95 (ms) | upd matched/sup/no-op | ins/cor | miss | backlog max | dump | n |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| im-gtk | plain | not-run | — | — | — | — | — | — | — | — | — | — |
| im-gtk | stabilized | measured | -11580.7 | -6515.3 | -11576.8 | 190.5/244.3 | 1/0/31 | 1/0 | 872 | 57 | no | 20 |
| pi-ghostty | plain | measured | -11624.7 | -6558.0 | -11618.9 | 11983.1/16069.9 | 14/0/737 | 5/9 | 856 | 57 | yes | 20 |
| pi-ghostty | stabilized | measured | -11626.0 | -6556.9 | -11615.6 | 7786.2/16077.3 | 17/0/501 | 5/12 | 834 | 57 | yes | 20 |

`1st useful`/`1st visible` are speech-end-anchored boundary offsets: the first useful update fires mid-clip, so the cell is NEGATIVE by construction (its magnitude is when the first words were recognized relative to the clip's final word end). Cross-arm deltas at these cells are the early-callback/early-visibility signal (same clips ⇒ same anchors, deltas cancel the anchor). The per-word VISIBLE lag is the verbatim `word lag med/p95` column.

### Stage decomposition (medians; p95 at n≥5)

| Route | Arm | speech→update | update→ack | ack→field | useful→field (merged) | field→frame | paint-qualified (S5) | frame basis | n |
|---|---|---|---|---|---|---|---|---|---|
| im-gtk | plain | — | — | — | — | — | — | — | — |
| im-gtk | stabilized | -11580.7 ms | — | — | 2.6 ms | — | — | editor read-poll proxy (frame NOT verified) | 20 |
| pi-ghostty | plain | -11624.7 ms | — | — | 3.5 ms | — | 42.7 ms | S5-qualified paint, post-update boundary (disclosed fallback) | 20 |
| pi-ghostty | stabilized | -11626.0 ms | — | — | 4.4 ms | — | 29.8 ms | S5-qualified paint, post-update boundary (disclosed fallback) | 20 |

Rows labelled `merged` carry the update→field latency in one cell (the runner recorded no coherent ack_ts for that arm); `ack→field` and `update→ack` are then absent. The `field→frame` cell is the EXACT first-visible-paint pairing — usually structurally absent because S5's correlator treats each replay's first drained event as baseline, and that event is usually the first-visible paint itself. `paint-qualified (S5)` is the disclosed fallback: the earliest S5-qualified paint at/after the useful update, using the pair's own (field→frame) latency — real measured pairs, boundary choice disclosed; the two cells are never merged. When neither exists the stage stays the labelled proxy: editor read-poll proxy (frame NOT verified).

### Early callback vs early field visibility

- pi-ghostty: plain-vs-stabilized first-useful-update median delta = +1.3 ms (plain NOT earlier at the callback boundary)
- pi-ghostty: plain-vs-stabilized first-visible-word median delta = -3.3 ms (plain EARLIER at the field boundary)

### Dominant stage per arm

- im-gtk/stabilized: dominant post-callback stage = useful→field (merged) at 2.6 ms median (n=20)
  · per-word speech→visible lag (verbatim metrics): med 190.5 ms / p95 244.3 ms — everything above that is accumulated BEFORE the callback/adapter stages
- pi-ghostty/plain: dominant post-callback stage = paint-qualified (S5) at 42.7 ms median (n=20)
  · per-word speech→visible lag (verbatim metrics): med 11983.1 ms / p95 16069.9 ms — everything above that is accumulated BEFORE the callback/adapter stages
- pi-ghostty/stabilized: dominant post-callback stage = paint-qualified (S5) at 29.8 ms median (n=20)
  · per-word speech→visible lag (verbatim metrics): med 7786.2 ms / p95 16077.3 ms — everything above that is accumulated BEFORE the callback/adapter stages

Candidate criteria for the T2 subtasks: the winning arm's update volume/burst profile (updates_total, superseded/no-op shares, worst_gap_ms above) sizes P1.M2.T2.S1's dispatch-promptness + burst fail-closed design; the dominant stage and its magnitude name what P1.M2.T2.S2's remediation must move.

### Instrumentation limits

- single machine / single session scope; editor read-poll instrumentation on the pi route (10 ms poll)
- im-gtk/plain: not-run (artifact file missing: /home/dustin/projects/voice-typing/plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T1S6/research/artifact-im-gtk-plain.json)
- Stage shares are medians over replays; p95 only at n≥5; misses counted, never imputed; replay counts may differ across arms (early budget break) — a disclosed limit, not pooled.
### Run history and discipline (S6)

- Four sequential arms, one CUDA model load at a time, each under `timeout -k 2 1500`
  (bash-tool backstop 1560 s), private compositor/daemon only, `G5_KEEP_SCRATCH=1`;
  after each run the artifact was copied into `research/` under its per-arm name and
  the scratch tmpdir was deleted immediately (tmpfs = RAM discipline).
- im-gtk × plain: attempt 1 aborted at replay 14 and attempt 2 at replay 0 with the
  same runner-side `RuntimeError("bulk delivery never re-armed")` — the ctl
  `delivery_state` never reached the armed state within the 150 s window after
  `start`. Per the re-run-once discipline the arm stands as **not-run**: no numbers
  exist for it and none were borrowed from any other arm.
- The other three arms each completed the full 20/20 replay budget with heartbeat
  sanity ok and zero clock failures. Their exit code 1 is the honest pre-T2 timing
  verdict recorded inside the artifacts — the runner worked; the timing bars did not.

### Early callback vs early field visibility — the R.8 answer

- **pi-ghostty, callback boundary**: plain's first useful update is **+1.3 ms later**
  than stabilized's (median of 20 matched replays each). The external_deps
  prediction — both callbacks fire in the same eligible decode, stabilized first
  inline, plain not inherently earlier — is **confirmed by measurement**: there is
  no early-plain-callback effect to harvest on this route.
- **pi-ghostty, field boundary**: plain's first visible word is **−3.3 ms earlier**
  (median) — noise-level, under the editor's 10 ms read-poll quantum.
- **Conclusion**: on pi-ghostty the callback choice does not move visible lag; both
  boundaries tie within ±3 ms against a per-word lag of ~8–12 s. The selector
  decision therefore rests on granularity/churn and burst behaviour (plain: 1521
  updates with 737 no-ops vs stabilized: 1422 updates with 501 no-ops), not latency.
- **im-gtk**: only the stabilized arm produced an artifact; the paired callback
  comparison on im-gtk remains UNMEASURED and must not be imputed from this session.

### Dominant-stage diagnosis (where the visible lag lives)

- **im-gtk (stabilized arm)**: per-word speech→visible **med 190.5 ms / p95 244.3 ms**.
  The adapter path is proven fast — first field paint follows the useful callback in
  **2.6 ms** median, ready→frame p95 2.5 ms. The lag is dominated by the
  recognizer/decode cadence (word audio-end → next useful update), not by relay,
  writer, or adapter.
- **pi-ghostty (both arms)**: per-word speech→visible **med 7786–11983 ms / p95
  ~16070 ms** — one to two orders of magnitude above im-gtk. The adapter path is
  NOT the bottleneck: when the field changes at all, it follows the callback within
  **3.5–4.4 ms** (merged cell; no coherent ack_ts anywhere, so the update→ack and
  ack→field splits stay absent and labelled), and the S5-qualified paint lands
  **29.8–42.7 ms** after its field change. The lag accumulates BEFORE the
  callback/adapter stages: hypothesis growth is sparse (only 14–17 of ~1400–1500
  updates correspond to field changes; 501–737 are same-text no-ops) and text lands
  largely in the sentence-end dumps (dump: yes on both pi arms; backlog max 57 words
  outstanding). This is the recognizer-cadence + bulk-delivery/writer complex —
  the delivery path T2 owns — not the paint path.
- **What P1.M2.T2.S2's remediation must move**: pi-ghostty per-word speech→visible
  med/p95 (7786/16077 stabilized, 11983/16070 plain) — mid-clip words must reach the
  field when their updates fire. The field paint itself is ready at ~4 ms and frames
  at ~30–43 ms; the remediation should NOT spend effort on the adapter paint path.
- **What P1.M2.T2.S1's dispatch-promptness + burst fail-closed design must survive**:
  plain's update volume (1521 updates / 20 replays ≈ 76 per replay, ~48% no-ops,
  worst_gap up to 16097 ms) and the end-of-utterance dump bursts (backlog max 57
  outstanding, sentence_end_dump yes on both pi arms). A dispatch design tuned on
  im-gtk's quiet profile (62 updates, no dumps) would be sized an order of magnitude
  too small.

### Instrumentation limits (S6-specific)

- im-gtk plain arm: two sanctioned attempts, both stopped by the same runner-side
  re-arm gate error; the row is not-run and no number is imputed. Re-running that
  arm (and completing the im-gtk pair) is explicitly left open for T2.
- The `1st useful` / `1st visible` cells are speech-end-anchored offsets and are
  negative by construction (the first useful update arrives mid-clip). Only their
  cross-arm DELTAS carry boundary signal (same clips ⇒ anchors cancel); absolute
  lag is the verbatim word-lag column.
- No ack_ts was recorded on any route this session, so the relay/dispatch
  (update→ack) and adapter (ack→field) split is absent everywhere; the merged
  useful→field cell carries that story, labelled as merged.
- Exact field→frame pairing at the first-visible boundary was structurally
  unavailable: S5's correlator consumes each replay's first drained field event as
  its baseline, and that event is usually the first-visible paint itself. The
  paint-qualified column uses the disclosed post-update fallback (S5's own
  field→frame pair latency), n=20 on both pi arms — real measured pairs, boundary
  choice disclosed, never merged with the exact cell.
- Comparability (gate-checked, per route-pair): identical clips, kernel, python,
  RealtimeSTT version, replay budget, warm policy; device dicts identical modulo
  the arms' own `partial_callback` label (the treatment variable — excluded from
  the equality check by design). Effective sources: plain =
  `on_realtime_transcription_update`, stabilized = `on_realtime_transcription_stabilized`.
