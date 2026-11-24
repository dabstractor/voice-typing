# Research — P1.M2.T1.S6: Paired callback comparison + visible-lag localization

Verified in-tree at HEAD 86ba158 (S4 landed) with S5 under parallel implementation
(its PRP is the contract). All line anchors grepped this session; **locate by named
symbol** — line numbers drift when S5 lands.

## 1. What exists and what S6 adds

| Piece | Status | Anchor (verify by grep) |
|---|---|---|
| R.8 arm selector (`--partial-source plain\|stabilized`) | LANDED (S4, commit 86ba158) | `tests/g5_timing_lab.py` `main` (~:1408), `build_inner_argv` :668, `start_daemon` :771 |
| Fail-closed source provenance | LANDED (S4) | `_resolve_partial_source` :799; warm log :1092-1103; artifact provenance :1205-1220; final line :1230-1237 |
| Preflight → blocked semantics | LANDED (S4) | `preflight` :634; `run_route` :1320 (blocked JSON + rc 1, nothing spawned) |
| Changed-span metrics engine | LANDED (S3, commit c7b10c1) | `tests/g5_timing_support.py`: `changed_spans` :234, `attribute_updates`, `aggregate` :911, `render_report_row` :1022 |
| Paired-runner commands (already documented) | LANDED (S4) | `tests/G5_TIMING_EVIDENCE.md` "### R.8 paired arms" :50-91 — the exact 4 commands S6 runs |
| Pi frame observer + disposable HOME | S5 CONTRACT (in flight) | `tests/g5_frame_observer.py` (NEW per S5), `_pi_window_env`, artifact `frame_observer` block + per-record `frame_qualified` |
| **S6: in-run stage decomposition** | NEW | `tests/g5_ab_compare.py` `stage_summary(records)` → additive artifact block |
| **S6: cross-arm comparison + diagnosis renderer** | NEW | same module: `check_comparable`, `compare`, `render_markdown` |
| **S6: the four measured runs + evidence section** | NEW | `tests/G5_TIMING_EVIDENCE.md` append after S5's section |

## 2. Data actually available for the stage split (verified)

`g5.ReplayRecord` (tests/g5_timing_support.py :109-130) per replay carries:
`feed_start` (pacer monotonic at audio-time 0), `words` (WordAlign start/end from
`tools/asr-lab/voice/*.words.json` — format `[{word, start, end}, ...]`, clips
jargon/natural/noisy/pauses), `field_events` (FieldEvent t/text — the ONLY
visibility truth), `update_ready` (ReadyEvent: `t`, `text`, `kind`
partial|final, `stage="daemon"`, gen/utt/seq, `disposition`
""|dispatched|coalesced|dropped|replaced, `ack_ts` = target APPLIED cross-check
only), `finals_ts`, `anchor_text`, `capped`, `heartbeats`, `partial_source`.

→ The full stage decomposition is computable **in-run from records**; no scratch
retention needed for the summary:

- speech_end = `feed_start + words[-1].end` (paced feed maps audio time → wall).
- first useful update = first partial ReadyEvent after feed_start whose
  normalized text grows vs anchor_text/running hypothesis
  (`g5.normalize_tokens`, `g5.changed_spans` — read-only reuse).
- first visible = first FieldEvent after feed_start with a non-empty changed
  span vs the running field state.
- update→ack (relay+queue+dispatch+adapter) vs ack→field (adapter paint) split
  wherever `ack_ts` is present; merged+labelled where absent.
- pi paint split: S5's per-record `frame_qualified` (field→frame) when
  `frame_observer.status == "verified"`; else labelled proxy/unverified.
- Per-arm artifact `metrics` (render_report_row :1022-1060) already exposes:
  insertions, corrections, misses, speech_med/p95_ms, worst_gap_ms,
  ready_insert/correct_p95_ms, max_words_outstanding, backlog_sustained,
  sentence_end_dump, unchanged_zero_edit_ok, updates_total/matched/missing/
  superseded/no_op/ambiguous, frames_unpaired, words_ambiguous, clock_failures,
  cap_failures, provenance_warnings. **S6's A/B table cites these; it does not
  recompute them.**

Artifact JSON (run_inner :1191-1228): `route`, `metrics`, `replays`,
`heartbeat_ok`, `field_log_pair_count`, `provenance{kernel, python,
partial_source_requested, partial_callback_effective, device, warm ("resident …;
one discarded warmup"), clips, route_note, field_instrument}`. Written to the
scratch tmpdir `artifact-<route>.json` — **the tmpdir is deleted on teardown
unless `G5_KEEP_SCRATCH=1`** (S5 keeps that hatch). Each run_route makes a fresh
tmpdir, so the plain and default arms don't collide in-run, but S6 must
copy+rename artifacts out per arm.

