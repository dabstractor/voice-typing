name: "P1.M1.T1.S3 — Remove bulk-only recorder wiring from product"
description: >

---

## Goal

**Feature Goal**: Finish retiring the Rev-4 bulk-text experiment at the **recorder-host** layer: remove the bulk-only realtime-lane SPLIT from `voice_typing/recorder_host.py`'s supported constructor/launch path — the `delivery == "bulk-text"` activation branch in `augment_kwargs_with_executor`, the `arm_bulk_realtime_executor` + `_default_bulk_realtime_executor_factory` helpers, and the two-lane `_prompt_targets` fan-out — leaving **ONE supported RecorderHost executor contract**: at most ONE `PromptedExecutor` object, injected as BOTH `transcription_executor` and `realtime_transcription_executor`. Preserve the shared partial/final executor, the capability probe + degrade-to-stock path, relay IDs (utterance_id/session_gen), the `feed_input` lab seam, and `partial_source`. Update the constructor and lane-wiring docstrings (Mode A). Clear the 3 live-red bulk-lane tests in `tests/test_prompt_engine.py` (S1 fallout) and add a structural no-bulk-lane migration pin. Fake-executor/fake-recorder validation only — no CUDA/model load.

**Deliverable**: Two files edited: (1) `voice_typing/recorder_host.py` — delete the activation branch + the two split helpers, simplify `_prompt_targets` to the single-contract form (1 arg) + update its one call site, rewrite the five prose sites; (2) `tests/test_prompt_engine.py` — remove the 3 bulk-lane tests + `_cfg_delivery` + the `arm_bulk_realtime_executor` import, re-pin the fan-out helper to the single contract, add `test_recorder_host_has_no_bulk_lane_surface`. No other file.

**Success Definition**:
- (a) `voice_typing/recorder_host.py` contains **zero** occurrences of `bulk` / `beam` / `"bulk-text"`; `augment_kwargs_with_executor` has NO delivery branch and returns the one shared executor; `_prompt_targets` is single-arg and returns `[prompt_executor]` or `[]`.
- (b) The shared contract is byte-identical: with `context_prompt=true` + an injected fake factory, `kwargs["transcription_executor"] is kwargs["realtime_transcription_executor"] is executor`; config-off → `None` + untouched kwargs; probe failure → ONE INFO line + `None`. Signature unchanged: `augment_kwargs_with_executor(kwargs, cfg, resolved, logger, *, executor_factory=None)`.
- (c) `tests/test_prompt_engine.py` → **30 passed** (baseline 3 failed / 29 passed; the 3 reds gone, +1 repin, +1 new pin).
- (d) `tests/test_recorder_host.py` green with an unchanged count (import-purity + IPC gate); `tests/test_streaming.py` `--collect-only` clean (watch set import surface intact).
- (e) `voice_typing.recorder_host` import purity holds (no `torch`/`ctranslate2`/`faster_whisper`/`realtimestt` in `sys.modules` after import).
- (f) `git diff --name-only` == exactly `{voice_typing/recorder_host.py, tests/test_prompt_engine.py}`.

## User Persona

**Target User**: (1) The maintainer — the recorder-host child carries one auditable executor contract instead of a dead two-lane activation path for a mode the config layer already rejects; (2) the downstream subtask **P1.M1.T2.S2** ("Acknowledge priming across recorder IPC"), which must add an explicit known-applied/known-clear prompt ACK "for both active lanes (one object is normal)" — after S3 there is only ever the one object, so its ACK reduces to a single target.

**Use Case**: First arm → the daemon spawns the `RecorderHost` child → `augment_kwargs_with_executor` (child-side) arms the shared `PromptedExecutor` into both kwargs (or degrades to stock) → `("prompt", …)` commands fan out to exactly that one executor → partials/finals carry relay identity back. No build can ever produce a second realtime executor.

**Pain Points Addressed**: a provably-dead activation branch (`delivery == "bulk-text"` is unconstructible since S1) plus two helpers that only it called; a `_prompt_targets` whose second lane can never populate; and 3 permanently-red tests in a supported pure-Python suite (S1 fallout) that will otherwise read as a regression forever.

## Why

- **S1 made the branch dead; S2 removes the daemon half; S3 removes the recorder half.** S1 (landed, `config.py:204-206`) rejects `output.delivery="bulk-text"` at construction, so `augment_kwargs_with_executor`'s `if getattr(cfg.output, "delivery", "stream-edit") == "bulk-text":` (`recorder_host.py:1191`) can never be true. S2 (parallel contract) detaches the daemon's bulk routing + its `cfg_to_kwargs` bulk branch (the `use_main_model_for_realtime=False` / `beam_size_realtime` override) and explicitly leaves `recorder_host.py` to S3. After both, no supported constructor or launch path can produce a split realtime lane.
- **One contract for T2.S2.** system_context.md:14 specifies the prompt ACK for "both active lanes (one object is normal)". The cleanest surface to build on is a module where the one object is the ONLY state — no conditional fan-out to reason about.
- **The split never qualified.** It was BUG-002's remediation for bulk R.1; `tests/G5_TIMING_EVIDENCE.md` records both routes FAIL (57-word backlog, sentence-end dump) with the split in place. It is a failed experiment, not evidence worth a live seam in the product module.
- **Clears real red tests, not by skipping.** The 3 bulk-lane tests fail today because the config they construct is retired. The function they test is being removed; the tests go with it, replaced by a pin that asserts the single contract.

## What

