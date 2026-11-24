# Research — P1.M7.T1.S1: Assemble G6 assessment; conditionally flip the default

## 1. The G6 rule (verbatim contract sources)

PRD §4.2sexies R.7 **G6 graduation to default**:

> verified G3 rows for the pi prompt in Ghostty, a graphical editor, and a browser text field;
> zero observed integrity failures; and ≥ 3 representative completed writing sessions where
> usable proofread words per minute — counting corrections, recovery, and rereading — beats
> 110 wpm. Otherwise report that and stay opt-in. **Never claim "works on Wayland" from one
> row; never fabricate user acceptance.**

R.2 provenance discipline (same PRD):

> NOT VERIFIED anywhere: insert+correct in the real chat prompt; speech-to-visible latency;
> desktop coverage; throughput; Hyprland relay behavior … **No operator acceptance on
> record. A passing transport probe NEVER flips any of these to "passed".**

PRD §7 acceptance criterion 13 (tail):

> graduation to the shipped default requires the G3 verified matrix plus the G6 throughput
> evidence — **until then the mode is opt-in and its claims are reported as unverified.**

Work-item contract adds: the flip is **Iff**-gated; `output.delivery` default flips to
`"bulk-text"` in lockstep (config.py + config.toml + tests) with the **precondition triple
still enforced**; otherwise record explicitly unmet and stay opt-in; **no fabricated user
acceptance**.

Decomposition into four machine-checkable-or-explicitly-manual conditions:

