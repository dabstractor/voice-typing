# Research — source-to-field bottleneck remediation (P1.M2.T2.S2 / BUG-002)

Pins the decision framework, the exact code seams per stage, the safety rails, and the
handoff contract to T2.S3. Verified in-tree this session; **locate by named symbol** (S1/S6
land in parallel and line numbers drift).

## 1. Inputs this task consumes (contracts)

- **P1.M2.T1.S6** (Implementing — treat its PRP as contract): the paired A/B runs
  (im-gtk × {plain, stabilized}, pi-ghostty × {plain, stabilized}) + `stage_summary`
  (speech→first-useful-update | update→ACK | ACK→field | field→frame shares) + the
  dominant-stage diagnosis appended to `tests/G5_TIMING_EVIDENCE.md` under a NON-verdict
  header ("## Paired callback comparison and stage diagnosis (P1.M2.T1.S6)"). Three run logs
  + one artifact already sit in its research/ dir; the evidence append may still be pending —
  S2 consumes whatever landed and records any gap as a limit (never imputes).
- **P1.M2.T2.S1** (Implementing): the bulk_controller prompt-dispatch fixes (burst
  coalescing, fail-closed overflow, generation re-check). S1 owns the WRITER stage; S2 must
  not re-touch `bulk_controller.py` — consume `tests/test_bulk_controller.py` +
  `tests/test_g2_bulk_gate.py` as green gates.
- **architecture/bulk_delivery_gate.md**: the stage model (recognizer→child→daemon | daemon→
  single writer | writer→target), the "diagnose the dominant stage BEFORE tuning" law, the
  R.7 gate numbers, and the g6-parser rule (below).
- **external_deps.md / T1.S6 §3**: RealtimeSTT 1.0.2 fires BOTH callbacks in the SAME
  eligible decode (stabilized first, inline) — plain is NOT earlier in invocation time; its
  plausible win is CONTENT granularity (smaller, more frequent hypotheses → more dispatch
  opportunities → earlier VISIBLE words). Selection is by visible lag, never by name.

## 2. The measured baseline (why a gap likely persists)

`tests/G5_TIMING_EVIDENCE.md` (2026-11-23 @ c9a0a05, authoritative verdict table :14):
im-gtk 20 insertions / 0 corrections (one visible commit per replay — the controller's
per-utterance coalescing never let a partial paint); pi-ghostty speech→visible 12,616 ms
median / 13,203 ms p95, sentence-end dump; both 57-word sustained backlog. S1 (controller
promptness) + selection (plain) attack the two known causes. S2 is the stage-specific
remediation for whatever share REMAINS dominant in S6's decomposition.

## 3. The code seams per stage (verified by grep this session)

### 3.0 Selection (applies FIRST, regardless of stage)
- `voice_typing/daemon.py:219-234`: `_PARTIAL_CALLBACK_ATTR = "on_realtime_transcription_stabilized"`
  with the in-code note "If stabilized proves too laggy, change this constant to
  on_realtime_transcription_update"; `_PARTIAL_SOURCES = {"plain": ...update, "stabilized": ...}`;
  the default-key resolution comment :227-228 (parent-side monkeypatch never reaches the child).
- `partial_source` flows: `_build_callbacks` (:353-392 selects exactly ONE key) → `_construct`
  (:439, :467) → `build_recorder` (:486-505, ineffective-selection warning :476-479) →
  `RecorderHost(partial_source=...)` (recorder_host.py :154/:171) → spawn child. Flipping the
  DEFAULT (the `_PARTIAL_CALLBACK_ATTR`/default-resolution constant) is the production
  selection; the g5 lab's `--partial-source` arm is measurement-only.
- R.8 rule: flip only if S6 shows plain wins on VISIBLE lag (speech→first-visible /
  ready→frame deltas), not on callback time; and only if churn (superseded/no_op shares)
  stays inside what S1's fail-closed controller absorbs.

### 3.1 Recognizer/cadence stage (speech→first-useful-update dominant)
- `voice_typing/daemon.py:342` (`cfg_to_kwargs`): `"realtime_processing_pause":
  cfg.asr.realtime_processing_pause` (default 0.15 s) — the realtime decode loop's pause.
- Bounded fix: a **bulk-only evaluation cadence** — when the recorder build is for bulk
  delivery (`cfg.output.delivery == "bulk-text"`), tighten the pause with a MODULE CONSTANT
  (e.g. `_BULK_REALTIME_PROCESSING_PAUSE = 0.05`) applied inside `_construct`/`cfg_to_kwargs`
  AFTER the cfg value, mirroring how lite mode overrides `post_speech_silence_duration`
  (§4.2ter precedent: a mode-scoped code constant, NOT a new config key — the contract forbids
  a new end-user knob). Stream-edit builds keep the cfg value byte-identically.
- Constraint: the child is built per mode at spawn; the override is a pure function of the
  EXISTING cfg (delivery mode) → no state, no knob. Document in the touched docstrings.

