# Research ledger — P1.M7.T2.S3 final consistency sweep + commit discipline

Recorded 2026-11-24 session. All facts verified against the working tree this session.
The PRP derives from these; cites are file:line or command-shaped.

## 1. The governing acceptance text (verbatim)

`plan/008_a47116bb2b79/delta_prd.md` §5 "Delta acceptance criteria":

- **#4 (this item's sign-off target):** "All work under AGENTS.md discipline (two timeouts on
  every non-trivial command; never foreground the daemon; bounded scratch); everything
  committed to `main` with sensible messages."
- **#2 tail (the no-over-claiming rule):** "No over-claiming: any field/latency not verified
  stays labeled unverified."
- §4 Mode B (delta_prd.md:91): "Every claim verified against the code as landed — no
  aspirational prose."

## 2. Upstream inputs (S3 depends on both)

- **P1.M7.T2.S1 (README)** — PRP: `plan/008_a47116bb2b79/P1M7T2S1/PRP.md`. Deliverable: README
  ducking + bulk-delivery sections, config-table rows, troubleshooting rows; bulk framing
  derived verbatim from `tests/G6_GRADUATION.md`'s `G6 DECISION:` line. README section map at
  HEAD already shows the intended shape: `## Media ducking while listening` (:204), `## Bulk
  text delivery (opt-in, experimental)` (:251), `### Session recovery (voicectl session)`
  (:308), `### Takeover semantics` (:318), troubleshooting `### Bulk delivery: …` (:489/:499/:517).
- **P1.M7.T2.S2 (dossier + installer)** — PRP: `plan/008_a47116bb2b79/P1M7T2S2/PRP.md`.
  Deliverable: `tests/ACCEPTANCE.md` → 14 rows (1–12 + D1 + 13), refreshed 1/11/12 + totals;
  `install.sh` usage line gains `session` + hint. Its success criteria (a)–(e) are exactly what
  S3 re-verifies. S2's G-SCOPE note: "the cross-doc consistency sweep is S3's. … Flag (commit
  message) any drift you notice — don't fix it." → S3 owns the fixing.
- S2's PRP pins row 13 framing: `G6 DECISION: STAY OPT-IN (unmet: A-g3-matrix, B-integrity,
  C-g5-timing, D-sessions)` must appear verbatim; status wording "PASS-as-specified: shipped
  OPT-IN, claims reported UNVERIFIED".

## 3. The four sweep surfaces (current state)

1. **README.md** (~600 lines, committed). Sections listed above; `## Configuration` (:343),
   `## Logs, status, stopping` (:532) hold the usage/commands prose.
2. **tests/ACCEPTANCE.md** — dossier. Header: "verified evidence for PRD §7 criteria 1–12"
   (S2 → 1–13 + D1). Row schema `| # | Criterion (PRD §7) | Status | Evidence |`. Evidence
   typing vocabulary: **LIVE / STATIC / PAST-LIVE**; "(Block below)" convention; method notes at
   bottom. **Known stale pointer:** row 7 says 'Formal "everything committed" sign-off owned by
   **P1.M6.T1.S3**' — a plan-006 task id; this task (P1.M7.T2.S3) now owns that sign-off and
   must redirect the pointer. Cross-ref to `plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md`
   stays (historical attribution). Stale-number greps after S2: `7/7`, `77 passed`, bare `424`.
