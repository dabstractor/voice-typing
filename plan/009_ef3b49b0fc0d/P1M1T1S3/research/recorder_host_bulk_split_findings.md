# S3 Research Findings — Remove bulk-only recorder wiring from product

## 0. Task restatement (one line)

Remove the Rev-4 bulk-only realtime-lane SPLIT from `voice_typing/recorder_host.py`'s supported
constructor/launch path (the `delivery == "bulk-text"` activation branch in
`augment_kwargs_with_executor`, the `arm_bulk_realtime_executor` + `_default_bulk_realtime_executor_
factory` helpers, and the two-lane `_prompt_targets` fan-out), leaving ONE supported
RecorderHost executor contract (the SAME PromptedExecutor object in BOTH
`transcription_executor` and `realtime_transcription_executor`) for P1.M1.T2.S2 to build the
prompt ACK on. Update the constructor + lane-wiring docstrings (Mode A). Retire the 3 dead
bulk-lane tests in `tests/test_prompt_engine.py` (live-red S1 fallout) and add a structural
no-bulk-lane pin. Fake-executor/fake-recorder validation only — no CUDA/model load.

## 1. Inputs / contract chain (verified)

- **S1 (LANDED, commit ae7db9f)** — `voice_typing/config.py:204-206`: `OutputConfig.__post_init__`
  raises `ValueError('output.delivery="bulk-text" is retired: ...')`. Consequence: no
  constructible config can carry `delivery == "bulk-text"`, so recorder_host's activation branch
  `if getattr(cfg.output, "delivery", "stream-edit") == "bulk-text":` (:1191) is PROVABLY DEAD.
- **S2 (in flight; CONTRACT, disjoint edit set)** — detaches the DAEMON bulk machinery
  (`daemon.py` only + test quarantine). It explicitly does NOT touch `recorder_host.py`
  ("recorder_host.augment_kwargs_with_executor's split executor is S3's"). S2 removes
  daemon's `cfg_to_kwargs` bulk branch (which set `use_main_model_for_realtime=False` +
  `beam_size_realtime=_BULK_REALTIME_BEAM_SIZE`) and quarantines `test_bulk_stage_remediation.py`
  (which asserts that daemon-side split via `daemon._BULK_REALTIME_BEAM_SIZE` — S2's, not S3's).
- **system_context.md:8** — "In recorder_host.py:augment_kwargs_with_executor the bulk-only split
  creates a second realtime executor; also inspect the daemon's ASR kwargs for split-specific
  behavior. Keep generation/utterance relay stamping, shared executor, `_feed_input` lab seam if
  independently useful, ordinary session recovery and generic idle/media/cancel behavior."
- **system_context.md:14** — P1.M1.T2.S2 will add "an explicit confirmed path ... for both active
  lanes (one object is normal)". S3 makes "one object" the ONLY state.

## 2. The recorder_host.py surface (1721 lines; line numbers verified by grep)

### 2.1 What gets REMOVED (the bulk-only split)

| Site | Lines | Content |
|---|---|---|
| Activation branch in `augment_kwargs_with_executor` | 1181-1196 | 11-line BUG-002 comment + `if getattr(cfg.output, "delivery", "stream-edit") == "bulk-text": realtime_executor = arm_bulk_realtime_executor(...); if realtime_executor is not None: kwargs["realtime_transcription_executor"] = realtime_executor` |
| `_default_bulk_realtime_executor_factory` | 1200-1208 | builds a `PromptedExecutor(..., beam_size=beam_size)` (greedy beam-1) |
| `arm_bulk_realtime_executor` | 1211-1266 | constructs a SECOND PromptedExecutor, probes it, overrides `kwargs["realtime_transcription_executor"]`, logs "bulk realtime lane: ..." |
| Two-lane logic in `_prompt_targets` | 1102-1121 | reads `extra_kwargs["realtime_transcription_executor"]`; appends it when `realtime is not prompt_executor` |
| Call site in `_abort_supervisor` | 1018 | `targets = _prompt_targets(extra_kwargs, prompt_executor)` |
| Prose | 691-695, 701-702, 1014-1017, 1105-1113, 1139-1150 (BUG-002 para) | "BULK-TEXT builds then SPLIT the lanes...", "plus the dedicated bulk realtime executor when the lanes are split", "bulk builds fan the update out to BOTH lanes..." |

