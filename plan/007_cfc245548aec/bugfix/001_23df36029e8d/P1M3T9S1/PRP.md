---
name: "bugfix P1.M3.T9.S1 — README.md: sweep streaming/cancel/configuration prose"
---

## Goal

**Feature Goal**: Make README.md's §Streaming dictation, §Backspace-cancel, and §Configuration
prose truthful against the 8 landed bugfixes (BUG-001..008, commits `03f9602`..`eac2d03`): every
statement matches the code, and every landed user-visible behavior that a reader would care about
is stated — recovery after a rejected final, live re-say after cancel, immediate stop-after-cancel,
stale-partial disarm guarantee, unknown-config-table rejection. Where a section needs no change,
record an explicit no-change verdict (the contract demands this per section).

**Deliverable**: An edited `README.md` (docs-only diff — no other file changes; `tests/ACCEPTANCE.md`
is the SIBLING task S2 and must NOT be touched).

**Success Definition**: `git diff --stat` shows README.md only; every new/changed claim verifies
against a pinned code line (greps below); no engine internals leak into user prose; the fast test
sweep is untouched and unaffected.

## User Persona (if applicable)

**Target User**: A user installing/configuring voice-typing from the README (and a future maintainer).

**Use Case**: Reading §Streaming/§Backspace-cancel/§Configuration to learn what the tool does while
dictating, what happens on hallucinated finals or cancels, and what config rejects.

**Pain Points Addressed**: Post-bugfix README is silent about rejected-final recovery (a user who
sees "filtered hallucination — not typed; keep dictating" has no doc explaining it) and still says
"rejects unknown keys" without the now-landed unknown-table rejection.

## Why

- The bugfix PRD's Recommendations require user-visible truthfulness (e.g. "log a user-visible
  warning when output freezes" landed; the README never mentions the behavior it accompanies).
- Contract (Mode B, SOW §5): the coherent bugfix delta ships with truthful docs; this subtask IS
  that changeset-level docs task, running LAST after all implementing subtasks (all Complete).

## What

Minimal, user-facing edits to exactly three README sections. Do NOT restate engine internals
(`resume()`, freeze classes, `_suppressed`, `_touch_speech` stay out of user prose). Do NOT cite
bug IDs in user-facing prose.

### Success Criteria

- [ ] §Streaming dictation: adds a safety-rail bullet for rejected finals (blocklist/min_chars →
      that utterance's tail freezes on screen, typing resumes at the next speech, journal warning +
      optional toast are the cue); adds the nothing-types-while-toggled-off guarantee; notes
      case-insensitive delta matching in the partials-live bullet.
- [ ] §Backspace-cancel: states the re-said sentence streams live; states cancel-then-stop disarms
      immediately (no drain wait).
