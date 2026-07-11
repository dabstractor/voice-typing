# PRP — P1.M1.T1.S1: Remove `partial/` from the hypr_notify comment in config.toml line 49

## Goal

**Feature Goal**: Correct one stale inline comment in the repo's `config.toml` so the user-facing config reference stops claiming that realtime **partials** fire a `hyprctl notify` popup. Per PRD §4.6, partials go to the **state file only** (the tmux status line consumes them); `hyprctl` fires only on start / final / stop. This is the single actionable gap identified by delta PRD §2.

**Deliverable**: `config.toml` with line 49's comment changed from `start/partial/final/stop` → `start/final/stop`. The value (`true`) and every other line are unchanged. Comment-only — no code, no test, no behavior change.

**Success Definition**: (a) `grep -n 'partial' config.toml` shows the two LEGITIMATE hits (lines 31 and 35, for `realtime_model` and `realtime_processing_pause`) but **line 49 no longer contains `partial`**; (b) the file still parses as valid TOML; (c) no other file is modified.

## User Persona

**Target User**: The end user reading `config.toml` as their tuning reference (this file is *both* the runtime default *and* the user-facing doc — PRD "Mode A", stated in the file header). A misleading comment leads them to believe toggling `hypr_notify` will suppress/show live partial popups, which it cannot.

**Use Case**: User opens `config.toml` to understand what `hypr_notify` controls.

**Pain Points Addressed**: Removes a comment that contradicts both the daemon's actual behavior (PRD §4.6 / `feedback.py`) and the rest of the documentation (`config.py:76`, `README.md`), which already say `start/final/stop`.

## Why

- **Documentation accuracy / single-source consistency.** `config.py:76` (`hypr_notify: bool = True   # hyprctl notify one-liner for start/final/stop`) and `README.md` are already correct; only `config.toml:49` lags. Delta PRD §2 verified this is the ONLY actionable gap.
- **Behavioral truth.** `voice_typing/feedback.py` proves partials never notify: `update_partial()` is documented `THROTTLED disk write … NEVER notify` (L97); phase flips `never fire hyprctl` (L110-112); only `set_listening` transitions (`● listening` / `■ stopped`, L153-154) and `record_final` (`✔ <text>`, gated by `notify_on_final`, L133-134) call `_notify()`. So `start/partial/final/stop` is factually wrong.
- **Lowest-risk change possible.** A single comment token deletion; zero runtime effect.

## What

Edit exactly one inline comment on one line of `config.toml`. Remove the token `partial/` (including the trailing slash) from the slash-separated list `start/partial/final/stop`, leaving `start/final/stop`. Do not alter the value, the other comment text, alignment whitespace, or any other line.

### Success Criteria

- [ ] `config.toml` line 49 comment reads `… notify one-liner for start/final/stop. Requires Hyprland; …` (no `partial`).
- [ ] `config.toml` line 49 value is still `hypr_notify = true` (unchanged).
- [ ] Lines 31 and 35 still contain `partial` (the `realtime_model` / `realtime_processing_pause` comments — correct, untouched).
- [ ] `config.toml` still parses with `tomllib`.
- [ ] `config.py`, `README.md`, and all other files are unmodified.

## All Needed Context

### Context Completeness Check

_Pass._ The exact line, the exact substring, the exact replacement, the two legitimately-untouched neighbor lines, and the behavioral proof (feedback.py) are all verified below against the real files. No prior knowledge of this codebase is required.

### Documentation & References

