---
name: "P1.M7.T1.S1 — Assemble the G6 graduation assessment; conditionally flip output.delivery default to bulk-text"
description: "Assemble the evidence-gated G6 graduation assessment (PRD §4.2sexies R.7 G6) from the committed evidence artifacts — the G3 verdict registers (pi-prompt-in-Ghostty, graphical editor, browser field), the G5 timing report (P1.M6.T4.S1, parallel), the G2/integrity registers, and operator-authored writing-session evidence — and IF AND ONLY IF every G6 condition is verifiably met, flip the output.delivery default from 'stream-edit' to 'bulk-text' in lockstep (config.py + config.toml + the one default-pinning test; precondition triple untouched). Otherwise record the unmet conditions explicitly and stay opt-in. Never fabricate user acceptance; a passing transport probe never flips a NOT VERIFIED claim. Deliverables: mechanical verdict engine + its unit tests, the operator sessions-evidence template (ships EMPTY), the bounded committed assessment doc, and the conditional lockstep flip."
---

# PRP — P1.M7.T1.S1: Assemble G6 assessment; conditionally flip the default

## Goal

**Feature Goal**: Close the G6 graduation gate (PRD §4.2sexies R.7) for bulk-text delivery
with an **honest, mechanically-derived, committed assessment**, and make the default-flip
decision it dictates — nothing more, nothing less. G6's conditions, verbatim from the PRD,
are the contract:

1. **Verified G3 rows** for the pi prompt in Ghostty, a graphical editor, and a browser
   text field (insert AND correct, visible, per R.7 G3).
2. **Zero observed integrity failures.**
3. **≥ 3 representative completed writing sessions** where usable proofread wpm — counting
   corrections, recovery, and rereading — **beats 110** (operator-dependent evidence).
