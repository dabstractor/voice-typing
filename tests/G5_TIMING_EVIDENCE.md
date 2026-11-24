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
| im-gtk | **fail** (counts 4/0 < 100; backlog sustained 57; correction p95 unexercised; frame bars unverified — field change-log proxy) | 4 | 0 | 871 | −1312.2/−802.4 (n=4, mid-speech inserts) | −802.4 | 3.4 / — | 57 | backlog-sustained, frame-unverified |
| pi-ghostty | **fail** (speech→visible 6714.0 ms median; sentence-end dump; backlog sustained 57; counts 14/14 < 100; unchanged⇒zero-edits breached) | 14 | 14 | 815 | 6714.0/13444.0 ✗ | 15831.6 ✗ | 11266.2 / 13150.8 ✗ | 57 | backlog-sustained, dump, unchanged-edit |

Both routes **FAIL G5** — 2026-11-24 qualification round (P1.M2.T2.S3), production selection
(stabilized + S1's prompt dispatch + S2's 0.05 s bulk cadence), 20 measured replays per route.
The utterance-granularity visibility failure persists on both routes: the field still
accumulates a multi-second, multi-word backlog (max 57 words outstanding) for the whole clip.
pi-ghostty's speech→visible median improved 7786.2 → 6714.0 ms (S2's cadence fix, −14%) but
remains ~13× the 500 ms bar, its sentence-end dump persists, its count floors collapsed to
14/14 (the S6 run's 108/169 came from the utterance-rewrite pattern this round no longer
produces), and — under the NEW paint-qualified frame basis (S5 observer) — its
ready→first-changed-frame bars now measure real visible change and FAIL (11.3 s/13.2 s).
im-gtk remains count/backlog-bound (4 insertions, 0 corrections, 57 outstanding) and its
frame basis is still the field change-log proxy, so its frame bars stay UNVERIFIED. Full
numbers, provenance and the A/B decision: "Qualification run (P1.M2.T2.S3)" below.
BUG-002 and PRD acceptance #13 remain OPEN; opt-in delivery (`output.delivery="bulk-text"`)
is retained; default delivery is unchanged; G6/README claims must not proceed on this
evidence (P1.M2.T3 owns them).

## Qualification run (P1.M2.T2.S3)

- Date: 2026-11-24 | HEAD: 2909e03 (P1.M2.T2.S2's bulk decode-cadence change, committed;
  S1's dispatch-promptness change landed at a14335c beneath it). The runs below executed at
  exactly this content. RealtimeSTT 1.0.2; model small.en, device=cuda, compute_type=float16,
  context_prompt=True; warm recorder resident across replays (ONE discarded warmup,
  `auto_unload_idle_seconds=0`); replay budget 20 per arm; the (mono, wall) heartbeat check
  passed on every run — 0 clock failures, 0 cap failures; kernel 7.3.5-arch1-1,
  Python 3.12.10, RTX 3080 Ti (12 GiB).

### S2 consumption and the A/B decision (item LOGIC sentence 1)

- S2's "Candidate remediation (P1.M2.T2.S2)" section consumed verbatim (not edited): stage =
  the recognizer/decode cadence; fix = module constant `_BULK_REALTIME_PROCESSING_PAUSE =
  0.05` in daemon.py, overriding `kwargs["realtime_processing_pause"]` AFTER `cfg_to_kwargs`
  and BEFORE the callback merge, ONLY when `cfg.output.delivery == "bulk-text"`; hermetic
  proof 9 tests + 131 bulk/recovery rails + the full-sweep control re-run. S2's handoff:
  qualify on BOTH real routes; re-open the selection default ONLY on an im-gtk/plain
  visible-lag win with churn inside S1's absorbed profile.
- A/B decision: **FIRED** — S2's change is recognizer-cadence scheduling (it alters update
  volume, burst profile and which updates become useful), so the S6 A/B conclusion had to be
  re-derived under the candidate scheduling. The paired arms ran per route (S6's exact
  commands, sequential, same clips/kernel/budget). Result: on pi-ghostty stabilized is
  visibly EARLIER than plain (6714.0 ms vs 11978.0 ms speech→visible median) with a better
  ins/cor balance (14/14 vs 9/15); on im-gtk the plain arm is NOT-RUN — two sanctioned
  attempts this round died on the same runner-side re-arm gate error S6 recorded twice
  ("bulk delivery never re-armed", after replay 11 of 20 and replay 14 of 20; an arm that
  fails twice stands not-run, no imputation). Plain therefore does not win on visible lag +
  counts on ANY route → the selection default is NOT flipped: `_PARTIAL_CALLBACK_ATTR` stays
  "stabilized" and daemon.py is untouched by this task. The unflagged (stabilized) arm IS
  the production selection that was qualified.

