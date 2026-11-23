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

---

## Failure classification vs the lazy-separator contract (P1.M1.T1.S2)

Method: the 16 fast reds were re-verified LIVE at S2 time (combined run of
`test_streaming_commit.py` + `test_streaming_core.py` + `test_streaming_freeze.py`:
**16 failed, 76 passed**; names match the inventory above byte-for-byte, including the
corrected #6 name `test_commit_extend_strips_spurious_mid_sentence_period`). Each (i) tag was
CONFIRMED by mapping its failing expectation onto a specific clause of the lazy-separator
contract (commit `26d570b`, "Carry a lazy separator across interrupted sessions") — not
transcribed from the record. Spot re-verified with fresh `--tb=line` this session: #8 (fail-safe
promote never fires: `assert False is True`), #12 (`('type', ' next sentence')` vs
`('type', 'Next sentence')` — leading separator + guard lowercase), #15 (`assert 3 > 3` — zero
backend calls from the post-resume empty-delta commit). The two (ii) tags were confirmed by
READING the test bodies (`test_streaming.py` — `test_a_delta_cadence` asserts `extends`
non-empty: "no delta-only extend cycle observed"; `test_b_commit_rewind_exact` asserts
`_has_revising_commit`: "a commit that rewound a non-empty tail", with a bounded same-session
retry) — pure cadence/liveness properties of the real-model harness; no separator/space facet
applies to either.

### Facet taxonomy (clauses of `26d570b`)

| Facet | Legacy (eager) expectation the test encodes vs HEAD (lazy) behavior |
|---|---|
| **F1 EAGER-SEP** | expects a standalone `('type', ' ')` op or a trailing space inside the typed delta at commit; HEAD glues the space into the NEXT payload (no lone-space keystroke) |
| **F2 EMPTY-DELTA-SEP** | an empty-delta commit still types the separator; HEAD defers it → zero keystrokes |
| **F3 SEP-FAILSAFE** | fail-safe promote on a FAILING separator keystroke; HEAD never emits that standalone op, so the fail-safe never reacts |
| **F4 RESET-DOUBLE-SEP** | "already spaced" state recognized across `reset_session`; HEAD re-separates (leading space) and the casing guard then lowercases |
| **F5 ABSORB-SPACING** | frozen/stranded absorb leaves exactly one trailing space; HEAD's lazy separator + absorb disagree (0 or 2) |

### The 20-row classification

| A.1# | Test (suite:line) | Class | Facet | Evidence (the eager expectation) |
|---|---|---|---|---|
| 1 | test_commit_extend_applies_casing_guard_to_the_delta (commit:116) | (i) | F1 | expected delta `' stop'`; actual carries `' stop '` (space rides in payload) |
| 2 | test_commit_empty_delta_types_only_the_space (commit:125) | (i) | F2 | expects `[('type','hello world ')]`; HEAD types `hello world`, defers the space |
| 3 | test_commit_shorter_final_backspaces_only_the_extra (commit:209) | (i) | F1 | expected sequence ends `('type',' ')`; never emitted standalone |
| 4 | test_commit_advances_checkpoint_next_partial_diffs_against_empty_tail (commit:226) | (i) | F1 | trailing-space placement diff (`' world '` vs `' world'`) |
| 5 | test_commit_checkpoint_guard_context_is_screen_truth (commit:241) | (i) | F1 | expects separator as a separate `' '` item between chunks |
| 6 | test_commit_extend_strips_spurious_mid_sentence_period (commit:252) | (i) | F1 | expected `['Done',' ','next']`; actual `['Done',' next']` |
| 7 | test_commit_frozen_absorbs_tail_and_types_separator (commit:288) | (i) | F1/F5 | frozen commit must type the separator; actual lacks it |
| 8 | test_commit_space_type_failure_keeps_checkpoint_at_boundary (commit:342) | (i) | F3 | fail-safe promote on separator-type failure (`frozen` set, `frozen_session` not) — re-verified live S2 |
| 9 | test_reset_session_clears_everything_including_frozen (commit:374) | (i) | F1 | separator placement across reset chunks |
| 10 | test_frozen_commit_space_type_failure_absorbs_nothing (commit:491) | (i) | F3 | same fail-safe family as #8 under freeze |
| 11 | test_mid_sentence_capitalized_partials_extend_case_insensitively (core:170) | (i) | F1 | expected `"and then he said"` + separate `" "`; actual glued |
| 12 | test_no_separator_after_clean_commit (core:538) | (i) | F4 | double separator across reset + guard lowercases — re-verified live S2 |
| 13 | test_note_user_keypress_frozen_commit_absorbs_then_boundary_lifts_and_next_types (freeze:210) | (i) | F1/F5 | frozen commit must still type the separator |
| 14 | test_session_frozen_tail_late_commit_absorbs_plus_separator_and_stays_frozen (freeze:243) | (i) | F1 | `('type','hello wor')` vs expected `'hello wor '` |
| 15 | test_rejected_final_freeze_lives_until_resume_then_next_utterance_types (freeze:314) | (i) | F2 | post-resume empty-delta commit → deferred separator → zero keystrokes — re-verified live S2 |
| 16 | test_cancel_then_resume_restores_live_delta_typing (freeze:389) | (i) | F1 | expects inter-final space typed eagerly |
| 17 | test_f_user_key_freeze (streaming:1569) | (i) | F1 | "must send ONLY the append_space separator, got `[]`" (deferred) |
| 18 | test_g_stranded_tail (streaming:1679) | (i) | F5 | absorbed `'…Keep sleeping  '` (two trailing spaces) vs one — FLAKY-CLASS, see watch-set note |
| 19 | test_a_delta_cadence (streaming:1157) | **(ii)** | — | "no delta-only extend cycle observed (every cycle rewound?)" — extend-vs-rewind CADENCE property; nothing about space placement |
| 20 | test_b_commit_rewind_exact (streaming:1219) | **(ii)** | — | "no revising commit (a commit that rewound a non-empty tail)" — rewind-existence property; not separator-shaped |