### 2.2 What STAYS (the preservation list — do not touch)

- `augment_kwargs_with_executor(kwargs, cfg, resolved, logger, *, executor_factory=None)` —
  signature UNCHANGED (test_streaming.py:1128 calls it positionally with `executor_factory=`);
  config gate (`context_prompt` false → None, stock path), the capability probe
  (`prompt_engine.probe_prompt_executor`), the broad degrade-to-None on ANY failure (ONE INFO
  line), and the SUCCESS arming `kwargs["transcription_executor"] = kwargs["realtime_
  transcription_executor"] = executor` (the SAME object — ONE model; RealtimeSTT skips its
  TranscriptionWorker). The function still returns `executor`.
- `_default_prompt_executor_factory` (:1124-1128) — the production factory seam.
- `_prompt_targets` — KEPT as a named seam (T2.S2 extends it to per-target ACKs) but simplified
  to the single-contract form: `_prompt_targets(prompt_executor) -> [prompt_executor]` or `[]`.
- `_ready_payload` (:1268-1289) — `context_prompt` + `partial_callback` additive keys.
- `_RelayIdentity` / `_RelayIds` / `_with_identity` (:1048-1100) — relay IDs (utterance_id /
  session_gen stamping). Untouched.
- `RecorderHost.__init__` params `feed_input` (the `_feed_input` lab seam — used by
  test_feed_audio.py; keep) and `partial_source` (the R.8 provenance knob; keep).
- The `("prompt", ...)` command handling in `_abort_supervisor` (:1009-1024) — the delivery-timing
  note (read only BETWEEN utterances) stays; only the BUG-002 fan-out prose + the 2-arg call change.
- All arm/disarm/text/abort/cancel/shutdown handling, `_handle_arm`, stale-final purge, bounded
  abort, `_run_text_and_emit_final`, `_child_resolved_device`, `_RelayFeedback`, `_RelayLatency`.

### 2.3 Import purity (verified this session)

`import voice_typing.recorder_host` leaves `torch`/`ctranslate2`/`faster_whisper`/`realtimestt`
OUT of `sys.modules` — `prompt_engine` is imported lazily INSIDE `augment_kwargs_with_executor`.
S3's deletions remove two functions that also imported lazily; purity is preserved trivially, but
the gate re-checks it.

## 3. Tests (verified shapes)

### 3.1 tests/test_prompt_engine.py — SUPPORTED, pure-Python, factory-injected (32 tests)

BASELINE THIS SESSION: **3 failed / 29 passed in 0.12s** — the 3 reds are S1 fallout:
`_cfg_delivery("bulk-text")` (:411-416) constructs `OutputConfig(delivery="bulk-text")` → S1's
`ValueError: ... is retired`. Reds: `test_bulk_delivery_splits_realtime_lane` (:418),
`test_bulk_realtime_lane_probe_failure_degrades_to_shared` (:435),
`test_bulk_realtime_lane_default_factory_uses_greedy_beam` (:470).

S3 edits:
- REMOVE the import `arm_bulk_realtime_executor` (:42); keep `_prompt_targets` (:40) and
  `augment_kwargs_with_executor` (:43).
- REMOVE the BUG-002 section banner (:399-409), `_cfg_delivery` (:411-416), the 3 bulk tests
  (:418-484). Then grep `OutputConfig`/`AsrConfig` usage — drop the imports if now unused.
- REPIN `test_prompt_targets_fanout_helper` (:486-498) → `test_prompt_targets_single_executor_
  contract`: `_prompt_targets(main) == [main]`; `_prompt_targets(None) == []`.
