# PRP — P1.M3.T1.S1: README.md — Lite mode section + config table for `lite_post_speech_silence_duration`

## Goal

**Feature Goal**: Sync README.md (Mode B changeset-level doc) so it documents the new `asr.lite_post_speech_silence_duration` config knob (default `0.5`, PRD §4.2ter/§4.5) and explains the load-bearing insight behind lite mode: the **silence gate, not the model size, is the perceived-latency bottleneck**, so lite's shorter threshold is what makes it *feel* instant — not merely the smaller model transcribing a little faster. The config field + config.toml line already landed (P1.M1.T1.S1, Complete); the daemon wiring is in parallel (P1.M2.T1.S1). This task is the user-facing doc.

**Deliverable** (ONE artifact, single-file edit — `README.md`; no new files):
1. **Config tuning table** (~line 160): add a new row for `asr.lite_post_speech_silence_duration` immediately AFTER the existing `asr.post_speech_silence_duration` row (groups the two silence-threshold knobs).
2. **Lite mode section** (~line 121-122): add one sentence after the "produces markedly faster finals, at lower accuracy." clause, explaining the silence-gate optimization (the PRD §4.2ter latency-note insight).

**Success Definition**:
- (a) `grep -n 'lite_post_speech_silence_duration' README.md` matches in BOTH the config table AND the Lite mode section (was: 0 matches).
- (b) The new table row matches the table's cell format (`` | `asr.lite_post_speech_silence_duration` | `0.5` | … | ``) and is placed directly after the `asr.post_speech_silence_duration` row.
- (c) The new Lite-mode sentence names the silence gate as the perceived-latency bottleneck + the 0.5 vs 0.6 default difference — matching PRD §4.2ter + config.toml:38.
- (d) The new prose matches the README's terse, command-first voice (em-dash `—`, backticks for config keys/values; no marketing, no changelog voice).
- (e) No out-of-scope files: README.md ONLY. NOT `tests/ACCEPTANCE.md` (that is P1.M3.T1.S2 — criterion #10), NOT config.py/config.toml (P1.M1.T1.S1 — landed), NOT daemon.py (P1.M2.T1.S1 — parallel), NOT the "Model lifecycle & VRAM" section or the First-run one-liner. No `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`. No new files.

## User Persona

**Target User**: "dustin, six months from now, and anyone who clones the repo" (README line 7-8) — a Linux power user tuning voice-typing for snappy short-snippet dictation.

**Use Case**: The user reads the Lite mode section, tries `toggle-lite`, and wants to know WHY it feels instant (and how to tune the snappiness). The config table row tells them the knob + tuning range (0.3 razor-snappy ↔ 0.6 safe); the Lite-mode sentence tells them the knob is the real latency lever.

**Pain Points Addressed**: Without this, a user sees "lite = faster finals" and assumes the model is the win — then is confused when nudging `post_speech_silence_duration` (the normal-mode knob) doesn't change lite's feel. The doc now points them at the lite-specific knob and explains the silence-gate bottleneck.

## Why

- **Closes the doc gap for a landed, load-bearing feature.** PRD §4.2ter's central finding is that the silence gate (not the model) is the perceived-latency bottleneck — that's *why* lite has its own shorter threshold. The config field + daemon wiring land the behavior; the README must land the *explanation*, or users tune the wrong knob.
- **The tuning table is the config reference.** It already lists `post_speech_silence_duration` (0.6) and `lite_model` but omits the new field — a user scanning the table for "how do I make lite snappier?" finds nothing. One row fixes that.
- **Mode B boundary.** Per-file doc updates (config.py/config.toml comments) were Mode A (P1.M1.T1.S1, landed). This task sweeps ONLY the cross-cutting README overview. It does not re-document config schema or touch code.
- **Parallel-safe.** The in-flight P1.M2.T1.S1 edits `daemon.py` + `tests/test_daemon.py`; this task edits `README.md`. Zero file overlap.

## What

Two surgical edits to `README.md`:
1. **Table row** (after `asr.post_speech_silence_duration`): `` | `asr.lite_post_speech_silence_duration` | `0.5` | lite-mode silence threshold — seconds of silence before a final in **lite mode**. Lower is snappier (0.3 = razor-snappy, may split a brief pause; 0.6 = safe). The silence gate, not the model size, is the perceived-latency bottleneck — this is what makes lite **feel** instant. | ``
2. **Lite-mode sentence** (after "at lower accuracy."): names the silence-gate bottleneck + the 0.5-vs-0.6 default difference.

### Success Criteria

- [ ] `grep -n 'lite_post_speech_silence_duration' README.md` → ≥2 matches (table + Lite-mode section).
- [ ] The new table row is directly after the `asr.post_speech_silence_duration` row; cell format matches the table (backticks on key + default).
- [ ] The new Lite-mode sentence states the silence gate (not the model) is the perceived-latency bottleneck and the 0.5 vs 0.6 default.
- [ ] The new row's tuning guidance (0.3 razor-snappy / 0.6 safe) matches config.toml:38 + PRD §4.2ter.
- [ ] The new prose uses the README voice (terse, em-dash, backticks; no marketing/changelog voice).
- [ ] `git status --porcelain` shows ONLY `M README.md`.

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research note: both edits are verbatim oldText→newText against the current README (anchors verified, unique); the config field + config.toml line are confirmed landed (the INPUT); the accuracy cross-checks (0.3/0.6 tuning, silence-gate insight, 0.5 default) are pinned to config.toml:38 + PRD §4.2ter; the scope (README only; ACCEPTANCE is S2; Model-lifecycle/First-run out of scope) is explicit; and the validation greps are executable as written.

### Documentation & References

```yaml
# MUST READ — the file being edited (the two edit sites + the README voice)
- file: README.md
  why: "EDIT. Config tuning table (~line 159-176): insert the new row after the
        `asr.post_speech_silence_duration` row (line 160). Lite mode section (~line 116-128):
        insert the silence-gate sentence after 'produces markedly faster finals, at lower accuracy.'
        (line 121-122). Both anchors are unique + reproduced verbatim in the Implementation Blueprint."
  critical: "README voice (line 7-8): terse, command-first, no hand-holding. The table uses backticks
             around `asr.<key>` and `<default>`; em-dash (—) is used throughout. Match in the new text.
             Do NOT touch the Model lifecycle section (326+) or the First-run one-liner (105) — out of scope."

# MUST READ — verified edit anchors + accuracy cross-checks + scope
- docfile: plan/005_723f4c529eea/P1M3T1S1/research/readme_lite_silence_gate.md
  why: "§1 what landed (config.py:59 + config.toml:38 + the parallel daemon task is disjoint). §2 the
        two exact edit sites. §3 accuracy cross-checks (0.3/0.6 tuning + silence-gate insight + 0.5
        default — all match config.toml:38 + PRD §4.2ter). §4 SCOPE: README only; ACCEPTANCE is S2;
        Model-lifecycle + First-run out of scope. §5 validation greps."
  section: "ALL load-bearing. §2 (anchors), §3 (accuracy), §4 (scope)."

# MUST READ — the PRD source of the insight being documented (READ-ONLY)
- docfile: PRD.md
  why: "§4.2ter Lite mode: 'The silence gate, not the model, is the perceived-latency bottleneck ...
        lite MUST use its own shorter post_speech_silence_duration (default 0.5) ... that is what
        makes lite actually FEEL instant, cutting stop→text latency from ~1.6s to ~0.6s. Tunable:
        ~0.3 = razor-snappy; ~0.6 = safe.' §4.5: the config schema line. This is the authoritative
        wording the README must convey."
  critical: "Do NOT edit PRD.md (forbidden). The README conveys the insight in its own terse voice,
             not by quoting the PRD."

# CONTEXT — the landed config (the INPUT; confirms the default + tuning wording)
- file: config.toml
  why: "Line 38: `lite_post_speech_silence_duration = 0.5  # PRD §4.2ter: lite-mode silence threshold
        (the silence gate, not the model, is the perceived-latency bottleneck). 0.3 = razor-snappy
        (may split a brief pause); 0.6 = safe.` The README row + sentence must agree with this
        (same 0.3/0.6 guidance, same silence-gate insight, default 0.5)."
  critical: "Do NOT edit config.toml (P1.M1.T1.S1 owns it — landed). It is the accuracy source."

# CONTEXT — the parallel task (DISJOINT; confirms README is NOT edited by it)
- file: plan/005_723f4c529eea/P1M2T1S1/PRP.md
  why: "P1.M2.T1.S1 (IN PARALLEL) edits voice_typing/daemon.py + tests/test_daemon.py (the cfg_to_kwargs
        lite override). It does NOT touch README.md (confirmed). Zero overlap with this task."
  critical: "No conflict. This task = README.md only; P1.M2.T1.S1 = daemon.py + test_daemon.py only."

# CONTEXT — the NEXT task (S2 owns ACCEPTANCE.md; do NOT touch it here)
- docfile: plan/005_723f4c529eea/P1M3T1S2/PRP.md
  why: "P1.M3.T1.S2 updates tests/ACCEPTANCE.md criterion #10 for lite_post_speech_silence_duration.
        That is a SEPARATE task — this task (S1) is README.md only."
  critical: "Do NOT edit tests/ACCEPTANCE.md in S1 (it's S2's deliverable)."
```

### Current Codebase tree (state at P1.M3.T1.S1 start)

```bash
/home/dustin/projects/voice-typing/
└── README.md            # <-- EDIT: +1 table row (after asr.post_speech_silence_duration) +1 Lite-mode sentence.
# config.py / config.toml: P1.M1.T1.S1 (LANDED — the INPUT). daemon.py: P1.M2.T1.S1 (PARALLEL).
# tests/ACCEPTANCE.md: P1.M3.T1.S2 (NEXT task — do NOT touch). PRD.md: READ-ONLY.
```

### Desired Codebase tree with files to be added

```bash
README.md                # MODIFIED: +1 config-table row +1 Lite-mode sentence (the silence-gate explanation).
# NOTHING ELSE. No new files. No code/config/tests/PRD changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — README.md ONLY. tests/ACCEPTANCE.md criterion #10 is P1.M3.T1.S2 (a separate task) —
#   do NOT touch it. config.py/config.toml are P1.M1.T1.S1 (landed); daemon.py is P1.M2.T1.S1
#   (parallel). Editing any of those = scope violation. (Research §4.)

# CRITICAL #2 — PLACE THE TABLE ROW DIRECTLY AFTER asr.post_speech_silence_duration (not after
#   lite_model). The item explicitly says "AFTER the existing asr.post_speech_silence_duration row" —
#   grouping the two silence-threshold knobs together. The verbatim edit anchors on the
#   post_speech_silence_duration row + the following realtime_processing_pause row. (Research §2.1.)

# CRITICAL #3 — MATCH THE TABLE CELL FORMAT. Rows are `| `asr.<key>` | `<default>` | <effect> |`
#   (backticks around the key AND the default value; pipe-delimited; em-dash — in the prose). A row
#   missing the backticks or the pipes renders broken. Copy the verbatim newText from the Blueprint.

# CRITICAL #4 — THE SILENCE-GATE INSIGHT IS THE POINT. The Lite-mode sentence MUST convey "the
#   silence gate, not the model, is the perceived-latency bottleneck" — that is PRD §4.2ter's central
#   finding and the whole reason the knob exists. A sentence that only says "lite is faster" without
#   the silence-gate WHY misses the task's purpose. (Research §3; PRD §4.2ter.)

# CRITICAL #5 — ACCURACY: the tuning guidance (0.3 razor-snappy / 0.6 safe) + the default (0.5) +
#   the normal-mode contrast (0.6) must match config.toml:38 + config.py:59 + PRD §4.2ter. Do NOT
#   invent different numbers. (Research §3.)

# GOTCHA #6 — README VOICE: terse, command-first, em-dash (—), backticks for config keys/values, no
#   marketing ("exciting"/"blazing"), no changelog voice ("Issue X"). Match the surrounding prose.

# GOTCHA #7 — NO TEST FRAMEWORK APPLIES. README.md is markdown; no pytest/ruff/mypy gate. Validation
#   is grep (the new field appears in 2 places) + git status (only README.md) + a manual accuracy
#   read. Do NOT invent a lint command. (Research §5.)

# GOTCHA #8 — DON'T OVER-EDIT. The Model lifecycle & VRAM section (326+) and the First-run one-liner
#   (105) mention lite mode but are accurate and out of scope — leave them. Edit ONLY the two places
#   the item names (Lite mode section + config table). (Research §4.)
```

## Implementation Blueprint

### Data models and structure

Not applicable — no code, no data models. A single markdown-file edit (one table row + one sentence).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm the edit anchors + the landed INPUT (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      grep -n 'lite_post_speech_silence_duration' README.md                    # expect: 0 matches (the gap)
      grep -n 'lite_post_speech_silence_duration' voice_typing/config.py config.toml  # expect: landed (the INPUT)
      grep -n 'asr.post_speech_silence_duration` | `0.6`' README.md            # the table-row anchor (line ~160)
      sed -n '121,122p' README.md                                              # the Lite-mode sentence anchor
  - EXPECTED: 0 README matches; config.py:59 + config.toml:38 present; the two anchors match the verbatim oldText below.
  - DO NOT: edit anything yet.

Task 2: EDIT README.md — config tuning table: add the lite_post_speech_silence_duration row (Edit A)
  - INSERT the new row between the `asr.post_speech_silence_duration` row and the
    `asr.realtime_processing_pause` row (groups the two silence-threshold knobs).
  - EXACT oldText→newText: see Edit A.

Task 3: EDIT README.md — Lite mode section: add the silence-gate sentence (Edit B)
  - INSERT the sentence between "at lower accuracy." and "Arm it with" (line ~121-122).
  - EXACT oldText→newText: see Edit B.

Task 4: VALIDATE (no file change — see Validation Loop)
  - grep checks + git status. No git commit unless the orchestrator directs it.
```

### Edits — verbatim oldText → newText

#### Edit A — `README.md` config tuning table (new row after `asr.post_speech_silence_duration`)

`oldText` (the post_speech row + the next row — unique; insert between):
```
| `asr.post_speech_silence_duration` | `0.6` | seconds of silence before a final is emitted. Lower is snappier but can cut deliberate pauses. |
| `asr.realtime_processing_pause` | `0.15` | cadence of the live partial previews. Lower is more responsive; higher uses less CPU. |
```
`newText`:
```
| `asr.post_speech_silence_duration` | `0.6` | seconds of silence before a final is emitted. Lower is snappier but can cut deliberate pauses. |
| `asr.lite_post_speech_silence_duration` | `0.5` | lite-mode silence threshold — seconds of silence before a final in **lite mode**. Lower is snappier (0.3 = razor-snappy, may split a brief pause; 0.6 = safe). The silence gate, not the model size, is the perceived-latency bottleneck — this is what makes lite **feel** instant. |
| `asr.realtime_processing_pause` | `0.15` | cadence of the live partial previews. Lower is more responsive; higher uses less CPU. |
```

#### Edit B — `README.md` Lite mode section (silence-gate sentence after "at lower accuracy.")

`oldText` (line ~122 — unique via "at lower accuracy. Arm it with"):
```
finals, at lower accuracy. Arm it with `voicectl toggle-lite` / `start-lite`, or the
```
`newText` (the new sentence is inserted between "at lower accuracy." and "Arm it with"; re-wrapped to ~80 cols; the trailing "or the" preserves the connection to the next line "**Alt+Super+D** keybind"):
```
finals, at lower accuracy. It also uses its own shorter silence threshold
(`asr.lite_post_speech_silence_duration`, default `0.5` s vs the normal `0.6`) — the silence
gate, not the model, is the perceived-latency bottleneck, so shortening it is what makes lite
feel instant rather than merely transcribing a little faster. Arm it with `voicectl toggle-lite` / `start-lite`, or the
```

> **Why these edits:** Edit A makes the tuning table the complete config reference (a user scanning for "how do I make lite snappier?" now finds the knob + its tuning range). Edit B conveys PRD §4.2ter's central insight (the silence gate is the bottleneck) right where the README claims lite is "faster" — so the reader learns the *why*, not just the *what*. Both match the README's terse voice + the landed config (config.toml:38 / config.py:59). No code, no tests, no other doc sections.

### Implementation Patterns & Key Details

```markdown
<!-- PATTERN: table rows are `| `asr.<key>` | `<default>` | <effect> |` — backticks on key AND default,
     pipe-delimited, em-dash (—) in prose. The new row mirrors the existing rows exactly. -->
| `asr.lite_post_speech_silence_duration` | `0.5` | lite-mode silence threshold — … |

<!-- PATTERN: the Lite-mode sentence states the INSIGHT (silence gate = bottleneck), not just the
     behavior, and contrasts the lite default (0.5) with the normal default (0.6). It slots into the
     existing paragraph between the "faster finals" claim and the "Arm it with" instruction. -->

<!-- GOTCHA: the new table row goes AFTER asr.post_speech_silence_duration (grouping silence knobs),
     NOT after lite_model. The item is explicit about placement. -->

<!-- GOTCHA: keep the trailing "or the" in Edit B's newText so the next line ("**Alt+Super+D** keybind")
     still connects — markdown joins wrapped lines with a space. -->
```

### Integration Points

```yaml
DOCUMENTATION ONLY:
  - README.md: "+1 config-table row (asr.lite_post_speech_silence_duration) +1 Lite-mode sentence"
  - effect: "users find the knob in the tuning table + understand the silence-gate insight in Lite mode"
NO code/config/test integration:
  - config.py/config.toml: UNCHANGED (P1.M1.T1.S1 landed the field — the INPUT)
  - daemon.py: UNCHANGED (P1.M2.T1.S1 parallel — the wiring)
  - tests/ACCEPTANCE.md: UNCHANGED (P1.M3.T1.S2 owns criterion #10)
```

## Validation Loop

> No test framework applies to a markdown file (Gotcha #7). Validation is grep + git status + a manual
> accuracy read. Run from `/home/dustin/projects/voice-typing`. Use the `edit` tool for the changes.

### Level 1: Structure intact

```bash
cd /home/dustin/projects/voice-typing
echo "--- README headers (expect the same set, incl. '## Lite mode' + '## Configuration') ---"
grep -nE '^#{1,3} ' README.md | wc -l     # expect the same count as pre-edit (no section added/removed)
echo "--- table fence / row sanity ---"
grep -c '^| `asr\.' README.md              # the asr-row count rises by 1 (the new row)
```

### Level 2: The two edits landed

```bash
cd /home/dustin/projects/voice-typing
echo "--- (Edit A) the new table row exists, right after post_speech_silence_duration ---"
grep -n 'lite_post_speech_silence_duration` | `0.5`' README.md    # expect 1 match (the table row)
grep -n -A1 'asr.post_speech_silence_duration` | `0.6`' README.md  # the NEXT line is the new row
echo "--- (Edit B) the Lite-mode silence-gate sentence exists ---"
grep -n 'silence gate, not the model' README.md                    # expect 1 match (the Lite-mode sentence)
grep -c 'lite_post_speech_silence_duration' README.md              # expect >=2 (table row + Lite-mode sentence)
# Expected: the new table row is directly after post_speech_silence_duration; the Lite-mode sentence is present;
#   lite_post_speech_silence_duration appears in >=2 places.
```

### Level 3: Accuracy read (manual — the docs match the deployed config)

```bash
cd /home/dustin/projects/voice-typing
echo "--- the README's tuning guidance + default match config.toml:38 ---"
grep -n 'lite_post_speech_silence_duration' config.toml           # 0.3 razor-snappy / 0.6 safe / default 0.5
grep -n 'lite_post_speech_silence_duration' voice_typing/config.py # default 0.5
# Read the new README row + sentence and confirm: default 0.5; 0.3 razor-snappy / 0.6 safe; normal mode 0.6;
#   "silence gate, not the model, is the perceived-latency bottleneck". All must match config.toml:38 + PRD §4.2ter.
```

### Level 4: Scope guard

```bash
cd /home/dustin/projects/voice-typing
echo "--- ONLY README.md changed by THIS task ---"
git status --porcelain
# Expected: " M README.md" (this task). daemon.py/test_daemon.py (if present) belong to P1.M2.T1.S1 (parallel);
#   config.py/config.toml are P1.M1.T1.S1 (landed); tests/ACCEPTANCE.md is P1.M3.T1.S2 (not yet started).
#   Any change to those files BY THIS TASK = scope violation.
echo "--- no new files ---"
git status --porcelain | grep '^??' | grep -vE 'plan/' && echo "FAIL: untracked non-plan files" || echo "OK: no new non-plan files"
echo "--- ACCEPTANCE.md NOT touched (S2 owns it) ---"
git status --porcelain tests/ACCEPTANCE.md 2>/dev/null && echo "FAIL: ACCEPTANCE.md edited (out of scope — S2)" || echo "OK: ACCEPTANCE.md untouched"
```

## Final Validation Checklist

### Technical Validation
- [ ] `grep -c 'lite_post_speech_silence_duration' README.md` → ≥2 (table row + Lite-mode sentence).
- [ ] `grep -n -A1 'asr.post_speech_silence_duration` | `0.6`' README.md` → the next line is the new row.
- [ ] `grep -n 'silence gate, not the model' README.md` → 1 match (the Lite-mode sentence).
- [ ] `git status --porcelain` → only `M README.md` from this task; `tests/ACCEPTANCE.md` untouched.

### Feature Validation
- [ ] The new table row lists `asr.lite_post_speech_silence_duration`, default `0.5`, with the 0.3/0.6 tuning guidance + the silence-gate insight.
- [ ] The new Lite-mode sentence conveys "the silence gate, not the model, is the perceived-latency bottleneck" + the 0.5-vs-0.6 default.
- [ ] The README's tuning guidance + default match config.toml:38 + config.py:59 (accuracy).

### Code Quality Validation
- [ ] The new table row matches the cell format (backticks on key + default; pipes; em-dash).
- [ ] The new prose matches the README voice (terse, command-first; no marketing/changelog voice).
- [ ] Only the two named places edited (Lite mode section + config table); Model-lifecycle/First-run untouched.

### Documentation & Deployment
- [ ] README is internally consistent (the "faster finals" claim now has the silence-gate *why*; the tuning table lists the knob).
- [ ] No new env vars/config keys/user-facing surfaces (pure doc); no ACCEPTANCE.md edit (S2).

---

## Anti-Patterns to Avoid

- ❌ Don't edit any file other than `README.md` — config.py/config.toml (P1.M1.T1.S1, landed), daemon.py (P1.M2.T1.S1, parallel), tests/ACCEPTANCE.md (P1.M3.T1.S2), PRD.md (forbidden) are all out of scope.
- ❌ Don't place the table row after `asr.lite_model` — the item says AFTER `asr.post_speech_silence_duration` (group the silence knobs). (Critical #2.)
- ❌ Don't omit the silence-gate *insight* from the Lite-mode sentence — "lite is faster" alone misses the point; state that the silence gate (not the model) is the bottleneck. (Critical #4.)
- ❌ Don't invent tuning numbers — use 0.3 razor-snappy / 0.6 safe / default 0.5 / normal 0.6, matching config.toml:38 + PRD §4.2ter. (Critical #5.)
- ❌ Don't break the table cell format — backticks on the key AND the default, pipe-delimited. (Critical #3.)
- ❌ Don't edit the Model lifecycle & VRAM section or the First-run one-liner — accurate + out of scope. (Gotcha #8.)
- ❌ Don't write changelog voice ("Issue X" / "newly added") in README prose — it is user-facing; describe behavior. (Gotcha #6.)
- ❌ Don't invent a lint/test command for markdown — validation is grep + git status. (Gotcha #7.)
- ❌ Don't drop the trailing "or the" in Edit B — the next line ("**Alt+Super+D** keybind") must still connect. (Gotcha on wrapping.)

---

**Confidence Score: 9.5/10** for one-pass success. The task is small and fully bounded: two verbatim oldText→newText edits against verified-unique anchors, the INPUT (config field) is confirmed landed, the accuracy wording is pinned to config.toml:38 + PRD §4.2ter, the scope (README only; ACCEPTANCE is S2; Model-lifecycle/First-run out) is explicit, and the validation greps deterministically confirm both edits landed in the right place. The −0.5 reserves: a docs task's phrasing is ultimately a human judgment call, and an implementer could place the table row in the wrong spot or under-state the silence-gate insight — but the grep gates (row directly after post_speech_silence_duration; "silence gate, not the model" present; only README.md modified; ACCEPTANCE untouched) catch those structurally.