Note: the inventory's suite:line refs are the research-record citations; the live
`test_streaming.py` defs currently sit at :1157 (a), :1219 (b), :1569 (f), :1679 (g) — same
tests, drifted line numbers.

### Watch set + re-run protocol

Watch set = the two (ii) candidates: `test_a_delta_cadence` and `test_b_commit_rewind_exact`.
Candidate causes for their reds: (a) a late regression from the post-T8 commits (`cf2dfb1`
debounce, `0e7dd05` clamped rewinds, `26d570b` lazy separator, `e5409a1` pacing); (b) real-model
flake on a loaded machine; (c) the lazy separator legitimately changing the properties'
frequency (an exact-confirm commit now rewinds nothing AND types nothing, so "revising commit"
becomes rarer; delta-only extends may be suppressed likewise). Only the protocol below can tell
these apart — never a guess.

Pre-change flake baseline (3 sequential runs of `tests/test_streaming.py` at the S2 code state,
`timeout 300 uv run pytest tests/test_streaming.py -q --tb=no`, real small.en; identical
outcomes all 3 runs, ~106 s each):

| Test | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| test_a_delta_cadence | FAIL | FAIL | FAIL |
| test_b_commit_rewind_exact | FAIL | FAIL | FAIL |
| test_c_pause_join | pass | pass | pass |
| test_d_decode_prompts | pass | pass | pass |
| test_e_cancel | pass | pass | pass |
| test_f_user_key_freeze | FAIL | FAIL | FAIL |
| test_g_stranded_tail | FAIL | FAIL | FAIL |

Totals per run: **3 passed / 4 failed** — matching the research record's 3P/4F.

Interpretation:
- `test_a_delta_cadence` + `test_b_commit_rewind_exact`: red in ALL 3 runs → **STABLE red,
  regression-shaped** (not flake-on-this-machine). They are classified (ii) and stay on the
  watch set: a later D3 change that turns them green is a FINDING to investigate, not noise.
- `test_f_user_key_freeze`: red in all 3 runs → stable (i), consistent with its F1 facet.
- `test_g_stranded_tail`: red in all 3 S2 runs, but PASSED in S1's single baseline run →
  **FLAKY** across the recorded population (record FAIL, S1 PASS, S2 F/F/F — 4F/1P over 5
  observations). Its F5 classification stands; do not count it as fixed or broken from any
  single observation.

PER-CHANGE PROTOCOL (for P1.M1.T2/T3/T4 and any streaming/daemon-touching change):
1. BEFORE and AFTER each change: one run of `tests/test_streaming.py`
   (`timeout 300 /home/dustin/.local/bin/uv run pytest tests/test_streaming.py -q --tb=no`)
   plus the 3 fast red suites combined
   (`timeout 120 /home/dustin/.local/bin/uv run pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q --tb=no`).
2. Decision rules:
   - A watch test red in ALL post-change runs AND green in the pre-change runs → **REGRESSION**
     (investigate that change; do not proceed until explained).
   - red↔green flips with NO code change in between → **FLAKE** (record the observation here as
     an addendum row; do not chase it).
   - The 16 fast (i) reds must remain **EXACTLY this set** (same names, same suites) after every
     change — ANY growth or shrinkage is a finding to investigate, even when it looks like an
     improvement.
3. Record every post-change run's totals + FAILED names as an addendum in this file (bounded:
   one row per run, no transcripts).

### Contract statement

**NO blanket skips; NO legacy behavior edits to fake parity** (§4.2sexies R.7 G1). No
`pytest.mark.skip`/`xfail` may be added for the (i) reds, and no test expectation may be edited
to make them pass. The (i) reds STAY RED: reconciling them with the lazy-separator contract is
a deliberate, separately-decided change — it must never happen as a side effect of an unrelated
task. The (i) set above is the invariant later subtasks diff against.