### A/B arms this round (S6 table shape; non-verdict vocabulary)

| Route | Arm | Status | speech lag med/p95 (ms) | ins/cor | miss | backlog max | dump | n |
|---|---|---|---|---|---|---|---|---|
| im-gtk | plain | not-run (2 attempts: runner-side bulk-delivery re-arm gate, replays 11/14 of 20) | — | — | — | — | — | — |
| im-gtk | stabilized | measured | −1312.2/−802.4 (live mid-speech inserts) | 4/0 | 871 | 57 | no | 20 |
| pi-ghostty | plain | measured | 11978.0/16081.3 | 9/15 | 858 | 57 | yes | 20 |
| pi-ghostty | stabilized | measured | 6714.0/13444.0 | 14/14 | 815 | 57 | yes | 20 |

### The qualification runs (production selection, UNFLAGGED)

- Effective source per run (the child's ready payload — the only effective-source truth):
  requested "default" resolved to `partial_callback_effective =
  on_realtime_transcription_stabilized` on both routes. `--partial-source` was used ONLY for
  the two A/B plain arms, never on the qualification runs.
- im-gtk production (rc=1, honest fail): 20/20 measured replays; ins 4 / cor 0 / miss 871;
  speech→visible med −1312.2 ms / p95 −802.4 ms — NEGATIVE by construction: the four matched
  words painted mid-clip, before their aligned speech-end (live insertions, not an
  end-of-utterance commit); at n=4 the speech bars are unexercised, not met; ready→changed
  ins p95 3.4 ms, correction path unexercised; max outstanding 57, backlog sustained; no
  sentence-end dump; unchanged ⇒ zero edits held; 73 updates total / 30 no-ops (the
  partial-streaming collapse persists: ~3.7 updates per replay). FRAME BASIS: the GTK field
  change log (an editor read-poll proxy) — this route has NO paint observer, so the
  ready→first-changed-FRAME bars are UNVERIFIED and are labeled, not passed.
- pi-ghostty production (rc=1, honest fail): 20/20 measured replays; ins 14 / cor 14 /
  miss 815; speech→visible med 6714.0 ms / p95 13444.0 ms, worst 15831.6 ms — far over the
  500 ms / 1 s bars; ready→first-changed-frame ins p95 11266.2 ms / cor p95 13150.8 ms
  (bars 100/50 ms). BASIS CHANGE vs the old 11.5/11.7 ms readings: those were FIELD-LOG
  change events (a read-poll proxy for frames); this round the pi frame basis is the
  S5-QUALIFIED paint observer (grim window-region digest, status "verified", disclosed
  post-update fallback, 20 qualified pairs, paint-once-changed med 13.7 / p95 71.1 ms) —
  the ready bars now measure PAINT-visible change, and they fail because visible field
  changes themselves lag seconds behind the update stream (1223 frames unpaired: updates
  arrive but the field does not visibly change). max outstanding 57, backlog sustained;
  sentence-end dump YES; unchanged ⇒ zero edits BREACHED (first recorded breach of that
  bar); 2128 updates / 893 no-ops.

### Gate application (bar by bar, production arm)

- im-gtk: count floors 4/0 vs ≥100/100 ✗; sustained backlog (57 ≥5 words ≥2.0 s) ✗;
  correction p95 unexercised ✗; speech med/p95 unexercised at n=4 (negative readings
  reported, not credited) *; unchanged⇒zero-edits ✓; dump ✓; clock/coverage ✓ (heartbeat
  passed, 0 clock/cap failures); frame bars UNVERIFIED (proxy basis — labeled, never
  passed). Verdict: fail.
- pi-ghostty: speech med 6714.0 ms vs ≤500 ✗; speech p95 13444.0 ms vs <1 s ✗; ready ins
  p95 11266.2 ms vs ≤100 ✗; ready cor p95 13150.8 ms vs ≤50 ✗ (paint-qualified basis);
  count floors 14/14 vs ≥100/100 ✗; sustained backlog (57) ✗; sentence-end dump ✗;
  unchanged⇒zero-edits ✗ (breached); clock/coverage ✓. Verdict: fail.

### Exact commands this round (exit codes recorded)

```sh
# scaffold smokes (wiring only, NEVER a measurement) — rc=0, pass:true both arms:
timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk
timeout -k 2 240 env G5_TIMING_LAB=1 G5_NO_DESKTOP=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk --partial-source plain
# A/B plain arms (sequential; one CUDA model load at a time):
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk --partial-source plain   # rc=1 twice: harness error 'bulk delivery never re-armed' (stands not-run)
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 PI_BIN="$(command -v pi)" .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty --partial-source plain   # rc=1 honest fail
# production (UNFLAGGED) qualification — the verdict-table source:
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk   # rc=1 honest fail
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 PI_BIN="$(command -v pi)" .venv/bin/python tests/g5_timing_lab.py --route pi-ghostty   # rc=1 honest fail
```

Artifacts (artifact JSON + stdout logs incl. the JSON verdict lines) copied to
`plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M2T2S3/research/runs/` (files dated
2026-11-24); scratch tmpdirs deleted immediately after copy. The im-gtk/plain arm's two
harness-error lines (both attempts) are in the archived stdout logs — the arm's record is
not-run, with no numbers imputed anywhere.

### Post-run regression + watch checks (P1.M2.T2.S3)

- CPU baseline (research §6): `timeout 500 .venv/bin/python -m pytest tests/test_daemon.py
  -q --tb=no` run BEFORE and AFTER the runs/evidence edit — both 20 failed / 243 passed,
  and the FAILED set diffed BY NAME against the canonical 20-name list
  (P1M1T3S1/research/bug004_named_daemon_baseline.md §1) is EMPTY in both directions
  (zero new names, zero fixed names). No CPU-suite regression from S1+S2's landed changes.
- Fast sweep: `timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py
  -q` → 41 failed / 1628 passed — name-for-name the documented population (the 20 daemon
  names above + the G1-classified streaming_commit 10 / core 2 / freeze 4 + the 4
  real-model names below + the 1 documented systemd environmental). No new failures.
- Real-model watch (research §7): RAN, bounded — `timeout 600 .venv/bin/python -m pytest
  tests/test_streaming.py -q --tb=no` → 4 failed / 3 passed in ~115 s; failing names
  exactly the documented baseline four (`test_a_delta_cadence`, `test_b_commit_rewind_exact`,
  `test_f_user_key_freeze`, `test_g_stranded_tail`). Outcome: baseline-identical — the watch
  neither clears nor indicts anything in this task; recorded, not claimed as a gate.
- Parser proof (research §2): `parse_route_verdicts` BEFORE the edit → {'im-gtk': 'fail',
  'pi-ghostty': 'fail'}; AFTER the edit → {'im-gtk': 'fail', 'pi-ghostty': 'fail'} —
  exactly the two current routes with this round's verdicts; no historical/A-B row leaks as
  current (both proofs saved beside the run artifacts).

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

# 2. the routes (private compositor; ~4-20 min each; NEVER interrupt mid-run;
#    G5_KEEP_SCRATCH=1 so the artifact JSON can be copied to this task's
#    research/runs/ dir, then the scratch tmpdir is DELETED — tmpfs = RAM):
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 .venv/bin/python tests/g5_timing_lab.py --route im-gtk
timeout -k 2 1500 env G5_TIMING_LAB=1 G5_KEEP_SCRATCH=1 PI_BIN="$(command -v pi)" \
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

## Provenance (2026-11-23 baseline runs — superseded by the qualification round above)

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
| speech-end→word-visible median | ≤ 500 ms | −1312.2 ms (n=4, live mid-speech inserts — unexercised, not met) * | 6714.0 ms ✗ |
| speech-end→word-visible p95 | < 1 s | −802.4 ms (n=4) * | 13444.0 ms ✗ |
| update-ready→first-changed-frame p95 (insertion) | ≤ 100 ms | 3.4 ms (field-log proxy — frame UNVERIFIED) | 11266.2 ms ✗ (paint-qualified) |
| update-ready→first-changed-frame p95 (correction) | ≤ 50 ms | not exercised ✗ | 13150.8 ms ✗ (paint-qualified) |
| unchanged ⇒ zero field events | must hold | ✓ | ✗ breached |
| ≥ 100 insertions AND ≥ 100 corrections | floors | 4/0 ✗ | 14/14 ✗ |
| sustained ≥5-word backlog (≥2.0 s) | must not | ✗ (max 57 words) | ✗ (max 57 words) |
| sentence-end dump | must not | ✓ none | ✗ dump |

Numbers are the 2026-11-24 qualification round (production selection; see "Qualification run
(P1.M2.T2.S3)"). Two honesty notes. (1) im-gtk's NEGATIVE speech readings: the four matched
words painted mid-clip, before their aligned speech-end — live insertions, not an
end-of-utterance commit; at n=4 the speech bars are unexercised rather than met, and the
BACKLOG column (57 outstanding) is the route's true verdict carrier. (2) pi's ready→frame
basis moved: the old 11.5/11.7 ms readings were FIELD-LOG change events (a read-poll proxy
for frames); since S5 the route carries the paint-qualified observer (verified, disclosed
post-update fallback), so this round's ready bars measure real paint-visible change — they
fail because visible changes lag seconds behind the update stream (1223 unpaired frames;
paint-once-changed is fast: med 13.7 / p95 71.1 ms, n=20). Read BOTH columns together; the
backlog flag is the gate's verdict carrier on both routes.

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

### im-gtk (PRODUCTION arm, 2026-11-24 qualification — 20 measured replays)
- counts 4/0 < 100 after the FULL replay budget (the partial-streaming collapse persists:
  73 updates total, 30 no-ops, ~3.7 updates per replay despite S2's 0.05 s cadence)
- backlog ≥5 words sustained ≥2.0 s (max outstanding 57)
- ready→frame correction p95 unexercised (0 correction ops reached the field)
- frame bars UNVERIFIED (no paint observer on this route; field change-log proxy only)

### pi-ghostty (PRODUCTION arm, 2026-11-24 qualification — 20 measured replays)
- speech→visible median 6714.0 ms > 500 ms (improved from S6's 7786.2 ms — still ~13× the bar)
- speech→visible p95 13444.0 ms ≥ 1000 ms (worst 15831.6 ms)
- ready→first-changed-frame ins p95 11266.2 ms > 100 ms; cor p95 13150.8 ms > 50 ms
  (paint-qualified basis — visible changes lag seconds behind the update stream)
- backlog ≥5 words sustained ≥2.0 s (max outstanding 57)
- sentence-end dump (an utterance delivered as one final edit)
- unchanged ⇒ zero field events BREACHED (first recorded breach of this bar)

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

- **BUG-002 / acceptance #13 (PRD R.1/R.7 G5): OPEN after the P1.M2.T2.S3 qualification
  (2026-11-24, HEAD 2909e03).** Both routes FAIL G5 on the production selection (stabilized
  + S1's prompt dispatch + S2's 0.05 s bulk cadence). Exact blockers: im-gtk — count floors
  4/0 ≪ 100/100 with a sustained 57-word backlog (the partial stream still collapses to
  ~4 updates per replay; the frame basis remains the read-poll proxy so the frame bars stay
  unverified); pi-ghostty — speech→visible 6714.0 ms median vs the 500 ms bar, sentence-end
  dump, sustained 57-word backlog, count floors 14/14, ready→frame 11.3 s/13.2 s on the
  paint-qualified basis, and a first-ever breach of unchanged⇒zero-edits. Opt-in
  (`output.delivery="bulk-text"`) retained; default delivery unchanged; G6/README claims
  remain P1.M2.T3's and must NOT proceed on this evidence.
- The im-gtk/plain A/B pair remains unrun after FOUR sanctioned attempts across two rounds
  (S6 ×2, this round ×2 — all "bulk delivery never re-armed"), making this a route-harness defect worth its own look before any future selection
  decision. Until then no plain-vs-stabilized conclusion exists on im-gtk.
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

## Candidate remediation (P1.M2.T2.S2)

- Date: 2026-11-24. HEAD: a14335c (S1's controller-promptness change landed at this commit).
- This section records a CANDIDATE, not a verdict. The verdict table above stays the
  authoritative one; refreshing it (and the G6/README claims) is T2.S3's qualification.
  Vocabulary here is the S6 evidence vocabulary (measured / candidate / blocked), never
  route verdicts.

### S6 verdict consumed (quoted numbers)

- pi-ghostty, both arms: per-word speech→visible med 7786.2 ms (stabilized) / 11983.1 ms
  (plain), p95 ~16070 ms — one to two orders of magnitude above every post-callback stage:
  useful→field (merged) 3.5–4.4 ms; S5-qualified paint 29.8–42.7 ms.
- im-gtk, stabilized arm: per-word speech→visible med 190.5 ms / p95 244.3 ms; useful→field
  (merged) 2.6 ms.
- S6's own pointer, verbatim: "the remediation should NOT spend effort on the adapter paint
  path"; the dominant share sits BEFORE the callback/adapter stages — the decode-evaluation
  cadence + delivery complex (hypothesis growth sparse: 14–17 of ~1400–1500 updates move the
  field; 501–737 same-text no-ops; sentence-end dumps, backlog max 57).
- im-gtk plain arm: not-run (two sanctioned attempts, runner-side re-arm gate error) — no
  numbers exist and none were borrowed.

### Selection (R.8) — deliberately NOT flipped, with the numbers

- pi-ghostty callback boundary: plain's first useful update is +1.3 ms LATER than
  stabilized's; field boundary: plain −3.3 ms earlier — under the editor's 10 ms read-poll
  quantum. S6's conclusion stands: the callback choice does not move visible lag.
- im-gtk's plain arm is not-run, so "plain wins on visible lag on BOTH routes" is not
  satisfied even at the noise level. The `_PARTIAL_CALLBACK_ATTR` default stays
  "stabilized"; churn deltas (737 vs 501 no-ops) are moot without a latency win.

### Chosen stage and the exact diff/settings

- Stage: the recognizer/decode cadence — the single dominant post-selection stage per S6 on
  both routes (everything measured downstream is ≤43 ms; the lag is seconds).
- Fix: module constant `_BULK_REALTIME_PROCESSING_PAUSE = 0.05` in `voice_typing/daemon.py`;
  `_construct` overrides `kwargs["realtime_processing_pause"]` to it AFTER `cfg_to_kwargs`
  (which stays delivery-blind) and BEFORE the callback merge, ONLY when
  `cfg.output.delivery == "bulk-text"`. Stream-edit builds keep
  `cfg.asr.realtime_processing_pause` byte-identically. Mode-scoped CODE constant (the
  §4.2ter lite-mode precedent) — NO new config key, no schema change. Docstrings updated on
  the constant + `_construct` (Mode A). One stage per changeset; relay and adapter untouched.
- Why this moves the measured number: `realtime_processing_pause` is RealtimeSTT's realtime
  decode loop's inter-evaluation sleep (cfg default 0.15 s). At bulk cadence, a mid-clip
  word's hypothesis update waits through that sleep between eligible decodes; 0.05 s
  shortens speech→useful-update without touching the paint path, the relay, the writer, or
  any guard. The recorder-host child builds via the same `_construct` with the full pickled
  cfg, so the spawn path inherits the override as a pure function of cfg (no state).

### Regression proof (hermetic; no live desktop, no G5 lab run)

- `timeout 300 .venv/bin/python -m pytest tests/test_bulk_stage_remediation.py -q`
  → 9 tests green (bulk → 0.05; stream → cfg value byte-identical incl. a non-default 0.2;
  override wins over ANY cfg value; pure function of cfg with no cross-build leak; config
  schema unchanged — AsrConfig keeps exactly one pause field, OutputConfig gains none;
  exactly ONE partial-callback key registered in BOTH modes and it is "stabilized";
  a recorder signature without the pause kwarg still builds in bulk mode; the child's
  executor `extra_kwargs` win their own keys and carry no pause key).
- `timeout 300 .venv/bin/python -m pytest tests/test_bulk_dispatch.py
  tests/test_bulk_context_prompt.py tests/test_session_recovery.py
  tests/test_bulk_controller.py tests/test_g2_bulk_gate.py -q` → 131 green
  (S1's gates + the bulk/recovery rails re-proven).
- `timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q`
  → 40 not-green / 1629 green; the 40-name population is IDENTICAL with the two changed
  files removed (control re-run: 40 not-green / 1620 green) — every one pre-existing
  (39 daemon/streaming/systemd environmental + 1 ordering-dependent ime_manager import
  flake that is green standalone). Zero not-green in any bulk or ducking suite.

### Known limits (non-verdict)

- CANDIDATE status: 0.05 s is a design choice inside the hermetic rails; its effect on the
  real routes is unmeasured by S2 (no G5 run was started here, per the automation law).
- S6 recorded no ack_ts on any route, so update→ack / ack→field stay unsplit; the relay and
  adapter stages are NOT indicted by any measured number and were not touched.
- The im-gtk/plain re-run and the paired-selection record remain open items (S6's list).

### T2.S3 handoff

- Qualify this candidate on BOTH real routes against the R.7 gate numbers, then refresh the
  verdict table above and the G6/README claims. If pi-ghostty's per-word lag does not move
  enough, the next measured suspects are the constant VALUE (0.05) and the bulk-delivery
  writer complex (S1's controller) — NOT the adapter paint path. Re-open the selection
  default ONLY on an im-gtk/plain re-run that shows a visible-lag win with churn inside
  S1's absorbed profile.