Subtractive edit of the product module (one branch, two helpers, one fan-out simplification, five docstring/comment sites) + test cleanup/re-pin. No behavior change for the shared path; no edits outside the two files.

### Success Criteria

- [ ] `grep -cE "bulk|beam" voice_typing/recorder_host.py` → 0.
- [ ] `augment_kwargs_with_executor`: no `delivery` reference; returns `executor` after arming BOTH kwargs with the SAME object; signature unchanged.
- [ ] `_prompt_targets(prompt_executor)` (single arg) → `[prompt_executor]` / `[]`; the `("prompt", …)` handler calls it with one arg.
- [ ] `RecorderHost` class/ctor docstring + `_worker_main` docstring + the prompt-handler comment + `_prompt_targets` docstring state the ONE-executor contract (Mode A); no "lanes are split" prose remains.
- [ ] `tests/test_prompt_engine.py`: no `arm_bulk_realtime_executor` import; `_cfg_delivery` + the 3 bulk-lane tests gone; `test_prompt_targets_single_executor_contract` green; `test_recorder_host_has_no_bulk_lane_surface` green; → 30 passed.
- [ ] `tests/test_recorder_host.py` green (unchanged count); `tests/test_streaming.py --collect-only` clean; import purity holds.
- [ ] `git diff --name-only` == `voice_typing/recorder_host.py`, `tests/test_prompt_engine.py`.

## All Needed Context

### Context Completeness Check

