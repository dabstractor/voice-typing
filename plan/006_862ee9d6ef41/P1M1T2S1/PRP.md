# PRP — P1.M1.T2.S1: Audit `clean()` against PRD §4.7 4-step spec & run unit tests

## Goal

**Feature Goal**: Produce an authoritative **gap report** (`plan/006_862ee9d6ef41/architecture/gap_textproc.md`) cross-checking `voice_typing/textproc.py`'s `clean()` function — step by step — against the PRD §4.7 4-step spec, plus confirm the two load-bearing behaviors the contract calls out (trailing-newline stripping per §4.3; blocklist normalization making `"Thank you."`/`"BYE!"`/`"bye"` all reject via their respective entries) and run the pure-Python unit suite (`tests/test_textproc.py`). This is a **verification/audit** subtask: the deliverable is the report; code changes happen ONLY if a real gap is found (none is expected — the audit finds `clean()` fully compliant).

**Deliverable**: One report at `plan/006_862ee9d6ef41/architecture/gap_textproc.md` (mirroring the `gap_config.md` convention from P1.M1.T1.S1) containing: (a) a per-step compliance table (PRD §4.7 expected vs `textproc.py` actual, with file:line); (b) the two contract-specific behavior checks (trailing newlines; blocklist normalization); (c) the unit-test pass/fail count; (d) a mismatches/drift section; (e) a conclusion. **This PRP's author has already performed the audit** (findings embedded below) — the implementing agent's job is to re-verify and transcribe, then write the report.

**Success Definition**:
- (a) `plan/006_862ee9d6ef41/architecture/gap_textproc.md` exists with the 5 sections above.
- (b) The recorded findings match the live re-verification: all 4 PRD §4.7 steps are **compliant**; `"Thank you."`/`"BYE!"`/`"bye"` each reject; trailing newlines are stripped.
- (c) `.venv/bin/python -m pytest tests/test_textproc.py -q` → all pass (record the count).
- (d) **No source files are modified** (because no defect exists — `clean()` is fully PRD §4.7-compliant per audit). If — and only if — the re-verification surfaces a REAL defect, fix it in `textproc.py` and record the fix; otherwise record "none — `clean()` is PRD §4.7-compliant per audit."
- (e) The report notes the §4.5/§4.7 boundary: the blocklist **contents** (incl. the VT-006 `"you"` removal) are a §4.5 config concern owned by P1.M1.T1.S1/S2 — NOT part of `clean()`'s logic, which correctly normalizes+matches whatever blocklist it is given.

## User Persona

**Target User**: The maintainer (human or AI agent) who needs to trust that the hallucination filter + text normalizer actually implements the PRD before relying on it (it gates every finalized utterance that reaches the typing backend). Also the downstream P1.M2.T1 (main-loop audit) which depends on `clean()`'s contract (`on_final → clean → type`).

**Use Case**: A future change to `textproc.py` (e.g. altering the strip logic, the blocklist normalization, or the min-length gate). The gap report + the unit tests are the reference that proves the change keeps (or breaks) PRD §4.7 compliance.

**Pain Points Addressed**: Closes the "does `clean()` actually do the 4 PRD steps, and do the hallucination entries actually catch `"Thank you."`/`"bye"` regardless of case + trailing punctuation?" question with recorded, re-runnable evidence — not an assumption.

## Why

