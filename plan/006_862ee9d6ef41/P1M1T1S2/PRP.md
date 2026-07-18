# PRP — P1.M1.T1.S2: Verify config.toml ↔ config.py schema lockstep & blocklist correctness

## Goal

**Feature Goal**: Verify that the repo `config.toml` mirrors `voice_typing/config.py` defaults **exactly** (zero drift), that the **blocklist** is correct in BOTH files (4 entries, includes the contract-required set, excludes bare `'you'` per VT-006), and that config.toml's comments are accurate per PRD §4.5 (Mode A "user-facing config reference"). Record the result by **appending a Lockstep & Mode-A Doc section to S1's `gap_config.md`**. This is a **verification/audit** subtask: the deliverable is the recorded result; code changes happen ONLY if a real drift is found (none exists).

**Deliverable**: An appended section (`## Lockstep & Mode-A Doc Verification (P1.M1.T1.S2)`) in `plan/006_862ee9d6ef41/architecture/gap_config.md` (S1's report) recording: (a) the drift-guard test result (`test_config_repo_default.py`'s 3 tests + the direct tomllib↔defaults comparison); (b) the blocklist correctness check (both files, VT-006); (c) the Mode A comment-accuracy scan; (d) the 20-key-set match; (e) the conclusion (no drift → no fix). No source changes expected.