4. Otherwise: report that and **stay opt-in**. **Never claim "works on Wayland" from one
   row; never fabricate user acceptance.** (R.2: "No operator acceptance on record. A
   passing transport probe NEVER flips any of these to 'passed'.")

The expected honest landing (R.2 records no operator acceptance; the sessions evidence
does not exist yet): conditions A–C assessed as measured, **condition D unmet** → decision
**STAY OPT-IN** → `output.delivery` default remains `"stream-edit"`, with comment pointers
to the assessment doc. That is a COMPLETE and successful delivery of this item. The flip
path is fully specified below and executes only if every condition is verifiably met —
including operator-authored session entries that the implementer is FORBIDDEN from writing.

**Deliverable** (4 CREATE, unconditional + up to 3 MODIFY, flip-path only):

1. `tests/g6_assessment.py` — CREATE. Pure-stdlib verdict engine + CLI (no CUDA, no
   desktop, no network, no live-service contact; reads committed artifacts only). Imports
   cleanly; NOT pytest-collected as a lab (its functions are exercised by the unit tests
   below). Emits the per-condition verdict block and the final
   `G6 DECISION: FLIP` / `G6 DECISION: STAY OPT-IN (unmet: …)` line.
2. `tests/test_g6_assessment.py` — CREATE. Unit tests of the decision logic on synthetic
   fixture files in tmp dirs (pytest-collected, fast, mocked file IO).
3. `tests/G6_WRITING_SESSIONS.md` — CREATE. The **EMPTY** operator template: entry format,
   the wpm accounting rules (usable proofread wpm counting corrections, recovery,
   rereading), and the explicit rule that implementer/automation MUST NOT add entries.
   Zero entries ⇒ condition D unmet.
4. `tests/G6_GRADUATION.md` — CREATE. The bounded committed assessment doc (the DOCS
   deliverable): environment provenance, one row per G6 condition (evidence path(s),
   counts, verdict `verified | unmet | not-run(reason)`), the decision line, the
   consequence (flip executed / stayed opt-in), and the outstanding-inputs section for a
   future re-run.
5. **Flip path ONLY** (executed iff the assessment prints `G6 DECISION: FLIP`):
   `voice_typing/config.py` default `delivery: str = "stream-edit"` → `"bulk-text"`
   (+comment), `config.toml` `delivery = "stream-edit"` → `"bulk-text"` (+comment), and
   the ONE default-pinning assertion `tests/test_config.py:58`. All in the SAME change
   (lockstep, duck_mode precedent commit `22009a0`). The precondition triple
   (`config.py` `VoiceTypingConfig.__post_init__` ~:400-430) is byte-identical on both
   paths.
6. Comment-pointer touch (both paths, value-neutral): the `delivery` comment blocks in
   `config.py:147-153` and `config.toml:50` reference `tests/G6_GRADUATION.md` and its
   verdict instead of the open-ended "until G6 graduation" sentence. Comments do not
   affect the repo-default lockstep test (it compares parsed values + key-set).

**Success Definition**:

- (a) `timeout 60 .venv/bin/python tests/g6_assessment.py` runs clean against the REAL
      committed artifacts and prints the per-condition block + decision; exit code 0 for
      EITHER decision (the decision is data, not an error).
- (b) `timeout 300 uv run pytest tests/test_g6_assessment.py -q` green: all-met ⇒ flip;
      sessions-file absent / <3 entries / any entry ≤110 wpm ⇒ no-flip; any failed G3 row
      ⇒ no-flip; G5 report absent or unparsable ⇒ no-flip; probe-only evidence never
      counts.
- (c) The committed `tests/G6_GRADUATION.md` verdict rows match the script's output
      verbatim (counts + paths), with environment provenance, and contain NO
      implementer-authored session entries.
- (d) `tests/G6_WRITING_SESSIONS.md` ships with ZERO entries (headers/format/rules only).
- (e) On the expected STAY-OPT-IN landing: `git diff` shows ZERO value changes to
      `config.py` / `config.toml` / any test — only the comment pointers (6) and the four
      new files. On the FLIP landing: the three lockstep sites flip together, the
      repo-default lockstep test is green, the key-set pin count is unchanged, and
      `VoiceTypingConfig.from_toml(repo config.toml)` loads cleanly (the precondition
      triple holds at the new defaults: `streaming=true`, `graceful_stop=false`,
      `keypress_action="disarm"` — verify, do not assume).
- (f) Honesty audit passes: no G3/G5 verdict artifact was edited; no session evidence was
      invented; no claim in the doc upgrades a `NOT VERIFIED` item on transport-probe
      evidence; the phrase "works on Wayland" appears nowhere as a claim.
- (g) No out-of-scope edits: no `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`,
      no daemon/bulk/controller/adapter source, no README (P1.M7.T2 owns docs sync), no
      ACCEPTANCE.md rows (P1.M7.T2.S2 owns those).

## User Persona

**Target User**: three consumers. (1) The **operator** (dustin): reads the assessment to
know whether bulk-text is now the shipped default and, if not, exactly which evidence is
still owed (the sessions template is where they record it). (2) The **orchestrator / future
implementer**: re-runs `tests/g6_assessment.py` after new evidence lands to get the same
mechanical decision. (3) **P1.M7.T2 docs sync**: consumes the assessment doc as the source
of truth for the README/ACCEPTANCE claims about bulk delivery's status.

**Use Case**: after G3 rows + G5 evidence land, run the assembler; it derives the verdict
from the committed registers; the graduation doc records it; the default flips only on a
fully-met gate. When sessions evidence is still owed, the doc says precisely that and the
shipped default stays the battle-tested `stream-edit`.

**User Journey**: `timeout 60 .venv/bin/python tests/g6_assessment.py` → per-condition
rows → `G6 DECISION: STAY OPT-IN (unmet: writing-sessions)` → implementer commits the doc
+ template + comment pointers → operator later records ≥3 sessions in
`tests/G6_WRITING_SESSIONS.md` → re-run flips the default in lockstep.

**Pain Points Addressed**: (1) G6 has never been assembled — R.2 explicitly lists
throughput/coverage as NOT VERIFIED with "no operator acceptance on record", so graduation
is currently undecidable-by-default; this item makes it decidable and honest. (2) The
failure mode this task exists to prevent: an agent "graduating" bulk-text on synthetic-lab
success and flipping the default without the operator-dependent evidence (fabricated user
acceptance — explicitly forbidden). (3) Drift: a future re-run must re-derive the decision
from artifacts, not from a stale prose claim.

## Why

- **PRD §4.2sexies R.7 G6 is the normative gate** for the default flip, and §7 criterion
  13 pins the product consequence: "graduation to the shipped default requires the G3
  verified matrix plus the G6 throughput evidence — until then the mode is opt-in and its
  claims are reported as unverified." This item IS that sentence, implemented.
- **The work-item contract** names the exact inputs: G3 rows (P1.M5.T2.S1/S2 — landed,
  Complete), G5 evidence (P1.M6.T4.S1 — in flight, parallel; its PRP commits
  `tests/G5_TIMING_EVIDENCE.md` with honest `pass | fail(reason) | blocked(reason)` rows),
  and the integrity-failure log (the G2 gate record + the verdict registers' failure
  fields — there is no separate runtime integrity file; see research §2). This PRP treats
  the parallel G5 PRP as a contract: if its report is absent at implementation time,
  condition C is `not-run(reason)` and the gate cannot pass — which is correct, not a bug.
- **The repo's evidence culture demands mechanical derivability**: the duck-mode default
  flip (P1.M2.T4.S1, commit `22009a0`) flipped a default ONLY "with evidence" from a
  checked-in, re-runnable script; G3/G5 gates all write committed verdict registers
  (jsonl/md). A prose-only G6 assessment would be the first un-derivable claim in the
  chain — the assembler script closes that gap and makes over-claiming structurally hard
  (absent ⇒ unmet, unparsable ⇒ unmet, probes never count).
- **The sessions template solves the real blocker honestly**: the one condition that
  automation cannot produce (operator-dependent wpm evidence) gets a sanctioned,
  format-pinned, EMPTY interface instead of either (a) fabricated entries or (b) an
  undocumented "someday" — and the assessment names it as the outstanding input.
- **Scope discipline**: this is the LAST code-touching gate of the bulk-delivery milestone
  (P1.M7.T2 is docs only). No daemon/controller/adapter behavior changes on either path;
  the only possible runtime-behavior change is the config default value itself, gated.

## What

A small assessment toolchain + doc + a strictly conditional config flip:

1. **`tests/g6_assessment.py`** — pure functions + `main()`. Conditions (research §1):
   - **A (G3 matrix)**: parse `plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl`
     (schema `{"row","passed",…}`) and `editor_browser_row_verdicts.jsonl` (schema
     `{"row","sub","pass","checks",…}`). MET iff every row in BOTH files is
     `passed`/`pass: true` with empty `checks`, AND the required row CLASSES are present,
     derived by enumerating actual `row` values (pi-prompt-in-Ghostty insert + correct;
     graphical-editor insert + correct; browser-field insert + correct — observed
     prefixes: `short-insert`, `editor-short-updates`, `editor-firstword-20sent`;
     enumerate, do not guess — see research §2 caveat). Any missing class ⇒
     `unmet(missing rows: …)`; any failed row ⇒ `unmet(failed rows: …)`.
   - **B (integrity)**: MET iff zero failed rows / non-empty `checks` across both G3
     registers AND `architecture/g2_gate_record.md` exists and contains no recorded
     failing trace (defensive grep; unparsable ⇒ `unmet(cannot read)`). Operator journal
     review is recorded in the DOC as an attested field (see G6_GRADUATION.md template),
     not parsed by the script.
   - **C (G5)**: MET iff `tests/G5_TIMING_EVIDENCE.md` exists, parses (match the verdict
     format the G5 PRP's report renders; every claimed route row is `pass`), and contains
     zero `fail`/`blocked` route verdicts. Absent file ⇒ `not-run(P1.M6.T4.S1 report
     absent)`; unparsable ⇒ `not-run(cannot parse report format)` — NEVER pass-by-default.
   - **D (sessions)**: MET iff `tests/G6_WRITING_SESSIONS.md` exists and contains ≥3 VALID
     entries — each with date, duration, raw word count, corrections/recovery/rereading
     accounting, computed usable wpm, and operator attribution — and every computed
     usable wpm > 110. Absent file / zero entries / <3 / any ≤110 ⇒
     `unmet(no/insufficient operator writing-session evidence on record)`.
   - **Decision**: `FLIP` iff A∧B∧C∧D; else `STAY OPT-IN (unmet: …)`. Print the block;
     exit 0 either way.
2. **`tests/test_g6_assessment.py`** — synthetic fixtures in tmp_path exercising every
   branch above (research §5).
3. **`tests/G6_WRITING_SESSIONS.md`** — empty template with the entry format + accounting
   rules + the implementer prohibition.
4. **`tests/G6_GRADUATION.md`** — the assessment record (script output + provenance +
   outstanding inputs).
5. **Conditional flip** — the three lockstep sites, only on `FLIP`.

### Success Criteria

- [ ] `tests/g6_assessment.py` + `tests/test_g6_assessment.py` + both markdown files created;
      unit tests green under `timeout 300 uv run pytest tests/test_g6_assessment.py -q`.
- [ ] Script run against the real artifacts prints per-condition verdicts + decision; the
      committed doc matches it verbatim.
- [ ] STAY-OPT-IN landing (expected): zero value changes in config.py/config.toml/tests;
      comment pointers only. FLIP landing: lockstep flip + `test_repo_config_toml_equals_defaults`
      green + key-set pin unchanged + default config loads through the precondition triple.
- [ ] Sessions template has zero entries; no implementer-authored session evidence anywhere.
- [ ] Config suites green after the change: `timeout 600 uv run pytest tests/test_config.py
      tests/test_config_repo_default.py -q`.
- [ ] No edits to PRD.md / tasks.json / prd_snapshot.md / .gitignore / daemon sources /
      verdict artifacts; no README or ACCEPTANCE.md rows.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge: every input artifact is named with its
exact path and observed schema; the decision logic is fully specified (including the
absent/unparsable ⇒ unmet rule); the flip mechanics cite exact file:line sites and the
in-repo precedent commit (`22009a0`, P1.M2.T4.S1) whose PRP (`plan/008_a47116bb2b79/
P1M2T4S1/PRP.md`) documents the lockstep pattern; every validation command is a
repo-verified form under the AGENTS.md timeout discipline.

### Documentation & References

```yaml
# MUST READ — the verified evidence inventory + decision design (THIS is the spec companion).
- file: plan/008_a47116bb2b79/P1M7T1S1/research/g6_assembly_research.md
  why: "§1 the four-condition decomposition with machine-checkable vs manual split + the
        expected honest landing (D unmet). §2 evidence inventory incl. observed jsonl schemas
        and the browser-row naming caveat (derive, don't guess). §3 the flip mechanics with
        exact file:line sites + the duck precedent. §4 deliverable design. §5/§6 validation +
        gotchas."
  critical: "G1 never write session entries. G2 absent/unparsable G5 ⇒ unmet, never passed;
             probes never count. G3 lockstep same-change flip."

# MUST READ — the G6 rule + provenance discipline (normative).
- file: PRD.md
  why: "§4.2sexies R.7 G6 (the gate text, quoted in this PRP's Goal); R.2 evidence table +
        'a passing transport probe NEVER flips … to passed' + 'No operator acceptance on
        record'; R.4 stopping rules; §7 criterion 13 (opt-in until graduated); §6 T9 (G1–G6
        ordering, G6 = writing-session throughput evidence)."
  critical: "The three specific G3 rows (pi prompt in Ghostty / graphical editor / browser
             field) are named in R.7 — GTK-entry rows from P1.M4.T5 are supporting matrix
             rows, but the named trio comes from the M5.T2 registers. Never claim 'works on
             Wayland' from one row."

# MUST READ — the parallel G5 contract (condition C's input; may be absent at implementation).
- file: plan/008_a47116bb2b79/P1M6T4S1/PRP.md
  why: "Deliverable 7 commits tests/G5_TIMING_EVIDENCE.md with per-route rows honestly
        labeled 'pass | fail(reason) | blocked(reason)' and no over-claiming ('a lab that
        never ran is not run, never passed'). Condition C parses THAT format; if the file
        is absent (task in flight), C = not-run and the gate stays closed — correct behavior."
  critical: "Treat this PRP as a contract. Do NOT re-run or modify the G5 lab; only read
             its report. Do not block on it — an absent report is a valid, recordable state."

# MUST READ — the G3 verdict registers (conditions A and B's inputs; schemas observed).
- file: plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl
  why: "G3 pi-prompt-in-Ghostty rows: {'row','passed','status','detail','versions',
        'evidence'} — observed rows desktop-boot, census-pre-drive, short-insert-1 …;
        ghostty 1.4.0-arch2 in versions. Condition A requires the insert AND correct row
        classes here, all passed."
- file: plan/008_a47116bb2b79/architecture/editor_browser_row_verdicts.jsonl
  why: "G3 graphical-editor + browser rows: {'row','sub','pass','checks','t_ms','oracle',…}
        — observed editor-short-updates, editor-firstword-20sent …; 'checks': [] = clean.
        Enumerate actual row values for the browser class (naming caveat, research §2)."
- file: plan/008_a47116bb2b79/architecture/g2_gate_record.md   # condition B input
- file: plan/008_a47116bb2b79/architecture/g3_pi_prompt_row.md # narrative cross-reference
- file: plan/008_a47116bb2b79/architecture/g3_editor_browser_rows.md

# MUST READ — the flip surface + lockstep guard.
- file: voice_typing/config.py
  why: ":147 delivery: str = \"stream-edit\" (the default + comment block :147-153 — the
        comment-pointer touch); :174-186 value validation (both values stay legal);
        ~:400-430 VoiceTypingConfig.__post_init__ precondition triple (bulk-text requires
        streaming=true + graceful_stop=false + keypress_action='disarm'; collected into ONE
        ValueError) — BYTE-IDENTICAL on both paths; current defaults already satisfy it."
  critical: "Do NOT touch the validation or the triple. If flipping, the default value must
             still load through from_toml(repo config.toml) — the triple holds at defaults
             (config.toml :31/:49/:54); verify with the config suites."
- file: config.toml
  why: ":50 delivery = \"stream-edit\" + its comment (the 'Opt-in … until G6 graduation'
        sentence becomes a pointer to tests/G6_GRADUATION.md + the verdict); :31
        graceful_stop=false, :49 streaming=true, :54 keypress_action=\"disarm\" (the triple
        at defaults)."
- file: tests/test_config.py
  why: ":58 the ONE default-pinning assertion (assert cfg.output.delivery == \"stream-edit\"
        # P1.M3.T3.S1 … opt-in until G6 graduation) — the only test line that changes on the
        flip path. :400-421 delivery value/type validation tests — untouched."
- file: tests/test_config_repo_default.py
  why: "The repo-default lockstep guard (test_repo_config_toml_equals_defaults, ~:17)
        compares config.toml to the dataclass defaults — it AUTO-ADAPTS to a lockstep flip
        and goes RED if only one side flips. NO structural edit; optional comment touch only
        (duck precedent, its PRP @138-139)."

# MUST READ — the default-flip precedent (pattern to follow verbatim).
- file: plan/008_a47116bb2b79/P1M2T4S1/PRP.md
  why: "The duck_mode 'off'→'mpris' flip WITH evidence: 2-file value flip + 1 test line +
        evidence script + evidence doc; commit 22009a0's message models the
        claims-are-recorded-not-assessed discipline. Its Gotcha #1 (lockstep) and its
        validation gates are the template for the flip path here."

# External — none required (all inputs are in-repo committed artifacts; no new libraries).
```

### Current Codebase tree (state at P1.M7.T1.S1 start)

```bash
/home/dustin/projects/voice-typing/
├── PRD.md                       # READ-ONLY (R.7 G6 + R.2 + §7.13 + §6 T9 = the contract)
├── config.toml                  # :50 delivery = "stream-edit" (+comment; the flip site 2)
├── voice_typing/config.py       # :147 default (+comment); :400-430 triple (UNTOUCHED)
├── tests/
│   ├── test_config.py           # :58 default pin (flip site 3)
│   ├── test_config_repo_default.py  # lockstep guard (auto-adapts; no structural edit)
│   ├── G1_BASELINE.md  D1_DUCK_EVIDENCE.md  ACCEPTANCE.md   # evidence-doc precedents (READ)
│   ├── g5_timing_lab.py …       # G5 harness (P1.M6.T4.S1, parallel; DO NOT touch)
│   └── (G5_TIMING_EVIDENCE.md)  # may not exist yet — valid input state for condition C
├── plan/008_a47116bb2b79/
│   ├── architecture/
│   │   ├── pi_row_verdicts.jsonl            # G3 pi/ghostty rows   (condition A/B input)
│   │   ├── editor_browser_row_verdicts.jsonl# G3 editor+browser    (condition A/B input)
│   │   ├── g2_gate_record.md                # G2 record            (condition B input)
│   │   └── g3_*.md …                        # narratives (cross-ref)
│   └── P1M6T4S1/PRP.md          # the G5 contract (parallel item)
└── (no G6 artifacts yet — this task creates them)
```

### Desired Codebase tree with files to be added

```bash
tests/
├── g6_assessment.py            # NEW — mechanical G6 verdict engine + CLI (pure stdlib)
├── test_g6_assessment.py       # NEW — unit tests of the decision logic (synthetic fixtures)
├── G6_WRITING_SESSIONS.md      # NEW — EMPTY operator template (zero entries; the honesty seam)
└── G6_GRADUATION.md            # NEW — the bounded committed assessment (the DOCS deliverable)
# CONDITIONAL (flip path only): config.py:147 value, config.toml:50 value, test_config.py:58 pin.
# UNCONDITIONAL comment-pointer touch: config.py:147-153 comment, config.toml:50 comment.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (G1) — NEVER write session entries. The ≥3 × >110-wpm writing sessions are
#   OPERATOR-dependent evidence (R.2: "never fabricate user acceptance"). The implementer
#   ships the template EMPTY and records condition D unmet. Inventing even one entry is the
#   single forbidden failure of this task. An honest "unmet" is a fully successful delivery.

# CRITICAL #2 (G2) — absent/unparsable evidence is UNMET, never passed. If
#   tests/G5_TIMING_EVIDENCE.md does not exist yet (P1.M6.T4.S1 in flight), condition C =
#   not-run(report absent) and the decision is STAY OPT-IN. A transport probe (tools/paste-lab,
#   tools/im-lab mechanism evidence) NEVER substitutes for G3/G5/G6 rows (R.2, verbatim).

# CRITICAL #3 (G3) — LOCKSTEP: on the flip path, config.py:147 + config.toml:50 +
#   test_config.py:58 change in the SAME change; test_repo_config_toml_equals_defaults is the
#   guard (red if only one side moves — that red is the guard working). The key-set pin count
#   does not change (no keys added/removed). Duck precedent: commit 22009a0 / P1M2T4S1 PRP.

# CRITICAL #4 (G4) — the precondition triple (config.py ~:400-430) is BYTE-IDENTICAL on both
#   paths. Do not "relax" it to make the flip load; it already holds at the current defaults
#   (streaming=true, graceful_stop=false, keypress_action="disarm" — config.toml :49/:31/:54).
#   Verify via the config suites after any flip; never via code change.

# CRITICAL #5 (G5) — do not modify ANY evidence artifact: the verdict jsonls, the G2 record,
#   the G5 report, the G3 narratives are READ-ONLY inputs (they are other items' committed
#   evidence). The assessment doc QUOTES counts/paths; it never rewrites sources. If a
#   register's format surprises you (e.g. browser row names differ from the observed
#   prefixes), ADAPT THE PARSER, never the data.

# CRITICAL #6 (G6) — bounded doc discipline: tests/G6_GRADUATION.md carries counts, paths,
#   verdicts, provenance — no log dumps, no full jsonl copies (AGENTS.md Rule 3 spirit).
#   Per-condition rows use only verified | unmet | not-run(reason).

# CRITICAL #7 (G7) — the script is NOT a lab: no CUDA, no desktop, no compositor, no
#   journalctl live-polling, no service control. Everything it reads is a committed file
#   (journal review, if any, is pasted by the operator into the doc as an attested field).
#   It must run green under `timeout 60` on a bare checkout (modulo the optional inputs).

# CRITICAL #8 (G8) — exit-code semantics: the script exits 0 for BOTH decisions. STAY
#   OPT-IN is a recorded verdict, not an error; do not make CI/future runs treat it as red.

# CRITICAL #9 (G9) — AGENTS.md timeout discipline applies to every command you run
#   (pytest under timeout 300-600; the script under timeout 60; voicectl never needed here).

# CRITICAL #10 (G10) — pytest collection: name the engine module so pytest does NOT collect
#   its __main__ (tests/test_g6_assessment.py holds the tests; tests/g6_assessment.py has an
#   if __name__ == "__main__": guard — repo pattern in every lab/script).
```

## Implementation Blueprint

### Data models and structure

No ORM/pydantic. The "model" is the assessment's condition results (pure dataclasses or
NamedTuples in `tests/g6_assessment.py`):

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class ConditionResult:
    condition: str          # "A-g3-matrix" | "B-integrity" | "C-g5-timing" | "D-sessions"
    verdict: str            # "verified" | "unmet" | "not-run"
    reason: str             # "" when verified; else the specific missing/failed evidence
    evidence: tuple[str, ...] = ()   # paths/counts quoted (never full contents)

@dataclass(frozen=True)
class Assessment:
    results: tuple[ConditionResult, ...]
    @property
    def flip(self) -> bool:
        return all(r.verdict == "verified" for r in self.results)
    @property
    def decision_line(self) -> str:
        unmet = [r.condition for r in self.results if r.verdict != "verified"]
        return "G6 DECISION: FLIP" if self.flip else \
               f"G6 DECISION: STAY OPT-IN (unmet: {', '.join(unmet)})"
```

Session-entry model (parsed from `G6_WRITING_SESSIONS.md` under a strict format):

```python
@dataclass(frozen=True)
class WritingSession:
    date: str            # YYYY-MM-DD
    minutes: float       # wall-clock session duration
    raw_words: int
    correction_min: float    # time spent correcting
    recovery_min: float      # time spent recovering (re-arming, cancel-respeak, freeze)
    rereading_min: float     # time spent proofreading/rereading
    @property
    def usable_wpm(self) -> float:
        # usable proofread wpm: raw words over (duration - corrections - recovery - rereading)
        # ... the accounting rules are documented in the template itself; the parser computes
        # and the template's example (commented) shows the arithmetic.
    attributed: str     # operator attribution line (e.g. "operator: dustin") — REQUIRED
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — inventory the inputs (read-only; no mutation).
  - RUN (from /home/dustin/projects/voice-typing):
      for f in plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl \
               plan/008_a47116bb2b79/architecture/editor_browser_row_verdicts.jsonl \
               plan/008_a47116bb2b79/architecture/g2_gate_record.md \
               tests/G5_TIMING_EVIDENCE.md tests/G6_WRITING_SESSIONS.md; do
        [ -f "$f" ] && echo "present: $f ($(wc -l < "$f") lines)" || echo "ABSENT: $f"
      done
      python3 - <<'PY'
      import json
      for p in ("plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl",
                "plan/008_a47116bb2b79/architecture/editor_browser_row_verdicts.jsonl"):
          rows=[json.loads(l) for l in open(p) if l.strip()]
          print(p.split('/')[-1], "rows:", [r["row"] for r in rows])
          print("  pass field:", "passed" if "passed" in rows[0] else "pass",
                "| all passed:", all(r.get("passed", r.get("pass")) for r in rows))
      PY
      grep -n 'delivery' voice_typing/config.py | head -3; grep -n 'delivery' config.toml
      sed -n '58p' tests/test_config.py
  - EXPECTED: both jsonls present + row names enumerated (derive the required-row classes
    from THIS output — research §2 caveat); g2_gate_record.md present; G5_TIMING_EVIDENCE.md
    possibly ABSENT (valid); G6 files absent; the three flip sites at the cited lines.
  - DO NOT: create/edit any file yet.

Task 1: CREATE tests/g6_assessment.py — the verdict engine (Blueprint data models above).
  - IMPLEMENT: load_pi_rows()/load_editor_browser_rows() (jsonl, tolerant of the two pass
    field names "passed"/"pass"; collect failures from "checks" non-empty); condition A
    (all rows passed + required row classes present — classes derived from Task 0's
    enumeration: pi ghostty insert+correct, graphical editor insert+correct, browser
    insert+correct); condition B (zero failed rows + g2_gate_record.md readable with no
    recorded failing trace); condition C (G5 report: exists, format matches the G5 PRP's
    per-route verdict rows, all "pass", zero fail/blocked — absent/unparsable ⇒ not-run,
    NEVER verified); condition D (sessions template: strict-format parser, ≥3 valid entries
    each usable_wpm > 110 with attribution — absent/empty/insufficient ⇒ unmet);
    Assessment + decision_line; main() prints the block + decision, exit 0 either way;
    if __name__ == "__main__" guard.
  - FOLLOW pattern: tests/g5_timing_support.py (pure-stdlib metrics/engine module imported
    by its test file — the sibling G5 PRP's deliverable 3; read it if present, else the
    plain-script pattern of tests/clipboard_g4_support.py).
  - NAMING: snake_case functions assess_*(); module docstring cites PRD R.7 G6 + this item.
  - PLACEMENT: tests/ (beside the other evidence tooling).
  - HARD RULES: no writes anywhere by default (stdout only); no edits to inputs; no
    network/CUDA/desktop; runs green with G5/sessions inputs absent.

Task 2: CREATE tests/test_g6_assessment.py — decision-logic unit tests (synthetic fixtures).
  - IMPLEMENT (tmp_path fixtures writing synthetic jsonls/md):
    test_all_conditions_met_yields_flip; test_sessions_file_absent_stays_opt_in;
    test_sessions_fewer_than_three_stays_opt_in; test_session_at_or_below_110_wpm_stays_opt_in;
    test_failed_g3_row_stays_opt_in; test_missing_g3_row_class_stays_opt_in;
    test_g5_report_absent_is_not_run_and_stays_opt_in; test_g5_unparsable_is_not_run;
    test_g5_failed_route_stays_opt_in; test_g2_record_missing_or_failing_stays_opt_in;
    test_transport_probe_evidence_never_counts (a sessions/G5 file citing only probe runs
    with no valid entries still ⇒ unmet); test_decision_line_format; test_exit_zero_both_ways
    (subprocess run of the module main on a synthetic dir, or main() return-code contract).
  - FOLLOW pattern: tests/test_g2_bulk_gate.py / tests/test_config.py (plain pytest, tmp_path,
    explicit asserts on messages).
  - COVERAGE: every branch of every condition; the absent-input paths are the point.
  - PLACEMENT: tests/.

Task 3: CREATE tests/G6_WRITING_SESSIONS.md — the EMPTY operator template.
  - CONTENT: title + purpose (G6 condition D evidence); THE RULE (entries are written by the
    OPERATOR only — automation/implementers must never add entries; entries lacking
    attribution are invalid); the entry format (date, duration_min, raw_words,
    correction_min, recovery_min, rereading_min, usable_wpm, attribution, notes); the
    accounting definition (usable proofread wpm = raw_words / (duration − corrections −
    recovery − rereading), in minutes — counting corrections, recovery, rereading per R.7);
    a commented-out EXAMPLE entry (clearly marked do-not-uncomment-as-evidence); then the
    literal line "## Recorded sessions" followed by "*(none on record)*".
  - HARD RULE: zero live entries. This file is the honesty seam (G1).

Task 4: RUN the assessment + CREATE tests/G6_GRADUATION.md — the bounded record.
  - RUN: timeout 60 .venv/bin/python tests/g6_assessment.py
  - CREATE the doc FROM the script's real output: header (date, HEAD sha, environment
    provenance: kernel/compositor/GPU as recorded in the G3/G5 artifacts); one row per
    condition (verdict + evidence paths + counts); the decision line verbatim; the
    consequence section (which path executed and what changed); outstanding-inputs section
    (exactly what a future re-run needs — e.g. "operator: record ≥3 sessions in
    tests/G6_WRITING_SESSIONS.md; then re-run tests/g6_assessment.py and execute the flip
    path per plan/008_a47116bb2b79/P1M7T1S1/PRP.md"); the operator journal-review attested
    field (explicitly "(not reviewed)" unless the operator provided one — never invent).
  - BOUNDED: counts + paths + verdicts only (G6 gotcha).

Task 5 (CONDITIONAL — ONLY on G6 DECISION: FLIP): the lockstep default flip.
  - MODIFY voice_typing/config.py:147 — `delivery: str = "stream-edit"` → `delivery: str =
    "bulk-text"`; update the :147-153 comment (graduated per G6, point at the doc).
  - MODIFY config.toml:50 — `delivery    = "stream-edit"` → `delivery    = "bulk-text"`;
    update the comment (same pointer).
  - MODIFY tests/test_config.py:58 — the pin asserts "bulk-text"; comment cites G6 doc.
  - SAME CHANGE (lockstep, G3); precondition triple untouched (G4); run the config suites
    (Validation L2) — from_toml(repo default) must load clean through the triple.
  - IF the decision is STAY OPT-IN (expected): SKIP this task entirely; do ONLY the
    comment-pointer touch on config.py:147-153 + config.toml:50 (values unchanged) so the
    shipped default points at the assessment verdict.

Task 6: VALIDATE — run the Validation Loop L1–L4; iterate until green. No git commit unless
  the orchestrator directs it. If asked, message:
  "P1.M7.T1.S1: G6 graduation assessment (+conditional delivery default flip per verdict)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — absent/unparsable evidence is UNMET, never passed (the core honesty rule):
def assess_g5(report_path: Path) -> ConditionResult:
    if not report_path.is_file():
        return ConditionResult("C-g5-timing", "not-run",
                               f"G5 report absent ({report_path}; P1.M6.T4.S1)")
    verdicts = parse_route_verdicts(report_path.read_text())  # match the G5 report format
    if verdicts is None:
        return ConditionResult("C-g5-timing", "not-run", "cannot parse report format")
    if any(v != "pass" for v in verdicts.values()):
        failed = [r for r, v in verdicts.items() if v != "pass"]
        return ConditionResult("C-g5-timing", "unmet", f"failing/blocked routes: {failed}")
    return ConditionResult("C-g5-timing", "verified", "",
                            tuple(f"{report_path}:{r}=pass" for r in verdicts))

# PATTERN 2 — sessions entries are operator-only; the parser enforces attribution:
#   an entry without an "attributed:" line is INVALID and never counts toward the ≥3.
#   usable_wpm = raw_words / max(minutes - correction - recovery - rereading, eps) — the
#   exact accounting the template documents; > 110 STRICTLY (110.0 does not beat 110).

# PATTERN 3 — decision is pure data; exit code carries no verdict:
#   print(assessment block); print(assessment.decision_line); sys.exit(0)  # both paths (G8)

# PATTERN 4 — lockstep flip (flip path only; duck precedent 22009a0):
#   config.py:147  delivery: str = "bulk-text"   # graduated per G6 — tests/G6_GRADUATION.md
#   config.toml:50 delivery    = "bulk-text"     # (same pointer comment)
#   tests/test_config.py:58  assert cfg.output.delivery == "bulk-text"
#   -> test_repo_config_toml_equals_defaults auto-adapts; red means one side missed (G3).
```

### Integration Points

```yaml
CONFIG (flip path only):
  - voice_typing/config.py:147 — OutputConfig.delivery default "stream-edit" -> "bulk-text"
  - config.toml:50 — the same value in the shipped default file (lockstep guard: tests/
    test_config_repo_default.py::test_repo_config_toml_equals_defaults)
  - tests/test_config.py:58 — the single default-pinning assertion
  - UNTOUCHED: config.py:174-186 (value validation — both values remain legal) and
    ~:400-430 (precondition triple — still enforced at the new default; it holds at the
    current streaming/graceful_stop/keypress_action defaults).

EVIDENCE (read-only inputs; never modified):
  - plan/008_a47116bb2b79/architecture/{pi_row_verdicts,editor_browser_row_verdicts}.jsonl
  - plan/008_a47116bb2b79/architecture/g2_gate_record.md (+ g3_*.md narratives)
  - tests/G5_TIMING_EVIDENCE.md (P1.M6.T4.S1; may be absent at run time)

DOWNSTREAM CONSUMERS:
  - P1.M7.T2.S1/S2 (docs sync): README bulk-delivery section + tests/ACCEPTANCE.md rows cite
    tests/G6_GRADUATION.md's verdict verbatim — do not soften "unmet" into prose optimism.
  - The operator: records future session evidence in tests/G6_WRITING_SESSIONS.md; a re-run
    of tests/g6_assessment.py re-derives the decision mechanically.

NO database. NO new dependencies. NO daemon/controller/adapter changes. NO service control.
```

## Validation Loop

> Run from `/home/dustin/projects/voice-typing`. AGENTS.md timeout discipline on everything.
> This task never touches the live desktop, the real clipboard, the microphone, or the
> running service — all validation is unit tests + file greps + the script itself.

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
uv run ruff check tests/g6_assessment.py tests/test_g6_assessment.py --fix
uv run ruff format tests/g6_assessment.py tests/test_g6_assessment.py
# Expected: clean. (No mypy in this repo's gates; ruff + pytest are the L1/L2 standard.)
grep -q 'if __name__ == "__main__"' tests/g6_assessment.py && echo "main guard OK"   # G10
```

### Level 2: Unit Tests (Component Validation)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 uv run pytest tests/test_g6_assessment.py -q          # the new decision-logic suite
# Flip path only — the lockstep + triple gates after Task 5:
timeout 600 uv run pytest tests/test_config.py tests/test_config_repo_default.py -q
# Expected: all green. On the flip path the repo-default lockstep test proves both config
# files moved together and the default config still loads through the precondition triple.
```

### Level 3: The Assessment Run (Integration — real artifacts)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python tests/g6_assessment.py
# Expected: per-condition block + decision line, exit 0. Cross-check by hand:
#   - condition A rows/counts vs `python3 -c "import json;print([json.loads(l)['row'] for l in open('plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl') if l.strip()])"`
#   - the decision matches the doc you committed (G6_GRADUATION.md quotes it verbatim).
# STAY-OPT-IN invariant (expected landing):
grep -n 'delivery: str = "stream-edit"' voice_typing/config.py        # still line ~147
grep -n 'delivery    = "stream-edit"' config.toml                     # still line ~50
sed -n '58p' tests/test_config.py                                     # pin unchanged
git status --porcelain | grep -vE '^\?\? (tests/g6_|tests/G6_|plan/)' && echo "CHECK: unexpected modified files" || echo "OK: only new files + sanctioned touches"
```

### Level 4: Honesty & Domain Audit (the gate this task exists to enforce)

```bash
cd /home/dustin/projects/voice-typing
# (a) No fabricated sessions: the template has zero entries and no entry exists anywhere in the diff.
grep -c '^| 20' tests/G6_WRITING_SESSIONS.md 2>/dev/null || echo "0 session entries (expected)"
git diff | grep -iE 'usable_wpm|attributed' && echo "CHECK: diff must not add session data" || echo "OK: no session data in diff"
# (b) No evidence artifact was edited:
git status --porcelain plan/008_a47116bb2b79/architecture/ && echo "CHECK: architecture evidence modified!" || echo "OK: evidence untouched"
# (c) No over-claiming language in the doc:
grep -inE 'works on wayland|fully verified|production-ready' tests/G6_GRADUATION.md && echo "CHECK: over-claim phrasing" || echo "OK: bounded claims"
grep -c 'not-run\|unmet\|verified' tests/G6_GRADUATION.md   # per-condition verdicts present
# (d) G1 watch set unaffected (quick sweep):
timeout 600 uv run pytest tests/test_zero_diff_rewind.py tests/test_config_repo_default.py -q
# Expected: zero session entries; evidence untouched; only sanctioned verdict vocabulary;
# watch set green.
```

## Final Validation Checklist

### Technical Validation

- [ ] L1: ruff clean on both new python files; main-guard present.
- [ ] L2: `tests/test_g6_assessment.py` green (every decision branch); on the flip path,
      config suites green (lockstep + triple).
- [ ] L3: the script runs under `timeout 60` on the real artifacts; decision line matches
      the committed doc verbatim; exit 0.
- [ ] L4: honesty audit green (no session data in the diff; evidence untouched; bounded
      vocabulary; watch set green).

### Feature Validation

- [ ] All four conditions assessed with explicit verdicts (`verified | unmet | not-run`).
- [ ] STAY-OPT-IN landing: default value unchanged at all three sites; comment pointers land.
- [ ] FLIP landing (only iff decision FLIP): three-site lockstep flip; key-set pin count
      unchanged; default config loads through the precondition triple.
- [ ] `tests/G6_GRADUATION.md` committed with provenance + outstanding-inputs section.
- [ ] `tests/G6_WRITING_SESSIONS.md` committed EMPTY (zero entries).

### Code Quality Validation

- [ ] Pure-stdlib engine; no writes; no network/CUDA/desktop; runs with optional inputs absent.
- [ ] Naming/placement follow the repo's tests/ tooling conventions; pytest does not collect
      the engine's main.
- [ ] No edits to PRD.md / tasks.json / prd_snapshot.md / .gitignore / daemon sources /
      evidence artifacts; no README or ACCEPTANCE.md changes (P1.M7.T2 owns them).

### Documentation & Deployment

- [ ] The assessment doc is the single source of truth for bulk-delivery's graduation status;
      P1.M7.T2 consumes it verbatim.
- [ ] The config comments point at the doc on both paths.
- [ ] No new env vars, deps, or service changes.

---

## Anti-Patterns to Avoid

- ❌ Don't write, seed, or "example-fill" session entries — fabricated user acceptance is THE
  forbidden failure (G1). An honest `unmet` is a complete success for this item.
- ❌ Don't treat an absent G5 report (parallel item in flight) as a pass, a blocker, or a
  reason to wait — record `not-run(report absent)` and proceed (G2/G8).
- ❌ Don't let transport-probe or lab-mechanism evidence count for G3/G5/G6 rows (R.2).
- ❌ Don't flip one config site without the others in the same change (lockstep, G3) and
  don't touch the validation or the precondition triple to "make it load" (G4).
- ❌ Don't edit any verdict jsonl / gate record / G5 report to tidy the data — adapt the
  parser (G5).
- ❌ Don't make STAY-OPT-IN a nonzero exit or a CI failure — it is recorded data (G8).
- ❌ Don't dump logs or full registers into the graduation doc — counts + paths + verdicts (G6).
- ❌ Don't run the daemon, touch the service, journalctl-poll, or boot a compositor from the
  assessment script (G7); the operator's journal review is an attested doc field only.
- ❌ Don't write README/ACCEPTANCE.md content — P1.M7.T2.S1/S2 own the docs sync.

---

## Confidence Score

**9/10** for one-pass implementation success. Every input artifact is named with its exact
path and observed schema (both jsonls read this session; the G2 record and narratives
listed; the G5 report's contract pinned by the parallel PRP); the decision logic is fully
specified including the two rules that make it honest (absent/unparsable ⇒ unmet;
operator-only session entries); the flip mechanics cite exact file:line sites
(`config.py:147`, `config.toml:50`, `tests/test_config.py:58`) with the in-repo precedent
commit (`22009a0`) and its PRP as the pattern; and the expected landing (STAY OPT-IN,
comment pointers only) requires zero runtime-behavior change, so the riskiest surface —
a value flip — is precisely the branch that the evidence gate will not open today. The −1
residual: the G5 report format arrives from the parallel item and the browser-row names in
`editor_browser_row_verdicts.jsonl` were not enumerated in this session — both are handled
by design (defensive parse ⇒ not-run; derive required-row classes from Task 0's preflight
enumeration), so the failure mode is an honest `not-run`, never a false pass.
