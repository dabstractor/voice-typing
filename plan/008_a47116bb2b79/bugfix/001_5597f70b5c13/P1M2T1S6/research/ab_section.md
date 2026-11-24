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
