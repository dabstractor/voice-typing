# Research Note: disconnecting daemon bulk routing and activation (P1.M1.T1.S2)

**Status:** EMPIRICALLY VERIFIED against the live repo at HEAD `47fda81` (S1 LANDED: `config.py:206` rejects `"bulk-text"`; the top-level triple `__post_init__` is REMOVED per the note at `config.py:425-430`). All line numbers verified this session.

## §1. Live state after S1 — the bulk surface is now DEAD CODE by construction

- `OutputConfig(delivery="bulk-text")` and `from_toml({"output":{"delivery":"bulk-text"}})` raise `ValueError` (S1). Therefore `VoiceTypingDaemon._bulk_mode()` (`daemon.py:2160`, `return self._cfg.output.delivery == "bulk-text"`) is **provably False for every constructible config** → every `if self._bulk_mode():` branch and every `_bulk_*` method is unreachable in production.
- **Red fallout (exactly S1's handoff, re-verified today):** `tests/test_bulk_dispatch.py + test_bulk_context_prompt.py + test_bulk_stage_remediation.py` → **44 failed / 8 passed**; `tests/test_session_recovery.py` → **4 failed / 29 passed** (the bulk Layer-B tests at `:439+`, `_make_armed_bulk_daemon` → `tbd._make_bulk_daemon`); `tests/test_daemon.py -k "bulk or delivery"` → **2 passed** (those two are the `_build_default_bulk_target` purity pin `:5794` and a status-surface test `:2265` — NOT red yet; see §4).
- The generic stream path is INTACT: the 265 other daemon tests pass; `_cmd_streaming` (`:3650`) → `_session_streaming` (`:1190`) → `_streaming_now` (`:2566`) → `_on_partial`/`on_final` is the per-arm streaming/block mode flow that has NOTHING to do with bulk and must be preserved byte-for-byte.

## §2. The detach inventory in daemon.py (154 `bulk` references — every site enumerated)

| # | Site (line) | What it is | Action |
|---|---|---|---|
| A | imports `:184` `BulkController`, `:189` `ImeProcess`, `:190` `ImeTarget`, `:191` `TakeoverWatch` | module-level bulk/ime imports | REMOVE from daemon.py (keep the modules themselves — they are lab references / S3's recorder-wiring scope) |
| B | `class _BulkTargetBundle` `:855-936` | the daemon-side bundle (`start/stop/acquire/active/cancel/apply…` over ImeProcess+ImeTarget+TakeoverWatch) | REMOVE (lab reference lives in voice_typing/ime/, not in the daemon) |
| C | `def _build_default_bulk_target` `:937-~960` | default bundle factory (ImeProcess spawn on start) | REMOVE from daemon.py (pinned by `test_default_bulk_target_factory_stays_pure` `test_daemon.py:5794` → that test goes with it) |
| D | ctor kwarg `bulk_target_factory=` `:978` | the injection seam | REMOVE the parameter (its only callers are bulk tests) |
| E | ctor body `:1256-1278` | `_bulk_target_factory`, `_bulk_ctrl`, `_bulk_bundle`, `_bulk_gen`, `_bulk_epoch`, `_bulk_delivery_active`, `_bulk_seq*`, `_bulk_dropped_no_id`, `_bulk_stop_thread` | REMOVE |
| F | ctor `:1287-1289` | `feedback.set_delivery_mode(cfg.output.delivery)` | KEEP but harden: the value is now always `"stream-edit"`; keep the call (feedback's status surface stays) |
| G | module docstring `:88-139` | the bulk wiring prose | REWRITE (Mode A docstrings) |
| H | `cfg_to_kwargs` `:517-545` | `if cfg.output.delivery == "bulk-text": realtime_processing_pause override` | REMOVE the branch (dead) — see also `recorder_host.augment_kwargs_with_executor` which is S3's |
| I | `_arm` `:1970-1972` (gen/epoch bump), `:2020` `_bulk_begin_delivery()` | arm-time activation | REMOVE |
| J | `_disarm` `:2076-2080` (epoch bump + `_bulk_schedule_stop()`) | stop-time activation | REMOVE |
| K | `on_final` `:1729-1732` → `_bulk_handle_final` | final routing | REMOVE the intercept (the stream/Rev1 path below it is the product path) |
| L | `_on_partial` `:2139-2140` → `_bulk_handle_partial` | partial routing | REMOVE the intercept |
| M | methods `:2160-2565` | `_bulk_mode/_bulk_wired/_bulk_identity/_bulk_next_seq/_bulk_handle_final/_bulk_handle_partial/_bulk_begin_delivery/_bulk_schedule_stop/_on_bulk_stopped/_on_bulk_applied/_bulk_cancel` | REMOVE the whole block |
| N | `_refresh_context_prompt` `:2786-2790` | `if self._bulk_mode(): … source = self._bulk_ctrl.confirmed_visible()` | REMOVE the branch; the `elif _streaming_now()` / `else _rev1_committed` logic is the product path (KEEP) |
| O | `cancel()` `:2834-2835` | `if self._bulk_mode(): return self._bulk_cancel()` intercept | REMOVE (generic cancel = len(tail)−1 compensation stays) |
| P | `status_snapshot` | reads `_bulk_delivery_active`? (verify: the `:2787` ref is `_bulk_wired` in `_refresh_context_prompt`; status carries `delivery_mode/state/reason` via FEEDBACK, not daemon attrs) | Verify + keep the feedback-sourced fields |
| Q | `request_shutdown` `:3256-3261` | bulk stopper schedule+join | REMOVE |
| R | `_clear_context_prompt` docstring `:1923-1930` | mentions `_bulk_cancel` D4 | trim the mention |
| S | `_refresh_context_prompt` docstring `:2741-2760` | the bulk SOURCE prose | rewrite |

**KEEP (the contract's explicit preserves):** `_cmd_streaming`/`_session_streaming`/`_streaming_now` (per-arm streaming vs block — the "stream partial/final AND explicit block accepted-final-only" the contract names); `_stream` (StreamingOutput) + `_rev1_committed` block path; the context-prompt push (stream-edit source only); generic `cancel()` with its tail compensation; `SessionRecovery` + `feedback.record_final` + `voicectl session --copy`; ducking seams (`_duck_engage/_duck_release`, `ducker=`); lifecycle (`_arm/_disarm/request_shutdown/shutdown`, lazy load, idle unload, auto-stop); recorder identity relay (`session_gen`/`utterance_id` stamping in recorder_host — S3 owns its wiring).

## §3. The test-side quarantine (the contract's "quarantine or repoint, don't reintroduce")

- **Remove from product tests:** the whole-file bulk suites `tests/test_bulk_dispatch.py` (22), `tests/test_bulk_context_prompt.py` (11), `tests/test_bulk_stage_remediation.py` (14), `tests/test_g5_timing_lab.py` (24, G5 lab — `build_cfg` sets `delivery="bulk-text"`), and the bulk Layer-B block in `tests/test_session_recovery.py` (`:439+`, `_make_armed_bulk_daemon`, the 4 reds) + its `import test_bulk_dispatch as tbd`. **Mechanism:** move the three bulk-only files under a quarantine dir (e.g. `tests/lab/` or `tools/lab-tests/`) that pytest does NOT collect by default (add `norecursedirs`/`testpaths` in pyproject, or simply relocate out of `tests/`) with a README noting they are Rev-4 lab references, not product acceptance — OR delete them if the lab already lives in `tools/` (check `tools/im-lab/`). The contract: "lab references rather than reintroduce shipped routing".
- **test_daemon.py:** remove `_make_s2_bulk_daemon` (`:5757`), `_S2BulkFeedback`, `_join_vt_threads`, `_pump_clock` IF bulk-only (check usage), the `--- 1. pure construction ---` arm-worker test block (grep `vt-bulk-arm`/`_bulk_` in test_daemon.py), and `test_default_bulk_target_factory_stays_pure` (`:5794`). Keep `test_status_snapshot_reflects_live_delivery_surface` (`:2265`) ONLY if it asserts the feedback-sourced `delivery_mode=="stream-edit"`; otherwise repoint it. **Keep ALL generic stream/block/cancel/duck/lifecycle tests.**
- **test_session_recovery.py:** keep the 29 green generic tests; drop the bulk Layer-B block + the `tbd` import; the `_draft_keys` "bulk (gen, uid)" docstring in `session_recovery.py:105` is a harmless comment (leave or trim — not S2's product surface).
- **New migration assertion (supported entry point):** `tests/test_daemon.py` gains `test_daemon_has_no_bulk_surface` — asserts `not hasattr(VoiceTypingDaemon, "_bulk_mode")`, `"bulk_target_factory" not in inspect.signature(VoiceTypingDaemon.__init__).parameters`, `daemon._build_default_bulk_target` absent, and that `from_toml({"output":{"delivery":"bulk-text"}})` raises (S1's contract) — proving the daemon cannot be activated in bulk by any route.

## §4. Mode A docstrings (the contract's DOCS line)

Rewrite: module docstring (`daemon.py:88-139` bulk prose → "native routing will be a SEPARATE opt-in integration (§4.8.1), not a `output.delivery` backend"); `_arm`/`_disarm`/`on_final`/`_on_partial`/`cancel`/`status_snapshot`/`request_shutdown` docstrings that mention P1.M6 bulk wiring → describe the generic-only path; `_refresh_context_prompt` SOURCE paragraph → stream-edit/rev1 only. State in the module docstring: `output.delivery` has ONE value (`stream-edit`); bulk-text is rejected at config load (S1); native editor sessions are a future separate surface.

## §5. Hazards

- **Don't remove `feedback.set_delivery_mode`/`set_delivery_state`** — they're the feedback/status surface (`feedback.py:216`, `ctl.py:170-199` renders `delivery:`). With bulk gone they carry `stream-edit`/`inactive`; harmless and still consumed by `voicectl status`. Keep.
- **Don't remove `voice_typing/bulk_controller.py`, `voice_typing/ime/*`** — they are the lab implementation; S3 ("Remove bulk-only recorder wiring") owns recorder_host's `augment_kwargs_with_executor` split-executor; the daemon-side removal here does NOT delete the modules.
- **recorder_host relay stamping** (`session_gen`/`utterance_id`): KEEP — the contract says "preserve recorder identity".
- **`_disarm`'s `:1998` shared clear** ("warm re-arm and is now shared with _bulk_cancel's D4") — keep the clear, trim the comment.
- **test_daemon.py's `hermetic_cfg` import** — keep; it's the media-isolation seam from the prior bugfix.
- **AGENTS.md:** two timeouts; `.venv/bin/python -m pytest`; test_daemon.py is CPU-only (267 tests, <90 s) — safe to run; never the daemon/CUDA suites.

## §6. Downstream

- **P1.M1.T1.S3** ("Remove bulk-only recorder wiring from product"): owns `recorder_host.augment_kwargs_with_executor`'s split executor + `cfg_to_kwargs`'s bulk `realtime_processing_pause` if any remains — S2 removes the DAEMON-side routing; S3 the recorder-side. Coordinate: S2 may remove the daemon's `cfg_to_kwargs` dead branch (it's daemon.py) but must not touch recorder_host.py.
- **P1.M1.T2.S3** ("Gate warm and cold capture on current priming") + T4 (native finals): consume the generic-only `_arm`/`on_final`/`_on_partial`/`cancel`/`request_shutdown` path S2 leaves behind.