- ADD `test_recorder_host_has_no_bulk_lane_surface` (the migration pin, mirrors S2's daemon pin):
  no `arm_bulk_realtime_executor` / `_default_bulk_realtime_executor_factory` attribute on the
  module; the module SOURCE contains no `"bulk-text"` and no `beam_size`; a context_prompt-on cfg
  + fake factory arms ONE object into BOTH kwargs; `_prompt_targets(executor) == [executor]`; and
  `VoiceTypingConfig.from_toml({"output": {"delivery": "bulk-text"}})` raises `ValueError` matching
  "retired" (documents the S1 chain that makes the removal safe).
- Existing shared-contract tests that STAY green: `test_executor_kwargs_injection_success` (:324,
  asserts `kwargs["realtime_transcription_executor"] is executor`), `test_executor_kwargs_config_
  off_is_stock_path` (:341), `test_executor_kwargs_probe_failure_degrades_with_one_info_line`
  (:356), `test_ready_payload_flag_true_and_false` (:389).
- Expected after S3: **30 passed** (29 − 0 + 1 repin + 1 new pin; the 3 reds gone).

### 3.2 tests/test_streaming.py — real-model WATCH SET (never run as CPU validation)

:1128-1138 calls `recorder_host.augment_kwargs_with_executor(kwargs, cfg, resolved, logger,
executor_factory=recording_factory)` and asserts `kwargs.get("transcription_executor") is executor`
AND `kwargs.get("realtime_transcription_executor") is executor` — the SHARED contract S3 preserves.
Signature + behavior unchanged → the watch set's import surface is intact. Validate with
`--collect-only` ONLY (AGENTS.md; system_context: "the real-model watch set (test_streaming.py
3P/4F) reproduces exactly as baselined").

### 3.3 tests/test_recorder_host.py — IPC gate (does NOT reference augment)

AGENTS.md classifies it as a CUDA suite (safe form `timeout 600`); its header claims hermetic.
Follow AGENTS.md's safe form. It imports `voice_typing.recorder_host` → the import-purity +
module-shape regression gate after S3's edits. Expected: unchanged count, green.

### 3.4 tests/test_bulk_stage_remediation.py — S2 QUARANTINES (not S3's)

Its one reference to the split is a comment (:228); its test (:233) asserts the DAEMON-side
`use_main_model_for_realtime=False` + `daemon._BULK_REALTIME_BEAM_SIZE` — S2's removal territory.
S3 does not touch it.

## 4. Design decision — delete the split helpers (no lab retention)

"Preserve independent experimental helpers only in lab paths, not an activation knob" and "label
any retained split helper as lab-only" are PERMISSIVE: preservation is allowed only in a lab path,
and labeling applies only IF retained. Recommended: **DELETE** `arm_bulk_realtime_executor` +
`_default_bulk_realtime_executor_factory` from the product module, because (a) the split never
qualified — G5 recorded both routes FAIL (57-word backlog, sentence-end dump) with the split in
place, so it is a failed remediation, not evidence worth a live seam; (b) the product module then
carries ZERO bulk identifiers — the same shape as S2's `test_daemon_has_no_bulk_surface` pin,
giving one auditable contract; (c) retention would depend on S2's quarantine-dir choice
(`tools/lab-tests/` vs `tests/lab/` — undetermined), coupling S3's one-pass success to S2's layout.
The evidence trail survives in git history, the quarantined `test_bulk_stage_remediation.py`
(comment), and `tests/G5_TIMING_EVIDENCE.md`. If the orchestrator wants a lab reference anyway,
the two helpers + their 3 tests can be relocated verbatim into S2's quarantine dir with a
LAB-ONLY module docstring — the PRP gives this as an explicit secondary path.

## 5. Downstream

- **P1.M1.T2.S2** ("Acknowledge priming across recorder IPC"): consumes the single-contract
  `_prompt_targets(executor) -> [executor]` + the augment invariant (ONE object in both kwargs).
  Its ACK ("known-applied/known-clear for both active lanes; one object is normal") reduces to
  exactly one target after S3.
- **P1.M1.T4.S3** ("Make recorder identity safe at capture boundaries"): relay IDs untouched.

## 6. Anti-patterns

- ❌ Don't change `augment_kwargs_with_executor`'s signature (test_streaming.py:1128 positional call).
- ❌ Don't touch `_RelayIds`/`_with_identity`/`_ready_payload`/`feed_input`/`partial_source`.
- ❌ Don't keep a dead `extra_kwargs` param on `_prompt_targets` "for compatibility" — one arg,
  one contract; T2.S2 extends from there.
- ❌ Don't leave the bulk-lane tests red or xfail them — remove them (the function they test is gone).
- ❌ Don't edit daemon.py / test_daemon.py / test_session_recovery.py / the bulk suites / pyproject
  (S2's). Don't run test_streaming/test_feed_audio/test_cuda_check or the daemon.
- ❌ Two timeouts on every pytest (AGENTS.md).