MISSING from provenance today (S6 adds, additive): `realtimestt_version`
(importlib.metadata.version("RealtimeSTT")), `replay_budget` (g5.REPLAY_BUDGET),
cadence note (paced_feed constants). `device` dict already records model/device.

## 3. External-contract facts that shape the diagnosis (external_deps.md)

- RealtimeSTT 1.0.2 fires **both legacy callbacks in the same eligible decode,
  stabilized first inline**; neither is gated on stable_delta/accepted. So
  **plain may NOT be earlier in invocation time** — the plausible delta is
  content granularity (more frequent smaller hypotheses → more dispatch
  opportunities → earlier VISIBLE words) and revision churn. Never claim
  "plain is earlier" until measured (gate doc § G5 verbatim).
- Exactly one callback per build (S1 selector); parent-side monkeypatching is
  not an A/B. Only isolated same-clip replays establish which callback wins.
- ASR-ready / daemon-ready / ACK / field / frame are DISTINCT clocks; no sample
  is credited on ACK alone (R.5 #3).

## 4. Gate constraints (architecture/bulk_delivery_gate.md § "Gate and evidence handoff")

- Append paired A/B data **separately** from the current verdict table, with
  commit, versions, selected source, exact commands, sample counts, misses,
  instrumentation limits. Diagnose the **dominant stage** (recognizer/processing
  cadence, relay, writer, adapter before paint) BEFORE any tuning; do not lower
  thresholds or disguise zero-edit violations.
- `tests/g6_assessment.py:parse_route_verdicts` (~:289) scans verdict tables and
  **overwrites duplicate route keys**; `_ROUTE_VERDICT_RE` matches
  `\*{0,2}(pass|fail|blocked)\*{0,2}` IGNORECASE. → S6's A/B tables must use a
  non-verdict vocabulary ("measured", "not-run", "unverified-clock") and MUST be
  proven non-interfering by a unit test: parse_route_verdicts(fixture doc) ==
  parse_route_verdicts(fixture doc + rendered section).
- The authoritative two-route verdict table (:14) stays **untouched** by S6;
  refreshing it belongs to T2.S3 qualification. S6's rows are exploratory.

## 5. Runbook facts (verified)

- Commands are already in the evidence doc :55-77 — run them verbatim:
  `timeout -k 2 1500 env G5_TIMING_LAB=1 [PI_BIN=…] .venv/bin/python
  tests/g5_timing_lab.py --route {im-gtk,pi-ghostty} [--partial-source plain]`.
- Bash-tool (outer) timeout must exceed 1500 (use ≥1560). Runs are sequential —
  never two arms at once (one CUDA model resident per run; GPU contention would
  corrupt cadence). NEVER interrupt mid-run (AGENTS.md); rc 124 ⇒ AGENTS cleanup
  before any retry.
- Warmup: one discarded warmup replay is built into the lab (provenance "warm"
  key) — matched arms inherit it; cite, don't re-implement.
- Budget: `g5.REPLAY_BUDGET` (20) identical across arms; the loop breaks early
  at insertions≥100 AND corrections≥100 — unequal `replays` counts across arms
  are a disclosed limit, not a disqualifier.
- Preflight blocks pi arms honestly if PI_BIN/ghostty/sway/xvfb-run/clips/
  alignments are missing → record as not-run rows; never fabricate.
- Teardown is the runner's own (finally: control quit, d.shutdown, srv.stop,
  poll stop, `lab.kill_all()` own-process-groups) + outer `timeout -k 2`.
- pyproject pins RealtimeSTT 1.0.2 (uv.lock:698-717); pytest>=9.1.1; no
  ruff/mypy in this repo. Validation = `.venv/bin/python -m pytest`.
- Sibling suites that must stay green UNEDITED: tests/test_g5_timing_support.py
  (S3), tests/test_g5_timing_lab.py (S4), tests/test_g5_frame_observer.py (S5).

## 6. Consumer handoff (what T2.S1/T2.S2 need from S6's output)

- T2.S1 ("Keep partial dispatch prompt and fail closed under bursts"): needs the
  winning arm's update rate/burst profile (updates_total, superseded/no_op
  shares, worst_gap_ms) to size the burst fail-closed design.
- T2.S2 ("Remediate the measured source-to-field bottleneck"): needs the
  dominant-stage verdict per route with numbers (speech→update vs update→ack vs
  ack→field vs field→frame shares) — i.e., exactly `stage_summary`.
- Selection rule (R.8): choose by VISIBLE word lag, not callback time —
  explicitly separate "early callback" (speech→first-useful-update delta) from
  "early field visibility" (speech→first-visible / ready→frame deltas).
