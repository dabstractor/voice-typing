# PRP — P1.M1.T1.S1: Audit config dataclass fields & defaults against PRD §4.5 schema

## Goal

**Feature Goal**: Produce an authoritative **gap report** (`plan/006_862ee9d6ef41/architecture/gap_config.md`) cross-checking EVERY `voice_typing/config.py` dataclass field (name, type, default) and the repo `config.toml` against the PRD §4.5 schema, plus confirm the `__post_init__` type-validation and unknown-key rejection behave per spec. This is a **verification/audit** subtask: the deliverable is the report; code changes happen ONLY if a real gap is found.

**Deliverable**: One report at `plan/006_862ee9d6ef41/architecture/gap_config.md` containing: (a) a per-field compliance table (PRD §4.5 expected vs config.py actual vs config.toml actual); (b) the validation-logic audit; (c) the test pass/fail counts; (d) a mismatches section; (e) a conclusion. **This PRP's author has already performed the audit** (findings embedded below) — the implementing agent's job is to re-verify and transcribe, then write the report.

**Success Definition**: (a) the gap report exists at the prescribed path with all required sections; (b) its findings match the verified audit below (all 19 scalar fields compliant; blocklist is an intentional VT-006 deviation, not a gap; 37 config tests pass); (c) the prescribed re-verification commands reproduce the results; (d) **no source files are modified** (because no real gap exists — see Anti-Patterns); (e) the report explicitly records the blocklist VT-006 deviation so no future agent "fixes" it.

## User Persona

**Target User**: The verification round's orchestrator and future maintainers who need a durable, evidence-backed record that the config schema matches the PRD (or, if a real gap existed, that it was fixed).

**Use Case**: Reviewing the gap report to confirm PRD §4.5 compliance before declaring the config layer done, and to understand WHY the blocklist differs from PRD §4.5's literal text.

**Pain Points Addressed**: Closes the "is the config schema actually PRD-compliant?" question with evidence; documents the one place the implementation intentionally diverges from the PRD's literal text (VT-006) so it isn't mistaken for drift.

## Why

- **Verification round mandate (system_context.md §"This round is verification, gap-analysis, and remediation — NOT greenfield build"):** confirm the existing, coded config layer matches PRD §4.5 before relying on it.
- **Catch silent drift:** the repo drift-guard test only checks `config.py ↔ config.toml` AGREEMENT — it does NOT check PRD compliance, so a field where BOTH drift from the PRD (or an intentional deviation) is invisible to the existing tests. This audit is the human/agent check that closes that gap.
- **Document intentional deviations:** the blocklist diverges from PRD §4.5's literal 5-entry list, but deliberately (VT-006). The report must record this as compliant-by-design, not as a defect to "fix" — otherwise a future agent re-introduces a real UX bug (see Anti-Patterns #1).
- **Lowest-risk outcome:** the audit (already done) finds everything compliant → no code changes → zero regression risk.

## What

Run the field/default cross-check (method below), confirm the validation logic, run the config tests, and write the gap report. **No code changes are expected** (the audit finds all-compliant). If — and only if — the re-verification surfaces a REAL mismatch not covered by the VT-006 deviation, fix it in config.py AND config.toml so both agree with PRD §4.5; otherwise record "none — config.toml already mirrors config.py per audit."

### Success Criteria

- [ ] `plan/006_862ee9d6ef41/architecture/gap_config.md` exists with: compliance table, validation audit, test counts, mismatches, conclusion.
- [ ] The report records all 19 scalar fields as compliant with PRD §4.5.
- [ ] The report records the blocklist VT-006 deviation as intentional/documented/tested (NOT a gap).
- [ ] `.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q` → 37 passed (reproduced).
- [ ] No source files modified (config.py/config.toml unchanged) UNLESS the re-verification finds a real, non-VT-006 mismatch.

## All Needed Context

### Context Completeness Check

_Pass._ This PRP's author has already executed the audit against the live code; every finding below is verified with the exact command and value. The implementing agent re-runs the commands to confirm, then transcribes the results into the report. No further investigation is required.

