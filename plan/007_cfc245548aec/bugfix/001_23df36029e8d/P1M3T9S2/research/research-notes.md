# Research — bugfix plan P1.M3.T9.S2 (tests/ACCEPTANCE.md rows 4/11/12 evidence refresh)

Repo @ 22d105a (all 8 bugfixes + README sweep landed; M1/M2 + T9.S1 Complete).

## Current state of the three rows (tests/ACCEPTANCE.md, `## Criteria` table ~L27+)

Each row is ONE physical (very long) line in the pipe table. Columns: `# | Criterion (PRD §7) | Status | Evidence`.

- **Row 4** (criterion: only daemon output reaches target; nothing typed while toggled off) —
  ALREADY refreshed inline with the BUG-004 fix commit `fe30155`: evidence now says the partial
  gate is `_on_partial`'s first line, pinned by `test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing`
  (mocked LIVE, tests/test_daemon.py). Architecture doc (`architecture/config_tests_docs.md:23`)
  prescribed exactly this: "Mode A update with the fix, then Mode B re-verify" → S2 = the re-verify.
- **Row 11** (streaming §4.2quater: T8a cadence, T8b commit revise, T8c casing, T8e cancel,
  T8g stranded freeze, streaming=false hatch) — NOT touched by any bugfix commit. Still cites only
  the pre-bugfix evidence: tests/test_streaming.py real-model a/b/c/e/g + two hatch tests.
  Missing: citations of the new BUG-001/002/003/008 regression tests.
- **Row 12** (cancel fallback: socket rewind, evdev-unavailable, listener warning once) — NOT
  touched. Missing: BUG-002 re-say-streams-live evidence on the cancel path + BUG-007
  cancel-then-stop immediate disarm evidence.

## Verified evidence commands (run this session, all green)

- `timeout 300 uv run pytest tests/test_streaming_core.py tests/test_streaming_freeze.py tests/test_streaming_commit.py -q`
  → **77 passed** (0.03 s, no CUDA).
- `timeout 300 uv run pytest tests/test_daemon.py -q -k "rejected_final_recovers or cancel_then_next_utterance or stop_after_cancel or on_partial_gated or user_keypress_frozen or cancel_suppression_drops or next_utterance_after_cancel"`
  → **7 passed**, 220 deselected.
- `timeout 300 uv run pytest tests/test_daemon.py -q --collect-only` → **227 tests** (fast/mocked).

## Test-name inventory for citations (verified names + current line numbers)

tests/test_daemon.py (mocked, fast):
- `test_on_partial_gated_on_listening_stale_partial_after_stop_types_nothing` :5043 — BUG-004 (row 4)
- `test_on_final_streaming_rejected_final_freezes_tail_and_keeps_bookkeeping` :4763 — BUG-001
- `test_rejected_final_recovers_at_next_speech_with_cue` :4799 — BUG-001 (recovery + WARNING cue)
- `test_cancel_suppression_drops_racing_final_and_clears_on_sentinel` :4526 — BUG-002/007
- `test_cancel_then_next_utterance_streams_live_daemon_level` :4579 — BUG-002 (daemon-level, no manual reset_boundary)
- `test_next_utterance_after_cancel_rearms_final_pending` :4692 — BUG-007
- `test_stop_after_cancel_disarms_immediately` :4644 — BUG-007
- `test_on_final_user_keypress_frozen_commit_absorbs_then_unfreezes` :4947 — BUG-003
- `test_on_final_streaming_false_is_verbatim_rev1_hatch` :4747 — hatch (row 11 currently cites **:4510 — STALE**)

tests/test_streaming_freeze.py (engine, fast):
- `test_rejected_final_freeze_lives_until_resume_then_next_utterance_types` :278 — BUG-001
- `test_resume_cannot_lift_backend_failure_freeze` :308 — backend-failure freeze stays session-class
- `test_resume_clears_post_cancel_suppression` :345 — BUG-002
- `test_cancel_then_resume_restores_live_delta_typing` :360 — BUG-002
- `test_session_frozen_tail_late_commit_absorbs_plus_separator_and_stays_frozen` :231 — BUG-003 (separator = trailing space)
- `test_note_user_keypress_frozen_commit_absorbs_then_boundary_lifts_and_next_types` :197 — BUG-003

tests/test_streaming_core.py (engine, fast):
- `test_mid_sentence_capitalized_partials_extend_case_insensitively` :155 — BUG-008
- `test_capitalized_partial_equal_length_case_only_diff_is_noop` :172 — BUG-008
- `test_frozen_suppresses_typing_but_keeps_tail_mirror` :296 · `test_suppressed_after_cancel_mirrors_only_until_boundary` :316

tests/test_streaming_commit.py (engine, fast):
- `test_commit_extend_matches_case_insensitively` :128 — BUG-008
- `test_commit_disabled_is_a_noop` :329 — hatch (row 11 cites **:307 — STALE**)

tests/test_control_socket.py: `test_dispatch_cancel_routes_to_daemon_cancel_and_returns_shape` :326
(row 12 cites **:278 — STALE**) · `test_dispatch_empty_line` :183, `test_round_trip_empty_line_gets_error_reply` :226 (BUG-005, not in rows 4/11/12 scope).

tests/test_key_listener.py: `test_zero_keyboard_warning_fires_once_at_first_arm` :459 (still accurate).

tests/test_streaming.py (CUDA-gated real-model, 7 tests): test_a_delta_cadence :1086,
test_b_commit_rewind_exact :1148, test_c_pause_join :1176, test_d_decode_prompts :1270,
test_e_cancel :1372, **test_f_user_key_freeze :1497** (uncited in row 11; directly relevant to
BUG-003's user-keypress freeze), test_g_stranded_tail :1607. Row 11's "7/7 green" claim was
captured BEFORE the bugfix commits changed voice_typing/streaming.py + daemon.py — re-run to
re-certify, or keep with the bugfix delta pinned by the 77 fast engine tests.

## Code pins for claim verification (from T9.S1 notes, spot-checked)

- Commit gate: `on_final`'s first line gates on `is_listening()` (voice_typing/daemon.py ~:1121).
- Partial gate: `_on_partial`'s first line gates on `is_listening()` (voice_typing/daemon.py ~:1376).
- resume hook: `grep -n "_stream.resume()" voice_typing/daemon.py` → :1396-1404 (`_touch_speech`).
- Rejected-final WARNING cue: daemon.py :1181-1183; hypr toast "filtered hallucination — not
  typed; keep dictating" :1185-1186.
- Bugfix commits: 03f9602 (resume seam) · 60356cc (rejected-final recovery) · e6cf128 (resume
  lifts post-cancel suppression) · 8dc1534 (daemon regression) · aae7060 (frozen-commit space) ·
  fe30155 (partial gate + row-4 edit) · c22df05 (empty-line reply) · bcf7205 (unknown tables) ·
  c9f2c8b (cancel sentinel finalization) · eac2d03 (case-insensitive extends) · 22d105a (README sweep).

## Contract constraints

- Mode B changeset-level docs sync: edit ONLY tests/ACCEPTANCE.md (README was sibling S1 — done).
- Criterion column (PRD §7 text) stays VERBATIM; only Status/Evidence cells change.
- Keep the doc's evidence-type tagging convention (LIVE / STATIC / PAST-LIVE).
- AGENTS.md: every pytest under GNU `timeout` + bash-tool timeout; never run the daemon in the
  foreground; don't run the 5–8 min E2E shell scripts for a docs task.
- FORBIDDEN to this implementer: PRD.md, tasks.json, prd_snapshot.md, source code.