```yaml
# THE CANONICAL TARGET (what the comment SHOULD say) — PRD's own §4.5 block
- docfile: plan/002_61d807f18dbe/prd_snapshot.md
  why: PRD §4.5 shows the canonical config.toml line: hypr_notify = true  # master switch
       for hyprctl popups (start/final/stop). The "(start/final/stop)" list is the
       authoritative phrasing — no 'partial'.
  critical: "Target phrase is start/final/stop. This matches config.py:76 and README.md."

# THE BEHAVIORAL TRUTH — why 'partial' is wrong
- file: voice_typing/feedback.py
  why: PRD §4.6 implementation. Confirms partials NEVER call hyprctl.
  pattern: "update_partial() (L97) = 'THROTTLED disk write; NEVER notify'. set_phase() (L110-112)
            = 'never fire hyprctl'. Only set_listening() transitions (L153-154: ●/■) and
            record_final() (L133-134: ✔, gated by notify_on_final) call _notify()."
  critical: "hyprctl fires ONLY on start/final/stop — never on a realtime partial."

# THE FIX SITE — the file + exact line to edit
- file: config.toml
  why: Line 49 (verified verbatim): hypr_notify = true      # show a hyprctl notify one-liner
       for start/partial/final/stop. Requires Hyprland; harmless elsewhere (the notify call
       is skipped when false).  ← the stale substring is 'start/partial/final/stop'.
  pattern: "Inline `# ...` comment after the value. Alignment whitespace varies per block;
            preserve the existing spaces between `true` and `#`."
  gotcha: "ONLY line 49's 'start/partial/final/stop' changes. Lines 31 and 35 ALSO contain
           'partial' (realtime_model 'live partial previews'; realtime_processing_pause 'live
           partial updates') — those are CORRECT and MUST NOT be touched."

# ALREADY-CORRECT siblings — DO NOT EDIT (delta PRD §2 verified)
- file: voice_typing/config.py
  why: Line 76 already reads '# hyprctl notify one-liner for start/final/stop' — correct.
  critical: "Do NOT edit config.py. It is already right."
- file: README.md
  why: Already documents partials as tmux-status-only (e.g. 'Watch the tmux status line for
       live partials, or the hyprctl popups') and hypr_notify as the master on/off switch.
  critical: "Do NOT edit README.md. It is already right."
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── config.toml              # line 49 = the ONLY line to edit (comment-only)
├── voice_typing/
│   ├── config.py            # line 76 hypr_notify docstring ALREADY correct — do NOT touch
│   └── feedback.py          # PROOF partials never notify (L97, L110-112, L133-154)
└── README.md                # ALREADY correct — do NOT touch
```

### Desired Codebase tree with files to be added/changed

```bash
config.toml                  # MODIFY line 49 comment only: start/partial/final/stop -> start/final/stop
# NO new files. NO changes to config.py / README.md / any .py / tests.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — 'partial' appears on THREE lines; edit ONLY line 49. Verified current state:
#   31: realtime_model    = "small.en"  # ... live partial previews ...   (CORRECT — realtime model)
#   35: realtime_processing_pause = 0.15 # ... live partial updates ...    (CORRECT — partial cadence)
#   49: hypr_notify = true  # ... start/partial/final/stop ...            (STALE — this is the edit)
# A naive `sed -i 's/partial//'` or global find/replace would CORRUPT lines 31 and 35.
# Use the UNIQUE substring 'start/partial/final/stop' (appears only on line 49), not 'partial'.

# CRITICAL #2 — comment-only. Do NOT change the value `true`, do NOT realign the column
# (the [feedback] block's alignment is intentional hand-formatting). Preserve every space.

# GOTCHA #3 — Do NOT 'helpfully' fix config.py or README.md. Delta PRD §2 verified both are
# already correct. Editing them is out of scope and would be noise in the changeset.

# GOTCHA #4 — full-path discipline: this machine aliases python3->uv run, pip->alias. For the
# TOML-parse validation use .venv/bin/python explicitly (or just python3 via uv run).

# GOTCHA #5 — this is subtask S1 of a larger spec-sync plan. The full pytest regression
# (T2.S2: 'confirm 197 tests still green') and the README sweep (T3.S1) are SIBLING subtasks,
# NOT this one. S1 touches config.toml line 49 only.
```

## Implementation Blueprint

### Data models and structure

None. No data models, schema, or code. This is a comment-token deletion in a TOML file.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT config.toml line 49 — remove the token 'partial/' from the comment list
  - FIND line 49. Its current exact text (verified):
      hypr_notify = true      # show a hyprctl notify one-liner for start/partial/final/stop. Requires Hyprland; harmless elsewhere (the notify call is skipped when false).
  - REPLACE the unique substring `start/partial/final/stop` with `start/final/stop`.
    (Leave 'start' and 'final/stop' in place; delete exactly the 8 characters `partial/`.)
  - RESULT line 49 (after edit):
      hypr_notify = true      # show a hyprctl notify one-liner for start/final/stop. Requires Hyprland; harmless elsewhere (the notify call is skipped when false).
  - The `oldText`/target MUST be `start/partial/final/stop` (unique on the line and in the file),
    NOT the bare word `partial` (which also appears, correctly, on lines 31 and 35).
  - DO NOT change the value `true`, the spaces between `true` and `#`, or any other character.

Task 2: VALIDATE (run the gates below). No git commit unless the orchestrator directs it (it
  manages commits between subtasks). If asked to commit, message:
  "P1.M1.T1.S1: fix stale hypr_notify comment in config.toml (partials never notify)".
```

### Implementation Patterns & Key Details

```python
# There is no code pattern. The entire change is one inline-comment token removal:
#   before: ... one-liner for start/partial/final/stop. Requires Hyprland; ...
#   after:  ... one-liner for start/final/stop. Requires Hyprland; ...
#
# Why this is correct: PRD §4.6 ('partials go to the state file only') + feedback.py
# (update_partial = 'NEVER notify'; only start/final/stop call _notify). The comment is
# the only place in the docs that still claims partials notify; config.py:76 and README.md
# already say start/final/stop. This edit brings config.toml in line with all of them.
```

### Integration Points

```yaml
CONFIG SCHEMA (voice_typing/config.py):
  - NO field is added/removed/renamed. hypr_notify stays `bool = True`. config.py is the schema
    source of truth and is ALREADY correct (line 76) — do NOT edit it. This subtask only aligns
    the config.toml MIRROR's comment with config.py's comment.

RUNTIME BEHAVIOR:
  - Zero change. Comments are not read by tomllib beyond `#` stripping; the parsed value
    (`hypr_notify = true`) is byte-identical before and after.

DOCUMENTATION (PRD "Mode A"):
  - This IS the doc fix (config.toml is the doc being corrected). Per the contract, no separate
    docs subtask is needed for this edit. (The README sweep is sibling subtask T3.S1.)
```

## Validation Loop

> Full paths for any python invocation (machine aliases python3→uv run). All gates are trivial —
> a one-line comment edit can only fail by (a) editing the wrong line, (b) corrupting lines 31/35,
> or (c) breaking TOML syntax. The gates catch all three.

### Level 1: The edit landed on the right line and the right substring

```bash
cd /home/dustin/projects/voice-typing
echo "--- line 49 must now read start/final/stop (no partial) ---"
sed -n '49p' config.toml
echo "--- 'start/final/stop' present on line 49? ---"
grep -n 'start/final/stop' config.toml   # EXPECT: line 49
echo "--- 'start/partial/final/stop' must be GONE everywhere ---"
grep -n 'start/partial/final/stop' config.toml && echo "L1 FAIL: stale phrase still present" || echo "L1 PASS: stale phrase removed"
# Expected: line 49 shows 'start/final/stop'; the third grep prints nothing + "L1 PASS".
```

### Level 2: The LEGITIMATE 'partial' mentions on lines 31 & 35 are intact

```bash
cd /home/dustin/projects/voice-typing
echo "--- all 'partial' occurrences (should be exactly lines 31 and 35 only now) ---"
grep -n 'partial' config.toml
test "$(grep -c 'partial' config.toml)" -eq 2 && echo "L2 PASS: exactly 2 partial hits (lines 31, 35)" || echo "L2 FAIL: expected 2 hits"
# Expected: line 31 (realtime_model 'live partial previews') + line 35 (realtime_processing_pause
# 'live partial updates') ONLY. If 1 or 3 hits, you edited the wrong line(s).
```

### Level 3: TOML still parses (comment didn't break syntax)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
import tomllib
d = tomllib.load(open("config.toml", "rb"))
assert d["feedback"]["hypr_notify"] is True, d["feedback"]["hypr_notify"]
print("L3 PASS: config.toml parses; feedback.hypr_notify ==", d["feedback"]["hypr_notify"])
PY
# Expected: "L3 PASS: config.toml parses; feedback.hypr_notify == True".
# (A comment-only change cannot break parsing, but this guards against an accidental value edit.)
```

### Level 4: No out-of-scope files touched

```bash
cd /home/dustin/projects/voice-typing
echo "--- git status: ONLY config.toml should appear as modified (plus any pre-existing orchestrator entries) ---"
git status --short
echo "--- diff confined to config.toml line 49? ---"
git diff config.toml
# Expected: a single-line diff on config.toml removing 'partial/'. config.py / README.md / *.py
# must NOT appear in the diff. (If the orchestrator's tasks.json shows as modified, that is
# pre-existing and not from this subtask.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: line 49 reads `start/final/stop`; `start/partial/final/stop` absent from the whole file.
- [ ] L2: exactly two `partial` hits remain (lines 31 and 35 — the legitimate ones).
- [ ] L3: `config.toml` parses with `tomllib`; `feedback.hypr_notify is True`.
- [ ] L4: `git diff` shows only the one-line comment change in `config.toml`.

### Feature Validation
- [ ] `config.toml:49` comment no longer claims partials fire `hyprctl` (now consistent with PRD §4.6, `feedback.py`, `config.py:76`, `README.md`).
- [ ] Value `hypr_notify = true` unchanged.
- [ ] No behavior change (comment-only).

### Code Quality Validation
- [ ] No other lines/whitespace in `config.toml` altered.
- [ ] `config.py` and `README.md` unmodified (already correct per delta PRD §2).

### Scope Boundary Validation
- [ ] No `.py` source, test, README, or sibling-subtask work (T2 regression / T3 README sweep) included.
- [ ] No git operations beyond the single-file edit.

---

## Anti-Patterns to Avoid

- ❌ Don't do a global `partial` find/replace or `sed s/partial//` — it will corrupt lines 31 and 35. Target the unique phrase `start/partial/final/stop`.
- ❌ Don't edit `config.py` or `README.md` "for consistency" — they are already correct; editing them is scope creep and adds review noise.
- ❌ Don't change the value `true`, realign the comment column, or touch any other line.
- ❌ Don't run the full pytest suite here — that is sibling subtask T2.S2 ("197 tests still green"). S1 is comment-only and cannot affect tests.
- ❌ Don't add a changelog/README note for this edit — per the contract (Mode A), this subtask IS the doc fix; no separate doc artifact.

---

## Confidence Score

**10/10** for one-pass implementation success. The change is a single 8-character deletion (`partial/`) in one inline comment, on one verified line, with a unique target substring. All three ways it could go wrong (wrong line, corrupting lines 31/35, breaking TOML) are explicitly guarded by validation gates L1–L3, and the behavioral justification (PRD §4.6 + feedback.py) is verified against the actual source.