### VERIFIED AUDIT FINDINGS (already performed — transcribe into the report)

**Method used (re-run to confirm):** programmatically dump every dataclass field (name/type/default) via `dataclasses.fields(...)`; parse `config.toml` via `tomllib`; compare each to the PRD §4.5 block (quoted in `selected_prd_content`).

**1. Field/default compliance — ALL MATCH PRD §4.5:**

| Section.field | PRD §4.5 | config.py default | config.toml | Match |
|---|---|---|---|---|
| asr.final_model | "distil-large-v3" | 'distil-large-v3' | "distil-large-v3" | ✅ |
| asr.realtime_model | "small.en" | 'small.en' | "small.en" | ✅ |
| asr.lite_model | "small.en" | 'small.en' | "small.en" | ✅ |
| asr.language | "en" | 'en' | "en" | ✅ |
| asr.device | "cuda" | 'cuda' | "cuda" | ✅ |
| asr.post_speech_silence_duration | 0.6 | 0.6 | 0.6 | ✅ |
| asr.lite_post_speech_silence_duration | 0.5 | 0.5 | 0.5 | ✅ |
| asr.realtime_processing_pause | 0.15 | 0.15 | 0.15 | ✅ |
| asr.auto_stop_idle_seconds | 30.0 | 30.0 | 30.0 | ✅ |
| asr.auto_unload_idle_seconds | 1800.0 | 1800.0 | 1800.0 | ✅ |
| output.backend | "wtype" | 'wtype' | "wtype" | ✅ |
| output.tmux_target | "" | '' | "" | ✅ |
| output.append_space | true | True | true | ✅ |
| feedback.state_file | "" | '' | "" | ✅ |
| feedback.hypr_notify | true | True | true | ✅ |
| feedback.notify_on_final | true | True | true | ✅ |
| feedback.notify_ms | 2500 | 2500 (int) | 2500 | ✅ |
| filter.min_chars | 2 | 2 (int) | 2 | ✅ |
| filter.blocklist | PRD §4.5 lists 5 (incl. "you") | 4-entry (NO "you") | 4-entry (NO "you") | ⚠️ INTENTIONAL DEV (VT-006) — see below |
| log.level | "INFO" | 'INFO' | "INFO" | ✅ |

**2. The blocklist is an INTENTIONAL, DOCUMENTED deviation (VT-006) — NOT a gap to fix:**
- PRD §4.5's literal blocklist has 5 entries incl. `"you"`. config.py + config.toml + the test all use **4 entries (no `"you"`)**.
- This is deliberate (VT-006): `"you"` is a common word users want to type as a standalone utterance; the blocklist matches on the punctuation/case-normalized form, so a blanket `"you"` entry silently dropped dictating the single word "you" with no feedback. The blocklist's job is multi-word silence hallucinations; a lone `"you"` is not one.
- Documented in THREE places:
  - `voice_typing/config.py:191` — `NOTE (VT-006)` on the `blocklist` field.
  - `config.toml:67` — `# NOTE (VT-006): the bare "you" entry was removed …`.
  - `tests/test_config.py:24` — `_PRD_BLOCKLIST` defined as the 4-entry list with the VT-006 comment, and `test_config.py:64 assert cfg.filter.blocklist == _PRD_BLOCKLIST` PINS it.
- **Adding `"you"` back would (a) break `test_config.py:64`, (b) contradict the documented VT-006 decision, and (c) re-introduce the silent-drop UX bug.** The report must record this as compliant-by-design.

**3. Validation logic audit (all present and correct):**
- `AsrConfig.__post_init__` (config.py:72) — numeric tuple (`for _name in (...)` at ~:85): `post_speech_silence_duration`, `lite_post_speech_silence_duration`, `realtime_processing_pause`, `auto_stop_idle_seconds`, `auto_unload_idle_seconds` → rejects `bool` (int subclass) + non-numeric with `TypeError`. String tuple (:99): `final_model`, `realtime_model`, `lite_model`, `language`, `device` → rejects non-str with `TypeError`.
- `FeedbackConfig.__post_init__` (config.py:140) — validates `notify_ms` is a genuine int (rejects bool) with `TypeError`.
- **Unknown-key rejection:** `config.py:232` (docstring "Unknown keys raise TypeError (dataclass __init__ rejects them)") + the Mapping check at `:241` → a typo'd key raises `TypeError` at load.
- `compute_type` is correctly NOT a config field (config.py:20 documents it as a cuda_check concern).

