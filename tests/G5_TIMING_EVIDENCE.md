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
