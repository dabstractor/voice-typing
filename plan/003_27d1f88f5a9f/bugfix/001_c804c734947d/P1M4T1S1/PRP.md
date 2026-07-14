# PRP — P1.M4.T1.S1: Update README.md teardown claims + phase lifecycle + config-validation description

## Goal

**Feature Goal**: Bring `README.md` into agreement with the **landed** bugfix behavior for three issues, so the user-facing docs no longer describe pre-fix (inaccurate) behavior. This is the **documentation-sync** subtask of the bugfix changeset (item DOCS: "This IS the documentation subtask"). Three prose-only edits within two existing README sections: (a) the SIGTERM/teardown budget (Issue 1), (b) the phase lifecycle's disarm→idle transition (Issue 2), and (c) config wrong-type rejection (Issue 4). **No code, no tests, no new files, no new headings.**

**Deliverable** (ONE artifact — `README.md`, three edits):
1. **Region C (teardown)** — rewrite the lines that currently claim "bounded at ≤10s" and "the old ~90s SIGKILL is gone" (the latter was PROVEN inaccurate by Issue 1) to state: teardown is **single-flight and bounded** — `RecorderHost.stop()` joins the child ≤5 s then SIGKILLs its process group, so one teardown is a few seconds, comfortably under `TimeoutStopSec=15`, and the SIGTERM path no longer races a double teardown.
2. **Region B (phase lifecycle)** — add an explicit sentence that disarming the mic (manual `stop`, `toggle` off, or the 30 s auto-stop) transitions `phase` back to **`idle`** (loaded, not listening), so a stopped daemon never reports a stale `listening`/`speaking`.
3. **Region A (config validation)** — add a sentence that a **wrong-typed** config value (e.g. `auto_stop_idle_seconds = "thirty"`) is also rejected at load with `TypeError` naming the field, mirroring the existing unknown-key behavior (bare ints accepted; bool rejected).

**Success Definition**:
- (a) `README.md` is still valid Markdown (parses; code-fence count even; **no heading text/level changed** so all `#anchor` links stay valid; manual ~76-col soft-wrap preserved in edited blocks).
- (b) The three new claims are **factually accurate** against the LANDED code: `_STOP_JOIN_TIMEOUT_S = 5.0` + `_stop_lock` single-flight (`recorder_host.py:87/:140/:255/:264-274`); `_disarm()` → `set_phase("idle")` (`daemon.py:918`); `__post_init__` → `TypeError` (`config.py:65/:121`); systemd `TimeoutStopSec=15` (`systemd/voice-typing.service:52`).
- (c) The stale/inaccurate claims are gone: no "bounded at ≤10s", no unqualified "the old ~90s SIGKILL is gone".
- (d) `git status --short` shows **ONLY** `README.md` modified. NO edit to `tests/ACCEPTANCE.md` (sibling task P1.M4.T1.S2 owns it), NO `.py` file, NO `config.toml`/`PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`.

## User Persona

**Target User**: The end user reading `README.md` (a Hyprland/Wayland Linux user running the voice-typing daemon under systemd) — and the maintainer who relies on the README to explain lifecycle/teardown/config behavior.

**Use Case**: (1) The user runs `systemctl --user stop voice-typing` (or logs out) and wants to know it will stop cleanly in seconds without a timeout failure — the teardown block answers that. (2) The user runs `voicectl status` after a `stop` and wants the `phase:` line to make sense — the lifecycle block explains the `idle` state. (3) The user typos a config value's type and wants to know it fails loudly at load — the config block documents that.

**Pain Points Addressed**: The README currently **over-promises** teardown ("SIGKILL is gone") that Issue 1 proved was false until the fix, and **under-documents** two fixes (phase→idle, config type validation) that a reader would otherwise not know exist. Correcting these prevents user confusion ("why did my stop time out?") and surfaces the now-reliable behavior.

## Why