**4. Test results (re-run to confirm):** `.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q` → **37 passed**.

**5. Conclusion:** All fields compliant with PRD §4.5. The single divergence (blocklist `"you"`) is an intentional, documented, tested design decision (VT-006). **No code changes required.** config.toml mirrors config.py.

### Documentation & References

```yaml
# THE SPEC BEING AUDITED AGAINST
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: §4.5 is the authoritative config schema (field names + defaults + the blocklist). The
       selected_prd_content in this PRP quotes it verbatim. Compare every field against this.
  critical: "PRD §4.5's blocklist lists 5 entries incl. 'you'. The implementation intentionally
            omits 'you' (VT-006). The audit must NOT call that a defect."

# THE CODE UNDER AUDIT
- file: voice_typing/config.py
  why: AsrConfig/OutputConfig/FeedbackConfig/FilterConfig/LogConfig dataclasses + __post_init__
        validation (72, 140) + unknown-key rejection (232/241). Dump fields via dataclasses.fields.
  pattern: "Fields are `name: type = default` (blocklist uses field(default_factory=lambda: [...])).
            __post_init__ raises TypeError on wrong types; unknown keys raise TypeError at load."
  gotcha: "compute_type is NOT here (cuda_check concern, documented at config.py:20). Don't flag its
           absence as a gap."

- file: config.toml
  why: The repo default that mirrors config.py (drift-guard-enforced). Parse with tomllib to compare
        values. The blocklist VT-006 note is at line 67.
  pattern: "Every [section] key mirrors a dataclass field. The drift guard checks agreement, NOT
            PRD compliance — that's why this audit exists."

# THE INTENTIONAL DEVIATION (must be understood, not "fixed")
- file: tests/test_config.py
  why: _PRD_BLOCKLIST (24) is the 4-entry list (VT-006 comment); test_config.py:64 pins
        cfg.filter.blocklist == _PRD_BLOCKLIST. This is why adding "you" back would break the suite.
  critical: "The test's _PRD_BLOCKLIST IS the authoritative pin — it deliberately omits 'you'. Do
            NOT 'reconcile' config.py toward PRD §4.5's 5-entry literal."

# THE EXISTING DRIFT GUARD (what it does + does NOT cover)
- file: tests/test_config_repo_default.py
  why: test_repo_config_toml_equals_defaults (config.py ↔ config.toml equality) +
        test_repo_config_toml_has_no_extra_keys (exact key set). These pass (37 total) but only
        prove config.py==config.toml, NOT PRD compliance. The gap report should note this coverage
        boundary explicitly.

# THE PROJECT CONTEXT
- docfile: plan/006_862ee9d6ef41/architecture/system_context.md
  why: States the config layer is "Fully implemented" (AsrConfig..LogConfig, tomllib loader, type
        validation) and that this round is verification/gap-analysis, not greenfield. Confirms the
        audit's scope (verify, don't rebuild).
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/config.py          # the 5 dataclasses + __post_init__ + from_toml  ← AUDIT (read-only)
├── config.toml                     # repo default mirroring config.py               ← AUDIT (read-only)
├── tests/test_config.py            # _PRD_BLOCKLIST @24; field/default tests         ← AUDIT (read-only)
├── tests/test_config_repo_default.py  # drift guard (config.py↔config.toml)          ← AUDIT (read-only)
└── plan/006_862ee9d6ef41/architecture/
    ├── system_context.md           # context (read-only)
    └── gap_config.md               # ← CREATE (this subtask's deliverable)
```

### Desired Codebase tree with files to be added