| # | Condition | Source of truth | Mechanically checkable? |
|---|-----------|-----------------|-------------------------|
| A | Verified G3 rows: pi prompt in isolated Ghostty **AND** a graphical editor **AND** a browser text field (insert AND correct on each) | `plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl` (M5.T2.S1) + `editor_browser_row_verdicts.jsonl` (M5.T2.S2) + narrative mds | YES — jsonl rows all `passed/pass: true` + required row classes present |
| B | Zero observed integrity failures | G2 gate record (`architecture/g2_gate_record.md`), zero failed rows in the G3/G5 verdict registers, operator journal review (read-only) | PARTLY — jsonl failures + G2 record; journal review is operator-attested |
| C | G5 timing evidence passing per claimed route | `tests/G5_TIMING_EVIDENCE.md` (P1.M6.T4.S1 — **in flight, parallel**; may not exist yet) | YES (parse the report's verdict lines; unparsable/absent ⇒ NOT met, never pass-by-default) |
| D | ≥3 representative completed writing sessions, usable proofread wpm > 110 each (counting corrections, recovery, rereading) | `tests/G6_WRITING_SESSIONS.md` — operator-authored entries ONLY | YES (file format), but the ENTRIES are human-only — the implementer MUST NOT write them |

**Expected honest landing: D is unmet** (no operator sessions on record, R.2). Therefore the
defaulted outcome of this task is: assessment doc records A/B/C as measured and D as unmet
→ **stay opt-in** ("stream-edit" remains the default), comment pointers updated, ZERO value
changes. The flip path stays fully specified for a future re-run once the operator records
sessions. BOTH outcomes are a successful delivery of this item.

## 2. Evidence inventory (verified present on disk)

- `plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl` — G3 pi-prompt-in-Ghostty rows
  (observed rows: `desktop-boot`, `census-pre-drive`, `short-insert-1`, …; schema
  `{"row","passed","status","detail","versions","evidence"}`; ghostty **1.4.0** in versions).
- `plan/008_a47116bb2b79/architecture/editor_browser_row_verdicts.jsonl` — G3 graphical
  editor + browser rows (observed: `editor-short-updates`, `editor-firstword-20sent`, …;
  schema `{"row","sub","pass","checks","t_ms","oracle",…}`; `checks: []` = no failures).
- Narrative: `architecture/g3_pi_prompt_row.md`, `g3_editor_browser_rows.md`,
  `g3_field_matrix.md`, `g3_gtk_rows.md`, `g2_gate_record.md`, `g4_clipboard_evidence.md`.
- `tests/G5_TIMING_EVIDENCE.md` — DOES NOT EXIST YET (P1.M6.T4.S1 implementing in
  parallel; its PRP commits this report with per-route rows honestly labeled
  `pass | fail(reason) | blocked(reason)`).
- No `integrity` marker exists in code (grepped `voice_typing/` + `tests/` — zero hits):
  integrity failures are surfaced as **failed rows / non-empty `checks`** in the verdict
  registers, the G2 gate record, and the daemon's bulk-path fault surface
  (`state.json` `delivery_state: fault`, `delivery_reason`). The assessment reads these;
  it never synthesizes them.
- G3 row-naming caveat: the browser rows' exact names were not enumerated in this session —
  the assembler must DERIVE required-row presence from the files themselves (enumerate
  `row` values; require the editor + browser insert AND correct classes), not hardcode
  guesses beyond the observed prefixes.

## 3. The flip mechanics (precedent: duck_mode flip, commit 22009a0, P1.M2.T4.S1)

Lockstep value flip, guarded by the repo-default comparison test:

1. `voice_typing/config.py:147` — `delivery: str = "stream-edit"` → `"bulk-text"` (+ comment).
2. `config.toml:50` — `delivery = "stream-edit"` → `"bulk-text"` (+ comment; drop the
   "stays the default until G6 graduation" sentence, point at the graduation doc).
3. `tests/test_config.py:58` — the ONE default-pinning assertion
   (`assert cfg.output.delivery == "stream-edit"  # … opt-in until G6 graduation`) →
   expects `"bulk-text"`.
4. `tests/test_config_repo_default.py` — NO structural edit: `test_repo_config_toml_equals_defaults`
   (the lockstep guard, ~line 17) auto-adapts; key-set pin count unchanged. Red if only one
   side flips — that is the point.
5. Precondition triple (config.py `VoiceTypingConfig.__post_init__` ~:400-430) stays
   byte-identical: it enforces `output.streaming=true, asr.graceful_stop=false,
   cancel.keypress_action="disarm"` when delivery=="bulk-text". Current defaults ALREADY
   satisfy the triple (config.toml:31 `graceful_stop=false`, :49 `streaming=true`,
   :54 `keypress_action="disarm"`) — verify at implementation; the flipped default must
   load cleanly through `from_toml(repo default)`.
6. Duck-precedent commit-message discipline: state (a) the value flip + why it is now safe,
   (b) that the claims are recorded, not assumed; reference the assessment doc.

No-flip path: ZERO value/test changes; only comment-line updates in config.py (:147-153
comment block) and config.toml (:50) pointing at `tests/G6_GRADUATION.md` and its verdict.
Comments do not affect the lockstep test (it compares parsed values/key-set).

## 4. Deliverable design (following the repo's evidence culture)

- `tests/g6_assessment.py` — pure-stdlib verdict engine + CLI (NOT pytest-collected as a
  lab; its FUNCTIONS are imported by the test file). Inputs are committed artifacts only;
  no CUDA, no desktop, no network, no live-service exercise. Reads the jsonls, the G5
  report (defensive verdict-line parse; absent/unparsable ⇒ unmet, never pass-by-default),
  and the sessions file (valid entry = date + duration + words + corrections/recovery/
  rereading accounting + computed usable wpm + operator attribution; ≥3 entries each >110).
  Prints the per-condition verdict block + final decision line
  `G6 DECISION: FLIP` or `G6 DECISION: STAY OPT-IN (unmet: …)`.
- `tests/test_g6_assessment.py` — unit tests of the decision logic on synthetic fixtures
  in tmp dirs: all-met ⇒ flip; sessions file absent/<3 entries/≤110 wpm ⇒ no flip; a failed
  G3 row ⇒ no flip; G5 report absent ⇒ no flip; transport-probe-only evidence ⇒ never counts.
- `tests/G6_WRITING_SESSIONS.md` — CREATE as an EMPTY operator template (entry format +
  wpm accounting rules + explicit "implementers must not add entries"). Zero entries ⇒ D
  unmet. This is the sanctioned, non-fabricating interface for the operator's evidence.
- `tests/G6_GRADUATION.md` — the bounded committed assessment: environment provenance,
  per-condition rows (condition, evidence path(s), counts, verdict), the decision, the
  no-flip/flip consequence, and the outstanding-inputs section (what a future re-run needs).
- Conditional MODIFIES (flip path only): the three lockstep sites in §3.

## 5. Validation commands (repo-verified forms, AGENTS.md timeout discipline)

- `timeout 300 uv run pytest tests/test_g6_assessment.py -q` (new unit tests)
- `timeout 60 .venv/bin/python tests/g6_assessment.py` (live-artifact run; exit 0 either
  way — the decision is data, not an error)
- Flip-path only: `timeout 600 uv run pytest tests/test_config.py tests/test_config_repo_default.py -q`
- No-flip invariant greps: `delivery: str = "stream-edit"` still in config.py:147;
  `delivery    = "stream-edit"` still in config.toml:50; test_config.py:58 unchanged.
- Honesty audit: `git diff` contains NO session entries authored by the implementer; the
  sessions template has zero entries or operator-attributed ones only; no G5/G3 verdict
  text was edited.
- G1 watch-set quick sweep (unchanged by this item): `timeout 600 uv run pytest
  tests/test_config.py tests/test_zero_diff_rewind.py -q`.

## 6. Gotchas

- **G1**: NEVER write/seed session entries (wpm evidence) — that is fabricating user
  acceptance, the explicitly forbidden failure mode. An empty sessions file is the correct,
  expected state at implementation time.
- **G2**: absent/unparsable G5 report ⇒ condition C UNMET ("not run"), never "passed"; a
  passing transport probe (paste-lab / im-lab mechanism evidence) NEVER substitutes for
  G3/G5/G6 (R.2).
- **G3**: lockstep discipline — flip config.py + config.toml + the one test pin in the SAME
  change or the repo-default guard goes red (that red is the guard working, not a bug).
- **G4**: "works on Wayland" style claims are forbidden from single rows; the doc's
  per-condition rows carry `verified | unmet | not-run(reason)` only.
- **G5**: the precondition triple enforcement code is NOT touched on either path.
- **G6**: bounded doc — counts + paths + verdicts, no giant log dumps (Rule-3 discipline).