**Success Definition**:
- (a) `gap_config.md` contains the S2 lockstep section with all required findings, citing file:line for every claim.
- (b) The recorded findings match the live verification: `.venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -q` → **37 passed**; `from_toml_file(repo) == VoiceTypingConfig()` → **True** (no drift); blocklist = 4 entries, no `'you'`, in both files; 20 keys == 20 fields; Mode A comments accurate.
- (c) **No source files are modified** (because no drift exists — the contract's "fix any drift" branch is not taken).
- (d) The section explicitly records the blocklist VT-006 deviation as intentional/documented/tested (so no future agent re-adds `'you'`).
- (e) S2 does NOT duplicate S1's field-compliance table (it appends a distinct lockstep-focused section).

## User Persona

**Target User**: The verification round's orchestrator + future maintainers who need an evidence-backed record that config.toml is in lockstep with config.py (the drift guarantee) and that the user-facing config doc (Mode A) is accurate.

**Use Case**: Reviewing `gap_config.md` to confirm the config layer is drift-free and doc-accurate before declaring the config audit (S1+S2+S3) complete.

**Pain Points Addressed**: The drift-guard test (`test_config_repo_default.py`) only proves config.py↔config.toml **agreement**; it does NOT prove PRD compliance (that's S1) NOR explicitly document the blocklist VT-006 rationale or Mode A comment accuracy. S2 closes those gaps with recorded evidence.

## Why

- **Verification round mandate.** This round is "verification, gap-analysis, and remediation — NOT greenfield build." S2 confirms the lockstep + blocklist + Mode A doc are correct before relying on them.
- **Distinct from S1.** S1 = "does config.py match PRD §4.5?" S2 = "does config.toml mirror config.py exactly (drift) + is the blocklist correct + are the comments accurate?" Both are needed; neither subsumes the other. (S1's table has a config.toml column, but S2 runs the dedicated drift-guard test + the focused blocklist + Mode A checks.)
- **Mode A doc guarantee.** config.toml is the user-facing reference (the file users edit). Its comments must be accurate — a stale keybind letter (e.g. SUPER+ALT+F) or a removed-field reference sends users to a dead key / confuses them. S2 scans for that (the SUPER+ALT+D check is already test-pinned; S2 does the broader scan).
- **Lowest-risk outcome.** The live verification (this PRP's author) finds everything compliant → no code changes → zero regression risk. The blocklist VT-006 trap is the single most likely error; S2 documents it as compliant-by-design.

## What

Run the lockstep test + direct comparison + blocklist check + Mode A comment scan; append the result to `gap_config.md`. **No code changes expected** (the audit finds all-compliant). If — and only if — the re-verification surfaces a REAL drift (config.toml ≠ config.py) not explained by VT-006, fix BOTH files (the drift guard demands agreement) and record the fix; otherwise record "none — config.toml mirrors config.py per audit."

### Success Criteria

- [ ] `.venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -q` → 37 passed (reproduced).
- [ ] `VoiceTypingConfig.from_toml_file(_repo_config_path()) == VoiceTypingConfig()` → True (no drift).
- [ ] Blocklist in BOTH config.py and config.toml = `['thank you.', 'thanks for watching.', 'bye.', 'thank you for watching']`; includes all 4 contract-required entries; no `'you'` (VT-006).
- [ ] config.py has 20 scalar fields == config.toml's 20 keys (the exact key set the drift-guard test pins).
- [ ] Mode A: every config.toml key commented; `lite_model` comment cites `SUPER+ALT+D` (matches hypr-binds.conf:52); no `SUPER+ALT+F` / `compute_type` stale refs.
- [ ] `gap_config.md` has the appended S2 lockstep section citing file:line for every claim.
- [ ] No source files modified (config.py/config.toml/tests unchanged) UNLESS a real non-VT-006 drift is found (not expected).

## All Needed Context

### Context Completeness Check

_Pass._ This PRP's author has already executed the full verification against the live code; every finding below is verified with the exact command and value. The implementing agent re-runs the commands to confirm, then transcribes the results into the appended section. No further investigation is required.

### VERIFIED FINDINGS (already performed — transcribe into the gap_config.md section)

**1. Drift-guard test — 37 passed:**
- `test_repo_config_toml_equals_defaults` — `from_toml_file(repo) == VoiceTypingConfig()` (THE lockstep proof).
- `test_repo_config_toml_has_no_extra_keys` — exact 20-key set: asr `{final_model, realtime_model, lite_model, language, device, post_speech_silence_duration, lite_post_speech_silence_duration, realtime_processing_pause, auto_stop_idle_seconds, auto_unload_idle_seconds}`, output `{backend, tmux_target, append_space}`, feedback `{state_file, hypr_notify, notify_ms, notify_on_final}`, filter `{min_chars, blocklist}`, log `{level}`.
- `test_repo_config_lite_model_comment_names_correct_keybind` — raw-text scan: `lite_model` line has `SUPER+ALT+D`, not `SUPER+ALT+F`.

**2. Direct comparison (independent of the test):**
- `VoiceTypingConfig.from_toml_file(_repo_config_path()) == VoiceTypingConfig()` → **True** (no drift).
- config.py: **20 scalar fields** (`dataclasses.fields` across AsrConfig..LogConfig`) == config.toml: **20 keys**. Match.

**3. Blocklist — correct in BOTH files (VT-006):**
- config.py `FilterConfig.blocklist` (config.py:192-200, default_factory): `['thank you.', 'thanks for watching.', 'bye.', 'thank you for watching']`.
- config.toml `[filter].blocklist` (config.toml:60-66): same 4 entries.
- Contract-required 4 entries present ✓; bare `'you'` absent ✓ (VT-006).
- VT-006 documented in 3 places: config.py:201-208, config.toml:67, tests/test_config.py:24; pinned by tests/test_config.py:64.

**4. Mode A comment accuracy — config.toml reads as documentation:**
- 20 keys, 20 trailing `#` comments (every key documented).
- `lite_model` comment cites `SUPER+ALT+D` (matches hypr-binds.conf:52 `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite`).
- No `SUPER+ALT+F` / `compute_type` stale references (grep clean).
- Comments accurately describe each field per §4.5 (device cpu auto-fallback, append_space, state_file XDG_RUNTIME_DIR, idle-stop vs idle-unload, etc.) — spot-checked, no inaccuracies.

**5. Conclusion:** config.toml mirrors config.py exactly (no drift). Blocklist is the documented VT-006 4-entry version in both files. Mode A comments are accurate. **No code changes required.**

### Documentation & References

```yaml
# THE INPUT CONTRACT (S1 — defines config.py + creates gap_config.md)
- file: plan/006_862ee9d6ef41/P1M1T1S1/PRP.md
  why: S1 audits config.py against PRD §4.5 AND creates gap_config.md (the report S2 appends to).
       S1's findings (all-compliant; blocklist VT-006 intentional) are the foundation S2 builds on.
  critical: "S2 APPENDS to gap_config.md (S1's deliverable) — do NOT overwrite it or duplicate S1's
       field-compliance table. S2's section is lockstep + blocklist-correctness + Mode A doc accuracy."

# THE SPEC
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: §4.5 is the authoritative config schema + the blocklist (5 entries incl. 'you' in the literal
       PRD text; the implementation omits 'you' per VT-006). Compare blocklist against this.
  critical: "PRD §4.5's literal blocklist has 5 entries incl. 'you'. The implementation intentionally
            omits 'you' (VT-006). S2 must NOT call that a defect — it's compliant-by-design."

# THE CODE UNDER AUDIT
- file: voice_typing/config.py
  why: FilterConfig.blocklist default_factory (192-200) + VT-006 NOTE (201-208). 20 scalar fields
        total. Dump via dataclasses.fields for the field count.
  pattern: "blocklist uses field(default_factory=lambda: [...]) — each instance gets its own list."
  gotcha: "compute_type is NOT a config field (cuda_check concern, config.py:20). Don't flag its absence."

# THE FILE UNDER AUDIT (config.toml — the user-facing Mode A reference)
- file: config.toml
  why: 76-line repo default. Parse with tomllib for value comparison; scan RAW text for comments
        (tomllib drops comments). blocklist @60-66; VT-006 note @67; lite_model SUPER+ALT+D @32.
  pattern: "Every [section] key mirrors a dataclass field + carries a trailing comment."
  gotcha: "tomllib.load DROPS comments — the SUPER+ALT+D check must read raw text, not the parsed dict."

# THE DRIFT-GUARD TEST (S2's primary proof)
- file: tests/test_config_repo_default.py
  why: 3 tests: test_repo_config_toml_equals_defaults (equality), test_repo_config_toml_has_no_extra_keys
        (exact 20-key set), test_repo_config_lite_model_comment_names_correct_keybind (SUPER+ALT+D raw
        text). These ARE the lockstep proof — run them and record the result.
  critical: "This guard checks config.py↔config.toml AGREEMENT only, NOT PRD compliance (that's S1).
            Record this coverage boundary in the section."

# THE BLOCKLIST PIN
- file: tests/test_config.py
  why: _PRD_BLOCKLIST (:24) is the authoritative 4-entry list (VT-006 comment); test_config.py:64 pins
        cfg.filter.blocklist == _PRD_BLOCKLIST. This is why re-adding 'you' would break the suite.
  critical: "The test's _PRD_BLOCKLIST IS the pin — it deliberately omits 'you'. Do NOT reconcile
            config.py toward PRD §4.5's 5-entry literal."

# THE KEYBIND SOURCE OF TRUTH (for the Mode A SUPER+ALT+D check)
- file: hypr-binds.conf
  why: :52 `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite` is the real lite keybind.
        config.toml's lite_model comment must cite SUPER+ALT+D (it does). :50 is CTRL SUPER ALT, D -> toggle (normal).
  critical: "D is the lite letter; CTRL+SUPER+ALT+D is normal toggle. config.toml's lite_model comment
            correctly says SUPER+ALT+D."

# THE PROJECT CONTEXT
- docfile: plan/006_862ee9d6ef41/architecture/system_context.md
  why: States this round is verification/gap-analysis, not greenfield. Confirms S2's scope (verify, don't rebuild).

# THIS SUBTASK'S OWN RESEARCH NOTE — the live verification + the distinct-from-S1 framing
- docfile: plan/006_862ee9d6ef41/P1M1T1S2/research/lockstep_and_blocklist_findings.md
  why: §1 S2≠S1 distinction; §2 the live lockstep results (37 passed, no drift); §3 blocklist correctness;
       §4 Mode A comment accuracy; §5 the gap_config.md APPEND shape.
  section: "§2 (live lockstep) and §5 (append shape) are load-bearing."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/config.py             # FilterConfig.blocklist @192-200 + VT-006 NOTE @201-208; 20 fields   ← AUDIT (read-only)
├── config.toml                        # repo default; blocklist @60-66 + VT-006 @67; lite_model SUPER+ALT+D @32   ← AUDIT (read-only)
├── tests/test_config_repo_default.py  # the 3 drift-guard tests (THE lockstep proof)                          ← RUN (read-only)
├── tests/test_config.py               # _PRD_BLOCKLIST @24; blocklist pin @64                                ← RUN (read-only)
├── hypr-binds.conf                    # :52 SUPER ALT, D -> toggle-lite (the SUPER+ALT+D source of truth)     ← AUDIT (read-only)
└── plan/006_862ee9d6ef41/architecture/
    └── gap_config.md                  # S1's report ← S2 APPENDS its lockstep section here
```

### Desired Codebase tree with files to be changed

```bash
plan/006_862ee9d6ef41/architecture/gap_config.md   # MODIFY: APPEND the "## Lockstep & Mode-A Doc Verification (P1.M1.T1.S2)" section.
# NO source changes expected (no drift exists). config.py/config.toml/tests UNCHANGED.
# (Only if the re-verification finds a REAL non-VT-006 drift would config.py+config.toml be edited together.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — S2 ≠ S1. S1 = PRD §4.5 field/default COMPLIANCE (does config.py match the PRD?).
# S2 = config.toml↔config.py LOCKSTEP (drift) + blocklist correctness + Mode A doc accuracy. Do NOT
# duplicate S1's field-compliance table. APPEND a distinct lockstep-focused section to gap_config.md.

# CRITICAL #2 — THE BLOCKLIST "you" OMISSION IS INTENTIONAL (VT-006), NOT A GAP. PRD §4.5 lists 5
# entries incl. "you"; config.py + config.toml + tests/test_config.py:_PRD_BLOCKLIST all use 4 (no
# "you"), BY DESIGN. Documented at config.py:201-208, config.toml:67, tests/test_config.py:24; pinned
# by tests/test_config.py:64. DO NOT re-add "you" — it breaks the test, contradicts VT-006, and
# re-introduces the silent-drop-of-"you" UX bug. Record it as compliant-by-design.

# CRITICAL #3 — THE DRIFT GUARD CHECKS AGREEMENT, NOT PRD COMPLIANCE. test_repo_config_toml_equals_
# defaults proves config.py == config.toml. If BOTH drift from the PRD (or carry VT-006), the guard is
# green. S2's section should note this coverage boundary explicitly (S1 is the PRD-compliance check).

# CRITICAL #4 — tomllib DROPS COMMENTS. The SUPER+ALT+D / SUPER+ALT+F check must read config.toml as
# RAW TEXT (open().read()), not the parsed dict. The existing test already does this; S2's scan too.

# CRITICAL #5 — BLOCKLIST IS A list[str] WITH default_factory. config.py's FilterConfig.blocklist is
# field(default_factory=lambda: [...]) — each instance gets a fresh list. When comparing, instantiate
# FilterConfig() (or VoiceTypingConfig().filter.blocklist) to get the value; don't read field.default
# (it's MISSING for factory fields). config.toml's [filter].blocklist is a plain TOML array.

# CRITICAL #6 — 20-KEY SET IS EXACT. The drift guard pins the precise key set (asr:10, output:3,
# feedback:4, filter:2, log:1 = 20). config.py has 20 scalar fields. A stray/renamed key fails
# test_repo_config_toml_has_no_extra_keys. compute_type is correctly ABSENT (cuda_check concern).

# GOTCHA #7 — APPEND, DON'T OVERWRITE gap_config.md. It's S1's deliverable. APPEND the S2 section.
# If gap_config.md does NOT yet exist (S1 still in flight), create a minimal file with the S2 section
# + a `<!-- P1.M1.T1.S1 field-compliance section: pending -->` placeholder. Do NOT fabricate S1's findings.

# GOTCHA #8 — REPORT-FIRST. The deliverable is the appended section. Do NOT edit config.py/config.toml
# unless the re-verification finds a REAL drift not explained by VT-006. If all compliant (expected),
# record "none — config.toml mirrors config.py per audit."

# GOTCHA #9 — FULL-PATH DISCIPLINE. Machine aliases python3->uv run. Use .venv/bin/python for the
# dump + pytest. No ruff/mypy in this project.
```

## Implementation Blueprint

### Data models and structure

This task audits data models; it does not change them. Under audit: `FilterConfig.blocklist: list[str]` (default_factory, 4-entry VT-006 list), composed in `VoiceTypingConfig` (20 scalar fields across AsrConfig/OutputConfig/FeedbackConfig/FilterConfig/LogConfig), mirrored by config.toml's 20 keys.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RE-VERIFY the lockstep (reproduce the findings; do not trust them blindly).
  - RUN the drift-guard + config tests:
        .venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -q
    EXPECT: 37 passed.
  - RUN the direct comparison + blocklist + key-count check:
        .venv/bin/python - <<'PY'
        import dataclasses, tomllib
        from voice_typing.config import VoiceTypingConfig, FilterConfig, _repo_config_path
        repo = VoiceTypingConfig.from_toml_file(_repo_config_path())
        default = VoiceTypingConfig()
        print("LOCKSTEP (toml==py defaults):", repo == default)
        with open(_repo_config_path(), "rb") as fh: data = tomllib.load(fh)
        toml_bl = data["filter"]["blocklist"]
        py_bl = default.filter.blocklist
        print("blocklist t==p:", toml_bl == py_bl, "| toml:", toml_bl)
        required = {"thank you.", "thanks for watching.", "bye.", "thank you for watching"}
        print("4 required present:", required.issubset(set(toml_bl)), "| no bare 'you':", "you" not in toml_bl)
        nfields = sum(len(dataclasses.fields(c)) for c in
                      (__import__("voice_typing.config", fromlist=["AsrConfig"]).AsrConfig,
                       __import__("voice_typing.config", fromlist=["OutputConfig"]).OutputConfig,
                       __import__("voice_typing.config", fromlist=["FeedbackConfig"]).FeedbackConfig,
                       FilterConfig,
                       __import__("voice_typing.config", fromlist=["LogConfig"]).LogConfig))
        print("config.py scalar fields:", nfields, "| config.toml keys:", sum(len(v) for v in data.values()))
        PY
    EXPECT: LOCKSTEP True; blocklist t==p True; 4 required present True; no 'you' True; 20 fields == 20 keys.
  - RUN the Mode A comment-accuracy scan:
        grep -nE 'SUPER\+ALT\+F|compute_type' config.toml   # EXPECT: no matches
        grep -n 'SUPER+ALT+D' config.toml                   # EXPECT: the lite_model line
        grep -n 'SUPER ALT, D' hypr-binds.conf              # EXPECT: the toggle-lite bind (source of truth)
  - If ANY check differs from the findings above, INVESTIGATE before writing the section (the tree may
    have moved; reconcile the report with what you observe; respect VT-006 for the blocklist).

Task 2: APPEND the S2 section to plan/006_862ee9d6ef41/architecture/gap_config.md.
  - IF gap_config.md EXISTS (S1 done): use the edit tool to APPEND (after S1's last section) a new:
        ## Lockstep & Mode-A Doc Verification (P1.M1.T1.S2)
  - IF gap_config.md does NOT exist (S1 in flight): use the write tool to CREATE a minimal file whose
    FIRST line is `<!-- P1.M1.T1.S1 field-compliance section: pending — S1 owns it; do not fabricate -->`
    followed by the S2 section below. (S1 will insert its content above/around it.)
  - STRUCTURE the S2 section with:
      1. Scope statement: "Verify config.toml ↔ config.py lockstep (drift) + blocklist correctness +
         Mode A comment accuracy. Distinct from S1 (PRD §4.5 field compliance)."
      2. Drift-guard test result: "tests/test_config_repo_default.py (3 tests) + tests/test_config.py
         → 37 passed." Name the 3 lockstep tests + what each asserts (equality / 20-key set /
         SUPER+ALT+D raw-text). Note the coverage boundary: agreement ≠ PRD compliance (S1 is the latter).
      3. Direct comparison result: "VoiceTypingConfig.from_toml_file(repo) == VoiceTypingConfig() →
         True (no drift). config.py 20 scalar fields == config.toml 20 keys."
      4. Blocklist correctness: "Both files = ['thank you.', 'thanks for watching.', 'bye.',
         'thank you for watching'] (4 entries). Includes all contract-required entries; NO bare 'you'
         (VT-006). Documented at config.py:201-208, config.toml:67, tests/test_config.py:24; pinned by
         tests/test_config.py:64. Compliant-by-design — NOT a gap." (This is the most important
         paragraph: it prevents a future agent from re-adding 'you'.)
      5. Mode A comment accuracy: "20 keys, 20 trailing comments. lite_model cites SUPER+ALT+D
         (matches hypr-binds.conf:52 bind = SUPER ALT, D, toggle-lite). No SUPER+ALT+F / compute_type
         stale references (grep clean). Comments describe each field accurately per §4.5."
      6. Conclusion: "No drift. config.toml mirrors config.py. Blocklist is the VT-006 4-entry version.
         Mode A doc is accurate. NO code changes required."
  - KEEP IT FACTUAL: cite file:line for every claim. No speculation. No duplication of S1's table.

Task 3: VALIDATE (run the gates below). No git commit unless the orchestrator directs it. If asked,
  message: "P1.M1.T1.S2: config.toml↔config.py lockstep verified (no drift); blocklist VT-006 correct; Mode A doc accurate".
  IF (and only if) Task 1 surfaced a REAL, non-VT-006 drift: fix BOTH config.py AND config.toml (the
  drift guard demands agreement), update config.toml comments (Mode A), and record the fix in the
  section's Conclusion. (Expected: this branch is NOT taken — no drift exists.)
```

### Implementation Patterns & Key Details

```python
# This is an audit/report task. The "pattern" is disciplined verification + honest reporting:
#   * Run the DEDICATED drift-guard test (test_config_repo_default.py) — it's the lockstep proof, not
#     just a column comparison.
#   * Compare config.toml parsed == VoiceTypingConfig() defaults (the equality is the drift signal).
#   * Check the blocklist in BOTH files + against the contract's required-4 + the VT-006 "no you" rule.
#   * Scan config.toml as RAW TEXT for comment accuracy (tomllib drops comments).
#   * Distinguish a REAL drift (both files wrong vs each other — none exists) from an INTENTIONAL
#     deviation (VT-006 blocklist — documented + tested). Only the former gets a fix.
#   * APPEND to gap_config.md; cite file:line for every claim.
#
# The trap to avoid (shared with S1): a naive "config.toml blocklist vs PRD §4.5 literal 5-entry list"
# flags the missing 'you' as a defect. It IS a diff from the raw PRD — but VT-006 (config.py:201-208 /
# config.toml:67 / test_config.py:24) makes it deliberate, and test_config.py:64 PINS the 4-entry
# version. "Fixing" it breaks the test + the UX. The section's job is to record this so no one trips it.
```

### Integration Points

```yaml
DOWNSTREAM / SIBLING:
  - S1 (P1.M1.T1.S1) creates gap_config.md (the field/default PRD-compliance report). S2 APPENDS its
    lockstep section to that same file. The two sections together form the complete config audit:
    S1 = PRD compliance, S2 = drift/lockstep + blocklist correctness + Mode A doc accuracy.
  - S3 (P1.M1.T1.S3) "Verify config search-order & XDG resolution path" is a separate concern (path
    resolution), not covered by S2.

CONFIG LAYER (voice_typing/config.py + config.toml):
  - UNCHANGED by S2 (expected). The verification confirms they're already in lockstep. If a real fix
    were needed, both files would change together (the drift guard demands it) — but no fix is expected.

TEST SUITE:
  - test_config_repo_default.py (3 lockstep tests) + test_config.py:64 (blocklist pin) are the
    existing guards. S2's section documents their coverage boundary (agreement, not PRD compliance).
```

## Validation Loop

> Full paths for python (machine aliases python3→uv run). No ruff/mypy. The gates verify the APPENDED
> section exists + is accurate + that NO source was changed (expected). All commands read-only except
> appending the section.

### Level 1: The S2 section is appended to gap_config.md and well-formed

```bash
cd /home/dustin/projects/voice-typing
DOC=plan/006_862ee9d6ef41/architecture/gap_config.md
test -f "$DOC" && echo "L1a PASS: gap_config.md exists" || echo "L1a FAIL"
echo "--- S2 section present ---"
grep -q 'Lockstep & Mode-A Doc Verification (P1.M1.T1.S2)' "$DOC" && echo "L1b PASS" || echo "L1b FAIL: S2 section missing"
echo "--- section cites the key findings ---"
grep -qi 'no drift\|mirrors config.py' "$DOC" && echo "L1c PASS (no-drift conclusion)" || echo "L1c CHECK"
grep -q 'VT-006' "$DOC" && echo "L1d PASS (VT-006 documented)" || echo "L1d FAIL: VT-006 not mentioned"
grep -qi 'SUPER+ALT+D\|SUPER ALT, D' "$DOC" && echo "L1e PASS (Mode A keybind cited)" || echo "L1e CHECK"
grep -qi '37 passed\|test_config_repo_default' "$DOC" && echo "L1f PASS (test evidence cited)" || echo "L1f CHECK"
# Expected: gap_config.md exists; S2 section present; cites no-drift, VT-006, SUPER+ALT+D, the 37-passed test.
```

### Level 2: The section's findings are reproducible (re-verify the lockstep)

```bash
cd /home/dustin/projects/voice-typing
echo "--- re-run the drift-guard + config tests (section claims 37 passed) ---"
.venv/bin/python -m pytest tests/test_config_repo_default.py tests/test_config.py -q 2>&1 | tail -3
echo "--- re-verify: no drift + blocklist correct in BOTH files ---"
.venv/bin/python - <<'PY'
import tomllib
from voice_typing.config import VoiceTypingConfig, _repo_config_path
repo = VoiceTypingConfig.from_toml_file(_repo_config_path())
assert repo == VoiceTypingConfig(), "DRIFT: config.toml != config.py defaults"
with open(_repo_config_path(), "rb") as fh: toml_bl = tomllib.load(fh)["filter"]["blocklist"]
py_bl = VoiceTypingConfig().filter.blocklist
assert toml_bl == py_bl, "blocklist drift between config.toml and config.py"
required = {"thank you.", "thanks for watching.", "bye.", "thank you for watching"}
assert required.issubset(set(toml_bl)) and "you" not in toml_bl, "blocklist correctness failed"
print("L2 PASS: no drift; blocklist correct in both files (4 entries, no 'you', VT-006)")
PY
echo "--- re-verify: Mode A keybind comment (raw text, not parsed) ---"
grep -q 'SUPER+ALT+D' config.toml && ! grep -q 'SUPER+ALT+F' config.toml && echo "L2b PASS: SUPER+ALT+D present, SUPER+ALT+F absent" || echo "L2b CHECK"
# Expected: 37 passed; L2 PASS; L2b PASS. Confirms the section's claims match the live code.
```

### Level 3: No source modified (expected — no drift found)

```bash
cd /home/dustin/projects/voice-typing
echo "--- git status: ONLY gap_config.md under plan/ should appear (no config.py/config.toml/tests) ---"
git status --short
echo "--- assert config.py + config.toml + tests + hypr-binds.conf UNCHANGED ---"
git diff --name-only | grep -E 'voice_typing/config\.py|config\.toml|tests/test_config|hypr-binds\.conf' && echo "L3 FAIL: source modified (unexpected — see Task 3 branch)" || echo "L3 PASS: no source changes (no drift found)"
# Expected: "no source changes". If this FAILs, either a real non-VT-006 drift was found+fixed
# (legitimate — verify the fix keeps the drift guard green AND both files agree) OR the agent wrongly
# re-added 'you' to the blocklist (NOT legitimate — revert; see Anti-Patterns #2).
```

### Level 4: The VT-006 trap is not tripped (blocklist still 4 entries, no drift)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
import tomllib
from voice_typing.config import VoiceTypingConfig, _repo_config_path
py_bl = VoiceTypingConfig().filter.blocklist
with open(_repo_config_path(), "rb") as fh: toml_bl = tomllib.load(fh)["filter"]["blocklist"]
assert "you" not in py_bl, 'blocklist re-added "you" — VT-006 trap tripped! revert.'
assert py_bl == toml_bl, "config.py != config.toml blocklist (drift introduced)"
assert VoiceTypingConfig.from_toml_file(_repo_config_path()) == VoiceTypingConfig(), "drift introduced"
print("L4 PASS: blocklist intact (4 entries, no 'you'); VT-006 respected; config.py==config.toml; no drift")
PY
# Expected: "L4 PASS". Safety net against the single most likely error (re-adding 'you' or introducing drift).
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: gap_config.md has the appended S2 section citing no-drift, VT-006, SUPER+ALT+D, 37-passed test.
- [ ] L2: 37 tests pass; direct comparison shows no drift; blocklist correct in both files; SUPER+ALT+D present / SUPER+ALT+F absent.
- [ ] L3: no source modified (config.py/config.toml/tests/hypr-binds.conf unchanged) — expected outcome.
- [ ] L4: blocklist still 4 entries (no 'you'); config.py==config.toml; no drift introduced.

### Feature Validation
- [ ] Section records config.toml↔config.py lockstep (drift-guard test + direct comparison) = no drift.
- [ ] Section records blocklist correctness: 4 entries, contract-required set present, no 'you' (VT-006), both files agree.
- [ ] Section records Mode A comment accuracy: 20 keys commented, SUPER+ALT+D correct, no stale refs.
- [ ] Section records the 20-key-set match (config.py 20 fields == config.toml 20 keys).
- [ ] Section notes the drift-guard coverage boundary (agreement ≠ PRD compliance; S1 is the latter).

### Code Quality Validation
- [ ] Every claim in the section cites a file:line (config.py:192-200/201-208, config.toml:60-66/67, tests/test_config_repo_default.py, hypr-binds.conf:52).
- [ ] Section distinguishes a REAL drift (none) from the INTENTIONAL VT-006 deviation.
- [ ] Section does NOT duplicate S1's field-compliance table (appends a distinct lockstep-focused section).

### Scope Boundary Validation
- [ ] No config.py/config.toml edits (unless a real non-VT-006 drift is found — not expected).
- [ ] No edits to test files, daemon.py, hypr-binds.conf, or any other module.
- [ ] Only `plan/006_862ee9d6ef41/architecture/gap_config.md` is modified (the appended S2 section).
- [ ] S2 does NOT do S1's job (PRD field compliance) or S3's job (search-order/XDG).

### Documentation & Deployment
- [ ] (The gap_config.md section IS the documentation deliverable.) It records the verification result durably.
- [ ] If asked to commit: message references lockstep verification + blocklist VT-006 + Mode A doc accuracy.

---

## Anti-Patterns to Avoid

- ❌ **Don't duplicate S1's field-compliance table.** S2's scope is lockstep (drift) + blocklist correctness + Mode A doc accuracy — distinct from S1's PRD §4.5 compliance. APPEND a focused section; don't re-derive S1's table.
- ❌ **Don't re-add `"you"` to the blocklist.** It's an intentional VT-006 deviation, documented in config.py:201-208, config.toml:67, and tests/test_config.py:24, and PINNED by tests/test_config.py:64. "Fixing" it breaks the test, contradicts the design decision, and re-introduces the silent-drop-of-"you" UX bug. Record it as compliant-by-design.
- ❌ Don't treat PRD §4.5's literal blocklist text as authoritative over the VT-006-corrected implementation. The test's `_PRD_BLOCKLIST` IS the authoritative pin.
- ❌ Don't trust the drift guard as proof of PRD compliance — it only checks config.py ↔ config.toml agreement. S1 is the PRD-compliance check; S2 is the lockstep check. Record the coverage boundary.
- ❌ Don't parse config.toml with tomllib to check COMMENT accuracy — tomllib drops comments. Read the file as RAW TEXT for the SUPER+ALT+D / stale-ref scan (the existing test does this; mirror it).
- ❌ Don't read `field.default` for the blocklist — it's a `default_factory` field (default is MISSING). Instantiate `FilterConfig()` (or `VoiceTypingConfig().filter.blocklist`) to get the value.
- ❌ Don't edit config.py or config.toml if no drift — the contract says record "none — config.toml mirrors config.py per audit." Source edits are the unexpected branch only.
- ❌ Don't OVERWRITE gap_config.md — it's S1's deliverable. APPEND the S2 section. If the file doesn't exist yet, create a minimal one with a `pending S1` placeholder; don't fabricate S1's findings.
- ❌ Don't flag `compute_type` as a missing field — it's a cuda_check concern by design (config.py:20), correctly absent from the 20-key schema.
- ❌ Don't invoke ruff/mypy — not configured. Use `.venv/bin/python -m pytest`.

---

## Confidence Score

**9.5/10** for one-pass "implementation" success. The deliverable is one appended report section whose every finding is already verified in this PRP (the live lockstep check is done: 37 passed, no drift, blocklist correct in both files, Mode A comments accurate, 20==20 keys). The implementing agent re-runs three read-only commands to confirm, then transcribes into the appended section. The −0.5 is the single most likely implementation error — an agent mechanically "diffing config.toml blocklist vs PRD §4.5 literal text" could mistake the VT-006 deviation for a defect and re-add `'you'`, breaking tests/test_config.py:64. That trap is called out as Anti-Pattern #2 and guarded by validation L4 (blocklist still 4 entries, no 'you', no drift) + the explicit "DO NOT re-add 'you'" instruction with its three documentation citations + the test pin. A secondary minor risk is the APPEND-vs-CREATE gap_config.md decision (if S1 hasn't landed), mitigated by Gotcha #7 + Task 2's explicit fallback.