_Pass._ Every removal site is enumerated with verified line numbers against the live 1721-line file; the preservation list names its owning symbols; the 3 red tests are reproduced (3 failed / 29 passed this session) with their cause (S1's `ValueError`); the real-model watch set's call shape is read (positional `executor_factory=`, shared-contract assertion) so the signature constraint is known; import purity is verified; and the S2 contract's disjoint edit set is confirmed. The reference implementations for the simplified `_prompt_targets`, the docstrings, and both new/repinned tests are copy-ready.

### Verified Current State (re-verified this session)

- **S1 landed** (`ae7db9f`): `voice_typing/config.py:204-206` — `if self.delivery == "bulk-text": raise ValueError('output.delivery="bulk-text" is retired: ...')`.
- **recorder_host.py removal sites** (grep-verified): activation branch `:1181-1196` (11-line BUG-002 comment `:1181-1190` + `if getattr(cfg.output, "delivery", "stream-edit") == "bulk-text":` `:1191` → `arm_bulk_realtime_executor(...)` `:1192-1194` → override `:1195-1196`); `_default_bulk_realtime_executor_factory` `:1200-1208`; `arm_bulk_realtime_executor` `:1211-1266`; `_prompt_targets` two-lane body `:1102-1121` (reads `(extra_kwargs or {}).get("realtime_transcription_executor")` `:1118-1120`); the call site `:1018` `targets = _prompt_targets(extra_kwargs, prompt_executor)`.
- **Prose sites**: `_worker_main` docstring `:691-695` ("BULK-TEXT builds (BUG-002 round 3) then SPLIT the lanes: ...") and `:701-702` ("(the shared executor, plus the dedicated bulk realtime executor when the lanes are split)"); the prompt-handler comment `:1014-1017` ("BUG-002 round 3: bulk builds fan the update out to BOTH lanes ..."); `_prompt_targets` docstring `:1105-1113`; `augment_kwargs_with_executor` docstring — its body has no bulk mention, but the comment block `:1181-1190` does.
- **The shared contract that STAYS** (`:1169-1179`): `kwargs["transcription_executor"] = executor; kwargs["realtime_transcription_executor"] = executor` + the "dynamic executor armed" INFO line; config gate `:1157-1158`; probe + broad degrade `:1159-1168`.
- **Baseline** `tests/test_prompt_engine.py`: **3 failed / 29 passed in 0.12s** — `test_bulk_delivery_splits_realtime_lane` (:418), `test_bulk_realtime_lane_probe_failure_degrades_to_shared` (:435), `test_bulk_realtime_lane_default_factory_uses_greedy_beam` (:470), all via `_cfg_delivery("bulk-text")` (:411-416) → S1's `ValueError`.
- **Import purity**: `import voice_typing.recorder_host` → no `torch`/`ctranslate2`/`faster_whisper`/`realtimestt` in `sys.modules` (`prompt_engine` is imported lazily inside the function).

### Documentation & References

```yaml
# THE INPUT CONTRACT (S1 — LANDED ae7db9f)
- file: voice_typing/config.py
  why: :204-206 rejects delivery="bulk-text" at construction — the reason the recorder_host branch
        is provably dead and the 3 tests are red. S3's pin re-asserts this chain.
  critical: "Do NOT edit config.py. S3's job is the recorder-side wiring only."

# THE PARALLEL SIBLING (S2 — CONTRACT, in flight; DISJOINT edit set)
- file: plan/009_ef3b49b0fc0d/P1M1T1S2/PRP.md
  why: S2 detaches the DAEMON bulk machinery (daemon.py + test quarantine). Its Critical #4:
        "DO NOT EDIT voice_typing/ EXCEPT daemon.py ... recorder_host.augment_kwargs_with_executor's
        split executor is P1.M1.T1.S3's." Its downstream note: "The quarantined test_bulk_stage_
        remediation asserts that split [daemon-side use_main_model_for_realtime/beam] — S3 may
        reference it as the lab pin while removing the product wiring."
  critical: "S3 edits ONLY recorder_host.py + test_prompt_engine.py. daemon.py, test_daemon.py,
            test_session_recovery.py, the bulk suites, pyproject.toml are S2's — do not touch."

# THE AUTHORITATIVE SITE MAP
- docfile: plan/009_ef3b49b0fc0d/architecture/system_context.md
  why: :8 — "In recorder_host.py:augment_kwargs_with_executor the bulk-only split creates a second
        realtime executor ... Keep generation/utterance relay stamping, shared executor, _feed_input
        lab seam if independently useful, ordinary session recovery and generic idle/media/cancel
        behavior. Bulk-specific tests can live as explicit lab references or be replaced at
        supported entry points by migration assertions." :14 — T2.S2's ACK "for both active lanes
        (one object is normal)".
  section: "Line 8 (the KEEP list + 'migration assertions') and line 14 (the downstream consumer) are load-bearing."

# THE FILE UNDER EDIT #1
- file: voice_typing/recorder_host.py
  why: 1721 lines. Removal sites :1181-1196 (activation), :1200-1208 + :1211-1266 (helpers),
        :1102-1121 (two-lane _prompt_targets), :1018 (call site); prose :691-695, :701-702,
        :1014-1017, :1105-1113. Keeper symbols: augment_kwargs_with_executor (:1131; shared arming
        :1169-1179), _default_prompt_executor_factory (:1124), _ready_payload (:1268),
        _RelayIdentity/_RelayIds/_with_identity (:1048-1100), RecorderHost.__init__ (:142; feed_input
        + partial_source params).
  pattern: "Child-side lazy imports (prompt_engine inside functions); broad degrade on probe failure
            with ONE INFO line; additive 'ready' keys. Keep that style in every docstring you touch."
  gotcha: "augment_kwargs_with_executor's SIGNATURE is load-bearing (test_streaming.py:1128 calls it
           positionally with executor_factory=). Do not add/remove params."

# THE FILE UNDER EDIT #2
- file: tests/test_prompt_engine.py
  why: PURE-PYTHON (faster_whisper faked via sys.modules; fake executor_factory seam). 32 tests;
        imports :40 _prompt_targets, :42 arm_bulk_realtime_executor (REMOVE), :43 augment_kwargs_
        with_executor (KEEP). Bulk block :399-484 (banner, _cfg_delivery, 3 tests). Fan-out test
        :486-498 (REPIN). Shared-contract tests :324/:341/:356/:389 STAY.
  pattern: "_FakeExecutor (:109) records warmup count + args; _RESOLVED_CUDA/_LOG module constants;
            augment is called with executor_factory=_FakeExecutor or a closure."
  gotcha: "After deleting _cfg_delivery, grep OutputConfig/AsrConfig — if unused, drop the imports."

# THE REAL-MODEL WATCH SET (collect-only gate; NEVER run)
- file: tests/test_streaming.py
  why: :1128-1138 calls recorder_host.augment_kwargs_with_executor(kwargs, cfg, resolved, logger,
        executor_factory=recording_factory) and asserts BOTH kwargs are the same executor — the
        shared contract S3 preserves. 3P/4F watch set (system_context) — --collect-only only.
  critical: "Its import surface must stay intact. Signature unchanged ⇒ intact. Validate with
            --collect-only; never execute (real models)."

# THE IPC GATE
- file: tests/test_recorder_host.py
  why: Imports voice_typing.recorder_host; exercises RecorderHost with canned events + a stubbed
        _worker_main. Does NOT reference augment_kwargs_with_executor. AGENTS.md classifies it as a
        CUDA suite → run under its safe form (timeout 600). Header claims hermetic.
  critical: "This is the module-shape regression gate after the deletions. Expected: unchanged
            count, green."

# THE SPEC
- docfile: plan/009_ef3b49b0fc0d/prd_snapshot.md
  why: §4.2sexies is "Legacy bulk text delivery experiment (Rev 4 reference, superseded)";
        §4.5 delivery = "existing keyboard-delivery default; native editor sessions do not use this
        selector"; §4.2quater rolling context prompt (initial_prompt / initial_prompt_realtime) is
        the shared-executor feature S3 preserves; R.5 identity relay is preserved.

# THIS SUBTASK'S RESEARCH NOTE
- docfile: plan/009_ef3b49b0fc0d/P1M1T1S3/research/recorder_host_bulk_split_findings.md
  why: §2 the removal table + the KEEP list; §3 the test shapes (baseline 3F/29P, the 3 reds, the
        repin, the new pin, the watch-set call shape); §4 the delete-vs-relocate decision; §5 the
        T2.S2 consumer.
  section: "§2 (site table) and §3.1 (test edits) are load-bearing."
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/
├── recorder_host.py            # 1721 lines; bulk split :1181-1266; _prompt_targets :1102; call :1018   ← EDIT (only voice_typing/ file)
├── config.py                   # S1: rejects bulk-text :204-206                                           ← READ-ONLY
└── daemon.py                   # S2 detaches the daemon bulk half (parallel)                             ← NOT S3's
tests/
├── test_prompt_engine.py       # 32 pure tests; 3 bulk-lane reds :418/:435/:470; fan-out :486           ← EDIT
├── test_recorder_host.py       # IPC gate (imports recorder_host; no augment refs)                       ← GATE
├── test_streaming.py           # real-model watch set; :1128 shared-contract call                        ← --collect-only
└── test_bulk_stage_remediation.py  # asserts DAEMON-side split (daemon._BULK_REALTIME_BEAM_SIZE)         ← S2 quarantines
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/recorder_host.py   # MODIFY: delete activation branch + 2 helpers; _prompt_targets → 1-arg single contract;
                                #          + its call site; rewrite 5 prose sites (Mode A ONE-executor contract)
tests/test_prompt_engine.py     # MODIFY: -arm_bulk import, -_cfg_delivery, -3 bulk tests; REPIN fan-out → single contract;
                                #          +test_recorder_host_has_no_bulk_lane_surface
# NOTHING ELSE. daemon.py / config.py / the bulk suites / pyproject.toml untouched (S2's).
```

### Known Gotchas of our Codebase & Library Quirks

```python
# CRITICAL #1 — THE SIGNATURE OF augment_kwargs_with_executor IS LOAD-BEARING. tests/test_streaming.py:1128
# calls it POSITIONALLY: augment_kwargs_with_executor(kwargs, cfg, resolved, logger, executor_factory=...).
# Keep (kwargs, cfg, resolved, logger, *, executor_factory=None) and the return value (the armed
# executor, or None on the stock/degrade path) byte-identical. S3 deletes a BRANCH inside it, nothing else.

# CRITICAL #2 — _prompt_targets GETS A NEW 1-ARG SIGNATURE. With the split gone, the second lane can never
# populate, so the extra_kwargs param is dead and misleading. New form:
#     def _prompt_targets(prompt_executor: Any) -> list[Any]:
#         return [prompt_executor] if prompt_executor is not None else []
# Update the ONE call site (:1018) to `_prompt_targets(prompt_executor)`. T2.S2 extends THIS seam to
# per-target ACKs — leave it as a named function (do not inline it into the command loop).

# CRITICAL #3 — THE 3 BULK-LANE TESTS ARE ALREADY RED (S1 FALLOUT), NOT A REGRESSION. They construct
# OutputConfig(delivery="bulk-text") via _cfg_delivery (:411-416) → S1's ValueError. The function
# they test is being deleted → REMOVE them (do not xfail/skip). Expected suite result after S3: 30 passed.

# CRITICAL #4 — KEEP THE SHARED CONTRACT TESTS GREEN AND UNTOUCHED: test_executor_kwargs_injection_success
# (:324 — asserts kwargs["realtime_transcription_executor"] is executor), test_executor_kwargs_config_
# off_is_stock_path (:341), test_executor_kwargs_probe_failure_degrades_with_one_info_line (:356),
# test_ready_payload_flag_true_and_false (:389). They ARE the one-contract proof.

# CRITICAL #5 — PRESERVATION LIST (do not touch): _RelayIdentity/_RelayIds/_with_identity (relay IDs),
# _ready_payload (context_prompt + partial_callback keys), _default_prompt_executor_factory, the
# capability probe + broad degrade, RecorderHost.__init__'s feed_input (the _feed_input lab seam used
# by test_feed_audio.py) and partial_source (R.8 provenance), all arm/disarm/text/abort/cancel/shutdown
# handling, stale-final purge, bounded abort, _run_text_and_emit_final.

# CRITICAL #6 — DELETE THE HELPERS; DO NOT RETAIN THEM IN THE PRODUCT MODULE. "Preserve independent
# experimental helpers only in lab paths" is PERMISSIVE. arm_bulk_realtime_executor + _default_bulk_
# realtime_executor_factory were the activation path's private helpers (nothing else calls them); the
# split never qualified (G5 both routes FAIL with it). Deleting them gives ZERO bulk identifiers in the
# module — the same auditable shape as S2's daemon pin. (Secondary path, only if the orchestrator asks
# for a lab reference: relocate both + their 3 tests verbatim into S2's quarantine dir with a LAB-ONLY
# module docstring. Default = delete.)

# GOTCHA #7 — IMPORT PURITY. recorder_host imports prompt_engine LAZILY inside functions (module scope
# is CUDA-free so the daemon can import it). The two deleted functions also imported lazily; purity is
# preserved trivially — but re-verify: after `import voice_typing.recorder_host`, none of torch /
# ctranslate2 / faster_whisper / realtimestt may be in sys.modules.

# GOTCHA #8 — NEVER RUN tests/test_streaming.py (real-model watch set) or test_feed_audio/test_cuda_check
# or the daemon. test_streaming → --collect-only ONLY. test_recorder_host.py → AGENTS.md safe form
# (timeout 600). test_prompt_engine.py → timeout 300. Two timeouts on EVERY pytest.

# GOTCHA #9 — UNUSED IMPORTS AFTER THE TEST CLEANUP. _cfg_delivery is the likely only user of OutputConfig
# (and maybe AsrConfig) in test_prompt_engine.py; grep after deleting it and drop imports that become
# unused (no ruff configured — do it by hand).

# GOTCHA #10 — S2 IS IN FLIGHT. Do not gate on daemon.py's state (S2 removes its cfg_to_kwargs bulk
# branch + _BULK_REALTIME_BEAM_SIZE). If a read-only grep still finds them at validation time, report
# "pending S2" — never edit daemon.py to make S3's gate pass.
```

## Implementation Blueprint

### Data models and structure

None new. Under edit: the module-level functions `augment_kwargs_with_executor` (signature unchanged; body loses one branch), `_prompt_targets` (2-arg → 1-arg), and the deletions of `_default_bulk_realtime_executor_factory` + `arm_bulk_realtime_executor`.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PRECHECK — S1 landed + reproduce the baseline.
  - RUN: grep -n 'is retired' voice_typing/config.py        # expect :206
  - RUN: timeout 300 .venv/bin/python -m pytest tests/test_prompt_engine.py -q --tb=no
    EXPECT: 3 failed, 29 passed (the 3 bulk-lane tests — S1 fallout).

Task 1: EDIT voice_typing/recorder_host.py — remove the split (work bottom-up so line numbers above hold).
  - 1a. DELETE `_default_bulk_realtime_executor_factory` (:1200-1208) and `arm_bulk_realtime_executor`
        (:1211-1266) entirely, including their docstrings and the blank lines between.
  - 1b. In `augment_kwargs_with_executor` (:1131-1198): DELETE the block :1181-1196 (the 11-line
        "# BUG-002 / validation round 3 (bulk-text only): split the lanes..." comment THROUGH the
        `if getattr(cfg.output, "delivery", "stream-edit") == "bulk-text":` branch and its body).
        The function then ends: `... logger.info("voice-typing context-prompt: dynamic executor armed ...")`
        followed by `return executor`. Verify the `return executor` line is intact and unconditional.
  - 1c. REWRITE the `augment_kwargs_with_executor` docstring to state the ONE-executor contract:
        """Child-side: conditionally arm the context-prompt executor into recorder kwargs.

        P1.M2.T5.S1 (PRD §4.2quater rolling context prompt). When cfg.asr.context_prompt is true:
        construct ONE PromptedExecutor for cfg.asr.lite_model at the resolved device/compute_type,
        run the CAPABILITY PROBE (build + 1 s warmup transcription), and on success mutate `kwargs`
        in place with kwargs["transcription_executor"] = kwargs["realtime_transcription_executor"]
        = executor — the SAME object: ONE model for partials AND finals (RealtimeSTT skips its
        TranscriptionWorker). On ANY probe failure — and when context_prompt is false, which takes
        the IDENTICAL stock path — kwargs are left untouched and None is returned (degrade to
        context-free decoding; PRD §8 never-crash).

        ONE EXECUTOR CONTRACT (P1.M1.T1.S3): there is no realtime-lane split. The Rev-4 bulk-text
        lane (a second beam-1 executor for partials) is retired together with output.delivery=
        "bulk-text", which the config layer rejects (P1.M1.T1.S1); `_prompt_targets` therefore
        always resolves to at most this one object — the surface P1.M1.T2.S2's prompt ACK builds on.

        Must run IN THE CHILD only: ... (keep the remaining existing paragraphs verbatim).
        """
  - 1d. SIMPLIFY `_prompt_targets` (:1102-1121) to:
        def _prompt_targets(prompt_executor: Any) -> list[Any]:
            """The executors a ("prompt", ...) command must update, in order.

            ONE EXECUTOR CONTRACT (P1.M1.T1.S3 / PRD §4.2quater): at most the shared context-prompt
            executor — the same object in BOTH the transcription and realtime kwargs. The former
            bulk-only second lane is retired (output.delivery="bulk-text" is rejected at config
            load, P1.M1.T1.S1), so this is always a 0- or 1-element list; the confirmed-prompt ACK
            (P1.M1.T2.S2) extends THIS seam. set_prompt itself never raises (prompt_engine contract).
            """
            return [prompt_executor] if prompt_executor is not None else []
  - 1e. UPDATE the one call site in `_abort_supervisor` (:1018): `targets = _prompt_targets(extra_kwargs, prompt_executor)`
        → `targets = _prompt_targets(prompt_executor)`. Trim the comment :1014-1017 to drop the
        "BUG-002 round 3: bulk builds fan the update out to BOTH lanes ..." sentences; KEEP the
        P1.M2.T5.S1 delivery-timing note (read only BETWEEN utterances).
  - 1f. REWRITE prose: `_worker_main` docstring :691-695 — delete "BULK-TEXT builds (BUG-002 round 3)
        then SPLIT the lanes: ... degrading to the shared executor on any probe failure." and replace
        with "ONE executor is armed (P1.M1.T1.S3) — there is no realtime-lane split."; :701-702 —
        "set_prompt fan-out via _prompt_targets (the shared executor, plus the dedicated bulk realtime
        executor when the lanes are split)" → "set_prompt via _prompt_targets (the one armed executor)".
  - 1g. REWRITE the RecorderHost class docstring (:130-140) — append ONE sentence after the stop()
        paragraph: "EXECUTOR CONTRACT (P1.M1.T1.S3): the child arms at most ONE context-prompt
        PromptedExecutor, injected as BOTH transcription_executor and realtime_transcription_executor;
        there is no bulk realtime lane (retired with output.delivery="bulk-text"). `feed_input` is the
        offline feed_audio lab seam; `partial_source` is the R.8 partial-callback provenance key."
  - 1h. VERIFY: grep -cE "bulk|beam" voice_typing/recorder_host.py → 0;
        grep -n "_prompt_targets(" voice_typing/recorder_host.py → exactly 2 hits (def + the 1 call);
        .venv/bin/python -c "import voice_typing.recorder_host" (import purity — see Gate L1).

