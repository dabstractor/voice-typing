# PRP — P1.M4.T1.S1: Verify and sync README.md + docs for the three-fix changeset

## Goal

**Feature Goal**: Verify `README.md` (the project's sole config/overview doc — there is no separate
`docs/` directory) is **consistent** with the three landed bugfixes (Issue 1 `_dispatch()` cross-mode
toggle-failure routing → `ok:false` → `voicectl` exit 1; Issue 2 `_final_pending` reset in
`_arm()`/`_disarm()`; Issue 3 `OutputConfig.__post_init__` `backend` value validation), then apply the
ONE contract-invited clarity touch-up: a sentence in the config-validation paragraph documenting that a
config value outside its allowed set (e.g. `output.backend = "wtyp"`) is rejected at load with
`ValueError` — the fail-fast surface Issue 3 (+ the pre-existing `asr.device` VT-005 check) add. This is
the **documentation task** of the changeset (item DOCS: "This IS the documentation task"). **No source,
no tests, no new files** — at most one prose sentence is added to README.md.

**Deliverable** (ONE artifact — `README.md`):
1. **VERIFY** (read-only) the README against the three fixes on the contract's three points: (A) the
   `output.backend` row consistency with load-time validation; (B) voicectl exit-code consistency with
   toggle failures now exiting 1; (C) confirm no `_final_pending`/drain/dispatch-internals docs are
   needed (Issues 1 & 2 are internal). **Expected verdict: the README is accurate on all three.**
2. **APPLY** the recommended touch-up — ONE verbatim sentence appended to the config-validation
   paragraph (`### Voice-activity constants are NOT config keys`) documenting wrong-*value* rejection at
   load (covers `output.backend` Issue 3 + `asr.device` VT-005). Exact `oldText`/`newText` in
   Implementation Blueprint → Task 2.