```bash
plan/006_862ee9d6ef41/architecture/gap_config.md   # NEW — the gap report (only deliverable)
# NO source changes expected (audit finds all-compliant). config.py/config.toml UNCHANGED.
# (Only if the re-verification finds a REAL non-VT-006 mismatch would config.py+config.toml be edited.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE BLOCKLIST "you" OMISSION IS INTENTIONAL (VT-006), NOT A GAP. PRD §4.5 lists 5
# blocklist entries incl. "you"; config.py + config.toml + tests/test_config.py:_PRD_BLOCKLIST all
# use 4 (no "you"), BY DESIGN. It is documented at config.py:191, config.toml:67, and
# tests/test_config.py:24, and PINNED by test_config.py:64. DO NOT add "you" back — it breaks the
# test, contradicts VT-006, and re-introduces the silent-drop-of-"you" UX bug. Record it in the
# report as compliant-by-design.

# CRITICAL #2 — THE DRIFT GUARD DOES NOT CHECK PRD COMPLIANCE. test_repo_config_toml_equals_defaults
# only proves config.py == config.toml. If BOTH drift from the PRD (or both carry an intentional
# deviation), the guard is green. This audit is the PRD-compliance check that the guard can't be.

# CRITICAL #3 — _PRD_BLOCKLIST (test_config.py:24) IS THE AUTHORITATIVE PIN, not PRD §4.5's literal
# text. The test's name says "PRD §4.5 authoritative blocklist" but it's the VT-006-corrected 4-entry
# version. The implementation matches the test; both deviate from the raw PRD deliberately.

# CRITICAL #4 — compute_type IS NOT A CONFIG FIELD (by design). It's a cuda_check concern
# (config.py:20). Do NOT flag its absence from AsrConfig as a missing field.

# CRITICAL #5 — BLOCKLIST IS A list[str] WITH default_factory (not a plain default). When dumping,
# use field.default_factory (not field.default) to see the value. The factory returns a fresh list
# per instance (test_blocklist_not_shared_between_instances at test_config.py:93 pins this).

# GOTCHA #6 — bool VS int. notify_ms/min_chars are int; append_space/hypr_notify/notify_on_final
# are bool. __post_init__ rejects bool for the int/float fields (bool is an int subclass). The audit
# confirms this rejection works (it's tested in test_config.py).

# GOTCHA #7 — THIS IS A REPORT-FIRST TASK. The deliverable is gap_config.md. Do NOT edit config.py /
# config.toml unless the re-verification finds a REAL mismatch not explained by VT-006. If all
# compliant (expected), record "none — config.toml already mirrors config.py per audit."

# GOTCHA #8 — FULL-PATH DISCIPLINE. Machine aliases python3->uv run. Use .venv/bin/python for the
# dump + pytest. No ruff/mypy in this project.
```

## Implementation Blueprint

### Data models and structure

This task audits data models; it does not change them. The dataclasses under audit are `AsrConfig` (10 fields), `OutputConfig` (3), `FeedbackConfig` (4), `FilterConfig` (2: `min_chars: int`, `blocklist: list[str]` via `default_factory`), `LogConfig` (1), composed in `VoiceTypingConfig` (fields: asr, output, feedback, filter, log).

### Implementation Tasks (ordered)