Task 2: EDIT tests/test_prompt_engine.py — retire the dead tests, re-pin, add the migration pin.
  - 2a. DELETE the import `arm_bulk_realtime_executor,` (:42). KEEP `_prompt_targets,` (:40) and
        `augment_kwargs_with_executor,` (:43).
  - 2b. DELETE the block :399-484: the BUG-002 banner comment, `_cfg_delivery`, and the three tests
        `test_bulk_delivery_splits_realtime_lane`, `test_bulk_realtime_lane_probe_failure_degrades_to_shared`,
        `test_bulk_realtime_lane_default_factory_uses_greedy_beam`.
  - 2c. REPIN :486-498 →
        def test_prompt_targets_single_executor_contract():
            """_prompt_targets (P1.M1.T1.S3): the ONE-executor contract — exactly the armed executor, or none."""
            main = _FakeExecutor("m", "d", "c")
            assert _prompt_targets(main) == [main]   # one object, one target
            assert _prompt_targets(None) == []       # nothing armed: no targets (the loop logs + ignores)
  - 2d. ADD the migration pin (place right after the repinned test):
        def test_recorder_host_has_no_bulk_lane_surface():
            """P1.M1.T1.S3: the Rev-4 bulk realtime-lane SPLIT is gone from recorder_host — ONE executor
            contract. No split helper exists, the module carries no bulk/beam wiring, augment arms the SAME
            object into both kwargs, the prompt fan-out reaches exactly that object, and the config layer
            (S1) rejects the only delivery value that could have requested a split."""
            import inspect
            import voice_typing.recorder_host as rh
            from voice_typing.config import VoiceTypingConfig
            assert not hasattr(rh, "arm_bulk_realtime_executor")
            assert not hasattr(rh, "_default_bulk_realtime_executor_factory")
            src = inspect.getsource(rh)
            assert "bulk" not in src.lower() and "beam" not in src.lower(), "bulk/beam wiring survived"
            assert "extra_kwargs" not in inspect.signature(rh._prompt_targets).parameters  # 1-arg seam
            # the ONE object lands in BOTH kwargs (context-prompt on, fake factory)
            kwargs: dict = {"model": "small.en", "device": "cuda"}
            executor = rh.augment_kwargs_with_executor(
                kwargs, VoiceTypingConfig(asr=AsrConfig(context_prompt=True)),
                _RESOLVED_CUDA, _LOG, executor_factory=_FakeExecutor,
            )
            assert executor is not None
            assert kwargs["transcription_executor"] is executor
            assert kwargs["realtime_transcription_executor"] is executor   # SAME object — no split
            assert rh._prompt_targets(executor) == [executor]
            # S1's chain: no constructible config can request the retired lane
            with pytest.raises(ValueError, match="retired"):
                VoiceTypingConfig.from_toml({"output": {"delivery": "bulk-text"}})
  - 2e. After the deletions, grep `OutputConfig` / `AsrConfig` usage in the file; drop any now-unused
        import (Gotcha #9). Confirm `pytest` and `logging` imports remain used.

Task 3: VALIDATE (gates below). No git commit unless the orchestrator directs. If asked:
  "P1.M1.T1.S3: remove bulk-only recorder wiring; ONE RecorderHost executor contract (recorder_host.py)".
```

### Implementation Patterns & Key Details

```python
# The subtractive core: augment_kwargs_with_executor BEFORE (abridged, :1169-1198) ...
#     kwargs["transcription_executor"] = executor
#     kwargs["realtime_transcription_executor"] = executor
#     logger.info("voice-typing context-prompt: dynamic executor armed ...")
#     # BUG-002 ... 11-line comment ...
#     if getattr(cfg.output, "delivery", "stream-edit") == "bulk-text":      # DEAD since S1
#         realtime_executor = arm_bulk_realtime_executor(kwargs, cfg, resolved, logger, executor_factory=...)
#         if realtime_executor is not None:
#             kwargs["realtime_transcription_executor"] = realtime_executor  # the SPLIT
#     return executor
# AFTER: the three shared lines, then `return executor`. The success invariant is now unconditional:
#     kwargs["transcription_executor"] is kwargs["realtime_transcription_executor"]   # always

# _prompt_targets AFTER (the 1-arg seam T2.S2 extends):
def _prompt_targets(prompt_executor: Any) -> list[Any]:
    return [prompt_executor] if prompt_executor is not None else []

# The migration pin's source scan ("bulk"/"beam" absent from inspect.getsource(rh)) is what makes the
# removal durable — a future re-introduction of ANY bulk/beam wiring in recorder_host.py turns it red,
# mirroring S2's test_daemon_has_no_bulk_surface on the daemon side.
```

### Integration Points

```yaml
DOWNSTREAM (NOT S3):
  - P1.M1.T2.S2 (Acknowledge priming across recorder IPC): builds the known-applied/known-clear
    prompt ACK on the 1-arg _prompt_targets(executor) -> [executor] seam + the ONE-object invariant.
    system_context.md:14 ("one object is normal") becomes the only state.
  - P1.M1.T4.S3 (recorder identity at capture boundaries): relay IDs (_RelayIds/_with_identity) untouched.
PARALLEL (S2 — CONTRACT):
  - S2 owns daemon.py (bulk detach incl. the cfg_to_kwargs use_main_model_for_realtime=False /
    beam_size_realtime branch), test_daemon.py, test_session_recovery.py, the bulk-suite quarantine,
    pyproject.toml. S3's edit set is disjoint. Together S2+S3 remove BOTH halves of the split
    (daemon kwargs override + child executor override).
PRESERVED SURFACES: augment_kwargs_with_executor signature + shared arming + degrade; the
  capability probe; _ready_payload's context_prompt/partial_callback keys; relay identity stamping;
  RecorderHost feed_input + partial_source params; all command handling.
NOT TOUCHED: voice_typing/{daemon.py, config.py, bulk_controller.py, ime/*, feedback.py, ctl.py,
  session_recovery.py, prompt_engine.py}; tests/{test_daemon,test_session_recovery,test_bulk_*,
  test_streaming,test_recorder_host}.py; pyproject.toml; config.toml.
```

## Validation Loop

> AGENTS.md two-timeout rule on EVERY pytest (inner GNU `timeout`, bash-tool timeout above it). `.venv/bin/python -m pytest`. NEVER run `test_streaming.py` (real-model watch set — `--collect-only` only), `test_feed_audio.py`, `test_cuda_check.py`, or the daemon.

### Level 1: The split is gone (static + import purity)

```bash
cd /home/dustin/projects/voice-typing
echo "--- zero bulk/beam identifiers in recorder_host.py ---"
grep -cE "bulk|beam" voice_typing/recorder_host.py                      # EXPECT 0
grep -nE "arm_bulk|_default_bulk|\"bulk-text\"|beam_size" voice_typing/recorder_host.py   # EXPECT no output
echo "--- _prompt_targets is the 1-arg seam; exactly def + one call ---"
grep -n "_prompt_targets(" voice_typing/recorder_host.py                 # EXPECT 2 lines: the def + the call
echo "--- augment signature unchanged + no delivery branch ---"
grep -n "def augment_kwargs_with_executor" voice_typing/recorder_host.py
sed -n "$(grep -n 'def augment_kwargs_with_executor' voice_typing/recorder_host.py | cut -d: -f1),+8p" voice_typing/recorder_host.py | grep -E "executor_factory"
grep -n "delivery" voice_typing/recorder_host.py                          # EXPECT no output
echo "--- import purity (module scope CUDA-free) ---"
timeout 60 .venv/bin/python -c "
import sys, voice_typing.recorder_host as rh
leaks=[m for m in ('torch','ctranslate2','faster_whisper','realtimestt') if m in sys.modules]
assert not leaks, leaks
assert not hasattr(rh,'arm_bulk_realtime_executor') and not hasattr(rh,'_default_bulk_realtime_executor_factory')
print('L1 PASS: import purity holds; split helpers absent')"
echo "--- scope ---"
git diff --name-only | grep -vE '^(voice_typing/recorder_host\.py|tests/test_prompt_engine\.py)$' | grep -vE '^plan/' | grep -E '\.py$|\.toml$|\.md$' && echo "L1 FAIL: out of scope" || echo "L1 PASS: only the two intended files"
```

### Level 2: The pure suite — reds cleared, pins green

```bash
cd /home/dustin/projects/voice-typing
echo "--- test_prompt_engine.py (baseline was 3 failed / 29 passed) ---"
timeout 300 .venv/bin/python -m pytest tests/test_prompt_engine.py -q 2>&1 | tail -2
# EXPECT: 30 passed (29 kept + the repinned fan-out counted once + the new pin; the 3 reds gone)
echo "--- the two pins by name ---"
timeout 300 .venv/bin/python -m pytest tests/test_prompt_engine.py -q -k "single_executor_contract or no_bulk_lane_surface" -v 2>&1 | grep -E "PASSED|FAILED|passed|failed"
echo "--- the shared-contract tests still green ---"
timeout 300 .venv/bin/python -m pytest tests/test_prompt_engine.py -q -k "executor_kwargs or ready_payload" 2>&1 | tail -1
```

### Level 3: Module-shape gates — IPC suite + watch-set import surface

```bash
cd /home/dustin/projects/voice-typing
echo "--- test_recorder_host.py (AGENTS.md safe form; imports recorder_host) ---"
timeout 600 .venv/bin/python -m pytest tests/test_recorder_host.py -q 2>&1 | tail -2
# EXPECT: all passed, count unchanged vs pre-edit (record the number)
echo "--- test_streaming.py: COLLECT-ONLY (real-model watch set — never execute) ---"
timeout 120 .venv/bin/python -m pytest tests/test_streaming.py --collect-only -q 2>&1 | tail -2
# EXPECT: collection succeeds (import surface intact: augment_kwargs_with_executor still importable, same signature)
echo "--- (read-only) S2's daemon half: report, do not edit ---"
grep -cE "_BULK_REALTIME_BEAM_SIZE|use_main_model_for_realtime\": False" voice_typing/daemon.py
# EXPECT 0 after S2 lands; if >0, report 'pending S2' (Gotcha #10). NEVER edit daemon.py here.
```

### Level 4: The ONE contract is behavioral, not textual (fake executor, no CUDA)

```bash
cd /home/dustin/projects/voice-typing
timeout 120 .venv/bin/python - <<'PY'
# Behavioral proof with a fake factory: whatever cfg is passed (the only constructible delivery is
# stream-edit), augment arms ONE object into BOTH kwargs and the fan-out reaches exactly it.
import logging
from voice_typing import recorder_host as rh
from voice_typing.config import VoiceTypingConfig
class Fake:
    def __init__(self, *a): self.args = a
    def warmup(self): pass
    def set_prompt(self, t): pass
import voice_typing.prompt_engine as pe
pe.probe_prompt_executor = lambda e: pe.PromptProbeResult(ok=True)   # fake probe — no model
kw = {}
ex = rh.augment_kwargs_with_executor(kw, VoiceTypingConfig(), {"device":"cpu","compute_type":"int8"},
                                     logging.getLogger("s3"), executor_factory=Fake)
assert ex is not None and kw["transcription_executor"] is ex and kw["realtime_transcription_executor"] is ex
assert rh._prompt_targets(ex) == [ex] and rh._prompt_targets(None) == []
print("L4 PASS: ONE executor object in both kwargs; fan-out = [executor]; no CUDA/model loaded")
PY
echo "--- confirm no model/CUDA module got imported by the above ---"
timeout 60 .venv/bin/python -c "
import sys, logging
from voice_typing import recorder_host as rh
from voice_typing.config import VoiceTypingConfig
class F:
    def __init__(s,*a): pass
    def warmup(s): pass
import voice_typing.prompt_engine as pe; pe.probe_prompt_executor=lambda e: pe.PromptProbeResult(ok=True)
rh.augment_kwargs_with_executor({}, VoiceTypingConfig(), {'device':'cpu','compute_type':'int8'}, logging.getLogger('x'), executor_factory=F)
assert not any(m in sys.modules for m in ('torch','ctranslate2','faster_whisper')), 'CUDA stack imported!'
print('L4b PASS: no torch/ctranslate2/faster_whisper imported on the fake path')"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: zero `bulk`/`beam` in `recorder_host.py`; `_prompt_targets` is 1-arg (def + one call); `augment_kwargs_with_executor` signature unchanged, no `delivery` branch; import purity holds; scope = the two files.
- [ ] L2: `test_prompt_engine.py` → 30 passed; the repinned + new pins green; the four shared-contract tests green.
- [ ] L3: `test_recorder_host.py` green (unchanged count); `test_streaming.py --collect-only` clean; S2's daemon half reported (not edited).
- [ ] L4: fake-factory behavioral proof — ONE object in both kwargs, fan-out `[executor]`, no CUDA stack imported.

### Feature Validation
- [ ] The bulk realtime split and its kwargs override are removed from every supported constructor/launch path (no activation branch, no helpers).
- [ ] Shared partial/final executor preserved (same object in both kwargs); capability degradation preserved (config-off → None/stock; probe failure → ONE INFO line → None).
- [ ] Relay IDs (`_RelayIds`/`_with_identity`/`_ready_payload`) preserved untouched.
- [ ] `feed_input` lab seam and `partial_source` preserved.
- [ ] ONE supported RecorderHost executor contract, consumed by P1.M1.T2.S2 via the 1-arg `_prompt_targets`.

### Code Quality Validation
- [ ] Subtractive edit: no shared-path code rewritten; deletions only + the fan-out simplification.
- [ ] Mode A docstrings updated (class/ctor docstring, `_worker_main`, prompt-handler comment, `_prompt_targets`, `augment_kwargs_with_executor`); no "lanes are split" prose remains.
- [ ] Dead test code removed (not xfailed); unused imports dropped.

### Scope Boundary Validation
- [ ] `voice_typing/` diff = `recorder_host.py` only; `daemon.py`/`config.py` untouched (S2/S1).
- [ ] No bulk-suite, `test_daemon.py`, `test_session_recovery.py`, `pyproject.toml` edits (S2's quarantine).
- [ ] No CUDA/model suites executed; `test_streaming.py` collect-only; two timeouts everywhere.

### Documentation & Deployment
- [ ] No retained split helper exists, so no "lab-only" label is needed — the PRP records the delete-vs-relocate decision; if relocated instead, the lab module carries a LAB-ONLY docstring.
- [ ] New/repinned tests carry docstrings naming P1.M1.T1.S3 and the ONE-executor contract.

---

## Anti-Patterns to Avoid

- ❌ **Don't change `augment_kwargs_with_executor`'s signature or return semantics** — `test_streaming.py:1128` calls it positionally with `executor_factory=`; the real-model watch set must keep collecting (Critical #1).
- ❌ **Don't keep a dead `extra_kwargs` param on `_prompt_targets`** "for compatibility" — the second lane can never populate; make it the 1-arg seam T2.S2 extends (Critical #2).
- ❌ **Don't xfail/skip the 3 red bulk-lane tests** — remove them; the function they test is deleted (Critical #3).
- ❌ Don't touch the four shared-contract tests (:324/:341/:356/:389) — they are the one-contract proof (Critical #4).
- ❌ Don't touch relay IDs, `_ready_payload`, `feed_input`, `partial_source`, or any command handling (Critical #5).
- ❌ Don't retain the split helpers inside the product module as "lab-only" functions — product module = zero bulk identifiers; relocation (if ever wanted) goes to S2's quarantine dir (Critical #6).
- ❌ Don't run `test_streaming.py`, `test_feed_audio.py`, `test_cuda_check.py`, or the daemon; `test_recorder_host.py` only under its `timeout 600` safe form (Gotcha #8).
- ❌ Don't edit `daemon.py` to clear S2's half of the split — report "pending S2" if its `_BULK_REALTIME_BEAM_SIZE`/`use_main_model_for_realtime: False` branch is still present at validation time (Gotcha #10).
- ❌ Don't leave unused imports (`OutputConfig`/`AsrConfig`) in `test_prompt_engine.py` after deleting `_cfg_delivery` (Gotcha #9).

---

## Confidence Score

**9.5/10** for one-pass success. The edit is subtractive with every removal and prose site enumerated by verified line number against the live 1721-line file; the preservation list names its owning symbols; the one signature constraint is read from its real caller; the 3 red tests are reproduced (3F/29P this session) with their cause (S1's `ValueError`) so the implementer knows the expected end state (30 passed); import purity is verified and re-gated; and the S2 contract's disjoint edit set is confirmed, with the daemon-half dependency handled as report-only. The reference implementations (`_prompt_targets`, the docstrings, both tests, the behavioral L4 proof with a fake probe) are copy-ready and CUDA-free. The −0.5: the `"bulk" not in src.lower()` source scan in the new pin could be tripped by an unrelated future comment containing the substring (e.g. "bulk" in prose) — acceptable as a drift guard, but the implementer should confirm the current module text is clean after edits (L1's grep does exactly that).
