# Research Note: G1 red classification vs the lazy-separator contract (P1.M1.T1.S2)

**Status:** EMPIRICALLY VERIFIED against the live repo (HEAD d78ff95 == code-state 2335a9e) + commit 26d570b + `plan/008_a47116bb2b79/architecture/d3_defects_g1_baseline.md` (the research record).

## §1. The lazy-separator contract at HEAD (what the (i) reds encode EAGERLY)

Commit **26d570b** "Carry a lazy separator across interrupted sessions" (2026-10-28, streaming.py +200/−88) established:
- **No standalone space keystrokes**: "Commit paths also stop emitting standalone space keystrokes: a lone space is its own short spawn that some apps silently drop … the space now rides inside the next payload." Implemented as the `_lead_sep` flag (streaming.py:277 "True while tail[0] is a SYNTHESIZED separator", set :664, carried lazily :796/:819, kept through rewinds :683/:803/:824).
- **Pending separator at non-commit exits** (immediate stop, keypress disarm, cancel, frozen commit) discharged on the first following fragment — partial or final-on-empty-tail; a session that simply ends leaves no stray space.
- **Screen vs decoder split**: recognized text never carries the space (prefix/minimal-diff compare against the stripped tail); keystroke accounting still counts it.
- **Disarm folds on-screen words into settled text**; a clean commit already carries the separator state.
- Tests were UPDATED in 26d570b (commit suites "now expect the separator glued into the payload") — the 16 fast reds are expectations that did NOT get that update or encode consequences of the deferral.

**Observable facets** (the classification taxonomy — every (i) red maps to one):
| Facet | Legacy (eager) expectation vs HEAD (lazy) behavior |
|---|---|
| **F1 EAGER-SEP** | expects a standalone `('type',' ')` op / trailing space inside the typed delta at commit; HEAD glues it into the NEXT payload |
| **F2 EMPTY-DELTA-SEP** | an empty-delta commit still types the separator; HEAD defers → zero keystrokes |
| **F3 SEP-FAILSAFE** | fail-safe promote on a FAILING separator keystroke; HEAD never emits that standalone op (the fail-safe reacts to a keystroke that never happened) |
| **F4 RESET-DOUBLE-SEP** | across reset_session the "already spaced" state is recognized; HEAD double-separates + the guard lowercases |
| **F5 ABSORB-SPACING** | frozen/stranded absorb leaves exactly one trailing space; HEAD's lazy separator + absorb disagree (0 or 2) |

## §2. The 20 reds — live re-verified classification (16 fast re-run TODAY + 4 real-model from the record)

**Fast reds reproduce EXACTLY** (re-run: `16 failed, 76 passed in 0.05s`; names match A.1 items 1–16 byte-for-byte, incl. the corrected name `test_commit_extend_strips_spurious_mid_sentence_period`):

| A.1# | Test (suite) | Facet | Evidence (the eager expectation) |
|---|---|---|---|
| 1 | test_commit_extend_applies_casing_guard_to_the_delta (commit:116) | F1 | expected delta `' stop'`; actual carries `' stop '` (space rides in payload) |
| 2 | test_commit_empty_delta_types_only_the_space (commit:125) | F2 | expects `[('type','hello world ')]`; HEAD types `hello world`, defers the space |
| 3 | test_commit_shorter_final_backspaces_only_the_extra (commit:209) | F1 | expected seq ends `('type',' ')`; never emitted standalone |
| 4 | test_commit_advances_checkpoint_next_partial_diffs_against_empty_tail (commit:226) | F1 | trailing-space placement diff (`' world '` vs `' world'`) |
| 5 | test_commit_checkpoint_guard_context_is_screen_truth (commit:241) | F1 | expects separator as separate `' '` item between chunks |
| 6 | test_commit_extend_strips_spurious_mid_sentence_period (commit:252) | F1 | expected `['Done',' ','next']`; actual `['Done',' next']` |
| 7 | test_commit_frozen_absorbs_tail_and_types_separator (commit:288) | F1/F5 | frozen commit must type separator; actual lacks it |
| 8 | test_commit_space_type_failure_keeps_checkpoint_at_boundary (commit:342) | F3 | fail-safe promotes on separator-type failure (`frozen` set, `frozen_session` not) |
| 9 | test_reset_session_clears_everything_including_frozen (commit:374) | F1 | separator placement across reset chunks |
| 10 | test_frozen_commit_space_type_failure_absorbs_nothing (commit:491) | F3 | same fail-safe family as #8 under freeze |
| 11 | test_mid_sentence_capitalized_partials_extend_case_insensitively (core:170) | F1 | expected `"and then he said"` + separate `" "`; actual glued |
| 12 | test_no_separator_after_clean_commit (core:538) | F4 | double separator across reset + guard lowercases |
| 13 | test_note_user_keypress_frozen_commit_absorbs_then_boundary_lifts_and_next_types (freeze:210) | F1/F5 | frozen commit must still type the separator |
| 14 | test_session_frozen_tail_late_commit_absorbs_plus_separator_and_stays_frozen (freeze:243) | F1 | `('type','hello wor')` vs expected `'hello wor '` |
| 15 | test_rejected_final_freeze_lives_until_resume_then_next_utterance_types (freeze:314) | F2 | post-resume commit is empty-delta → deferred separator → ZERO keystrokes |
| 16 | test_cancel_then_resume_restores_live_delta_typing (freeze:389) | F1 | expects inter-final space typed eagerly |
| 17 | test_f_user_key_freeze (streaming:1627) | F1 | "must send ONLY the append_space separator, got `[]`" (deferred) |
| 18 | test_g_stranded_tail (streaming:1795) | F5 | absorbed `'…Keep sleeping  '` (two trailing spaces) vs one |
| **19** | **test_a_delta_cadence (streaming:1202)** | — **(ii)** | "no delta-only extend cycle observed (every cycle rewound?)" — an extend-vs-rewind CADENCE property; nothing about space placement |
| **20** | **test_b_commit_rewind_exact (streaming:1236)** | — **(ii)** | "no revising commit (a commit that rewound a non-empty tail) across 4 commits" — a rewind-existence property; not separator-shaped |