- **The README must not lie about the critical regression.** Issue 1 (Critical) was *exactly* that `systemctl stop` while armed hung 15 s → SIGKILL — the precise failure PRD §8 says MUST be eliminated. The current README asserts that failure "is gone", which was false pre-fix. Now that the fix has landed (P1.M1.T2: single-flight `_stop_lock` + `_teardown_done` Event + 5 s budget), the claim can finally be made **truthfully and precisely** (single-flight, ≤5 s join, under `TimeoutStopSec=15`).
- **Issue 2's fix (phase→idle) is invisible without docs.** `_disarm()` now calls `set_phase("idle")` (`daemon.py:918`), but the README's lifecycle paragraph only enumerates states without stating the disarm transition. A user (or a future overlay UI keying off `phase`) reading the README would not know `phase` returns to `idle` on stop. PRD §4.6 ("once loaded, `phase` cycles `idle`/`listening`/`speaking`") expects this documented.
- **Issue 4's fix (config type validation) extends the §4.5 "fail loud" promise to types.** The README documents unknown-key rejection but not wrong-type rejection; a user whose `auto_stop_idle_seconds = "thirty"` previously got a silent runtime break now gets a clear load-time `TypeError` — and the README should say so, mirroring the unknown-key paragraph.
- **Small, surgical, low-risk, unblocks the changeset close-out.** P1.M4 (Documentation Sync) is the final milestone; S1 (README) + S2 (ACCEPTANCE.md) together close out the bugfix. This task is prose-only and touches one file.

## What

Three edits to `README.md`, each an exact `edit`-tool replacement (verbatim `oldText`/`newText` in Implementation Blueprint → Tasks 1–3). The edits:
- **Edit C** rewrites the teardown paragraph (last paragraph of `### Model lifecycle & VRAM`).
- **Edit B** inserts one sentence into the phase-lifecycle paragraph (same section).
- **Edit A** appends sentences to the config-validation paragraph (`### Voice-activity constants are NOT config keys`).

All three preserve the existing ~76-column soft-wrap, inline-code backticks, em dashes, and section headings.

### Success Criteria

- [ ] `README.md` parses as valid Markdown (fence count even; `### `/`## ` heading lines unchanged in count + text).
- [ ] Edit C present: README contains "single-flight" + "5 s" (or "up to 5 s") + "`TimeoutStopSec=15`" + "no longer race a second, parallel teardown"; does NOT contain "bounded at ≤10s".
- [ ] Edit B present: README's lifecycle paragraph states disarming (`stop`/`toggle` off/30 s auto-stop) transitions `phase` to `idle`.
- [ ] Edit A present: README states a wrong-typed value raises `TypeError` at load naming the field; mentions bare ints accepted / bool rejected.
- [ ] Factual accuracy gates (L2) all pass — the README's numbers match the landed code.
- [ ] `git status --short` shows only `README.md`.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge of this codebase: the three exact `oldText`/`newText` blocks are provided verbatim (copy-paste into the `edit` tool); the post-fix behavior each edit documents is VERIFIED against the landed code with file:line citations (research §2); the markdown wrapping/anchor conventions are pinned (research §4); the sibling-task scope boundary (`tests/ACCEPTANCE.md` = P1.M4.T1.S2) is explicit; and the validation gates (markdown validity + accuracy grep + scope guard) are all executable as written.

### Documentation & References