```yaml
Task 1: RE-VERIFY the audit (reproduce the findings above; do not trust them blindly).
  - RUN the field/default dump:
        .venv/bin/python - <<'PY'
        import dataclasses, tomllib
        from voice_typing import config as c
        from voice_typing.config import _repo_config_path
        for cls in (c.AsrConfig, c.OutputConfig, c.FeedbackConfig, c.FilterConfig, c.LogConfig):
            print(f"[{cls.__name__}]")
            for f in dataclasses.fields(cls):
                d = f"<factory {f.default_factory()!r}>" if f.default_factory is not dataclasses.MISSING else repr(f.default)
                print(f"  {f.name:38} : {f.type!s:12} = {d}")
        with open(_repo_config_path(), "rb") as fh: data = tomllib.load(fh)
        print("config.toml [filter].blocklist:", data["filter"]["blocklist"])
        PY
  - RUN the tests: .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q
  - EXPECT: 37 passed; the dump matches the table in "VERIFIED AUDIT FINDINGS"; blocklist = 4 entries
    (no "you") in BOTH config.py and config.toml.
  - If the dump/test differ from the table above, INVESTIGATE before writing the report (the tree may
    have moved since this audit; reconcile the report with what you observe, and only THEN decide if a
    real fix is warranted — respecting VT-006 for the blocklist).

Task 2: WRITE plan/006_862ee9d6ef41/architecture/gap_config.md (the deliverable).
  - USE the write tool. Structure the report with these sections:
      1. Title + date + scope ("Audit voice_typing/config.py dataclasses + repo config.toml against
         PRD §4.5; P1.M1.T1.S1").
      2. Method (the dataclass.fields dump + tomllib parse + pytest run — quote the commands).
      3. Field/default compliance TABLE (transcribe the table from VERIFIED AUDIT FINDINGS §1 —
         one row per field with PRD §4.5 / config.py / config.toml / Match).
      4. Intentional deviation: filter.blocklist (VT-006). State the 4-vs-5-entry difference, the
         reason, the 3 documentation sites (config.py:191, config.toml:67, test_config.py:24), the
         pinning test (test_config.py:64), and that it is compliant-by-design — NOT a gap. (This is
         the single most important section: it prevents a future agent from re-adding "you".)
      5. Validation logic audit (transcribe §3: AsrConfig.__post_init__ numeric+string tuples,
         FeedbackConfig.notify_ms, unknown-key rejection, compute_type-not-a-field).
      6. Test results: "37 passed (tests/test_config.py + tests/test_config_repo_default.py)".
      7. Mismatches requiring action: "None. All fields compliant; the blocklist deviation is the
         documented VT-006 design decision. config.toml mirrors config.py."
      8. Coverage boundary note: the drift guard checks config.py↔config.toml AGREEMENT only, not
         PRD compliance — this audit is the latter.
  - KEEP IT FACTUAL: cite file:line for every claim. No speculation.

Task 3: VALIDATE (run the gates below). No git commit unless the orchestrator directs it. If asked,
  message: "P1.M1.T1.S1: config schema audit report — all fields PRD §4.5 compliant (blocklist VT-006 intentional)".
  IF (and only if) Task 1 surfaced a REAL, non-VT-006 mismatch: fix it in config.py AND config.toml
  (so the drift guard stays green AND both match PRD §4.5), update config.toml comments (Mode A),
  and record the fix in the report's Mismatches section. (Expected: this branch is NOT taken.)
```

### Implementation Patterns & Key Details

```python
# This is an audit/report task. The "pattern" is disciplined verification + honest reporting:
#   * Dump the actual defaults (don't read the PRD and assume the code matches).
#   * Compare THREE sources: PRD §4.5  vs  config.py default  vs  config.toml value.
#   * Distinguish a REAL gap (both files wrong vs PRD, no design rationale) from an INTENTIONAL
#     deviation (documented + tested + rationale) like VT-006. Only the former gets a fix.
#   * Cite file:line for every claim in the report.
#
# The trap to avoid: a naive "diff config.py defaults vs PRD §4.5 literal text" flags the blocklist
# as a mismatch. It IS a diff — but VT-006 (config.py:191 / config.toml:67 / test_config.py:24) makes
# it deliberate, and test_config.py:64 PINS the 4-entry version. "Fixing" it breaks the test + the UX.
# The report's job is to record this so no one trips the trap later.
```

### Integration Points

```yaml
DOWNSTREAM CONSUMERS (sibling subtasks — NOT S1):
  - P1.M1.T1.S2 "Verify config.toml ↔ config.py schema lockstep & blocklist correctness": S1's
    report feeds S2 — S2 confirms the lockstep (drift guard) and the blocklist correctness, which
    S1 has already established is the VT-006 4-entry version. S1 and S2 together close the config
    audit; S1 = field/default PRD compliance, S2 = lockstep + blocklist-correctness confirmation.
  - P1.M1.T1.S3 "Verify config search-order & XDG resolution path": separate concern (path
    resolution), not covered by S1.

CONFIG LAYER (voice_typing/config.py + config.toml):
  - UNCHANGED by S1 (expected). The audit confirms they already comply with PRD §4.5 (modulo the
    documented VT-006 blocklist deviation). If a real fix were needed, both files would change
    together (the drift guard demands it) — but no fix is expected.

TEST SUITE:
  - test_config.py:64 (_PRD_BLOCKLIST pin) + test_config_repo_default.py (drift guard) are the
    existing guards. S1's report documents their coverage boundary (agreement, not PRD compliance).
```