### 3.2 Relay stage (update→ACK dominant: relay+queue+dispatch+adapter)
- Path: `recorder_host.py` `_RelayFeedback.update_partial` → evt_q → `_read_loop` →
  `_dispatch` → daemon `_on_partial` (:2023-2045: listening gate → `_bulk_handle_partial`
  enqueue-and-return) → `BulkController.on_partial`.
- The DISPATCH LAW (daemon.py:97): on_final/_on_partial run on the host reader thread and
  only ENQUEUE. A measured relay lag therefore implicates (a) evt_q serialization behind
  other event kinds, (b) any accidental work in `_dispatch`/`_on_partial` before the enqueue,
  or (c) child-side callback contention (both callbacks fire in the same decode; the
  non-selected one still runs — its cost lands in the same thread).
- Bounded fix ("prompt routing of usable updates"): ensure a usable partial's path to
  `controller.on_partial` is strictly enqueue + immediate condition-notify — e.g. dispatch
  partials ahead of non-barrier event kinds in `_read_loop`/`_dispatch`, or drop/skip the
  non-selected sibling callback's work in the child (register only the selected key — already
  the case via `_build_callbacks`; verify). DO NOT batch, buffer, or defer partials; DO NOT
  let a partial wait on a final's barrier.

### 3.3 Adapter stage (ACK→field / field→frame dominant)
- `voice_typing/ime/target.py`: `acquire` (:97), `verify` (:127, :268 — per-op
  `surrounding_text` round-trips), `show` (:151-231, the two `request("show", ...)`
  sites), `_SHOW_TIMEOUT_S`/`_ACQUIRE_TIMEOUT_S`. `pi_editor.py:PiEditorTarget` mirrors it.
- Bounded fix ("eliminate measured redundant adapter waits"): ONLY if S6 shows ACK→field
  dominates AND the wait is a redundant round-trip (e.g. a per-show verify that the op's own
  result already proves). Gate doc hard rule: ownership/caret verification and the one-edit
  proofs MUST remain intact — weaken nothing. If the wait is load-bearing (real verification),
  the honest output is a BLOCKER note, not a removal.

## 4. Safety rails (verbatim from the contract + gate doc)

- The legacy stream-edit branch (`_on_partial` → `_stream.on_partial`) must not change;
  `_bulk_handle_partial` keeps enqueue-only. Final filtering, R.6 recovery
  (`tests/test_session_recovery.py`), takeover, and no-retry safety stay intact.
- Do NOT invent text between callbacks; do NOT remove guards; no second writer; no timer
  deferring the first useful partial (S1's law).
- `tests/g6_assessment.py:parse_route_verdicts` overwrites duplicate route keys — any
  G5_TIMING_EVIDENCE.md append uses NON-verdict vocabulary ("candidate", "measured",
  "blocked") and NEVER touches the authoritative verdict table (:14) — refreshing it is
  T2.S3's qualification.
- No live-desktop runs in S2: the candidate is proven by mocked-clock/transport regressions;
  the real-route qualification (both routes, gate numbers) is T2.S3. R.7 automation law.
- AGENTS.md: every command under GNU `timeout` (inner) + a strictly larger bash-tool timeout;
  full tool paths; never interrupt a G5 run mid-flight (and S2 shouldn't start one).

## 5. Regression + evidence plan

- Stage-specific regression (NEW `tests/test_bulk_stage_remediation.py`, hermetic): a fake
  recorder clock + fake relay/transport pin the stage contract — e.g. for the cadence fix:
  `_construct` with a bulk cfg gets the tightened pause, a stream cfg keeps cfg value; for a
  relay fix: a partial enqueued behind other kinds still reaches `on_partial` before them /
  with zero added wait; for an adapter fix: the removed wait changes NO ownership/caret/one-edit
  assertion (reuse `bulk_delivery.rendered_equal` + the G2 fake-target traces).
- Re-run where affected (the contract's list): `tests/test_bulk_dispatch.py`,
  `tests/test_bulk_context_prompt.py`, `tests/test_session_recovery.py`, plus S1's
  `tests/test_bulk_controller.py` + `tests/test_g2_bulk_gate.py` and the fast sweep.
- `tests/G5_TIMING_EVIDENCE.md` append: "## Candidate remediation (P1.M2.T2.S2)" — dated,
  the S6 stage verdict consumed, the chosen stage + fix, the exact diff/settings, the
  regression proof, and either the handoff line for T2.S3 or the explicit blocker.
- Touched-symbol docstrings (Mode A): `_PARTIAL_CALLBACK_ATTR`/`_PARTIAL_SOURCES` (if the
  default flips), `cfg_to_kwargs`/`_construct` (cadence constant), `_read_loop`/`_dispatch`
  (routing), `ImeTarget.show`/`verify` (adapter) — whichever seams move.