```yaml
# MUST READ — this task's research (exact current README text + verified code facts + scope).
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/P1M4T1S1/research/readme_doc_sync_facts.md
  why: "§1 the THREE README regions (exact current text + line numbers) to edit. §2 the VERIFIED
        post-fix code facts each edit must match (5.0s _STOP_JOIN_TIMEOUT_S; _stop_lock single-flight;
        _disarm->set_phase('idle') at daemon.py:918; __post_init__->TypeError at config.py:65/121;
        TimeoutStopSec=15). §3 scope boundaries (README only; NOT ACCEPTANCE.md=S2; NOT code). §4
        markdown conventions (~76-col wrap, backticks, em dash, no heading changes). §5 validation."
  section: "ALL load-bearing. §1 (regions), §2 (facts), §3 (scope), §4 (style)."

# MUST READ — the file being edited. READ to confirm the exact anchor text before editing.
- file: README.md
  why: "The TARGET file. The three regions: config-validation paragraph (lines ~162-165, in
        '### Voice-activity constants are NOT config keys'); phase-lifecycle paragraph (lines
        ~308-312, in '### Model lifecycle & VRAM'); teardown paragraph (lines ~330-333, same
        section). READ these regions to confirm the verbatim oldText matches byte-for-byte
        (including the ≤ and — glyphs) before applying each edit."
  critical: "The edit tool requires EXACT oldText. Run the Task 0 preflight (greps a unique
             substring of each region) to confirm the anchors before editing. Do NOT edit lines
             287-290 (the second phase mention in 'Logs, status, stopping') — redundant with B."

# MUST READ — the consumed/fixed code (READ-ONLY; do NOT edit). Confirms the README claims are true.
- file: voice_typing/recorder_host.py
  why: ":87 _STOP_JOIN_TIMEOUT_S=5.0 (the ≤5s join budget); :140 _stop_lock; :255 stop() default
        timeout=_STOP_JOIN_TIMEOUT_S; :264-274 the SINGLE-FLIGHT body-under-lock comment (Issue 1).
        Edit C cites 'up to 5 s' + 'single-flight' from these."
- file: voice_typing/daemon.py
  why: ":918 _disarm() -> self._feedback.set_phase('idle') (Issue 2). :554 _teardown_done Event +
        :342 _TEARDOWN_WAIT_TIMEOUT=8.0 (Issue 1 daemon-side coordination). Edit B cites disarm->idle."
- file: voice_typing/config.py
  why: ":65 AsrConfig.__post_init__ + :121 FeedbackConfig.__post_init__ -> TypeError naming the
        field (Issue 4). Edit A cites wrong-type -> TypeError at load."
- file: systemd/voice-typing.service
  why: ":52 TimeoutStopSec=15 (Edit C cites this; the 'old ~90s' was systemd's default, this unit
        overrides to 15)."

# CONTEXT — the bug-analysis root cause + the PRD promises (READ-ONLY).
- docfile: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/architecture/bug_analysis.md
  why: "Issue 1 (double-teardown race on SIGTERM), Issue 2 (phase stuck on disarm), Issue 4
        (silent wrong-type) root causes — confirms WHY the README's old claims were inaccurate."
- docfile: PRD.md
  why: "§4.2bis (bounded teardown prerequisite), §4.6 (phase cycles idle/listening/speaking),
        §4.5 (unknown keys raise TypeError). The README edits restate these post-fix."
  critical: "Do NOT edit PRD.md (forbidden)."

# CONTEXT — the sibling task that owns ACCEPTANCE.md (do NOT collide).
- file: plan/003_27d1f88f5a9f/bugfix/001_c804c734947d/tasks.json
  why: "P1.M4.T1.S2 = 'Update tests/ACCEPTANCE.md teardown criteria + add SIGTERM-path test
        coverage note'. CONFIRMS ACCEPTANCE.md is S2's file — this task (S1) must NOT touch it."
```

### Current Codebase tree (state at P1.M4.T1.S1 start)

The bugfix milestones P1.M1 (Issue 1), P1.M2.T1 (Issue 2), P1.M3.T1.S1 (Issue 4 impl) are **Complete/landed**; P1.M3.T1.S2 (Issue 4 tests) is running in parallel. `README.md` (333 lines) still documents pre-fix behavior in three spots.

```bash
/home/dustin/projects/voice-typing/
├── README.md                 # ← EDIT (3 prose blocks). config-val ¶ ~162-165; phase ¶ ~308-312; teardown ¶ ~330-333.
├── PRD.md                    # READ-ONLY (forbidden).
├── systemd/voice-typing.service  # READ-ONLY (:52 TimeoutStopSec=15).
├── voice_typing/
│   ├── daemon.py             # LANDED (READ-ONLY): :918 _disarm->set_phase('idle'); :554/_342 teardown.
│   ├── recorder_host.py      # LANDED (READ-ONLY): :87 _STOP_JOIN_TIMEOUT_S=5.0; :140/:264 _stop_lock single-flight.
│   └── config.py             # LANDED (READ-ONLY): :65/:121 __post_init__->TypeError.
└── tests/
    └── ACCEPTANCE.md         # ← DO NOT TOUCH (sibling P1.M4.T1.S2 owns it).
# NO new files. NO code edits. NO heading changes. NO config.toml/pyproject.toml/uv.lock edits.
```

### Desired Codebase tree with files to be added