## Validation Loop

> Full paths for python (machine aliases python3->uv run). No ruff/mypy. The gates verify the REPORT
> exists, is accurate, and that NO source was changed (expected outcome). All commands are read-only
> except writing the report.

### Level 1: The gap report exists and is well-formed

```bash
cd /home/dustin/projects/voice-typing
DOC=plan/006_862ee9d6ef41/architecture/gap_config.md
test -f "$DOC" && echo "L1a PASS: report exists" || echo "L1a FAIL"
echo "--- required sections present ---"
grep -E '^#{1,3} ' "$DOC" | head -30
echo "--- cites the VT-006 blocklist deviation ---"
grep -q 'VT-006' "$DOC" && echo "L1b PASS (VT-006 documented)" || echo "L1b FAIL: VT-006 not mentioned"
echo "--- records compliance conclusion ---"
grep -qi 'compliant\|no.*mismatch\|mirrors config.py' "$DOC" && echo "L1c PASS" || echo "L1c CHECK"
# Expected: report exists; has titled sections; documents VT-006; states all-compliant / no mismatches.
```

### Level 2: The report's findings are reproducible (re-verify the audit)

```bash
cd /home/dustin/projects/voice-typing
echo "--- re-run the config tests (report claims 37 passed) ---"
.venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py -q 2>&1 | tail -3
echo "--- re-dump: every scalar default matches PRD §4.5; blocklist = 4 entries (VT-006) ---"
.venv/bin/python - <<'PY'
import dataclasses, tomllib
from voice_typing import config as c
from voice_typing.config import _repo_config_path, FilterConfig
# spot-check a few PRD-§4.5 defaults + the blocklist
a = c.AsrConfig(); o = c.OutputConfig(); f = c.FeedbackConfig(); fc = FilterConfig(); l = c.LogConfig()
assert a.lite_post_speech_silence_duration == 0.5 and a.auto_unload_idle_seconds == 1800.0
assert o.backend == "wtype" and o.append_space is True
assert f.notify_ms == 2500 and f.hypr_notify is True
assert fc.min_chars == 2
assert fc.blocklist == ["thank you.", "thanks for watching.", "bye.", "thank you for watching"], fc.blocklist
with open(_repo_config_path(), "rb") as fh: data = tomllib.load(fh)
assert data["filter"]["blocklist"] == fc.blocklist, "config.py != config.toml blocklist (drift!)"
print("L2 PASS: spot-checked defaults; blocklist config.py==config.toml (4 entries, VT-006)")
PY
# Expected: 37 passed + "L2 PASS". Confirms the report's claims match the live code.
```

### Level 3: No source modified (expected — audit found all-compliant)

```bash
cd /home/dustin/projects/voice-typing
echo "--- git status: ONLY the new report under plan/ should appear (no config.py/config.toml) ---"
git status --short
echo "--- assert config.py + config.toml + tests UNCHANGED ---"
git diff --name-only | grep -E 'voice_typing/config\.py|config\.toml|tests/test_config' && echo "L3 FAIL: source modified (unexpected — see Task 3 branch)" || echo "L3 PASS: no source changes (audit found all-compliant)"
# Expected: "no source changes". If this FAILs, either a real non-VT-006 mismatch was found+fixed
# (legitimate — verify the fix agrees with PRD §4.5 AND keeps the drift guard green), or the agent
# wrongly re-added "you" to the blocklist (NOT legitimate — revert; see Anti-Patterns #1).
```