3. **config.toml** — Mode A self-documenting ("Both the daemon's runtime default AND the
   user-facing config reference"). Header contract: config.py is schema source of truth, "Keep
   the two in lockstep"; unknown keys AND tables REJECTED at load. Key-set pinned by
   `tests/test_config.py` (54 tests) + `tests/test_config_repo_default.py` (3).
4. **voicectl --help** (`voice_typing/ctl.py`): usage/epilog at :333 — "subcommands: toggle,
   start, stop, status, quit, cancel, session [--copy]  (see the project README for the full
   usage table)"; command help :338 "toggle | start | stop | status | quit | cancel | session";
   `--copy` help :343; unknown command → exit 64 (:353-:375, `if cmd not in _COMMANDS`).
   `_COMMANDS` is the landed command set — enumerate it (grep around :375) and diff vs epilog
   vs README vs install.sh usage line. NOTE: epilog string above does NOT name lite commands —
   verify whether `toggle-lite`/`start-lite` are in `_COMMANDS` and whether the epilog/README/
   install.sh usage surfaces agree; any disagreement is a finding.
   - `voicectl --help` is daemon-free (argparse exits before socket) → safe under
     `timeout 15`. `voicectl status` needs a live daemon — do NOT run it for this sweep; use
     unit tests (`tests/test_voicectl.py`, 36 tests) as the behavior oracle.
5. **install.sh** usage echo block ~:209 (S2's edit target): must list
   `toggle|start|stop|status|cancel|session|quit`. Pins: `tests/test_systemd_unit.py:205`
   (`test_install_sh_offline_grep_and_summary`) greps install.sh strings;
   `tests/test_voicectl.py` may pin usage text — read greps before any edit.

## 4. G1 baseline + watch set (tests/G1_BASELINE.md — classification authority)

- Recorded at code-state `2335a9e` / HEAD `d78ff95`, 2026-11-23. **15 suites, 380P / 19F.**
- Methodology parity requirement: `timeout 300 /home/dustin/.local/bin/uv run pytest <file> -q
  --tb=line`, **one file per call**, bash-tool timeout ≥ 360. No daemon/voicectl/E2E/CUDA
  beyond the suites themselves.
- **Invariant:** the 16 fast (i) legacy lazy-separator reds (commit×10, core×2, freeze×4) must
  remain EXACTLY that named set — growth or shrinkage is a finding even if it looks better.
- **Watch set (ii):** `test_a_delta_cadence`, `test_b_commit_rewind_exact` (stable red,
  regression-shaped). `test_g_stranded_tail` = FLAKY class (4F/2P over 6 observations; single
  observations prove nothing).
- **Contract:** NO blanket skips, NO expectation edits to fake parity; reconciling (i) reds is
  a separately-decided change, never a side effect.
- 5 non-G1 files NOT run by the baseline and contract-forbidden hang vectors:
  `test_feed_audio`, `test_daemon`, `test_recorder_host`, `test_cuda_check` (+
  `test_systemd_unit` not in the G1 set). If S3 needs them (it shouldn't beyond config/voicectl
  suites), `timeout 600` + bash-tool 660.
- G1_BASELINE.md is **read-only for S3** except: if a NEW failure (not in the 20-row table)
  appears, append ONE bounded drift-addendum row and escalate — never reclassify.

## 5. Git / commit discipline facts

- Current branch: `main` (local; `ahead 51` of origin/main — pushing is NOT part of any
  criterion; "committed to main" is local). Side branches exist (`backup-19…`,
  `fix/ydotoold-datagram`) — fine, work just must be on main.
- `plan/` IS tracked (324 files under plan/008_… committed). "Repo clean" therefore includes
  committing the S1/S2/S3 `plan/008_a47116bb2b79/P1M7T2S{1,2,3}/` PRP+research dirs.
- `plan/008_a47116bb2b79/tasks.json` is orchestrator-owned (tracked, modified by the
  orchestrator as tasks complete) — leave it alone; flag its state in the sign-off.
- Commit message convention (from `git log`): imperative one-liners with the item id in
  parentheses — "Add G6 assessment; default stays opt-in (P1.M7.T1.S1)", "Add voicectl session
  [--copy] (P1.M6.T2.S3)". S3's own commit should read e.g.
  "Final doc consistency sweep + dossier sign-off (P1.M7.T2.S3)".

## 6. Evidence files the over-claiming audit checks against

- `tests/G6_GRADUATION.md` — decision line (above) + per-condition table (pi-prompt
  not-verified, browser insert-only/correction REFUSED, edit-count-law warm-up overcount, G5
  both routes failing, 0 writing sessions). Re-derive: `timeout 60 .venv/bin/python
  tests/g6_assessment.py` — never soften "unmet".
- `tests/G5_TIMING_EVIDENCE.md` — im-gtk backlog sustained; pi-ghostty 12.6 s median.
- `tests/G6_WRITING_SESSIONS.md` — 0 valid sessions.
- `tests/D1_DUCK_EVIDENCE.md` — 12/12 scripted checks, 107 ms pause; re-run
  `timeout 900 bash tests/d1_duck_evidence.sh` (only if duck claims disputed).
- `plan/008_a47116bb2b79/architecture/{g2_gate_record.md, g3_field_matrix.md,
  pi_row_verdicts.jsonl, editor_browser_row_verdicts.jsonl, g4_clipboard_verdicts.jsonl}`.

## 7. Sequencing constraint

S1 and S2 are inputs. Preflight MUST confirm both landed (git log contains their item-id
commits; README has the sections; ACCEPTANCE has 14 rows; install.sh lists `session`). If a
sibling deliverable is absent, STOP and report — do not sweep a half-state and do not
re-implement a sibling's task.

## 8. AGENTS.md discipline (embeds for the PRP)

Two timeouts on every non-trivial command (inner GNU `timeout` + bash-tool margin); `voicectl`
always under `timeout 30` (control socket has no read timeout); never foreground the daemon;
prefer unit tests over the 5–8 min shell gates; bounded scratch under /tmp (tmpfs = RAM);
giant scratch files are `rm -f`'d on sight, never read.
