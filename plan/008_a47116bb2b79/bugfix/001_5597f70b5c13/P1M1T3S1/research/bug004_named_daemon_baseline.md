# Research: BUG-004 — named 20-case daemon baseline (FRESH CAPTURE, 2026-11-23)

**Status:** Fresh bounded hermetic run executed at the post-T1.S1/S2 tree (commits 74252cd + 0749bdb
landed; T1.S3 in flight). Read-only — no repo mutation. Load-bearing evidence for `P1M1T3.S1/PRP.md`.

## 1. FRESH CAPTURE (the canonical current list — names, never counts)

```
timeout 500 .venv/bin/python -m pytest tests/test_daemon.py -q --tb=no
→ 20 failed, 218 passed in 15.43s        (CPU-only; no CUDA, no model load, no hang)
```

The 20 named node IDs (verbatim):
1. `test_cfg_to_kwargs_cuda_path`
2. `test_cfg_to_kwargs_calls_resolve_with_cfg_defaults`
3. `test_on_final_happy_path_appends_space`
4. `test_on_final_typing_raises_is_caught_and_record_still_happens`
5. `test_on_final_clears_final_pending`
6. `test_stop_within_session_stray_partial_after_final_disarms_immediately`
7. `test_on_final_lock_held_across_type_text`
8. `test_on_final_serializes_two_concurrent_callbacks`
9. `test_on_final_emits_structured_latency_line`
10. `test_resolved_device_unaffected_by_cuda_check_failure`
11. `test_status_device_reseeded_not_stale_after_child_death`
12. `test_status_device_reseeded_not_stale_after_idle_unload`
13. `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel`
14. `test_on_final_streaming_commit_types_via_engine`
15. `test_on_final_streaming_revise_minimal_diff`
16. `test_on_final_streaming_pushes_context_prompt_to_host`
17. `test_refresh_context_prompt_missing_host_seam_is_silent_noop`
18. `test_on_final_user_keypress_frozen_commit_absorbs_then_unfreezes`
19. `test_lost_sentinel_self_heals_after_timeout`
20. `test_sentinel_consume_clears_suppress_since`

**Facet samples (--tb=line):** #3 `:748 assert ['hello world '] == ['hello world', ' ']`;
#19 `:5226 assert ['fresh sentence '] == ['fresh sentence', ' ']` — classic lazy-separator (the
eager-separator contract: separator as its OWN type op vs HEAD gluing it). **But NOT all are
separator facets:** #1 `:178 assert 'float16' == 'float32'` (compute_type expectation) and #11
`:4296 assert ('cuda' == 'cuda' …` (multi-field status/reseed comparison) are different facets —
the addendum must carry each case's ACTUAL one-liner, not a blanket label. (Classification itself
remains S2/owner-of-record territory; the addendum records reasons, not verdicts.)

## 2. PROVENANCE — supplied vs fresh (report drift; never infer from counts)

| source | code state | result | provenance |
|---|---|---|---|
| SUPPLIED comparison (audit, PRD h3.3) | base `2335a9e` | 211P / 21F | historical; DO NOT re-run (contract forbids the unisolated base worktree) |
| SUPPLIED comparison (audit, PRD h3.3) | HEAD `573d78f` | 217P / 20F | historical; HEAD set = strict subset of base set (fixed `test_status_snapshot_keys_and_cuda_values`, zero introduced) |
| FRESH (this research, 2026-11-23) | post-T1.S1/S2 | **218P / 20F** | current tree; the +1 passer vs 573d78f is T1 hermeticity test growth, NOT a failure identity change |

Checks consistent with the supplied claims: `test_status_snapshot_keys_and_cuda_values` is ABSENT
from the fresh failure list (fixed, as supplied). The fresh 20 names are the canonical set the
addendum records; the implementer re-captures and diffs for SET IDENTITY (pass-count drift from
T1.S3 landing more passing tests is expected and harmless; a failure-NAME change is drift to report).

## 3. The two doc edit sites (verbatim current text)

**tests/G1_BASELINE.md** (header, the exclusion to correct):
"The 5 non-G1 files (`test_feed_audio`, `test_daemon`, `test_recorder_host`, `test_cuda_check` —
contract-forbidden hang vectors — and `test_systemd_unit`, not in the G1 set) were NOT run."
→ The addendum reclassifies test_daemon.py as CPU-only (~16 s) and records its named 20; the
REAL hang vectors (test_feed_audio / test_recorder_host / test_cuda_check) stay; test_systemd_unit
is T2.S1's scope. PRESERVE: the 15-suite table, the historic totals (380P/19F run vs 379P/20F
record), the 16 fast lazy-separator reds inventory, the real-model watch rule (test_streaming.py
3P/4F — re-run before/after any change), the `test_g_stranded_tail` flake note.

**AGENTS.md:92** (the hang-vector row to correct):
"| `uv run pytest …` / `.venv/bin/pytest …` | Several suites (`test_feed_audio.py`, `test_daemon.py`,
`test_recorder_host.py`) load real CUDA models. Cold cuDNN/cuBLAS init + two model loads is minutes
on first run, and a regression can deadlock on the recorder/GIL. | `timeout 600 uv run pytest <file> -q` … |"
→ Remove `test_daemon.py` from the CUDA-model list (its header: "NO real RealtimeSTT / NO model
load / NO CUDA"; 5,409 lines; runs 15.4 s CPU-only). Add a SEPARATE bounded-CPU row (or note):
test_daemon.py is hermetic (post-T1: fake ASR/mic/IM/typing/media), runs ~16 s, still under the
two-timeout discipline (`timeout 500` inner, bash-tool ≥ 560). RETAIN the 600 s rule + CUDA-model
list for test_feed_audio/test_recorder_host/test_cuda_check, and Rule 1 (two timeouts) unchanged.

## 4. Future set-diff rule (the addendum's operative content)

Any sweep touching daemon code runs the file bounded and diffs the FAILED-name set against the
addendum's 20: **a name present now but not in the addendum = a NEW failure — investigate before
trusting the change; a name gone = fixed — update the addendum (dated).** Counts are never evidence
(passers grow with new tests). Consumers: P1.M2.T1.S1, P1.M2.T2.S3, P1.M2.T3.S2.

## 5. Scope

- Files edited: `tests/G1_BASELINE.md` (addendum + exclusion correction) + `AGENTS.md` (hang-vector
  row). NOTHING else. No skips/xfails, no test edits, no source, no base-worktree run, no E2E/live
  service. Parallel T2.S1 edits tests/test_systemd_unit.py — DISJOINT.