3. **RUN** the contract's mandated drift guard: `timeout 60 .venv/bin/python -m pytest
   tests/test_config_repo_default.py -q` (must stay green — it reads `config.toml`, not README).

**Success Definition**:
- (a) The README is verified consistent with all three fixes (the `output.backend` row lists the 3
  valid values; "auto-falls-back" is accurate as a *runtime* behavior; no exit-code contradiction; no
  internal-mechanism docs leaked) — recorded in the commit message / PR description.
- (b) **If the touch-up is applied**: the config-validation paragraph now documents wrong-*value*
  rejection at load (`ValueError`, naming `output.backend` + `asr.device`), completing the fail-fast
  picture alongside the existing unknown-key + wrong-*type* (`TypeError`) sentences. The sentence is
  wrapped to ~80 cols, matches the README tone, and adds no new heading (anchors stay valid).
- (c) `timeout 60 .venv/bin/python -m pytest tests/test_config_repo_default.py -q` → **3 passed**
  (unchanged — the test does not read README; `OutputConfig` defaults are unchanged).
- (d) **No source/test files modified.** `git status --short` shows ONLY `README.md` (if the touch-up
  was applied) OR nothing (if the zero-diff fallback was taken). NO edit to `voice_typing/*.py`,
  `tests/*`, `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`, `config.toml`, `pyproject.toml`,
  `uv.lock`.

> **VERIFIED VERDICT (this PRP's research): the README is accurate on all three fixes — no fix needed.**
> The single recommended touch-up (one sentence) is contract-invited ("noting that config values are
> validated at load time"), test-safe (no test reads README; the drift guard reads `config.toml`), and
> low-regret. If the reviewer prefers zero diff, the README remains accurate without it (§4 of the
> research note gives the commit-message text for that path).

## User Persona

**Target User**: the operator who hand-edits `~/.config/voice-typing/config.toml` and reads the README
to understand what each key does + what happens on a mistake — and the downstream P1.M5/P1.M6
acceptance/README-completeness audits that need the changeset's user-facing behavior documented.

**Use Case**: A user typos `output.backend = "wtyp"` and restarts the daemon. Pre-fix: silent load →
`make_backend` crash → systemd `Restart=on-failure` loop (findable only via `journalctl`). Post-fix
(Issue 3): the daemon fails at LOAD with `[output] backend must be "wtype", "ydotool", or "tmux", got
'wtyp'`. The touch-up sentence tells the user (in the README they're reading while editing config) that
this is the expected, fail-fast behavior — so they correct the typo instead of filing a bug.

**Pain Points Addressed**: Without the touch-up, the README documents that unknown keys and wrong *types*
fail at load, but is silent on wrong *values* — leaving a user unsure whether `backend = "wtyp"` will
fail loudly (it now does) or silently misbehave. The sentence closes that gap for both enum fields
(`output.backend` + `asr.device`).

## Why

- **The README is deployed verbatim** (install.sh points users at it; it IS the config documentation —
  no separate `docs/`). A doc that drifts from the code ships straight to the user. This task certifies
  no drift accompanied the three fixes.
- **Issue 3 added a user-facing fail-fast behavior** (load-time `ValueError` for a bad `backend`) that
  the README's config-validation paragraph did not previously cover. The touch-up documents it so the
  behavior is discoverable where the user is (editing config) — exactly the contract's "noting that
  config values are validated at load time."
- **Issues 1 & 2 are internal correctness fixes** (dispatch-layer response shaping; `_final_pending`
  lifecycle) with NO user-facing config/API surface change beyond making the daemon match its already-
  documented behavior (toggle errors now surface; stop no longer spuriously drains). The audit CONFIRMS
  the README correctly does not mention these internals (and should not).
- **Closes the changeset** (P1.M4 = documentation sync; S1 is the only subtask). With the three fixes
  landed + verified consistent, the changeset is ready to ship.
- **Read-only + parallel-safe.** The task reads README + the landed code and edits ONLY README.md. The
  parallel P1.M3.T1.S1 (Issue 3 impl) edits `config.py` + `test_config.py` — a different file; no
  conflict. (P1.M3.T1.S1 is the fix whose surface the touch-up documents; it has LANDED —
  `OutputConfig.__post_init__` at config.py:126/136.)

## What

A read-only verification of `README.md` (the 333-line overview + config doc) against the three landed
fixes — checking the `output.backend` row (line 175), the config-validation paragraph (~lines 194-202),
and confirming the absence of internal-mechanism docs (no `_final_pending`/drain-internals/dispatch).
Then ONE verbatim prose touch-up: append a sentence to the config-validation paragraph documenting
wrong-value rejection at load. Then run the drift-guard test.

### Success Criteria

- [ ] README verified: `output.backend` row (line 175) lists `wtype`/`ydotool`/`tmux` (matches
  `OutputConfig.__post_init__`'s valid set); "auto-falls-back" is accurate (runtime `_WtypeWithFallback`).
- [ ] README verified: NO explicit voicectl exit-code table exists (grep confirms) → nothing contradicts
  the Issue 1 fix (toggle failure → exit 1); recorded as a finding.
- [ ] README verified: no `_final_pending`/drain-internals/dispatch-layer docs leaked (the one "drain"
  hit at line 130 is the user-facing §4.2 #2 graceful-drain FEATURE, not the internal mechanism).
- [ ] **If touch-up applied**: the config-validation paragraph documents wrong-value → `ValueError` at
  load (naming `output.backend` + `asr.device`); sentence wrapped ~80 cols; no new heading.
- [ ] `timeout 60 .venv/bin/python -m pytest tests/test_config_repo_default.py -q` → 3 passed.
- [ ] `git status --short` shows ONLY `README.md` (touch-up) OR nothing (zero-diff fallback); no
  source/test/forbidden file touched.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research note: the
verification's three points + the verified verdict (README accurate) + the exact touch-up edit
(byte-exact oldText/newText) + the test-safety proof (no test reads README; drift guard reads
`config.toml`) + the zero-diff fallback (commit-message text) + the scope boundaries are all pinned.
The task re-verifies live (re-grep + re-read + re-run) rather than trusting the verdict.

### Documentation & References

```yaml
# MUST READ — the verification verdict + the 3 points + the touch-up + test safety + scope
- docfile: plan/006_862ee9d6ef41/bugfix/001_ce96ba984c11/P1M4T1S1/research/readme_doc_verification.md
  why: "§0 THE VERDICT: README accurate; one touch-up recommended. §1 the 3 verification points (A backend
        row; B exit codes — README has NONE, so vacuously consistent; C internal fixes — correctly absent).
        §2 the verbatim touch-up (oldText/newText) + WHY the wording (ValueError not TypeError; names both
        backend+device; 'crash-looping later') + test safety (no test reads README). §3 scope boundaries.
        §4 the zero-diff fallback (commit-message text). §5 tooling."
  section: "ALL load-bearing. §1 (the 3 points), §2 (the touch-up), §4 (fallback)."

# MUST READ — the file being verified + (optionally) edited.
- file: README.md
  why: "VERIFY TARGET (+ optional 1-sentence edit). output.backend row :175 (3 valid values + accurate
        'auto-falls-back'). config-validation paragraph ~:194-202 (unknown-key TypeError + wrong-TYPE
        TypeError sentences — the touch-up appends the wrong-VALUE ValueError sentence). Line 130's
        'graceful drain on stop' = the user-facing §4.2 #2 FEATURE (not the _final_pending mechanism).
        READ in full to confirm no exit-code table + no internal-mechanism leak."
  critical: "RE-VERIFY by grep (do NOT trust line numbers blindly). The touch-up's oldText anchor is the
             paragraph tail 'feature at runtime. Bare integers ... bool is not.' — confirm it is present +
             unique before editing. The README uses ~76-82 col manual soft-wrap; wrap the new sentence to match."

# MUST READ — the bugfix architecture context (the Documentation Surface + the 3 fixes' locations)
- docfile: plan/006_862ee9d6ef41/bugfix/001_ce96ba984c11/architecture/system_context.md
  why: "§Documentation Surface confirms: README already documents output.backend valid values (~:167/175);
        Issues 1 & 2 are internal correctness fixes with no user-facing config/API surface change; this
        task is 'a no-op sweep if no drift exists.' §Issue1/2/3 give the fix locations (daemon.py _dispatch
        ~:1918; _arm/_disarm _final_pending; config.py OutputConfig.__post_init__) to confirm landed."
  critical: "The system_context's claim that the README is accurate is CORROBORATED by this PRP's live grep.
             Do NOT edit the system_context (READ-ONLY architecture doc)."

# MUST READ — the Issue 3 fix contract (the surface the touch-up documents)
- file: plan/006_862ee9d6ef41/bugfix/001_ce96ba984c11/P1M3T1S1/PRP.md
  why: "Defines OutputConfig.__post_init__: backend ∈ {wtype,ydotool,tmux} else ValueError
        f'[output] backend must be \"wtype\", \"ydotool\", or \"tmux\", got {backend!r}'. Confirms the
        ValueError (not TypeError) choice the touch-up sentence must mirror, + the valid-value set that
        must match the README row. LANDED (config.py:126/136)."
  critical: "P1.M3.T1.S1 edits config.py + test_config.py (NOT README). This task edits README.md only —
             no file overlap. The touch-up documents P1.M3.T1.S1's user-facing surface."

# MUST READ — the landed fix code (confirm the behavior the README must reflect). READ, do NOT edit.
- file: voice_typing/config.py
  why: "OutputConfig (:119) + __post_init__ (:126) — backend validation raises ValueError (:136). AsrConfig
        device validation (VT-005, the precedent) — also ValueError for a bad enum value. Confirms the
        touch-up's 'ValueError' wording + the 'backend/device' pairing."
- file: voice_typing/daemon.py
  why: "_dispatch() cross-mode toggle routing (Issue 1) + _final_pending reset in _arm()/_disarm()
        (Issue 2 — :1013/:1041 with 'Issue 2' comments). Confirms the fixes are landed; the README need
        NOT mention these internals (they are correct-by-code, surfaced via documented behavior)."
- file: voice_typing/ctl.py
  why: ":63 `return f\"error: {...}\", 1` — a toggle failure (ok:false) now exits 1 (Issue 1 client surface).
        Confirms exit 1 is the documented-by-PRD-§4.8 command-error code; no README exit-code doc to sync."

# MUST READ — the drift guard (the contract's run command). READ/run, do NOT edit.
- file: tests/test_config_repo_default.py
  why: "Asserts config.toml == dataclass defaults. Reads config.toml (NOT README). OutputConfig defaults
        unchanged (backend='wtype') -> stays green (3 passed). Run it; record the count."

# CONTEXT — the PRD (the changeset's bug-fix requirements). READ-ONLY.
- docfile: plan/006_862ee9d6ef41/bugfix/001_ce96ba984c11/prd_snapshot.md
  why: "§2.2/§3.0 Issue 1, §2.2/§3.1 Issue 2, §2.3/§3.2 Issue 3 — the three fixes + the doc-sync intent.
        §2.4 Testing Summary flags 'output.backend value validation' as the Issue 3 gap this changeset closes."
  critical: "Do NOT edit the prd_snapshot (READ-ONLY)."
```

### Current Codebase tree (state at P1.M4.T1.S1 start)

The three fixes are LANDED (P1.M1.T1.S1, P1.M2.T1.S1 Complete; P1.M3.T1.S1 LANDED — config.py:126/136
present). README.md (333 lines) is the sole overview/config doc.

```bash
/home/dustin/projects/voice-typing/
├── README.md                 # ← VERIFY (+ optional 1-sentence touch-up in the config-validation paragraph).
├── PRD.md                    # READ-ONLY (forbidden).
├── config.toml               # READ-ONLY (drift guard reads it; OutputConfig defaults unchanged).
├── voice_typing/
│   ├── config.py             # LANDED (READ-ONLY): OutputConfig.__post_init__ :126 (Issue 3).
│   ├── daemon.py             # LANDED (READ-ONLY): _dispatch cross-mode routing + _final_pending reset (Issues 1&2).
│   └── ctl.py                # LANDED (READ-ONLY): :63 exit 1 on ok:false (Issue 1 client surface).
└── tests/
    └── test_config_repo_default.py  # RUN (the contract's drift guard) — 3 passed; reads config.toml, NOT README.
# NO docs/ directory (README IS the config doc). NO source/test edits. At most README.md +1 sentence.
```

### Desired Codebase tree with files to be added

```bash
README.md   # MODIFIED (optional): +1 sentence in the config-validation paragraph (wrong-value -> ValueError at load).
            #          OR unchanged (zero-diff fallback — verification recorded in the commit message).
# NOTHING ELSE.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — README.md ONLY (and at most +1 sentence). Do NOT edit voice_typing/*.py, tests/*,
#   PRD.md/tasks.json/prd_snapshot.md/.gitignore/config.toml/pyproject.toml/uv.lock. The three fixes are
#   LANDED; this task only verifies + (optionally) documents. (Research §3.)

# CRITICAL #2 — THE TOUCH-UP IS A CLARIFICATION, NOT A FIX. The README is ALREADY accurate (the output.backend
#   row lists the 3 valid values; it does not mislead). The sentence documents a fail-fast mode (wrong-value
#   -> ValueError) the paragraph previously omitted. Use ValueError (NOT TypeError) — the type IS valid (str),
#   the value is not (mirrors OutputConfig.__post_init__). (Research §2; Critical-as in P1M3T1S1.)

# CRITICAL #3 — THE oldText ANCHOR MUST MATCH BYTE-FOR-BYTE. The touch-up anchors on the paragraph tail
#   "feature at runtime. Bare integers are accepted for numeric fields; a `true`/`false`\nbool is not."
#   Re-grep (`grep -n "Bare integers are accepted" README.md`) to confirm it is present + unique before
#   editing. If the paragraph was edited by a sibling, re-read + re-anchor (trivial, one-line).

# CRITICAL #4 — PRESERVE THE ~76-82 COL MANUAL SOFT-WRAP. The README is hand-wrapped (hard newlines within
#   paragraphs). Wrap the new sentence to ~80 cols (matching the surrounding lines). Do NOT reflow the
#   paragraph or collapse it onto one line. Do NOT change any heading (## / ###) — internal `#anchor` links
#   depend on stable headings.

# CRITICAL #5 — NO TEST READS README. `grep -rnlE "README" tests/` returns only tests/ACCEPTANCE.md (a
#   markdown doc, not a test asserting README content). So a README prose edit CANNOT break any test. The
#   drift guard (test_config_repo_default.py) reads config.toml, not README — it stays green (3 passed)
#   regardless. (Research §2 test safety.)

# CRITICAL #6 — THE README HAS NO VOICETCL EXIT-CODE TABLE. Grep confirms no "exit code|exits 0/1/2|EX_USAGE"
#   in README. The contract's parenthetical "the README already documents exit codes 0/1/2/64" is NOT borne
#   out — there is no such section. This is FINE (the contract's "(if any)" covers it): there is nothing to
#   contradict the Issue 1 fix (toggle failure -> exit 1). Do NOT hunt for a non-existent exit-code section;
#   record "no exit-code doc in README -> vacuously consistent" as the finding. (Research §1 Point B.)

# CRITICAL #7 — DO NOT ADD INTERNAL-MECHANISM DOCS. The README correctly omits _final_pending, the
#   dispatch-layer response shaping, and the drain internals (Issues 1 & 2 are internal correctness fixes).
#   The one "drain" hit (line 130) is the user-facing §4.2 #2 graceful-drain FEATURE description — leave it.
#   Do NOT add _final_pending/dispatch docs (the contract explicitly forbids it). (Research §1 Point C.)

# GOTCHA #8 — TWO TIMEOUTS PER AGENTS.md RULE 1. test_config_repo_default.py is pure-stdlib + sub-second,
#   but STILL wrap: `timeout 60 .venv/bin/python -m pytest tests/test_config_repo_default.py -q` (inner) +
#   set the bash-tool `timeout` param above it (outer). NEVER run untimed pytest in this repo.

# GOTCHA #9 — FULL PATHS (zsh aliases python/pytest -> uv run). Always `.venv/bin/python -m pytest`. mypy
#   NOT installed (skip). ruff at /home/dustin/.local/bin/ruff is OPTIONAL (not in .venv; not a gate; the
#   README is Markdown — ruff/mypy do not apply). (Research §5.)
```

## Implementation Blueprint

### Data models and structure

None — documentation task. The deliverable is a verification + (optional) one prose sentence. No code,
no data models.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: VERIFY README.md against the three fixes (read-only) — record findings
  - READ README.md in full (333 lines). Confirm the 3 contract points:
    A) output.backend row (~:175): lists wtype/ydotool/tmux; "auto-falls-back to ydotool" is accurate
       (runtime _WtypeWithFallback, not config). GREP: `grep -n 'output.backend' README.md`.
    B) voicectl exit codes: GREP `grep -niE 'exit code|exits? (0|1|2|64)|exit [0-9]|sysexits|EX_USAGE' README.md`
       -> expect NO hits (no exit-code table). Record "no exit-code doc -> vacuously consistent with the
       Issue 1 fix (toggle failure -> exit 1)".
    C) internal mechanisms: GREP `grep -niE '_final_pending|drain|dispatch|cross.mode' README.md` -> expect
       ONLY line 130's user-facing "graceful drain on stop" FEATURE (NOT the _final_pending mechanism).
       Confirm no _final_pending/dispatch-layer docs leaked.
  - CONFIRM the three fixes are landed (so the README reflects reality):
       `grep -nE 'def __post_init__|backend must be' voice_typing/config.py`  # Issue 3: :126/:136
       `grep -n '_final_pending = False.*Issue 2' voice_typing/daemon.py`     # Issue 2: _arm/_disarm reset
  - EXPECTED: all 3 points PASS (README accurate). RECORD the findings for the commit message.
  - DO NOT: edit anything yet.

Task 2: APPLY the touch-up (the recommended action) — use the `edit` tool with the EXACT oldText/newText
        in "Edit R1" below. (If the reviewer prefers zero diff, SKIP this task and use the commit-message
        text in research §4 instead — both paths are contract-valid.)
  - FILE: README.md
  - ANCHOR: the config-validation paragraph tail ("...bool is not."). Re-grep
    `grep -n "Bare integers are accepted" README.md` to confirm the anchor is present + unique first.
  - EDIT: append ONE sentence documenting wrong-value -> ValueError at load (names output.backend +
    asr.device), wrapped ~80 cols.
  - DO NOT: change any heading; reflow the paragraph; use TypeError (Critical #2/#4).

Task 3: VALIDATE — L1 (README valid markdown + touch-up present) + L2 (drift guard green) + L3 (scope
        guard: ONLY README.md, or zero diff) + L4 (accuracy spot-checks). Iterate until all gates pass.
        No git commit unless the orchestrator directs it. If asked: message "P1.M4.T1.S1: README verified
        consistent with the three-fix changeset; [+1-sentence wrong-value fail-fast note applied | zero-diff
        fallback, finding recorded in commit message]; drift guard green (3 passed)".
```

#### Edit R1 — `README.md` config-validation paragraph (apply via `edit`; optional — zero-diff fallback in research §4)

`oldText` (the paragraph tail — unique; re-grep to confirm before editing):

```
feature at runtime. Bare integers are accepted for numeric fields; a `true`/`false`
bool is not.
```

`newText` (append ONE sentence, wrapped ~80 cols to match the README):

```
feature at runtime. Bare integers are accepted for numeric fields; a `true`/`false`
bool is not. A value outside a field's allowed set is rejected the same way — for
example `output.backend = "wtyp"` or `asr.device = "gpu"` raises `ValueError` at
load (the type is valid, the value is not), so a typo fails fast at startup instead
of crash-looping later.
```

> **Why this edit:** the paragraph already documents unknown-key (`TypeError`) + wrong-*type*
> (`TypeError`) rejection; this adds the third fail-fast mode — wrong-*value* (`ValueError`) — which
> `asr.device` (VT-005) and now `output.backend` (Issue 3) both enforce. `ValueError` (not `TypeError`)
> mirrors the code (the type is valid; the value is not). Naming both fields completes the picture for
> both enum fields, not just the changeset's one. "crash-looping later" references the systemd
> `Restart=on-failure` loop Issue 3 prevents. The sentence mirrors the preceding "wrong type" sentence's
> structure for prose consistency.

### Implementation Patterns & Key Details

```python
# PATTERN: documentation touch-up consumes the LANDED code's behavior — cite the real exception type.
#   OutputConfig.__post_init__ (config.py:126) + AsrConfig device check raise ValueError for a bad enum
#   value -> the README sentence says "ValueError" (NOT TypeError; the type IS valid). Names BOTH fields
#   (output.backend Issue 3 + asr.device VT-005) so the fail-fast picture is complete.

# GOTCHA: the oldText anchor must match byte-for-byte. Re-grep `grep -n "Bare integers are accepted" README.md`
#   to confirm the paragraph tail before editing. If a sibling edited the paragraph, re-read + re-anchor.

# GOTCHA: preserve ~80-col manual soft-wrap (the README is hand-wrapped, not reflowed). Wrap the new
#   sentence to match; do NOT collapse the paragraph onto one line. Do NOT change headings (anchors).

# GOTCHA: the zero-diff fallback is contract-valid. If the reviewer prefers no README change, SKIP Edit R1
#   and record the verification in the commit message (research §4 gives the text). The README is accurate
#   without the touch-up.
```

### Integration Points

```yaml
README.md (the ONLY file modified — and at most +1 sentence):
  - verify: "output.backend row :175 (3 valid values); no exit-code table; no internal-mechanism leak"
  - edit (optional): "config-validation paragraph ~:194-202 += 1 sentence (wrong-value -> ValueError at load)"
DO NOT TOUCH:
  - voice_typing/*.py  # fixes LANDED; this task verifies + documents only
  - tests/*            # the drift guard is RUN, not edited
  - tests/ACCEPTANCE.md  # acceptance doc, different concern (not an overview doc for this changeset)
  - PRD.md / tasks.json / prd_snapshot.md / .gitignore / config.toml / pyproject.toml / uv.lock
DEPENDENCIES: none (read-only verification + an optional prose edit + the existing pytest drift guard).
```

## Validation Loop

> This is a DOCUMENTATION VERIFICATION task. The gate is: README verified consistent + (if applied) the
> touch-up present + the drift guard green + NO source/test modified. No GPU/CUDA/daemon/mic (the drift
> guard parses `config.toml`). Run via bash from the repo root (zsh aliases bare python).

### Level 1: README validity + touch-up presence (if applied)

```bash
cd /home/dustin/projects/voice-typing
# 1a — README parses as text (no binary corruption); code-fence count is EVEN (no unclosed ``` block).
FENCES=$(grep -c '```' README.md); echo "fences=$FENCES"; [ $((FENCES % 2)) -eq 0 ] && echo "L1 ok: fences balanced" || echo "L1 FAIL: unbalanced fences"
# 1b — IF the touch-up was applied, the new sentence is present + the ValueError wording is correct:
grep -nE 'ValueError.*at load|outside a field.s allowed set' README.md && echo "L1 ok: touch-up present" || echo "L1 note: touch-up NOT applied (zero-diff fallback — verify that was intended)"
# 1c — no heading was added/removed/renamed (anchors intact): capture before/after heading sets if unsure.
grep -cE '^#{2,3} ' README.md   # record the count (should be unchanged from before the edit)
# Expected: fences balanced; IF touch-up applied the ValueError sentence is present; heading count unchanged.
```

### Level 2: The contract's drift guard (re-run live) — TWO TIMEOUTS

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m pytest tests/test_config_repo_default.py -q | tee /tmp/repo_default_audit.log
echo "exit: ${PIPESTATUS[0]}"
# Expected: exit 0; "3 passed in 0.01s". This test reads config.toml (NOT README) + asserts config.toml ==
#   dataclass defaults; OutputConfig defaults are unchanged (backend='wtype') -> stays green regardless of
#   the README edit. (The touch-up is prose; it cannot affect this test.)
COUNT=$(grep -oE '[0-9]+ passed' /tmp/repo_default_audit.log | head -1)
echo "drift guard: $COUNT"
rm -f /tmp/repo_default_audit.log   # one-shot tee of a <1KB summary; remove it after the check
```

### Level 3: Scope guard (no out-of-scope edits)

```bash
cd /home/dustin/projects/voice-typing
git status --porcelain
# Expected: ONLY " M README.md" (if the touch-up was applied) OR EMPTY (zero-diff fallback). Any change to
#   voice_typing/*.py, tests/*, config.toml, PRD.md, tasks.json, prd_snapshot.md, .gitignore, pyproject.toml,
#   uv.lock is a SCOPE VIOLATION (the fixes are LANDED; this task verifies + documents only).
git diff --name-only
# Expected: README.md (or empty).
! git status --porcelain | grep -qE 'voice_typing/|tests/|config\.toml|PRD\.md|tasks.json|prd_snapshot.md|pyproject.toml|uv.lock' && echo "L3 ok: no source/test/config/forbidden file modified" || echo "L3 FAIL: out-of-scope file modified"
```

### Level 4: Accuracy spot-checks (the README reflects the landed fixes)

```bash
cd /home/dustin/projects/voice-typing
# (A) output.backend row lists the 3 valid values (matches OutputConfig.__post_init__):
grep -n 'output.backend.*wtype.*ydotool.*tmux' README.md
# (Issue 3 landed) OutputConfig.__post_init__ + the ValueError message:
grep -nE 'def __post_init__|backend must be .wtype., .ydotool., or .tmux.' voice_typing/config.py
# (B) NO exit-code table in README (vacuously consistent with toggle -> exit 1):
grep -niE 'exit code|exits? (0|1|2|64)|sysexits|EX_USAGE' README.md && echo "L4 note: an exit-code doc EXISTS (verify it is consistent)" || echo "L4 ok: no exit-code doc (vacuously consistent)"
# (Issue 1 client surface) ctl.py exits 1 on ok:false:
grep -n 'return f"error:' voice_typing/ctl.py   # expect the exit-1 path
# (C) no _final_pending/dispatch-internals leaked (the one 'drain' hit is the user-facing feature):
grep -niE '_final_pending|cross.mode|dispatch.layer' README.md && echo "L4 FAIL: internal-mechanism doc leaked" || echo "L4 ok: no internal-mechanism leak"
grep -niE 'graceful drain on stop' README.md     # the legitimate user-facing §4.2 #2 feature (line ~130) — keep
# (Issue 2 landed) _final_pending reset in _arm/_disarm:
grep -n '_final_pending = False.*Issue 2' voice_typing/daemon.py   # expect 2 hits (_arm + _disarm)
# Expected: (A) row + fix present; (B) no exit-code doc + ctl exit-1 path present; (C) no leak + the
#   user-facing drain feature line present; Issue 2 reset present.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: README parses; fences balanced; IF touch-up applied the `ValueError` sentence is present; heading count unchanged.
- [ ] L2: `timeout 60 .venv/bin/python -m pytest tests/test_config_repo_default.py -q` → exit 0; **3 passed**.
- [ ] L3: `git status --short` shows ONLY `README.md` (touch-up) OR nothing (zero-diff); no source/test/config/forbidden file touched.
- [ ] L4: output.backend row lists 3 valid values; no exit-code table; no internal-mechanism leak; all 3 fixes confirmed landed.

### Feature (Verification) Validation
- [ ] **(A)** `output.backend` row (line 175) lists `wtype`/`ydotool`/`tmux`; "auto-falls-back" is accurate (runtime).
- [ ] **(B)** README has no voicectl exit-code table → vacuously consistent with the Issue 1 fix (exit 1).
- [ ] **(C)** No `_final_pending`/drain-internals/dispatch docs leaked (line 130's drain is the user-facing feature).
- [ ] **(touch-up, if applied)** config-validation paragraph documents wrong-value → `ValueError` at load (names `output.backend` + `asr.device`).

### Code Quality Validation
- [ ] IF touch-up applied: sentence wrapped ~80 cols; matches README tone; uses `ValueError` (not TypeError); no new heading.
- [ ] The verification findings are recorded for the commit message (the 3 points + the touch-up decision).
- [ ] No code/test/forbidden file modified.

### Documentation & Deployment
- [ ] The README reflects the post-fix behavior for all three issues (verified live).
- [ ] The changeset's user-facing fail-fast surface (Issue 3 load-time `ValueError`) is documented (touch-up) OR the gap is recorded (zero-diff).
- [ ] Adjacent concerns correctly deferred (the fixes themselves → P1.M1/M2/M3; acceptance criteria → P1.M5/P1.M6).

---

## Anti-Patterns to Avoid

- ❌ Don't edit any file other than `README.md` — especially not `voice_typing/*.py` (fixes LANDED), `tests/*`
  (the drift guard is RUN, not edited), `tests/ACCEPTANCE.md` (different concern), or `PRD.md`/`tasks.json`/
  `prd_snapshot.md`/`.gitignore`/`config.toml`/`pyproject.toml`/`uv.lock` (Critical #1).
- ❌ Don't use `TypeError` in the touch-up — wrong-*value* is a `ValueError` (the type IS valid; mirrors
  `OutputConfig.__post_init__`/`AsrConfig` device check) (Critical #2).
- ❌ Don't guess the `oldText` anchor — re-grep `grep -n "Bare integers are accepted" README.md` to confirm the
  paragraph tail is present + unique before editing (Critical #3).
- ❌ Don't reflow the paragraph or change headings — preserve the ~80-col manual soft-wrap + stable `#anchor`
  links (Critical #4).
- ❌ Don't add internal-mechanism docs (`_final_pending`/dispatch-layer/drain-internals) — Issues 1 & 2 are
  internal; the README correctly omits them (Critical #7).
- ❌ Don't hunt for a non-existent voicectl exit-code table — the README has none; that's the finding (Critical #6).
- ❌ Don't run pytest without `timeout 60` (inner) + the bash-tool timeout — AGENTS.md Rule 1 (Gotcha #8).
- ❌ Don't use bare `python`/`pytest` (zsh aliases) — `.venv/bin/python -m pytest` (Gotcha #9).

---

## Confidence Score

**9.5/10** for one-pass success. This is a read-only verification (the README is verified accurate on all
three fixes this round) + ONE optional, byte-exact prose touch-up (verbatim `oldText`/`newText` provided)
that is contract-invited ("noting that config values are validated at load time") and test-safe (no test
reads README; the drift guard reads `config.toml`, not README; `OutputConfig` defaults are unchanged →
**3 passed** this round). The three fixes are confirmed LANDED (`OutputConfig.__post_init__` config.py:126/136;
`_final_pending` reset daemon.py:1013/1041; `_dispatch` cross-mode routing). The zero-diff fallback
(commit-message text in research §4) makes the task succeed even if the reviewer prefers no README change.
The −0.5 reserves: (a) the `oldText` anchor could shift if a sibling edited the config-validation paragraph
— mitigated by the Task-1 re-grep; (b) an implementer might over-edit (add an exit-code table, or re-document
the internal mechanisms) — mitigated by Critical #6/#7. Both are bounded, one-line corrections gated by the
L3/L4 checks.