- [ ] §Configuration: the unknown-key rejection sentence also covers unknown top-level tables
      (typo'd `[secton]` fails loudly at load).
- [ ] Explicit no-change verdicts recorded (in the subtask result / commit message, not in README)
      for BUG-003 (space already promised) and BUG-005 (README documents no socket framing).
- [ ] `git diff --stat` = README.md only.

## All Needed Context

### Context Completeness Check

"If someone knew nothing about this codebase, would they have everything needed to implement this
successfully?" — Yes: the exact landed behaviors are pinned to code lines below, the README's
current text at each edit point is quoted/located by line, and the contract's minimal-edit rule and
no-change-verdict requirement are stated.

### Documentation & References

```yaml
# MUST READ - Include these in your context window
- file: README.md
  why: THE edit target (436 lines @ eac2d03). §Streaming dictation :129 (bullets: partials-live
        ~:138, silence-commit ~:142, continuations ~:147, pause-never-ends ~:151; safety rails:
        stranded-tails ~:154, keystrokes-win ~:157, rollback-hatch ~:159); §Backspace-cancel
        :164-181 (idempotent ~:172, listener ~:176, one-warning ~:178, fallback bind ~:180);
        §Configuration :197 (key table :205-233, VAD-constants note :234, unknown-keys sentence
        :243-244); §Logs/status :339-388 (documents NO socket request framing).
  pattern: match the existing voice — bold lead-in bullets, em-dashes, parenthetical config-key
           references like (`asr.lite_post_speech_silence_duration`, default `0.8` s).
  gotcha: §Upgrading from Rev 1 (:114-128) legitimately mentions toggle-lite/mode — do NOT "fix"
          those; they describe the upgrade path, not current behavior.

- file: voice_typing/daemon.py
  why: Source of truth for the behaviors being documented. :1181-1186 the rejected-final cue
        (journal WARNING "streaming: final rejected by filter (blocklist/min_chars); tail frozen
        as-is, typing resumes at next speech" + `feedback.notify("filtered hallucination — not
        typed; keep dictating")`, self-gated on `hypr_notify`); :1396-1404 genuinely-new speech
        lifts rejected-final freeze AND post-cancel suppression via `stream.resume()`;
        `_on_partial` listening gate (BUG-004).
  pattern: READ ONLY.
  gotcha: :1154-1168 comments describe the OLD session-freeze — read :1170+ for landed behavior.

- file: voice_typing/streaming.py
  why: `reset_after_cancel()` :220, `resume()` :293 (API names — for your understanding only,
        NOT for README prose); frozen-commit trailing space; case-insensitive extend match.
  pattern: READ ONLY.

- file: voice_typing/config.py
  why: Unknown top-level tables now raise TypeError like unknown keys (BUG-006).
  pattern: READ ONLY.

- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/architecture/config_tests_docs.md
  why: :22 = README heading line-number inventory (matches above); :31-35+ = per-bug docs-duty
        rows (BUG-001/002 → this sweep; BUG-003 "README already promises space-separated words";
        BUG-005 "README §Logs/status only if it documents request framing" — it doesn't).
  section: README heading map + per-bug docs table.

- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/research_notes/… (or sibling PRP dirs)
  why: Skip — the table below supersedes; this PRP is self-contained.

- file: AGENTS.md  (repo root)
  why: Run rules still apply to validation commands (timeouts), though this docs task runs
        nothing heavy: validation is grep/read-based.
  pattern: any command you do run gets an inner `timeout` + bash-tool timeout.
```

### Landed behaviors → README actions (the core table)

| Bug | Landed behavior (verify pin) | README action |
|---|---|---|
| BUG-001 | Rejected final freezes only that utterance's tail; typing resumes at next speech. Cue: journal WARNING + optional toast "filtered hallucination — not typed; keep dictating" (daemon.py:1181-1186, resume hook :1396-1404) | §Streaming safety rails: ADD bullet |
| BUG-002 | Re-said sentence after Backspace-cancel streams live (same resume hook) | §Backspace-cancel: extend the "just say the sentence again" line |
| BUG-003 | Frozen commit appends trailing space (internal) | NO CHANGE — verdict |
| BUG-004 | Stale partials never type while toggled off (`_on_partial` listening gate) | §Streaming: ADD one-line guarantee (pause bullet or safety rails) |
| BUG-005 | Empty socket line gets an error reply (internal framing) | NO CHANGE — verdict (README documents no framing) |
| BUG-006 | Unknown top-level config tables raise TypeError | §Configuration :243-244: extend the sentence |
| BUG-007 | Cancel-then-stop disarms immediately (sentinel finalizes; no ~5s drain) | §Backspace-cancel: ADD clause |
| BUG-008 | Extend match is case-insensitive → clean deltas after the casing guard | §Streaming partials-live bullet (~:138): ADD clause |

### Current Codebase tree (relevant excerpt)

```bash
README.md                       # EDIT TARGET (only file this task touches)
voice_typing/daemon.py          # READ ONLY — behavior pins :1181-1186, :1396-1404
voice_typing/streaming.py       # READ ONLY — resume() :293, reset_after_cancel() :220
voice_typing/config.py          # READ ONLY — unknown-table rejection
tests/ACCEPTANCE.md             # FORBIDDEN here — sibling task P1.M3.T9.S2 owns it
```

### Desired Codebase tree with files to be added and responsibility of file

No new files.

### Known Gotchas of our codebase & Library Quirks

```python
# GOTCHA: README:121-126 (§Upgrading from Rev 1) intentionally mentions toggle-lite/mode: lite —
#   that is upgrade-path documentation, NOT staleness. Leave it.
# GOTCHA: keep prose user-facing — the toast text quoted in README must be VERBATIM
#   "filtered hallucination — not typed; keep dictating" (daemon.py:1186); never paraphrase cues.
# GOTCHA: the toast is optional (feedback.hypr_notify master switch) — phrase as "a toast (if
#   notifications are on) plus a journal warning", matching §Feedback surfaces' gating language.
# GOTCHA: do not add a `filtered`/rejected-final row to the config table — nothing is configurable
#   about it (blocklist/min_chars rows already exist).
# GOTCHA: markdown tables in §Configuration are pipe-aligned in places; keep edits inside the
#   prose sentence at :243-244, not the table.
```

## Implementation Blueprint

### Data models and structure

None — documentation-only.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: VERIFY every claim pin before editing (bash-tool timeout 30; inner timeouts)
  - grep -n "filtered hallucination" voice_typing/daemon.py        # → :1186 (toast text verbatim)
  - grep -n "_stream.resume()" voice_typing/daemon.py              # → the next-speech lift hook
  - sed -n '239,246p' README.md                                    # the unknown-keys sentence
  - grep -n "unknown" voice_typing/config.py | head                # table rejection
  # If ANY pin has moved/changed meaning since this PRP, re-read the code at the new location
  # and document THAT behavior — never write a claim you have not re-verified.

Task 2: EDIT README.md §Streaming dictation (:129-181)
  - Safety rails (~:154-160): ADD one bullet, e.g.
      "**Rejected finals recover.** A hallucination caught by `filter.blocklist` (or a final
      below `filter.min_chars`) is not typed: that utterance's fragment freezes on screen as
      last shown, a journal warning (and, if notifications are on, a brief toast) says
      `filtered hallucination — not typed; keep dictating`, and live typing resumes with your
      next words."
  - Partials-live bullet (~:138): append a clause noting extensions match case-insensitively,
    so a casing-corrected fragment still extends by clean deltas instead of full rewinds.
  - Pause-never-ends bullet (~:151) or safety rails: one line that nothing is ever typed while
    dictation is toggled off (partials are gated like finals).

Task 3: EDIT README.md §Backspace-cancel (:164-181)
  - Extend the erase paragraph: the re-said sentence types LIVE again from its first words
    (suppression lifts as soon as you speak again).
  - Add: stopping right after a cancel disarms immediately — no drain wait.

Task 4: EDIT README.md §Configuration (:243-244)
  - Extend "The config loader (`config.py`) rejects unknown keys with `TypeError`" to also say
    unknown top-level TABLES (a typo'd `[outpt]` section) are rejected the same way — a mistyped
    section fails loudly instead of silently disabling a feature.

Task 5: RECORD no-change verdicts + commit
  - In the commit message (and subtask result): BUG-003 no change (space-separated words already
    promised by existing prose); BUG-005 no change (README documents no socket request framing).
  - Commit README.md alone, e.g. "Sync README streaming/cancel/config prose with the bugfix
    behaviors". Do NOT touch tests/ACCEPTANCE.md, PRD.md, tasks.json, plan snapshots.
```

### Implementation Patterns & Key Details

```markdown
<!-- PATTERN: match the existing bullet voice (bold lead-in, config keys in backticks, em-dash) -->
- **Rejected finals recover.** A hallucination caught by `filter.blocklist` … — keep dictating;
  live typing resumes with your next words.

<!-- PATTERN: the config-loader sentence edit (minimal, inside the existing sentence) -->
The config loader (`config.py`) rejects unknown keys — and unknown top-level tables — with
`TypeError`, so a stray key *or a mistyped section name* makes the daemon fail to load …

<!-- GOTCHA: never paraphrase the toast text; quote it verbatim from daemon.py:1186. -->
```

### Integration Points

```yaml
DOCS:
  - README.md §Streaming dictation / §Backspace-cancel / §Configuration — the only surface.
  - tests/ACCEPTANCE.md is OWNED BY SIBLING S2 — out of scope here.
OPTIONAL (flag, do not do by default): config.toml's header comment "Unknown keys are REJECTED"
  could gain "and tables" — contract scopes this task to README.md; only include if the operator
  or S2 confirms.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
bash -n <(echo) 2>/dev/null; # n/a — markdown only. Use a render sanity check:
timeout 30 .venv/bin/python - <<'PY'   # bash-tool timeout 40
import re, pathlib
t = pathlib.Path("README.md").read_text()
assert t.count("## Streaming dictation") == 1 and t.count("### Backspace-cancel") == 1
for frag in ("filtered hallucination — not typed; keep dictating",):
    assert frag in t, frag
# no engine internals leaked into user prose:
for bad in ("resume()", "reset_after_cancel", "_suppressed", "_touch_speech", "BUG-0"):
    assert bad not in t, bad
PY
```

### Level 2: Claim verification (component validation)

```bash
# every new claim's pin still holds — bash-tool timeout 30:
grep -n "filtered hallucination" voice_typing/daemon.py          # toast text matches README verbatim
grep -n "_stream.resume()" voice_typing/daemon.py                # next-speech lift exists
grep -rn "unknown" voice_typing/config.py | grep -i table        # table rejection exists
grep -n "toggle-lite" README.md                                  # ONLY in §Upgrading (:121-126)
```

### Level 3: Integration (system validation)

```bash
# docs-only change: nothing to run heavy. Confirm the daemon suite is unaffected ONLY if you
# touched anything beyond README.md (you should not have):
git diff --stat        # → README.md only  — bash-tool timeout 30
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Readability pass: render the three sections and check the new bullets read as user prose
# (no code identifiers beyond config keys, no bug IDs):
sed -n '129,182p' README.md; sed -n '234,246p' README.md   # bash-tool timeout 30
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 1 render/structure check passes; no internals/bug-IDs in README.
- [ ] Level 2: all claim pins grep-verified; toggle-lite appears only in §Upgrading.
- [ ] Level 3: `git diff --stat` = README.md only.
- [ ] No test suite regressed (docs-only; nothing executed beyond greps).

### Feature Validation

- [ ] §Streaming: rejected-final recovery bullet + toggled-off guarantee + case-insensitive delta clause.
- [ ] §Backspace-cancel: live re-say + immediate stop-after-cancel.
- [ ] §Configuration: unknown-table rejection sentence.
- [ ] No-change verdicts recorded for BUG-003 and BUG-005.

### Code Quality Validation

- [ ] Existing bullet/table voice and formatting preserved; toast text verbatim.
- [ ] No edits outside the three sections (and none needed elsewhere).

### Documentation & Deployment

- [ ] Commit message states the verdicts; README.md alone committed.

## Anti-Patterns to Avoid

- ❌ Don't restate engine internals (resume(), freeze classes) or cite BUG-IDs in user prose.
- ❌ Don't paraphrase the toast text — quote `daemon.py:1186` verbatim.
- ❌ Don't "fix" §Upgrading from Rev 1's toggle-lite mentions (legitimate upgrade-path docs).
- ❌ Don't touch tests/ACCEPTANCE.md (sibling S2), voice_typing/*, PRD.md, tasks.json, plan files.
- ❌ Don't force an edit where the contract wants an explicit no-change verdict (BUG-003/005).

---

**Confidence Score: 9/10** — every edit point is pinned to README line + code line, the landed
behaviors were re-verified at HEAD (`eac2d03`), and the task is a scoped docs diff with grep-based
validation. Residual risk: only line drift between PRP writing and execution, covered by Task 1's
re-verification step.