```bash
README.md   # MODIFIED: 3 prose edits (Edit A config-val, Edit B phase-lifecycle, Edit C teardown). No other file.
# NOTHING ELSE.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — README.md ONLY. This is the documentation subtask. Do NOT edit any .py file, do NOT
#   edit tests/ACCEPTANCE.md (that is sibling P1.M4.T1.S2 — colliding would cause a merge conflict /
#   scope violation), do NOT edit PRD.md/tasks.json/prd_snapshot.md/.gitignore/config.toml/pyproject.toml/
#   uv.lock. The bugfixes are LANDED; you only document them. (research §3; item OUTPUT.)

# CRITICAL #2 — the edit tool needs EXACT oldText (byte-for-byte incl. the ≤ and — glyphs). Run the
#   Task 0 preflight greps to confirm each anchor substring is present and unique before editing. If an
#   anchor does not match, re-read the exact README region and adjust oldText — do NOT guess.

# CRITICAL #3 — PRESERVE the ~76-column manual soft-wrap. The README uses hard newlines within
#   paragraphs (NOT a reflowed single line). New/edited prose MUST be wrapped the same way (~76 cols),
#   one sentence per logical line-block, matching the surrounding style. Do NOT reflow the whole file —
#   edit only the three blocks. (research §4.)

# CRITICAL #4 — DO NOT change any heading text or level (## / ###). Internal `#anchor` links and the
#   README's structure depend on stable headings. Your edits are prose WITHIN existing sections only.
#   L1 validates that the set of heading lines is unchanged. (research §4.)

# CRITICAL #5 — the "old ~90s SIGKILL is gone" claim was INACCURATE pre-fix (Issue 1 proved the SIGTERM
#   path still SIGKILLed at 15s). Edit C must REPLACE it with a TRUTHFUL, precise claim (single-flight,
#   ≤5s join, under TimeoutStopSec=15, no double-teardown race). Do NOT keep the unqualified "is gone"
#   phrasing — it was the inaccurate claim this task fixes. (item clause (a); research §1 Region C.)

# CRITICAL #6 — do NOT also edit the second phase mention (README lines ~287-290, in 'Logs, status,
#   stopping'). The item targets the lifecycle paragraph (~308-312). Editing both is redundant and
#   bloats the diff. Edit B goes in the lifecycle paragraph only. (research §1 Region B note.)

# CRITICAL #7 — accuracy over marketing. Every number/claim in the new prose must be verifiable in the
#   landed code (research §2). Cite the real budget: host.stop() joins ≤5s (not "instant"); the overall
#   stop is "a few seconds" / "well under 15s" (not a precise single number, because the daemon-side
#   _TEARDOWN_WAIT_TIMEOUT=8.0 covers ~7s of join+SIGKILL+cleanup). Do NOT invent numbers.

# GOTCHA #8 — FULL PATHS for tooling (zsh aliases python/pytest). Validation greps run via bash from
#   the repo root. mypy/ruff are irrelevant for a .md file — the gates are markdown validity + accuracy
#   grep + scope guard. (research §5.)
```

## Implementation Blueprint

### Data models and structure

None — documentation only. The edits consume the landed code's behavior (cited file:line in research §2) and restate it in user-facing prose.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — confirm the three anchors are present + unique (no mutation).
  - RUN (from /home/dustin/projects/voice-typing):
      test -f README.md && echo "ok: README.md present" || echo "PREFLIGHT FAIL"
      # Region C anchor (teardown) — must be present + unique:
      grep -c "bounded at ≤10s" README.md                      # expect 1
      grep -n "old ~90s systemd stop" README.md               # expect 1 line
      # Region B anchor (phase lifecycle):
      grep -c "surfaces the lifecycle: \`phase:\` is \`unloaded\`" README.md   # expect 1
      # Region A anchor (config validation):
      grep -c "rejects unknown keys" README.md                # expect 1
      # Sanity: heading set (capture BEFORE; L1 will compare AFTER):
      grep -nE '^#{2,3} ' README.md | wc -l                   # record the count
      grep -nE '^#{2,3} ' README.md > /tmp/readme_headings_before.txt
      # Sanity: ACCEPTANCE.md must NOT be touched by this task:
      test -f tests/ACCEPTANCE.md && echo "note: tests/ACCEPTANCE.md exists (S2 owns it; do NOT edit)" || echo "note: no tests/ACCEPTANCE.md"
  - EXPECTED: README.md present; each anchor grep returns 1 (unique); heading count recorded;
    ACCEPTANCE.md presence noted (it is S2's file). If any anchor count is 0, re-read the exact
    README region and adjust the oldText in the corresponding Task.
  - DO NOT: edit anything yet, or touch any non-README file.

Task 1: EDIT C — teardown paragraph (item clause (a), Issue 1). Use the `edit` tool with the
        EXACT oldText/newText in "Edit C SOURCE" below.
  - FILE: README.md
  - REGION: last paragraph of `### Model lifecycle & VRAM` (lines ~330-333).
  - MUST state: single-flight; RecorderHost.stop() joins ≤5s then SIGKILLs the process group; a
    few seconds, under TimeoutStopSec=15; SIGTERM path no longer races a double teardown.
  - MUST REMOVE: "bounded at ≤10s" and the unqualified "old ~90s SIGKILL is gone".