All 18 (i) tags from the research record are CONFIRMED by facet mapping (each eager expectation is directly explained by 26d570b's contract). #19/#20 assert harness-level properties over a REAL small.en run — no separator facet applies.

## §3. The (ii) candidates — why they might be red (regression vs flake)

Read at test_streaming.py:1202/:1236 — both assert POSITIVE liveness properties of the real-model harness:
- **#19** requires ≥1 delta-only extend cycle (`extends` non-empty) during a streamed utterance.
- **#20** requires ≥1 revising commit (a commit that rewound a non-empty tail), with a bounded same-session retry (re-feed utt_punct).
Candidate causes: (a) **late regression** from the post-T8 commits (cf2dfb1 debounce 10-19, 0e7dd05 clamped rewinds 10-25, 26d570b lazy separator 10-28, e5409a1 pacing 10-28) — e.g. if debounce/clamping now suppresses delta-only extends or revising commits entirely; (b) **real-model flake** on a loaded machine (espeak audio + model nondeterminism); (c) interaction with the lazy separator (a commit that confirms the tail exactly now rewinds nothing AND types nothing — arguably still "revising"? no: a revising commit REQUIRES a rewind; an exact-confirm carries lazily with zero ops → could make #20's premise rarer). Note (c) blurs the line: the separator change can legitimately alter these properties' frequency — which is exactly why they need the re-run protocol rather than a guess.

## §4. The pre/post re-run protocol (the watch-set disambiguator)

- **Pre-change flake baseline (this subtask)**: run `tests/test_streaming.py` **3×** at pre-change HEAD (each `timeout 300 uv run pytest ... -q`, bash-tool timeout ≥360; ~106 s/run). Record per-run per-test outcomes for ALL 7 tests (bounded table). Interpretation: all-3-runs-red = STABLE red (regression-shaped); flips = FLAKY.
- **Per-D3-change protocol** (P1.M1.T2/T3/T4 and any later streaming/daemon-touching change): re-run `tests/test_streaming.py` once BEFORE and once AFTER the change; also re-run the 3 fast red suites (commit/core/freeze, ~0.05 s) after every change. Rules: a watch test red in ALL post-change runs but GREEN in all pre-change runs → REGRESSION (investigate that change); red↔green flips without a code change → flake (record, don't chase); the 16 (i) fast reds must stay EXACTLY the known set — any growth/shrinkage = finding (a deliberate reconciliation is later work, never an accident).
- **NO blanket skips, NO legacy behavior edits to fake parity** (contract + PRD R.7 G1).

## §5. Deliverable shape

APPEND to `tests/G1_BASELINE.md` (S1's committed doc): a "Failure classification (P1.M1.T1.S2)" section = the 20-row table (Class + Facet + one-line evidence), the watch-set subsection (the two (ii) tests + the 3-run pre-change baseline + the per-change protocol), and the no-skip/no-parity-edit statement. Commit the doc change alone. S1's doc does NOT exist yet at research time (in flight) — S2 must verify it exists first (STOP if not: the input contract is unmet).

## §6. Facts for the implementer

- HEAD d78ff95 == code-state 2335a9e for voice_typing//tests//config.toml (verify: `git diff 2335a9e --stat -- voice_typing/ tests/ config.toml` empty).
- The combined fast run `pytest tests/test_streaming_commit.py tests/test_streaming_core.py tests/test_streaming_freeze.py -q` → `16 failed, 76 passed` (verified today; fine for the classification re-verify — S1's baseline used one-file-per-call for the RECORD, but S2's verification may combine since only counts+names matter).
- test_streaming.py = 7 tests, ~106 s, real small.en on wav fixtures; 3P/4F (a, b, f, g red) in the research run. The 4 excluded/forbidden suites and the two-timeout rule per repo AGENTS.md apply.
- test name correction: A.1 #6 is `test_commit_extend_strips_spurious_mid_sentence_period` (the doc's "stips…strips" is a typo).