- **PRD §4.7 is the spec; §4.3 imposes the trailing-newline strip.** The blocklist is the primary defense against Whisper's silence hallucination ("thank you." on silent audio — a top-3 project risk, PRD §8). VAD gating + this filter + PRD test T4 assert it together. This audit confirms the filter's LOGIC matches the spec before the heavier T4 idle-stability gate relies on it.
- **Catch silent drift the unit tests might not pin to the PRD.** The unit tests pin BEHAVIOR (whitespace/min-length/blocklist/punctuation) but do not explicitly map each assertion to "PRD §4.7 step N." A future refactor could pass the tests yet drift from the PRD's step ordering/wording. This audit is the human/agent check that closes that mapping gap, and records it durably in `gap_textproc.md`.
- **Document the one place the broader feature intentionally diverges from the PRD's literal text.** PRD §4.5's blocklist lists a bare `"you"`, but the code omits it (VT-006 — it silently dropped dictating the word "you"). That is a §4.5/config finding (already in `gap_config.md`); this §4.7 audit must state the BOUNDARY — `clean()`'s LOGIC is unaffected (it normalizes+matches whatever blocklist it receives) — so the VT-006 deviation isn't mistaken for a `textproc.py` defect.
- **Lowest-risk outcome.** The live verification (this PRP's author) finds `clean()` fully §4.7-compliant → no code changes → zero regression risk. The deliverable is the recorded evidence.
- **Scope discipline.** T2.S1 owns ONLY `textproc.py` audit + `gap_textproc.md`. It does NOT re-audit config (P1.M1.T1.S1/S2/S3 own §4.5), does NOT audit typing backends (P1.M1.T3), does NOT touch the daemon `on_final` wiring (P1.M2.T1), and does NOT modify source unless a real defect is found.

## What

Re-verify `clean()` against PRD §4.7's 4 steps + the two contract behaviors, run `tests/test_textproc.py`, and write `gap_textproc.md`. No code change expected.

### PRD §4.7 spec (the authority)

```
clean(text) -> str | None:
1. text.strip(); strip trailing newlines; collapse internal whitespace runs to single spaces.
2. Reject if len < filter.min_chars.
3. Reject if lowercase-stripped-of-trailing-punctuation form is in blocklist.
4. Return cleaned text. Caller appends a single space when append_space.
```
Plus §4.3: "strip trailing newlines in textproc." Plus the blocklist-normalization intent: `"Thank you."`, `"BYE!"`, `"bye"` all reject (case- + trailing-punctuation-insensitive, exact not substring).

### Success Criteria

- [ ] `plan/006_862ee9d6ef41/architecture/gap_textproc.md` exists with: per-step table, the two behavior checks, test counts, mismatches, conclusion.
- [ ] The report records: step 1 ✅, step 2 ✅, step 3 ✅, step 4 ✅ (each with `textproc.py` file:line).
- [ ] The report records: trailing-newline strip ✅ (cite `test_drops_trailing_newlines_and_collapses`); blocklist normalization ✅ (cite `test_blocklist_matches_with_or_without_trailing_punct` + `test_rejects_default_blocklist_thank_you`).
- [ ] `.venv/bin/python -m pytest tests/test_textproc.py -q` → all pass (record the count).
- [ ] No source files modified (record "none — compliant per audit"); OR a real fix recorded with justification.
- [ ] The report notes the §4.5/§4.7 boundary (VT-006 `"you"` removal is a config concern, not a `clean()` logic defect).

## All Needed Context

### Context Completeness Check

_Pass._ The verbatim current `clean()` body (with file:line), the `_TRAILING_PUNCT` strip class, every relevant unit test (with file:line), the contract's two behavior checks mapped to specific tests, the blocklist-contents boundary (VT-006), and the `gap_config.md` report convention to mirror are all below. An agent new to this repo can re-verify + transcribe from this PRP alone. No CUDA/daemon/audio needed — `textproc.py` is pure stdlib.

### Documentation & References

```yaml
# THE SPEC (the authority)
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: §4.7 is the 4-step clean() spec (strip+collapse / min_chars / blocklist-normalized / return-no-
       space); §4.3 imposes "strip trailing newlines in textproc"; §4.5 gives the canonical blocklist
       (incl. the bare "you" the code intentionally omits — VT-006). §8 names silence-hallucination as
       a top-3 risk this filter defends against.
  critical: "§4.7 step 3 = 'lowercase-stripped-of-trailing-punctuation form is in blocklist' — BOTH the
            input AND each blocklist entry are normalized the same way, and the match is EXACT (not
            substring). The audit must confirm both halves."

# THE AUDIT TARGET (verbatim current body)
- file: voice_typing/textproc.py
  why: clean() @ L39-70. Step 1 @ L55 `cleaned = " ".join(text.split())` (split()-no-args splits on ANY
        whitespace run + discards leading/trailing empties -> join yields strip+trailing-newline-drop+
        collapse in one expression). Step 2 @ L58 `if len(cleaned) < cfg.min_chars: return None` (on the
        CLEANED length). Step 3 @ L65-67 `key = cleaned.lower().rstrip(_TRAILING_PUNCT); if key in
        {b.lower().rstrip(_TRAILING_PUNCT) for b in cfg.blocklist}: return None` (normalizes BOTH sides;
        exact set membership, not substring). Step 4 @ L70 `return cleaned` (no space appended).
        _TRAILING_PUNCT @ L36 = ".!?," + ";" (= .!,;? — the trailing-punct strip class).
  pattern: "Each step is one expression; map them 1:1 to PRD §4.7 steps 1-4 in the compliance table with
            the file:line. Note step 1 is a benign SUPERSET of the PRD wording (strips ALL trailing
            whitespace, not only newlines) — record as compliant, not drift."
  gotcha: "rstrip(_TRAILING_PUNCT) strips a CHARACTER SET from the right end, not a suffix — so 'bye!!'
          -> 'bye' and 'thank you.' -> 'thank you' (internal space untouched). Confirm this is what
          makes 'BYE!'/'bye'/'Thank you.' all reject."

# THE UNIT TESTS (the behavior pinning)
- file: tests/test_textproc.py
  why: Comprehensive coverage mapping to each PRD step:
        * Step 1 (whitespace): test_collapses_internal_whitespace_runs L23, test_strips_leading_and_
          trailing_whitespace L27, test_drops_trailing_newlines_and_collapses L31 (THE §4.3 check),
          test_tabs_are_whitespace_too L35.
        * Step 2 (min_chars): test_rejects_below_min_chars L43, test_accepts_at_min_chars_boundary L48,
          test_rejects_empty_string L52, test_rejects_whitespace_only L56, test_min_length_uses_cleaned_
          text_not_raw L61, test_custom_min_chars L66.
        * Step 3 (blocklist): test_rejects_default_blocklist_thank_you L76, test_blocklist_is_case_
          insensitive L80, test_blocklist_matches_with_or_without_trailing_punct L85 (Bye/bye./BYE! all
          None — THE normalization check), test_blocklist_entry_without_punctuation_matches L92,
          test_blocklist_is_exact_not_substring L101 (yourself NOT dropped), test_empty_blocklist_
          never_rejects L109.
        * Step 4 (punctuation preserved + no space): test_internal_punctuation_preserved L118,
          test_question_mark_preserved L123, test_period_preserved_when_not_blocklisted L127,
          test_never_appends_trailing_space L135.
        * Aggregate: test_returns_none_for_every_rejection_reason L142.
  pattern: "The audit table should cite the test(s) that pin each step. Run the whole file and record
            the pass count."
  critical: "test_blocklist_matches_with_or_without_trailing_punct (L85-89) IS the contract's
            'Thank you./BYE!/bye all reject' proof — it asserts Bye/bye./BYE! each -> None. Cite it."

# THE BLOCKLIST CONTENTS + the VT-006 boundary (a §4.5 concern, NOT clean()'s logic)
- file: voice_typing/config.py
  why: FilterConfig.blocklist @ L184-196 (default omits the bare 'you' — VT-006, intentional; documented
        in gap_config.md). clean() RECEIVES cfg.blocklist as an input; its LOGIC (normalize both sides,
        exact match) is correct regardless of the contents. So the 'you' removal is NOT a textproc gap.
  critical: "State the boundary in the report: 'the blocklist CONTENTS are a §4.5 config concern
            (P1.M1.T1.S1/S2, recorded in gap_config.md); clean()'s LOGIC correctly normalizes+matches
            whatever blocklist it receives — VT-006 is not a textproc.py defect.'"

# THE REPORT CONVENTION TO MIRROR
- docfile: plan/006_862ee9d6ef41/architecture/gap_config.md
  why: The sibling audit's gap report — mirror its structure: Date/Scope/Audited artifacts (read-only)/
       Bottom line/Method (commands run, re-verification)/per-item compliance table/test pass-fail/
       mismatches/conclusion. Same "report-first; fix only if a real gap" discipline.
  critical: "gap_textproc.md goes in plan/006_862ee9d6ef41/architecture/ (same dir as gap_config.md).
            It is the ONLY file this subtask creates."

# THE PARALLEL ITEM (no-conflict boundary)
- docfile: plan/006_862ee9d6ef41/P1M1T1S3/PRP.md
  why: T1.S3 (parallel) verifies config search-order (_candidate_paths/_xdg_config_path/load) and
        APPENDS a section to gap_config.md. T2.S1 audits textproc.py and writes a NEW gap_textproc.md.
        Different module, different report file. No overlap.
  critical: "T1.S3 touches config.py + gap_config.md; T2.S1 touches textproc.py + gap_textproc.md. No
            file conflict. Do NOT append to gap_config.md — textproc gets its own report."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── textproc.py          # clean() @ L39-70; _TRAILING_PUNCT @ L36. ← AUDIT (read-only unless a real defect).
├── tests/
│   └── test_textproc.py     # ~20 tests pinning all 4 steps. ← RUN (record pass count).
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_config.md        # sibling audit's report (P1.M1.T1.S1) — mirror its structure.
    └── gap_textproc.md      # ← CREATE (this subtask's ONLY deliverable).
```

### Desired Codebase tree with files to be added/changed

```bash
plan/006_862ee9d6ef41/architecture/gap_textproc.md   # NEW — the gap report (only deliverable).
# NO source/test changes expected (clean() is PRD §4.7-compliant per audit). If a real defect is found,
# voice_typing/textproc.py is the ONLY source file that may be edited (with justification in the report).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS A REPORT-FIRST TASK. The deliverable is gap_textproc.md. Do NOT edit textproc.py
# unless the re-verification surfaces a REAL defect (none is expected — the audit finds clean() fully
# compliant). If you "improve" clean() without a defect, you risk regressing the 20 unit tests for no
# spec reason. (Mirrors P1.M1.T1.S1's discipline.)

# CRITICAL #2 — STEP 1 IS A SUPERSET, NOT DRIFT. PRD §4.7 step 1 says "text.strip(); strip trailing
# newlines; collapse internal whitespace". clean() does `" ".join(text.split())`, which strips ALL
# leading/trailing whitespace (not only newlines) + collapses all internal whitespace runs. That is a
# benign SUPERSET of the PRD wording (stripping trailing spaces too is strictly more correct). Record
# as COMPLIANT, not as drift. test_drops_trailing_newlines_and_collapses (L31) pins the newline case.

# CRITICAL #3 — STEP 3 NORMALIZES BOTH SIDES + IS EXACT (NOT SUBSTRING). The blocklist check builds
# `key = cleaned.lower().rstrip(_TRAILING_PUNCT)` for the INPUT and `{b.lower().rstrip(_TRAILING_PUNCT)
# for b in cfg.blocklist}` for the ENTRIES — then EXACT set membership (`key in {...}`). This is why
# "Bye"/"bye."/"BYE!" all normalize to "bye" and match the "bye." entry (which also normalizes to "bye"),
# while "yourself" does NOT match "you". Confirm both halves in the audit; cite test_blocklist_matches_
# with_or_without_trailing_punct (L85) + test_blocklist_is_exact_not_substring (L101).

# CRITICAL #4 — rstrip STRIPS A CHARACTER SET, NOT A SUFFIX. `"bye!!".rstrip(".!,;?")` -> "bye" (strips
# both trailing '!'), and `"thank you.".rstrip(...)` -> "thank you" (the internal space is NOT touched
# — rstrip only strips from the right end). This is the mechanism that makes multi-word hallucinations
# ("thank you for watching.") normalize correctly. Do NOT mis-report this as a bug.

# CRITICAL #5 — THE VT-006 "you" REMOVAL IS A §4.5 CONCERN, NOT A textproc GAP. PRD §4.5's blocklist
# lists a bare "you"; the code omits it (VT-006 — it silently dropped dictating the word "you"). That
# divergence is already recorded in gap_config.md (P1.M1.T1.S1). clean()'s LOGIC is correct regardless
# of the blocklist contents — it normalizes+matches whatever it receives. State this boundary in the
# report so the VT-006 deviation isn't mistaken for a textproc.py defect.

# GOTCHA #6 — FULL-PATH DISCIPLINE. Machine aliases python3->uv run. Use .venv/bin/python for the
# pytest run + any one-off checks. No ruff/mypy configured — don't invoke them.

# GOTCHA #7 — DON'T APPEND TO gap_config.md. textproc gets its OWN report (gap_textproc.md) in the same
# architecture/ dir. T1.S3 appends to gap_config.md (config search-order) — that's a different file;
# do not conflate.

# GOTCHA #8 — RECORD COMMANDS + COUNTS, not assertions. The report's Method section must show the
# actual commands run + the actual pytest pass count (re-verified live), mirroring gap_config.md's
# "Commands run (re-verification)" block. Do not copy this PRP's embedded findings verbatim without
# re-running — re-verify, then transcribe the live result.
```

## Implementation Blueprint

### Data models and structure

None. `clean()` takes `(text: str, cfg: FilterConfig) -> str | None`; `FilterConfig` has `min_chars: int` + `blocklist: list[str]`. No ORM/pydantic. The only "structure" the subtask produces is the markdown report.

### Audit Tasks (ordered by dependencies)

```yaml
Task 1: RE-VERIFY clean() against PRD §4.7 + the two contract behaviors (read-only)
  - READ voice_typing/textproc.py (clean() @ L39-70; _TRAILING_PUNCT @ L36). Map each step 1:1 to PRD
    §4.7 (step 1 @ L55; step 2 @ L58; step 3 @ L65-67; step 4 @ L70). Record file:line for each.
  - RUN the contract's two behavior checks live (pure stdlib, ms):
        .venv/bin/python - <<'PY'
        from voice_typing.textproc import clean, _TRAILING_PUNCT
        from voice_typing.config import FilterConfig
        cfg = FilterConfig()   # default blocklist (VT-006: no bare "you")
        # (a) trailing newlines stripped (PRD §4.3):
        assert clean("Hello\n\nworld\n", cfg) == "Hello world", "trailing newline not stripped"
        # (b) blocklist normalization — "Thank you."/"BYE!"/"bye" all reject via their entries:
        assert clean("Thank you.", cfg) is None, "'Thank you.' should reject (thank you. entry)"
        assert clean("BYE!", cfg) is None, "'BYE!' should reject (bye. entry, ! stripped)"
        assert clean("bye", cfg) is None, "'bye' should reject (bye. entry)"
        # exact-not-substring (yourself survives a "you" entry when present):
        cfg2 = FilterConfig(min_chars=2, blocklist=["you"])
        assert clean("yourself", cfg2) == "yourself"
        assert clean("you", cfg2) is None
        print("behavior checks PASS; _TRAILING_PUNCT =", repr(_TRAILING_PUNCT))
        PY
  - EXPECTED: all asserts pass; prints `_TRAILING_PUNCT = '.!,;?'` (".!?," + ";"). Record the output.
  - DO NOT edit textproc.py unless a check FAILS (none should).

Task 2: RUN the unit suite + record the pass count
  - RUN: .venv/bin/python -m pytest tests/test_textproc.py -q
  - EXPECTED: all pass (record the count, e.g. "20 passed" — whatever the live run shows). Also note the
    key tests per step (see the References block for the file:line map).
  - IF a test FAILS: that is a REAL defect — investigate root cause, decide whether it's a textproc.py
    bug or a stale test, fix the MINIMAL side, and record the fix + justification in the report. (Not
    expected; the suite is green on the live tree.)

Task 3: WRITE plan/006_862ee9d6ef41/architecture/gap_textproc.md (the deliverable)
  - STRUCTURE (mirror gap_config.md):
        # Gap Report — P1.M1.T2.S1: textproc.clean() vs PRD §4.7
        **Date:** <re-verification date>
        **Scope:** Audit voice_typing/textproc.py clean() against the PRD §4.7 4-step spec + §4.3
          trailing-newline strip + the blocklist-normalization intent. Subtask P1.M1.T2.S1 of round
          006_862ee9d6ef41.
        **Audited artifacts (read-only):** voice_typing/textproc.py; tests/test_textproc.py;
          voice_typing/config.py (FilterConfig defaults for context).
        **Bottom line:** ✅ clean() is COMPLIANT with PRD §4.7 (all 4 steps). No source files modified.
        ## 1. Method  (commands run: the Task-1 python block + the Task-2 pytest invocation; re-verified live)
        ## 2. Per-step compliance table
            | PRD §4.7 step | Expected | textproc.py actual | file:line | Tests | Verdict |
            | 1 strip+collapse | strip+trailing-newline+collapse | " ".join(text.split()) | L55 | L23/27/31/35 | ✅ |
            | 2 min_chars | reject if len(cleaned)<min_chars | if len(cleaned)<cfg.min_chars: return None | L58 | L43/48/52/56/61/66 | ✅ |
            | 3 blocklist | lowercase+rstrip-punct, exact match, both sides | key=cleaned.lower().rstrip(PUNCT); if key in {b.lower().rstrip(PUNCT) ...}: return None | L65-67 | L76/80/85/92/101/109 | ✅ |
            | 4 return | cleaned text, no space | return cleaned | L70 | L118/123/127/135 | ✅ |
            (note step 1 is a benign superset — strips all trailing whitespace, not only newlines.)
        ## 3. Contract behavior checks
            - Trailing-newline strip (§4.3): ✅ — clean("Hello\n\nworld\n")=="Hello world".
            - Blocklist normalization: ✅ — "Thank you."/"BYE!"/"bye" each -> None (Thank you.->thank you
              matches thank you. entry; BYE!->bye matches bye. entry; bye->bye matches bye. entry).
              _TRAILING_PUNCT = '.!,;?' (rstrip is a char-set, not a suffix).
        ## 4. Test results  (tests/test_textproc.py -q -> <N> passed — record the live count)
        ## 5. Mismatches / drift  (none — clean() is §4.7-compliant)
        ## 6. Boundary note  (the VT-006 "you" blocklist removal is a §4.5 config concern recorded in
              gap_config.md; clean()'s LOGIC is correct regardless of blocklist contents — not a textproc gap)
        ## 7. Conclusion  (PASS — no fix; clean() matches PRD §4.7 exactly; the unit suite pins every step)
  - CONSTRAINTS:
      * Re-verify live (Task 1/2) BEFORE transcribing — do not copy this PRP's numbers without re-running.
      * Cite file:line for every textproc.py claim; cite the test(s) pinning each step.
      * Record the actual pytest count (e.g. "20 passed"), not an assumed number.
      * State the §4.5/§4.7 VT-006 boundary explicitly (section 6).
  - DO NOT: edit textproc.py (no defect); append to gap_config.md (textproc gets its own report); or run
    CUDA/daemon/audio (textproc is pure stdlib).

Task 4: VALIDATE — run the Validation Loop L1–L3; fix until all green. No git commit unless the orchestrator
  directs it. If asked, message:
  "P1.M1.T2.S1: audit textproc.clean() vs PRD §4.7 — gap_textproc.md (PASS, no fix)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — report-first audit (mirror gap_config.md). The deliverable is the markdown report; source
# edits happen ONLY if a real defect is found. The report records: per-step compliance (with file:line +
# pinning tests), the contract behavior checks (run live), the test count (run live), mismatches (none
# expected), and the conclusion. Re-verify live, then transcribe — do not copy without re-running.

# PATTERN 2 — the one-expression-per-step clean() shape. Each PRD §4.7 step is exactly one expression:
#   step 1: cleaned = " ".join(text.split())                 # strip + trailing-newline-drop + collapse
#   step 2: if len(cleaned) < cfg.min_chars: return None     # min-length on the CLEANED text
#   step 3: key = cleaned.lower().rstrip(_TRAILING_PUNCT)    # normalize input ...
#           if key in {b.lower().rstrip(_TRAILING_PUNCT) for b in cfg.blocklist}: return None  # ...+ entries; exact
#   step 4: return cleaned                                    # no space (caller appends)
# The audit table maps these 1:1 to the PRD steps. _TRAILING_PUNCT = ".!?," + ";" (= .!,;?).

# PATTERN 3 — the boundary statement. The blocklist CONTENTS (incl. VT-006 "you" removal) are a §4.5
# config concern (gap_config.md). clean()'s LOGIC is correct for ANY blocklist — it normalizes both
# sides and matches exactly. State this so the VT-006 deviation isn't mistaken for a textproc defect.
```

### Integration Points

```yaml
DOWNSTREAM — P1.M2.T1 (main-loop audit, §4.2 #1-2):
  - P1.M2.T1 audits daemon.on_final's `txt = textproc.clean(text, cfg.filter); if txt is not None: <type>`.
    This audit's per-step compliance table is the reference clean()'s contract is checked against. The
    report confirms clean() returns str|None (None gates typing) + never appends a space (on_final does).

SIBLING AUDIT REPORTS (architecture/):
  - gap_config.md (P1.M1.T1.S1/S2/S3) — config schema, lockstep, search-order. gap_textproc.md joins it
    as the textproc §4.7 audit. Same dir, same report-first discipline, distinct module.

NO SOURCE / TEST CHANGES (expected):
  - textproc.py, test_textproc.py, config.py: UNCHANGED (clean() is compliant; the suite is green).
  - If a real defect IS found, textproc.py is the only source file that may be edited (minimal fix +
    justification in the report); test_textproc.py may be updated only if a test was stale (not if the
    code was wrong).
```

## Validation Loop

> Full paths (machine aliases python3→uv run). All gates are FAST + hermetic — `textproc.py` is pure
> stdlib; NO CUDA/daemon/audio/network. No ruff/mypy configured. Run from `/home/dustin/projects/voice-typing`.

### Level 1: The report exists + is well-formed + embeds the re-verification

```bash
cd /home/dustin/projects/voice-typing
DOC=plan/006_862ee9d6ef41/architecture/gap_textproc.md
echo "--- L1a: the report exists ---"
test -f "$DOC" && echo "L1a PASS: report exists" || echo "L1a FAIL: report missing"
echo "--- L1b: required sections present ---"
for sec in "Bottom line" "Method" "Per-step compliance" "Contract behavior" "Test results" "Mismatch" "Boundary" "Conclusion"; do
  grep -qi "$sec" "$DOC" && echo "  ok: $sec" || echo "  L1b FAIL: missing $sec"
done
echo "--- L1c: verdict is PASS / compliant (no fix) ---"
grep -qiE 'compliant|✅|PASS|no.*fix|no source files modified' "$DOC" && echo "L1c PASS" || echo "L1c CHECK"
echo "--- L1d: the VT-006 boundary is documented ---"
grep -qi 'VT-006' "$DOC" && echo "L1d PASS (VT-006 boundary noted)" || echo "L1d FAIL: VT-006 not mentioned"
# Expected: report exists; all sections present; verdict compliant/no-fix; VT-006 boundary documented.
```

### Level 2: The live re-verification matches the report (clean() is §4.7-compliant)

```bash
cd /home/dustin/projects/voice-typing
echo "--- L2a: the 4 steps map to textproc.py file:line (cited in the report) ---"
grep -qE 'L5[0-9]|L6[0-9]|:5[0-9]|:6[0-9]' plan/006_862ee9d6ef41/architecture/gap_textproc.md && echo "L2a PASS: file:line cites present" || echo "L2a CHECK"
echo "--- L2b: the contract behavior checks pass live (re-run) ---"
.venv/bin/python - <<'PY'
from voice_typing.textproc import clean
from voice_typing.config import FilterConfig
cfg = FilterConfig()
assert clean("Hello\n\nworld\n", cfg) == "Hello world"            # §4.3 trailing newlines
assert clean("Thank you.", cfg) is None and clean("BYE!", cfg) is None and clean("bye", cfg) is None
print("L2b PASS: trailing-newline + blocklist-normalization checks hold live")
PY
echo "--- L2c: the report's recorded pytest count matches a fresh run ---"
fresh=$(.venv/bin/python -m pytest tests/test_textproc.py -q 2>&1 | tail -1)
echo "fresh run: $fresh"
grep -q "$(echo "$fresh" | grep -oE '[0-9]+ passed')" plan/006_862ee9d6ef41/architecture/gap_textproc.md \
  && echo "L2c PASS: report count matches live" || echo "L2c CHECK: report count vs live — verify"
# Expected: file:line cites present; behavior checks pass live; the report's pass count matches a fresh run.
```

### Level 3: No regression + scope clean (no source edits unless a real defect was found)

```bash
cd /home/dustin/projects/voice-typing
echo "--- L3a: textproc unit suite green ---"
.venv/bin/python -m pytest tests/test_textproc.py -q 2>&1 | tail -3
echo "--- L3b: broader sanity (no other suite broke) ---"
.venv/bin/python -m pytest tests/test_textproc.py tests/test_config.py -q 2>&1 | tail -3
echo "--- L3c: scope — ONLY gap_textproc.md created (no source edits expected) ---"
git status --short
git diff --quiet voice_typing/textproc.py voice_typing/config.py tests/test_textproc.py 2>/dev/null \
  && echo "L3c PASS: no source/test edits (report-only, as expected)" \
  || echo "L3c NOTE: a source/test file was edited — confirm it's a justified real-defect fix recorded in the report"
test -f plan/006_862ee9d6ef41/architecture/gap_textproc.md && echo "L3c PASS: gap_textproc.md is the deliverable"
# Expected: textproc suite green; broader sanity green; git status shows gap_textproc.md as a new
# (untracked) file under plan/006_862ee9d6ef41/architecture/; NO edits to textproc.py/config.py/
# test_textproc.py (unless a real defect was found + justified in the report).
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `gap_textproc.md` exists; all 7 sections present; verdict compliant/no-fix; VT-006 boundary documented.
- [ ] L2: file:line cites present; the 2 contract behavior checks pass LIVE; the report's pytest count matches a fresh run.
- [ ] L3: textproc suite green; broader sanity green; only `gap_textproc.md` created (no source edits unless a justified real-defect fix).

### Feature Validation
- [ ] Per-step table records steps 1-4 each ✅ with `textproc.py` file:line + the pinning test(s).
- [ ] Trailing-newline strip (§4.3) confirmed ✅ (live + `test_drops_trailing_newlines_and_collapses`).
- [ ] Blocklist normalization confirmed ✅ (`"Thank you."`/`"BYE!"`/`"bye"` each → None; `_TRAILING_PUNCT` = `.!,;?`; rstrip is char-set not suffix).
- [ ] Step 3 confirmed exact-not-substring (both sides normalized; `test_blocklist_is_exact_not_substring`).
- [ ] Step 4 confirmed no space appended (`test_never_appends_trailing_space`).

### Code Quality Validation
- [ ] Report mirrors `gap_config.md`'s structure (Date/Scope/Artifacts/Bottom line/Method/table/tests/mismatches/conclusion).
- [ ] Method section shows the actual commands run (re-verification), not assumptions.
- [ ] Every textproc.py claim cites file:line; every step cites its pinning test(s).
- [ ] The §4.5/§4.7 VT-006 boundary is stated explicitly.

### Scope Boundary Validation
- [ ] `voice_typing/textproc.py` unmodified UNLESS a real defect was found + justified (none expected).
- [ ] `voice_typing/config.py`, `tests/test_textproc.py` unmodified (blocklist contents are §4.5/S1's concern).
- [ ] `gap_config.md` unmodified (textproc gets its OWN report; T1.S3 appends to gap_config.md, not this task).
- [ ] No daemon.py / typing_backends.py / ctl.py / README edits (sibling subtasks own those).
- [ ] PRD.md, tasks.json, prd_snapshot.md, .gitignore NOT modified.

### Documentation & Deployment
- [ ] (No user-facing docs — internal audit report, contract §5 "DOCS: none".) The gap report is the durable record.
- [ ] If asked to commit: message references the §4.7 audit + PASS verdict for traceability.

---

## Anti-Patterns to Avoid

- ❌ Don't edit `textproc.py` without a REAL defect — this is a report-first audit; `clean()` is §4.7-compliant. "Improving" it risks regressing the 20 unit tests for no spec reason (CRITICAL #1).
- ❌ Don't report step 1's all-whitespace strip as DRIFT — it's a benign SUPERSET of the PRD wording (strips trailing spaces too, not only newlines). Record as COMPLIANT (CRITICAL #2).
- ❌ Don't mis-read `rstrip(_TRAILING_PUNCT)` as a suffix strip — it strips a CHARACTER SET from the right end (`"bye!!"` → `"bye"`; internal spaces untouched). That's the mechanism that makes multi-word hallucinations normalize correctly; not a bug (CRITICAL #4).
- ❌ Don't conflate the VT-006 `"you"` blocklist removal with a `textproc.py` defect — the blocklist CONTENTS are a §4.5 config concern (gap_config.md); `clean()`'s LOGIC is correct for any blocklist (CRITICAL #5).
- ❌ Don't append to `gap_config.md` — textproc gets its OWN `gap_textproc.md` in the same dir (T1.S3 owns gap_config.md appends; CRITICAL #7).
- ❌ Don't transcribe this PRP's embedded numbers without re-running — re-verify live (Task 1/2), then record the actual file:line + pytest count (Gotcha #8).
- ❌ Don't run CUDA/daemon/audio "to be sure" — `textproc.py` is pure stdlib; the audit + tests run in milliseconds (Gotcha #6).
- ❌ Don't skip the file:line citations or the pinning-test citations — the report's value is the precise PRD-step ↔ code-line ↔ test mapping (gap_config.md's discipline).
- ❌ Don't use bare `python`/`pytest` (machine aliases python3→uv run). Use `.venv/bin/python -m pytest` (Gotcha #6).

---

## Confidence Score

**9.5/10** for one-pass implementation success. This is a report-first audit of a ~30-line pure-stdlib function, and the author has already performed the verification: `clean()` maps 1:1 to all 4 PRD §4.7 steps (step 1 `" ".join(text.split())` @ L55; step 2 min_chars @ L58; step 3 normalize-both-sides-exact @ L65-67; step 4 return-no-space @ L70), the two contract behaviors hold (`"Hello\n\nworld\n"` → `"Hello world"`; `"Thank you."`/`"BYE!"`/`"bye"` each → None), and the unit suite (`tests/test_textproc.py`, ~20 tests) pins every step including the exact-not-substring + never-append-space invariants. The deliverable is a markdown report mirroring the established `gap_config.md` convention, with re-verification commands the implementer re-runs in milliseconds. The −0.5 is solely the small risk of a stale test count or file:line if `textproc.py`/`test_textproc.py` shifted since this audit — mitigated by L2c (the report's recorded count must match a fresh run) and the re-verify-before-transcribe discipline. No source changes are expected; the only deliverable is `gap_textproc.md` recording PASS.