### Level 4: The VT-006 trap is not tripped (blocklist still 4 entries)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
from voice_typing.config import FilterConfig
import tomllib
from voice_typing.config import _repo_config_path
py_bl = FilterConfig().blocklist
with open(_repo_config_path(), "rb") as fh: toml_bl = tomllib.load(fh)["filter"]["blocklist"]
assert "you" not in py_bl, 'blocklist re-added "you" — VT-006 trap tripped! revert.'
assert py_bl == toml_bl, "config.py != config.toml blocklist"
print("L4 PASS: blocklist intact (4 entries, no 'you'); VT-006 respected; config.py==config.toml")
PY
# Expected: "L4 PASS". This is the safety net against the single most likely implementation error.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: gap_config.md exists with all sections; documents VT-006; states all-compliant.
- [ ] L2: 37 config tests pass; spot-checked defaults + blocklist match the live code (reproducible).
- [ ] L3: no source modified (config.py/config.toml/tests unchanged) — expected outcome.
- [ ] L4: blocklist still 4 entries (no "you"); VT-006 respected; config.py==config.toml.

### Feature Validation
- [ ] Report's compliance table covers all 19 scalar fields + the blocklist.
- [ ] Report records the blocklist VT-006 deviation as intentional/documented/tested (not a gap).
- [ ] Report records the validation logic (numeric/string/notify_ms/unknown-key) as present.
- [ ] Report's test count matches the re-run (37 passed).

### Code Quality Validation
- [ ] Every claim in the report cites a file:line.
- [ ] Report distinguishes REAL gaps from INTENTIONAL deviations.
- [ ] Report notes the drift-guard coverage boundary (agreement ≠ PRD compliance).

### Scope Boundary Validation
- [ ] No config.py/config.toml edits (unless a real non-VT-006 mismatch is found — not expected).
- [ ] No edits to test files, daemon.py, or any other module.
- [ ] Only `plan/006_862ee9d6ef41/architecture/gap_config.md` is added.

---

## Anti-Patterns to Avoid

- ❌ **Don't re-add `"you"` to the blocklist.** It's an intentional VT-006 deviation, documented in config.py:191, config.toml:67, and tests/test_config.py:24, and PINNED by test_config.py:64. "Fixing" it breaks the test, contradicts the design decision, and re-introduces the silent-drop-of-"you" UX bug. Record it as compliant-by-design.
- ❌ Don't treat PRD §4.5's literal blocklist text as authoritative over the VT-006-corrected implementation. The test's `_PRD_BLOCKLIST` IS the authoritative pin (it's labeled "PRD §4.5 authoritative blocklist" but is the corrected 4-entry version).
- ❌ Don't trust the drift guard as proof of PRD compliance — it only checks config.py ↔ config.toml agreement. This audit is specifically the PRD-compliance check the guard can't do.
- ❌ Don't flag `compute_type` as a missing field — it's a cuda_check concern by design (config.py:20).
- ❌ Don't read the PRD and assume the code matches — dump the actual defaults with `dataclasses.fields` and compare three sources (PRD §4.5 / config.py / config.toml).
- ❌ Don't edit config.py or config.toml if all-compliant — the contract says note "none — config.toml already mirrors config.py per audit." Source edits are the unexpected branch only.
- ❌ Don't conflate this audit (S1: field/default PRD compliance) with S2 (lockstep + blocklist-correctness confirmation) or S3 (search-order/XDG). Write the report; don't expand scope.
- ❌ Don't invoke ruff/mypy — not configured.

---

## Confidence Score

**9.5/10** for one-pass "implementation" success. The deliverable is one report whose every finding is already verified in this PRP (the audit is done). The implementing agent re-runs two read-only commands to confirm, then transcribes. The −0.5 is the single most likely implementation error — an agent mechanically "diffing config.py vs PRD §4.5" could mistake the VT-006 blocklist deviation for a gap and re-add `"you"`, breaking test_config.py:64. That trap is called out as Anti-Pattern #1 and guarded by validation L4 (blocklist still 4 entries, no "you") + the explicit "DO NOT add 'you' back" instruction with its three documentation citations.