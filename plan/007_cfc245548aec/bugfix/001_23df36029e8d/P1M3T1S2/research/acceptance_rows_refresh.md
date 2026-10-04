# Research — P1.M3.T9.S2: refresh ACCEPTANCE.md rows 4/11/12 evidence

Mode B docs task. Ground truth verified live 2025-10-03. Facts:

## 1. Row locations + current state

- Row 4 `:35` — "nothing typed while toggled off". Evidence ALREADY cites the new gate test (P1.M1.T4.S1's
  Mode-A edit landed it): `test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing`
  (`tests/test_daemon.py:4972`). What row 4 still LACKS: the typed-output-correctness citation for the
  frozen-commit separator fix — `test_commit_frozen_absorbs_tail_and_types_separator`
  (`tests/test_streaming_commit.py:245`) proves commits stay space-separated (BUG-003), which is exactly
  "only the daemon's typed output reaches the target" correctness.
- Row 11 `:42` — streaming criteria (T8a/b/c/e/g + rollback hatch). Current evidence cites only the
  CUDA-gated `tests/test_streaming.py` 7/7 + hatch tests. LACKS the new fast daemon-level sequencing
  regression tests: `test_rejected_final_recovers_at_next_speech_with_cue` (`tests/test_daemon.py:4730`)
  and `test_cancel_then_next_utterance_streams_live_daemon_level` (`tests/test_daemon.py:4579`).
- Row 12 `:43` — cancel fallback (socket rewind, listener-failure-once). LACKS the same
  cancel-to-live-typing citation (the re-said sentence after socket cancel streams live = the T8e
  contract's continuation).

## 2. Verified-passing tests to cite (targeted run: 4 passed in 0.04s)

| Test | File:line | Bug/task | Row |
|---|---|---|---|
| `test_rejected_final_recovers_at_next_speech_with_cue` | test_daemon.py:4730 | BUG-001 / P1.M1.T1.S2 | 11 |
| `test_cancel_then_next_utterance_streams_live_daemon_level` | test_daemon.py:4579 | BUG-002 / P1.M1.T2.S2 | 11, 12 |
| `test_commit_frozen_absorbs_tail_and_types_separator` | test_streaming_commit.py:245 | BUG-003 / P1.M1.T3.S1 | 4 |
| `test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing` | test_daemon.py:4972 | BUG-004 / P1.M1.T4.S1 | 4 (already cited) |

## 3. M2 minors status (cite only if landed at implementation time)

- BUG-005 empty-line (P1.M2.T5.S1, Implementing): tests EXIST — `test_round_trip_empty_line_gets_error_reply`
  (test_control_socket.py:226), `test_dispatch_empty_line` (:183). NOT row 4/11/12 material (socket row);
  only mention if the implementer judges row-adjacent — default: leave to those rows' own evidence.
- BUG-006 unknown-table (P1.M2.T6.S1, Planned): test does NOT exist. NO row 4/11/12 claim depends on it. Skip.
- BUG-007 stop-after-cancel (P1.M2.T7.S1, Planned): test does NOT exist (only
  `test_on_final_clears_final_pending` :828 etc., pre-existing). Row 12 makes no stop-latency claim — skip.

## 4. Why the refresh matters (PRD Overview)

"The unit suites pass because they drive engine methods directly and even manually invoke
reset_boundary(), masking the daemon-level sequencing bugs." The old row-11 evidence (CUDA-gated
test_streaming.py only) had the same blind spot at the matrix level. The new daemon-level tests are the
ones that pin the fixed sequencing — rows 11/12 must cite them or the matrix again overstates coverage.

## 5. Edit mechanics

- Each row is ONE markdown table line (:35/:42/:43). Extend the Evidence cell text (keep Status PASS —
  every cited test passes). Anchor on unique quoted substrings (row text is unique; line numbers drift).
- KEEP all existing citations (CUDA-gated suite, hatch tests, E2E/STATIC refs) — the refresh ADDS the
  new fast-suite citations; it does not replace the real-model evidence.
- GATE: before writing each citation, re-run the test (`.venv/bin/python -m pytest <nodeid> -q`) —
  "do not invent evidence". Verify acceptance diff scope: only tests/ACCEPTANCE.md.
- Disjoint from S1 (README.md only) and every M2 task (code/config files).
