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

- The daemon's default bulk factory builds its bundle PURE and never spawns the
  IM child ("spawn is lazy inside acquire" — but `ImeTarget.acquire` on a
  not-RUNNING ImeProcess returns "ime no reply"). The im-gtk route's factory
  performs the G3 start_adapter recipe (spawn → seat-bound globals → ping-pump
  activation — pings pump the host's event loop; a log-only wait deadlocks
  because activate is processed only around request handling) and returns the
  daemon's own `_BulkTargetBundle`, so attach/teardown wiring is exactly the
  production default.
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
