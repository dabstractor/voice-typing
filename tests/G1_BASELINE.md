# G1 regression baseline (PRD §4.2sexies R.7)

Code-state **`2335a9e`** at HEAD **`d78ff95`** (plan-docs-only on top; `git diff 2335a9e --stat
-- voice_typing/ tests/ config.toml` EMPTY before the runs). Recorded **2026-11-23**.
Methodology (parity with the research record): `timeout 300 /home/dustin/.local/bin/uv run
pytest <file> -q --tb=line`, **one file per call**, bash-tool timeout ≥ 360. No daemon, no
voicectl, no E2E scripts, no CUDA suites. The 5 non-G1 files (`test_feed_audio`,
`test_daemon`, `test_recorder_host`, `test_cuda_check` — contract-forbidden hang vectors —
and `test_systemd_unit`, not in the G1 set) were NOT run.

## Results (15 suites)

| # | File | Passed | Failed | Runtime |
|---|------|-------:|-------:|---------|
| 1 | tests/test_streaming_commit.py | 22 | **10** | 0.02 s |
| 2 | tests/test_streaming_core.py | 32 | **2** | 0.02 s |
| 3 | tests/test_streaming_freeze.py | 22 | **4** | 0.02 s |
| 4 | tests/test_streaming.py | **4** | **3** | 106.65 s (real small.en on wav fixtures) |
| 5 | tests/test_zero_diff_rewind.py | 3 | 0 | 0.01 s |
| 6 | tests/test_key_listener.py | 32 | 0 | 0.04 s |
| 7 | tests/test_control_socket.py | 27 | 0 | 3.39 s |
| 8 | tests/test_config.py | 54 | 0 | 0.03 s |
| 9 | tests/test_config_repo_default.py | 3 | 0 | 0.02 s |
| 10 | tests/test_textproc.py | 31 | 0 | 0.02 s |
| 11 | tests/test_typing_backends.py | 36 | 0 | 0.82 s |
| 12 | tests/test_voicectl.py | 36 | 0 | 2.54 s |
| 13 | tests/test_feedback.py | 38 | 0 | 0.05 s |
| 14 | tests/test_prompt_engine.py | 28 | 0 | 0.13 s |
| 15 | tests/test_context_prompt_refresh.py | 12 | 0 | 0.03 s |
| | **Total (this run)** | **380** | **19** | |
| | Total (research record, Part A) | 379 | 20 | |

## Drift vs research record

The research record (`plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md` Part A)
measured **379P / 20F** at the same code state. This re-run measured **380P / 19F**. The
entire delta is ONE test:

- `tests/test_streaming.py::test_g_stranded_tail` — **FAILED in the record, PASSED here**
  (record's expectation: absorbed committed `'…Keep sleeping  '` with two trailing spaces vs
  expected one). Every other suite reproduced its recorded counts and failure names exactly.

Investigation notes (record-only; no code/test/fixture was touched):

- `tests/test_streaming.py` is the real-model harness (small.en decoding wav fixtures) — the
  only nondeterministic file in the set. The research record itself flags it: for its reds
  #19/#20, "either a late regression from the post-T8 commits … or a real-model flake on a
  loaded machine. G1 must treat 3P/4F as the pre-change number and re-run this file
  before/after any D3 change to disambiguate." A single re-run flipping one of its four reds
  to green is consistent with exactly that flake class (decode/cadence timing on a loaded
  machine), not with moved code — the preflight diff over `voice_typing/ tests/ config.toml`
  vs `2335a9e` is empty.
- The file's other three reds (`test_a_delta_cadence`, `test_b_commit_rewind_exact`,
  `test_f_user_key_freeze`) reproduced in this run with reasons matching the record.
- **Standing rule for later subtasks:** treat the record's 3P/4F as the conservative
  pre-change number for this file and re-run it before/after any change, per the record's own
  instruction; do not count `test_g_stranded_tail` as fixed by anything in this plan until a
  deterministic cause is shown (S2 owns classification).

## Failure inventory (names + one-line reasons; classification = S2's deliverable)

Legend: **(i)** = legacy lazy-separator contract red per the record (tests encode the eager
separator contract; HEAD since `26d570b` defers it). **(ii)** = new/unclassified. One-liners
from the record's A.1; fresh `--tb=line` output agreed with all of them.

tests/test_streaming_commit.py (10, all reproduce here):

