# Research — P1.M7.T2.S2: ACCEPTANCE.md rows + install.sh usage

Recorded 2026-11-23. All file cites verified at HEAD this session.

## 1. Current tests/ACCEPTANCE.md state (the file being edited)

- Header: "records the verified evidence for PRD §7 criteria **1–12**" → must become 1–13 + the
  ducking row.
- Intro "Cross-checked dossier" paragraph (plan/006 round): ends with
  "**424 LIVE-green test executions this round**" — historical (plan 006 dossier), stale as a
  current total.
- Row 1 evidence contains "= **424 LIVE-green**" (T1 `test_feed_audio.py` 9/9 82.09s + T2 196
  unit of which textproc 21 + mocked daemon+recorder 219). Suites have since grown (ducking,
  bulk, D3 tests) → re-measure or re-attribute.
- **Row 11 (STALE — the crux)**: claims `tests/test_streaming.py` **"suite 7/7 green via
  `timeout 900 .venv/bin/python -m pytest tests/test_streaming.py -v`"** and the mocked trio
  run "`timeout 300 uv run pytest tests/test_streaming_core.py tests/test_streaming_freeze.py
  tests/test_streaming_commit.py -q` → **77 passed**". Item note: HEAD measures **3/7** and
  **76/18** (76 passed / 18 failed across the trio).
- Row 12 (cancel fallback): cites `test_e_cancel`, `test_dispatch_cancel_routes_to_daemon_
  cancel_and_returns_shape` (test_control_socket.py:326), T7 cancel smoke, `test_zero_keyboard_
  warning_fires_once_at_first_arm` (test_key_listener.py:459), BUG-002/BUG-007 `-k` runs
  (→ 7 passed / 4 passed). Predates D3.2/D3.3 → gains their regression tests.
- Rows are a markdown table: `| # | Criterion (PRD §7) | Status | Evidence |`.
- 12 rows today; need 14 (12 + ducking + #13).

## 2. G1 baseline reconciliation source — tests/G1_BASELINE.md (READ FIRST at implementation)

- 20-row classification table: **18 × (i)** legacy lazy-separator reds (16 fast: commit×10,
  core×2, freeze×4 — mapped to facets F1–F5 of commit `26d570b`; plus streaming `test_f_user_
  key_freeze` (i)/F1 and `test_g_stranded_tail` (i)/F5 **FLAKY** 4F/2P over 6 observations) and
  **2 × (ii)** watch-set reds (`test_a_delta_cadence`, `test_b_commit_rewind_exact` — cadence/
  rewind properties, stable red across 4 observations, "regression-shaped").
- `test_streaming.py` pre-change flake baseline: **3 passed / 4 failed** (a,b,f,g red; c,d,e
  green) × 3 runs + spot run. Matches HEAD 3/7.
- Trio at S2-time: **76 passed / 16 failed**; HEAD measures **76/18** → **2 reds beyond the
  classified 16** = NEW failures (or newly-added failing tests). MUST be named and reported —
  never hidden, never skipped ("no parity faking"; G1 contract statement: no skips, no
  expectation edits; the (i) set is the invariant to diff against).
- Per-change protocol section + "Record every post-change run's totals + FAILED names as an
  addendum" — the ACCEPTANCE row cites numbers, G1_BASELINE.md is the classification authority.

## 3. Ducking row (D1) content — tests/D1_DUCK_EVIDENCE.md

- Recorded 2026-11-23, HEAD `b9da1eb`, scripted `timeout 900 bash tests/d1_duck_evidence.sh`,
  **exit 0, 12/12 scenario checks PASS**.
- Five §4.2quinquies acceptance scenarios → scripted checks: (1) MPRIS pause ≤~1 s (**107 ms**
  measured after arm return) + resume at stop + journal lines; (2) volume tier 40%→15%→exact
  40% restore; (3) sovereignty ×4 (user-resume honored, user-paused stays paused, 60% kept);
  (4) `duck_mode="off"` zero `ducking:` journal lines (byte-identical); (5) default engages
  with NO `[audio]` key in config (post-flip default `mpris`).
- Verbatim journal lines available in the file (paused/resumed MPRIS player(s), sink volume
  40% -> 15%, keeping user value, restored sink volume 40%).
- Placement decision: insert as row labeled **"D1"** (§4.2quinquies) between rows 12 and 13.

## 4. Row #13 content (§7 item 13 — bulk text)

- PRD §7.13: mode works per spec, opt-in; "graduation to the shipped default requires the G3
  verified matrix plus the G6 throughput evidence — until then the mode is opt-in and its
  claims are reported as unverified."
- `tests/G6_GRADUATION.md` (exists; assessed 2026-11-23 @ HEAD `69952ae`):
  `G6 DECISION: STAY OPT-IN (unmet: A-g3-matrix, B-integrity, C-g5-timing, D-sessions)`.
  Mechanically re-derivable: `timeout 60 .venv/bin/python tests/g6_assessment.py` (pure stdlib,
  reads committed registers only). Conditions: A unmet (edit-count-law failed row
  "warm-up overcount"; pi-prompt-ghostty "not verified (visibility instrumentation absent)";
  browser insert-only, correction REFUSED); B unmet (edit-count-law register row); C unmet
  (G5: im-gtk backlog sustained 20 inserts/0 corrections <100 floor; pi-ghostty speech→visible
  12.6 s median); D unmet (0 of ≥3 operator writing sessions, `tests/G6_WRITING_SESSIONS.md`).
- Evidence files for the row's links: `plan/008_a47116bb2b79/architecture/g2_gate_record.md`
  (13/13 traces), `g3_field_matrix.md`, `pi_row_verdicts.jsonl` (24 rows),
  `editor_browser_row_verdicts.jsonl` (17 rows), `g4_clipboard_verdicts.jsonl` (L1 unprovable →
  refuse; L2–L6 verified), `tests/G5_TIMING_EVIDENCE.md`, `tests/G6_GRADUATION.md`.
- Status framing: the criterion's own pass condition = mode shipped + opt-in + claims reported
  unverified → status line must encode "shipped opt-in; claims reported unverified per G6" and
  the unmet technical gates reported, not softened.

## 5. install.sh usage (the code edit)

- Line 209 today:
  `echo "usage  : $REPO/.venv/bin/voicectl toggle|start|stop|status|cancel|quit"`
  followed by keybind hint lines 210–211.
- Target: add `session` to the command list + one hint line for `session [--copy]`
  (semantics from `voice_typing/ctl.py`: prints most recent COMPLETED session; `--copy` stages
  to Wayland clipboard, "copied N chars", no added newline; exit 1 no-session; exit 64 misuse;
  works in BOTH delivery modes).
- Guard: `tests/test_systemd_unit.py:205 test_install_sh_offline_grep_and_summary` greps
  install.sh — read it before editing; run the suite after. `tests/test_voicectl.py` (36 tests)
  may pin usage strings — grep for "usage"/"quit" there too.
- README currently has NO verbatim copy of that usage line (verified: no match for
  "toggle|start|stop|status" in README.md) → no coupling to fix here; S1 owns README's
  "six→seven commands" sentence; S3 owns the final sweep.

## 6. D3 cancel-behavior changes (row 12 refresh substance)

- D3.2 (P1.M1.T3, auto-repeat compensation audit): regression tests incl.
  `test_autorepeat_ignored`, `test_repeated_backspace_presses_route_one_cancel_each`
  (key-listener level; names from research notes — VERIFY at HEAD with grep before citing).
- D3.3 (P1.M1.T4, suppression-window latch bound): `test_cancel_suppression_drop_cap_force_
  closes_window_and_processes_final`, `test_arm_clears_stale_cancel_suppression`,
  `test_fresh_arm_clears_suppress_since`, `test_sentinel_consume_clears_suppress_since`,
  `test_cancel_suppression_repress_restamp_does_not_reset_drop_counter`,
  `test_cancel_suppression_drop_counter_resets_on_sentinel_close`,
  `test_lost_sentinel_self_heals_after_timeout` (same verify-first rule).
- Core row-12 claims (socket rewind identical, no-op second cancel, listener failure logged
  once at arm) are asserted unchanged by D3 PRPs; re-run the cited commands to confirm.

## 7. Mode B definition (delta_prd.md:91)

"**Mode B — changeset-level sync (final task, depends on all above):** … `install.sh` printed
usage gains `session`. `tests/ACCEPTANCE.md`: add the ducking row and row #13 with actual
command output links; refresh row #12 if D3 changes cancel behavior. Every claim verified
against the code as landed — no aspirational prose." This task IS the Mode B tail half.

## 8. Boundaries (from sibling PRPs)

- P1.M7.T2.S1 (parallel, README): explicitly does NOT edit ACCEPTANCE.md — no conflict.
- P1.M7.T2.S3 (final sweep + commit discipline): owns cross-doc consistency sweep (e.g.
  README↔ACCEPTANCE↔config drift) — flag drift, don't sweep it here.
- G6 task froze config values — we change no config/code.
- FORBIDDEN: editing tests, G1_BASELINE.md classification, PRD, tasks.json, source files.