Task 2: EDIT B — phase lifecycle paragraph (item clause (b), Issue 2). Use the `edit` tool with
        the EXACT oldText/newText in "Edit B SOURCE" below.
  - FILE: README.md
  - REGION: the "`voicectl status` surfaces the lifecycle" paragraph (lines ~308-312).
  - MUST ADD: disarming (manual stop / toggle off / 30s auto-stop) transitions `phase` to `idle`.
  - DO NOT: also edit the ~287-290 phase mention (redundant; Critical #6).

Task 3: EDIT A — config validation paragraph (item clause (c), Issue 4). Use the `edit` tool with
        the EXACT oldText/newText in "Edit A SOURCE" below.
  - FILE: README.md
  - REGION: end of the "### Voice-activity constants are NOT config keys" paragraph (lines ~162-165).
  - MUST ADD: a wrong-typed value raises TypeError at load naming the field (e.g.
    auto_stop_idle_seconds = "thirty"); bare ints accepted for numeric fields; bool rejected.

Task 4: VALIDATE — run the Validation Loop L1 (markdown validity + heading-unchanged) + L2
        (factual-accuracy grep against landed code) + L3 (scope guard) + L4 (new-phrase presence).
        Iterate until all gates pass. No git commit unless the orchestrator directs it. If asked:
        message "P1.M4.T1.S1: README.md teardown/phase/config doc sync (3 prose edits, no code)".
```

#### Edit C SOURCE — teardown paragraph (write verbatim via `edit`)

oldText (current README lines ~330-333; includes the `≤` and `—` glyphs):

```
`voicectl quit` and `systemctl --user stop` complete in seconds. Teardown is
bounded at ≤10s — if `recorder.shutdown()` wedges, the recorder's worker processes
are force-terminated so VRAM is actually released. The old ~90s systemd stop
timeout (`Failed with result 'timeout'` / SIGKILL) is gone.
```

newText:

```
`voicectl quit` and `systemctl --user stop` (and any session logout, which systemd
signals with SIGTERM) complete in seconds. Teardown is **single-flight and
bounded**: `RecorderHost.stop()` joins the recorder-host child for up to 5 s, then
SIGKILLs its process group, so VRAM is force-released even when
`recorder.shutdown()` wedges in RealtimeSTT's thread joins. One teardown therefore
takes a few seconds — comfortably under the unit's `TimeoutStopSec=15`, so there is
no systemd `Failed with result 'timeout'` / SIGKILL. The teardown is single-flight
under a lock, so the SIGTERM signal-handler thread and the main-thread `finally`
block no longer race a second, parallel teardown (that double-teardown was what blew
the 15 s budget on `systemctl stop` while armed).
```

#### Edit B SOURCE — phase lifecycle paragraph (write verbatim via `edit`)

oldText (current README lines ~308-312):

```
`voicectl status` surfaces the lifecycle: `phase:` is `unloaded` (boot /
idle-unloaded), `loading` (first arm), `idle` (loaded, disarmed), or `listening`
(armed); the `models:` line ends in `(loaded)` or `(not loaded)`. The journal logs
`voice-typing models loaded (lazy load complete); recorder resident` on load and
`voice-typing idle-unload: 1800.0s disarmed; unloading models` on idle teardown.
```

newText (one sentence inserted after the `(loaded)`/`(not loaded)` clause):

```
`voicectl status` surfaces the lifecycle: `phase:` is `unloaded` (boot /
idle-unloaded), `loading` (first arm), `idle` (loaded, disarmed), or `listening`
(armed); the `models:` line ends in `(loaded)` or `(not loaded)`. Disarming the mic
— a manual `stop`, a `toggle` off, or the 30 s auto-stop — transitions `phase` back
to **`idle`** (loaded, not listening), so a stopped daemon never reports a stale
`listening`/`speaking` while `listening:` is off. The journal logs
`voice-typing models loaded (lazy load complete); recorder resident` on load and
`voice-typing idle-unload: 1800.0s disarmed; unloading models` on idle teardown.
```

#### Edit A SOURCE — config validation paragraph (write verbatim via `edit`)

oldText (current README lines ~162-165):

```
To change VAD sensitivity, edit `daemon.py` and restart the daemon. Do **not** add
these names to `config.toml`. The config loader (`config.py`) rejects unknown keys
with `TypeError`, so a stray key makes the daemon fail to load and systemd's
`Restart=on-failure` loops it forever.
```

newText (sentences appended after "...loops it forever."):

```
To change VAD sensitivity, edit `daemon.py` and restart the daemon. Do **not** add
these names to `config.toml`. The config loader (`config.py`) rejects unknown keys
with `TypeError`, so a stray key makes the daemon fail to load and systemd's
`Restart=on-failure` loops it forever. A value of the **wrong type** is rejected the
same way: `auto_stop_idle_seconds = "thirty"` (a string where a number is expected)
or `device = 123` (a number where a string is expected) raises `TypeError` at load
with a message naming the field, rather than loading silently and breaking the
feature at runtime. Bare integers are accepted for numeric fields; a `true`/`false`
bool is not.
```

### Implementation Patterns & Key Details

```python
# PATTERN: documentation edits consume the LANDED code's behavior — cite real numbers, never invent.
#   Edit C: "joins ... for up to 5 s" <- recorder_host.py:87 _STOP_JOIN_TIMEOUT_S=5.0 (NOT "instant",
#           NOT "10s"). "single-flight under a lock" <- recorder_host.py:140/:264 _stop_lock.
#           "TimeoutStopSec=15" <- systemd/voice-typing.service:52.
#   Edit B: "transitions phase back to idle" <- daemon.py:918 _disarm()->set_phase("idle").
#   Edit A: "raises TypeError at load with a message naming the field" <- config.py:65/:121 __post_init__.

# GOTCHA: the oldText must match byte-for-byte including glyphs (≤ in "≤10s", — em dashes). The
#   preflight greps confirm each anchor substring is present + unique before you edit.

# GOTCHA: preserve ~76-col manual soft-wrap (the README is hand-wrapped, not reflowed). Wrap new
#   prose at ~76 cols, matching the surrounding lines. Do NOT collapse a paragraph onto one line.

# GOTCHA: do NOT change headings (##/###) — internal #anchor links depend on them. Your edits are
#   prose WITHIN existing sections. L1 asserts the heading set is byte-identical before/after.
```

### Integration Points

```yaml
README.md (the ONLY file modified):
  - Edit A: append to "### Voice-activity constants are NOT config keys" paragraph (~line 162-165)
  - Edit B: insert one sentence in the "### Model lifecycle & VRAM" lifecycle paragraph (~308-312)
  - Edit C: rewrite the teardown paragraph, end of "### Model lifecycle & VRAM" (~330-333)
DO NOT TOUCH:
  - "tests/ACCEPTANCE.md"  # sibling P1.M4.T1.S2 owns it
  - any voice_typing/*.py  # fixes are LANDED; this task only documents them
  - PRD.md / tasks.json / prd_snapshot.md / .gitignore / config.toml / pyproject.toml / uv.lock
DEPENDENCIES: none (pure markdown; no tooling beyond bash + the edit tool).
```

## Validation Loop

> Documentation has no pytest. Gates = markdown validity + factual-accuracy grep + scope guard +
> new-phrase presence. Run via bash from the repo root (zsh aliases bare python).

### Level 1: Markdown validity + structural integrity

```bash
cd /home/dustin/projects/voice-typing
# 1a — file parses as text (no binary corruption); fence count is EVEN (no unclosed ``` block).
FENCES=$(grep -c '```' README.md); echo "fences=$FENCES"; [ $((FENCES % 2)) -eq 0 ] && echo "L1 ok: fences balanced" || echo "L1 FAIL: unbalanced fences"
# 1b — heading set is UNCHANGED (no heading text/level added/removed/renamed -> anchors intact).
grep -nE '^#{2,3} ' README.md > /tmp/readme_headings_after.txt
diff -u /tmp/readme_headings_before.txt /tmp/readme_headings_after.txt && echo "L1 ok: headings unchanged" || echo "L1 FAIL: heading set changed (anchors may break)"
# 1c — no accidental control chars / the ≤ and — glyphs survived (edited regions still UTF-8).
grep -c "≤\|—" README.md >/dev/null && echo "L1 ok: special glyphs present"
# Expected: fences balanced (even count); headings diff is EMPTY; glyphs present.
```

### Level 2: Factual accuracy — the README's NEW claims match the LANDED code

```bash
cd /home/dustin/projects/voice-typing
# Edit C must be true: host.stop() join budget is 5.0s, single-flight lock exists, TimeoutStopSec=15.
grep -q "_STOP_JOIN_TIMEOUT_S: float = 5.0" voice_typing/recorder_host.py && echo "L2 ok: 5.0s join budget" || echo "L2 FAIL"
grep -q "_stop_lock" voice_typing/recorder_host.py && echo "L2 ok: single-flight lock" || echo "L2 FAIL"
grep -q "TimeoutStopSec=15" systemd/voice-typing.service && echo "L2 ok: TimeoutStopSec=15" || echo "L2 FAIL"
# Edit B must be true: _disarm() sets phase idle.
grep -q 'set_phase("idle")' voice_typing/daemon.py && echo "L2 ok: disarm->idle" || echo "L2 FAIL"
# Edit A must be true: __post_init__ raises TypeError naming the field.
grep -q "def __post_init__" voice_typing/config.py && grep -q "raise TypeError" voice_typing/config.py && echo "L2 ok: config type validation" || echo "L2 FAIL"
# Expected: all 5 "L2 ok" lines. If any FAIL, the README claim diverges from code -> reconcile (fix the
#   README, NOT the code — code is landed/owned by other tasks).
```

### Level 3: Scope guard — ONLY README.md changed

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: ONLY " M README.md". Any other file (esp. tests/ACCEPTANCE.md, any .py, config.toml,
#   PRD.md, tasks.json) is a SCOPE VIOLATION.
git diff --name-only
# Expected: README.md
# Explicitly confirm the sibling-owned file was NOT touched:
git diff --quiet tests/ACCEPTANCE.md 2>/dev/null && echo "L3 ok: tests/ACCEPTANCE.md untouched (S2 owns it)" || echo "L3 FAIL: ACCEPTANCE.md modified"
```

### Level 4: New-phrase presence + stale-claim removal

```bash
cd /home/dustin/projects/voice-typing
# Edit C — new claims present; stale claim gone.
grep -q "single-flight" README.md && echo "L4 ok: 'single-flight' present" || echo "L4 FAIL"
grep -qE "up to 5 s|5 s," README.md && echo "L4 ok: '5 s' present" || echo "L4 FAIL"
grep -q "TimeoutStopSec=15" README.md && echo "L4 ok: TimeoutStopSec cited" || echo "L4 FAIL"
grep -q "bounded at ≤10s" README.md && echo "L4 FAIL: stale '≤10s' still present" || echo "L4 ok: stale '≤10s' removed"
# Edit B — disarm->idle sentence present.
grep -qE "Disarming the mic|transitions .?phase.? back" README.md && echo "L4 ok: disarm->idle present" || echo "L4 FAIL"
# Edit A — wrong-type rejection present.
grep -qiE "wrong type|wrong-typed" README.md && echo "L4 ok: wrong-type mention present" || echo "L4 FAIL"
grep -q 'auto_stop_idle_seconds = "thirty"' README.md && echo "L4 ok: 'thirty' example present" || echo "L4 FAIL"
# Expected: all "L4 ok" lines; the stale '≤10s' line is gone.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: README parses; code-fence count even; heading set byte-identical (anchors intact); glyphs survived.
- [ ] L2: all 5 accuracy greps pass (5.0s budget, `_stop_lock`, `TimeoutStopSec=15`, `_disarm`→`set_phase("idle")`, `__post_init__`→`TypeError`).
- [ ] L3: `git status --short` shows ONLY ` M README.md`; `tests/ACCEPTANCE.md` untouched.
- [ ] L4: new phrases present (single-flight, 5 s, TimeoutStopSec=15, disarm→idle, wrong-type/"thirty"); stale "≤10s" removed.

### Feature Validation
- [ ] Edit C: teardown paragraph truthfully documents single-flight + ≤5 s join + SIGKILL process group + under `TimeoutStopSec=15` + no double-teardown race on SIGTERM.
- [ ] Edit B: lifecycle paragraph explicitly states disarm (stop/toggle-off/30 s auto-stop) → `phase` `idle`.
- [ ] Edit A: config paragraph states wrong-typed value → `TypeError` at load naming the field; bare int accepted; bool rejected.
- [ ] No claim in the new prose is unverifiable in the landed code.

### Code Quality Validation
- [ ] Edited prose follows the existing ~76-column manual soft-wrap (no reflow of unrelated lines).
- [ ] Inline code uses backticks; em dashes/`≤`/`≥` glyphs preserved; `**bold**` for emphasis consistent.
- [ ] No heading text/level changed; no new heading added; no Table of Contents added.
- [ ] Tone matches surrounding user-facing prose (factual, second-person).

### Documentation & Deployment
- [ ] The three fixes (Issues 1/2/4) are now accurately reflected in the user-facing README.
- [ ] No stale/inaccurate claim remains ("bounded at ≤10s", unqualified "SIGKILL is gone").
- [ ] `tests/ACCEPTANCE.md` left for sibling task P1.M4.T1.S2 (no collision).

---

## Anti-Patterns to Avoid

- ❌ Don't edit any file other than `README.md` — especially not `tests/ACCEPTANCE.md` (sibling P1.M4.T1.S2 owns it) or any `.py` file (fixes are landed; you only document them) (Critical #1).
- ❌ Don't keep the unqualified "old ~90s SIGKILL is gone" / "bounded at ≤10s" — those were the inaccurate pre-fix claims this task corrects; replace them with the truthful single-flight/≤5 s claim (Critical #5).
- ❌ Don't change any heading text or level — internal `#anchor` links depend on stable headings; edit prose WITHIN sections only (Critical #4).
- ❌ Don't reflow the whole README or collapse paragraphs onto one line — preserve the ~76-col manual soft-wrap; edit only the three blocks (Critical #3).
- ❌ Don't edit the second phase mention (~lines 287-290) — the lifecycle paragraph (~308-312) is the item's target; editing both is redundant (Critical #6).
- ❌ Don't invent numbers — cite the real budget (≤5 s join; "a few seconds"; `TimeoutStopSec=15`); the daemon-side wait is 8 s but the user-facing fact is "seconds, well under 15 s" (Critical #7).
- ❌ Don't guess the `oldText` — run the Task 0 preflight greps to confirm each anchor is present + unique byte-for-byte (incl. `≤`/`—`) before editing (Critical #2).

---

## Confidence Score

**9.5/10** for one-pass success. This is three surgical prose edits to one Markdown file, each with verbatim `oldText`/`newText` provided for the `edit` tool. Every claim in the new prose is VERIFIED against the landed code with file:line citations (research §2): `_STOP_JOIN_TIMEOUT_S=5.0` + `_stop_lock` single-flight (recorder_host.py:87/:140/:264), `_disarm()`→`set_phase("idle")` (daemon.py:918), `__post_init__`→`TypeError` (config.py:65/:121), `TimeoutStopSec=15` (systemd unit:52). The sibling-task boundary (`tests/ACCEPTANCE.md` = P1.M4.T1.S2) is explicit, and the scope guard (L3) enforces it. The only residual risk (the −0.5) is byte-exact `oldText` matching the README's current text — mitigated by the Task 0 preflight greps that confirm each anchor substring is present + unique before editing; if an anchor shifts (e.g. a sibling reflowed a line), re-reading the exact region and adjusting `oldText` is a trivial, bounded fix gated by the L4 new-phrase presence checks.
