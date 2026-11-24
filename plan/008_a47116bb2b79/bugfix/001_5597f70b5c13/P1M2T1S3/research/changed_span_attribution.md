# Research — changed-span attribution for the G5 engine (P1.M2.T1.S3)

## 1. The mandate (verbatim, architecture/bulk_delivery_gate.md § "G5 experiment and instrumentation")

> "`wrap_ready` currently stamps daemon receipt before gates, not producer ready. `ready_to_frame`
> windowing can charge a late change to the next callback or disappear unpaired; its previous-state
> tracking can lose the prior snapshot. `resolve_visibility` assumes position/contiguous blocks and
> can overstate Pi delay on rewrites. Use changed-span aware alignment against independent field
> snapshots; preserve first genuine visibility for repeated/corrected words, distinguish initial
> anchored text from new insertions, and expose misses, ambiguous matches, superseded/no-op updates,
> clock/cap failures. An unobserved edit does not become a fast event. Include deterministic
> synthetic rapid-update, revision/repeat, no-op and late-frame cases using
> `tests/test_g5_timing_support.py`."

Also binding (same doc): "producer ready (before IPC) and daemon receipt are separate
clocks/checkpoints. Match by gen/utterance/seq where possible"; "Save bounded aggregate
counters/provenance for ready, coalesced/dispatched, in-time ACK and observed change"; "No sample
may be credited merely because target ACKs" (⇒ the item's RESEARCH NOTE: **Target APPLIED is not a
frame**); thresholds/floors/backlog/dump rules are quoted verbatim in the module constants.

Item-specific: next-callback windows can misattribute rapid/repeated frames; positional matching
overstates lag on rewrites. Mock clocks + synthetic field traces only — NO live GUI.

## 2. What exists today (tests/g5_timing_support.py @ HEAD, 616 lines)

- Data model: `WordAlign(word,start,end)`, `FieldEvent(t,text,kind)` (kind is a producer hint,
  never truth), `ReplayRecord(route,clip,feed_start,words,field_events,update_ready:list[tuple
  (ts,text,"partial"|"final")],finals_ts,anchor:int)`, `FrameSample(delta_ms,cls)`, `RouteMetrics`.
- `resolve_visibility(words,field_events,anchor,window_fwd=12,window_back=24) -> list[float|None]`:
  longest contiguous prefix-block positional match + one-word substitution rescue; `seen` write-once
  (first appearance kept); token-position floor `anchor`. Defects: positional assumption (rewrites
  move words), repeats indistinguishable, no span awareness (whole-text presence, not additions).
- `ready_to_frame(update_ready,field_events) -> (list[FrameSample], violations)`: window =
  [dispatch ts, next dispatch ts); `prev_text` from a rolling cursor `ei` (first update starts ""
  even when the field holds anchor text ⇒ lost prior snapshot); a late frame lands in the NEXT
  window (can hit a newer identical callback ⇒ false zero-diff violation or a wrong fast sample);
  `identical` is textual equality with the PREVIOUS update, not with the rendered field state.
- `aggregate(records,route)` → `RouteMetrics` + `failures` (thresholds, floors, backlog, dump,
  zero-diff). `outstanding_series`, `split_utterances`, `sentence_end_dump`, `heartbeat_ok`,
  `render_report_row` (one JSON line), `render_markdown` (MAX_REPORT_LINES=120).
- Consumers (verified by grep): `tests/test_g5_timing_support.py` (the 14-test comparability
  contract — all must stay green) and `tests/g5_timing_lab.py` (guarded `__main__`; builds records
  at :929-990: `anchor=flog.anchor()` = normalized-token count of the last event text; events
  filtered to `[fs-0.5, end_t]`; `update_ready` = raw (t,text,kind) tuples from the `wrap_ready`
  deque at :741-763, which wraps `d.on_final`/`d._on_partial` ⇒ daemon-receipt stamps).
- Lab `FieldLog` (g5_timing_lab.py:161-193): deque cap 4000 events (RAM rule) ⇒ a cap-overflow flag
  belongs on the record contract, not in the engine.

## 3. Identity/disposition plumbing the contract can key on (already landed — NO src edits needed)

- `voice_typing/recorder_host.py`: the CHILD stamps identity at the decode source (`_RelayIds`):
  payloads carry `(session_gen, utterance_id)`; `session_gen` bumps at every 'arm'; the utterance id
  rotates only at `on_speech` (late events keep their utterance's id); the host exposes
  `relay_identity` readable INSIDE the `on_final`/`on_partial` callbacks (module docstring :37-62).
- `voice_typing/daemon.py`: `_bulk_handle_partial`/`_bulk_handle_final` synthesize a per
  `(gen, utterance)` seq (`_bulk_next_seq`) before controller ingress; a missing identity drops +
  counts (module comment :102-103).
- `voice_typing/bulk_controller.py`: pending partials replace only the same key in place (the
  coalescing-disposition source); bounded deque; one in-flight op; receiver-owned 250 ms deadline.
- P1.M2.T1.S1 (COMPLETE): `partial_source` selector threaded end-to-end; the spawn-ready payload
  reports the installed callback key (`"partial_callback"` provenance) — S6's A/B needs this on the
  record.
- P1.M2.T1.S2 (IN FLIGHT, parallel): `voice_typing/daemon.py` `_BulkTargetBundle.start` +
  `_arm_work` wiring + `tests/test_daemon.py` + `README.md` — **fully disjoint** from this item's
  three files.

## 4. Downstream consumers (the contract's customers)

- P1.M2.T1.S4 (route runner): populates the new ReadyEvent fields (stage, gen/utt/seq, disposition,
  ack_ts) and re-wires `wrap_ready`-equivalent capture — owns g5_timing_lab.py.
- P1.M2.T1.S6 (paired comparison): needs calibrated labels + `partial_source` provenance to compare
  plain vs stabilized honestly.
- P1.M2.T2.S3 (final qualification): needs the coverage/miss counters in the evidence rows.

## 5. Evidence-file constraints (tests/G5_TIMING_EVIDENCE.md)

- Historical verdict table (lines 14-19) + thresholds table (81-92) are the failed baseline —
  APPEND ONLY, never rewrite numbers.
- `tests/g6_assessment.py:parse_route_verdicts` scans verdict tables and overwrites duplicate route
  keys ⇒ the appended measurement-method section must NOT contain a table with route+verdict-shaped
  columns (grep the parser before finalizing the section shape; prose/bullets are safe).

## 6. Purity constraint

`g5_timing_support.py` is dual-imported (unit tests + live lab) and pure-stdlib by design — do NOT
import `voice_typing.*` (e.g. `bulk_delivery.rendered_equal`): re-implement normalized-text
equality locally with `normalize_tokens` (the module already owns the normalization rules).