1. `test_commit_extend_applies_casing_guard_to_the_delta` (:116) — typed delta
   `['then he said', ' stop ']` carries the trailing space; expected `' stop'` (separator
   deferred to its own later event). (i)
2. `test_commit_empty_delta_types_only_the_space` (:125) — actual `[('type','hello world')]`
   missing the trailing space; expected `[('type','hello world ')]`. (i)
3. `test_commit_shorter_final_backspaces_only_the_extra` (:209) — expected sequence ends with
   `('type', ' ')`; actual never types the separator op. (i)
4. `test_commit_advances_checkpoint_next_partial_diffs_against_empty_tail` (:226) — typed
   chunks differ in trailing-space placement (`' world '` vs `' world'`). (i)
5. `test_commit_checkpoint_guard_context_is_screen_truth` (:241) — expected separator as a
   separate `' '` item between chunks; actual glues it onto a typed chunk. (i)
6. `test_commit_extend_strips_spurious_mid_sentence_period` (:252) — expected
   `['Done', ' ', 'next']`; actual `['Done', ' next']` (separator folded into delta). (i)
7. `test_commit_frozen_absorbs_tail_and_types_separator` (:288) — frozen commit must type the
   separator; actual `[('type','hello wor')]` lacks the trailing space. (i)
8. `test_commit_space_type_failure_keeps_checkpoint_at_boundary` (:342) — `frozen` set but
   `frozen_session` not promoted on separator-type failure (fail-safe promote path reacts to
   a separator keystroke that never happened). (i)
9. `test_reset_session_clears_everything_including_frozen` (:374) — separator placement in
   typed sequence (`['Hello',' world ','Next']` vs expected separator as own item). (i)
10. `test_frozen_commit_space_type_failure_absorbs_nothing` (:491) — `frozen_session` not
    True after separator-type failure under freeze (same fail-safe family as #8). (i)

tests/test_streaming_core.py (2, both reproduce here):

11. `test_mid_sentence_capitalized_partials_extend_case_insensitively` (:170) — first chunk
    `'and then he said '` (space glued); expected `"and then he said"` + separate `" "`. (i)
12. `test_no_separator_after_clean_commit` (:538) — after commit + 2× `reset_session`, actual
    `('type',' next sentence')` (leading space + lowercase) vs expected
    `('type','Next sentence')` — lazy separator's "clean commit already spaced" state not
    recognized across the session reset → double separator + guard lowercases. (i)

tests/test_streaming_freeze.py (4, all reproduce here):

13. `test_note_user_keypress_frozen_commit_absorbs_then_boundary_lifts_and_next_types` (:210)
    — a frozen commit must absorb (no revision keystrokes) but still type the separator;
    separator not typed. (i)
14. `test_session_frozen_tail_late_commit_absorbs_plus_separator_and_stays_frozen` (:243) —
    `('type','hello wor')` vs expected `('type','hello wor ')`. (i)
15. `test_rejected_final_freeze_lives_until_resume_then_next_utterance_types` (:314) —
    "the next commit must produce real backend calls": post-resume commit is an empty-delta
    commit, and with the separator deferred it produces zero keystrokes. (i)
16. `test_cancel_then_resume_restores_live_delta_typing` (:389) — expected commit's
    inter-final space typed eagerly `[('type','Hello world '), …]`; actual has no trailing
    space. (i)

tests/test_streaming.py (3 reproduced here + 1 flake-drift, see Drift above):

17. `test_f_user_key_freeze` (:1627) — "between the keypress and the commit the engine must
    send ONLY the append_space separator, got `[]`" — the separator is deferred, not sent.
    (i) — reproduced here.
18. `test_g_stranded_tail` (:1795) — absorbed committed `'…Keep sleeping  '` (two trailing
    spaces) vs expected one. (i) — **DID NOT reproduce this run (passed); see Drift.**
19. `test_a_delta_cadence` (:1202) — "no delta-only extend cycle observed (every cycle
    rewound?)". **(ii) — NOT separator-shaped** (extend-vs-rewind cadence property) —
    reproduced here.
20. `test_b_commit_rewind_exact` (:1236) — "no revising commit (a commit that rewound a
    non-empty tail) across 4 commits". **(ii) — NOT separator-shaped** (rewind property) —
    reproduced here.

---

Classification of these reds (legacy lazy-separator contract vs new) = **P1.M1.T1.S2**.
Every later subtask diffs its post-change suite results against THIS file; drift from these
numbers is a finding to investigate, never to "fix" silently.
