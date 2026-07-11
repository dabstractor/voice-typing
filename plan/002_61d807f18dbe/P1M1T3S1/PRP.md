# PRP — P1.M1.T3.S1: Verify README.md documents all delta knobs and notification discipline correctly

## Goal

**Feature Goal**: **Verify** (not rewrite) that `README.md` correctly documents the two delta knobs (`asr.auto_stop_idle_seconds`, `feedback.notify_on_final`), the master switch (`feedback.hypr_notify`), and the notification discipline (`start/final/stop` = `●`/`✔`/`■`, with partials routed to the tmux status line ONLY) — and that this matches the corrected `config.toml` comment (P1.M1.T1.S1, commit `05fa62e`, which removed the stale `partial/` so `hypr_notify` now reads "start/final/stop"). This is the **Mode B changeset-level docs sweep** for the idle auto-stop / notify_on_final delta. The expected verdict (per delta PRD §5) is **"README.md already correct — no edits needed."**

**Deliverable**: A **documented verdict** — either `README.md verified correct, no edits needed` (expected) or, if a precise-pattern grep surfaces a genuine stale-wording contradiction with `config.toml`, the **specific one-line edit** made to fix it. In the expected (no-edit) case, **zero file changes**; the output is the verdict + the grep evidence.

**Success Definition**:
- (a) All three delta knobs are confirmed present in README with values + framing that match `config.toml` + PRD §4.5/§4.6: `asr.auto_stop_idle_seconds` (forgotten-hot-mic framing, `0` disables, fires `■` stop popup), `feedback.notify_on_final` (`✔ <text>`, optional, redundant-with-typed-text framing), `feedback.hypr_notify` (master on/off switch).
- (b) The notification discipline in README is `start/final/stop` (`●`/`✔`/`■`), with **no partial as a notification trigger** — every `partial` mention is tmux/status-line or idle-watchdog context. A **precise** stale-phrase grep returns zero matches.
- (c) README's wording is consistent with the corrected `config.toml` line 49 (`hypr_notify = true # ... start/final/stop`).
- (d) **If (expected) README is already correct**: zero file changes; the verdict + grep evidence are the deliverable. **If (unexpected) a genuine contradiction is found**: one localized wording edit (remove a stale `partial` from a notification context) — NOT a rewrite, NOT a cross-cutting sweep.
- (e) No out-of-scope work: no pytest run (P1.M1.T2.S2), no config.toml/source/test edits, no README rewrite/restructure.

> **VERIFIED VERDICT (this PRP's research, 2026-07-11): `README.md verified correct, no edits needed`.**
> All three knobs documented (lines 56, 129, 137, 138); notification discipline is `●`/`✔`/`■` (start/final/stop);
> precise stale-phrase grep = zero matches. The implementing agent re-confirms via §Validation and records this verdict.

## User Persona

Not applicable (internal documentation-verification gate; no user-facing surface). The contract §5 "DOCS: [Mode B] This IS the changeset-level docs sweep" — the audience is the maintainer + the next reader of README, but the task itself produces a verdict, not a user-facing artifact.

## Why

- **Delta PRD §5 is the mandate**: "README.md already documents both new knobs... No cross-cutting README/overview sweep is warranted." This subtask is the **confirmation pass** that certifies that claim against the actual README bytes — it does not assume it.
- **The stale-comment fix (P1.M1.T1.S1) established the canonical discipline.** `config.toml`'s `hypr_notify` comment had a stale `partial/` (implying partials trigger popups); T1.S1 removed it so the comment now reads "start/final/stop". README must agree. A README that still said "start/partial/final/stop" would silently contradict the corrected config and mislead users into expecting a partial popup that never fires.
- **Mode B docs sweep, scoped tight.** Delta PRD §5 explicitly rules out a cross-cutting README rewrite. This task is a **read + grep + verdict** — the lightest possible docs gate — with a single permitted escape hatch (a one-line stale-wording fix) that the verification proves is unneeded.
- **Cheap, deterministic, no GPU/mic/daemon/pytest.** Pure text verification (grep + read). Runs in milliseconds. The right gate to close out the delta's docs acceptance (PRD §7.7: "README documents ... config tuning table ...").

## What

Run the verification greps (precise patterns — see Gotcha #1), read any flagged line in context, and record the verdict. The three delta knobs + the master switch + the notification discipline must all be present and consistent with `config.toml` line 49. Expected outcome: README is correct → verdict + zero changes. The catch-all: if a precise-pattern match proves a real contradiction, make ONE localized wording edit.

### Success Criteria

- [ ] `grep -n 'auto_stop_idle_seconds' README.md` finds the config-table row (line ~129) with the forgotten-hot-mic + `■` stop-popup + `0 disables` framing.
- [ ] `grep -n 'notify_on_final' README.md` finds the first-run note (line ~56) AND the config-table row (line ~137) with the `✔ <text>` + "redundant" framing.
- [ ] `grep -n 'hypr_notify' README.md` finds the master-switch mention (line ~138).
- [ ] `grep -nE '●|✔|■' README.md` finds exactly the start/final/stop symbols in NOTIFICATION context (no `partial` among them).
- [ ] The **precise** stale-phrase grep (Validation L2) returns **zero matches** — no `partial)` / `partial popup` / `notify on partial` / `start/partial` / `partial/final` as a notification trigger.
- [ ] README's notification wording is consistent with `config.toml` line 49 (`start/final/stop`).
- [ ] **Expected path**: zero file changes; the verdict `README.md verified correct, no edits needed` + grep evidence are recorded. **Catch-all path** (only if L2 is non-empty): one localized README wording edit removing the stale `partial` from a notification context.
- [ ] No pytest run, no config.toml/source/test/pyproject edit, no README rewrite/restructure.

## All Needed Context

### Context Completeness Check

_Pass._ This is a verification task. The exact grep commands are given, the precise-vs-broad grep distinction (Gotcha #1 — the load-bearing methodological insight) is documented with the two known false-positive lines analyzed, the verified verdict + line numbers are captured in this PRP's research, and the catch-all edit procedure is specified. A developer new to this codebase can run the gate and record the verdict from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the verified README evidence + the precise-vs-broad grep methodology (this task's own research)
- docfile: plan/002_61d807f18dbe/P1M1T3S1/research/readme_delta_knob_verification.md
  why: "§0 is the VERIFIED VERDICT (README correct, no edit). §1 quotes config.toml line 49 (the canonical
        'start/final/stop'). §2 is the per-knob README evidence table (line numbers + wording). §3 proves the
        notification discipline is ●/✔/■ with NO partial notification (every 'partial' mention cataloged as
        tmux/status context). §4 is the GREP METHODOLOGY — precise patterns vs the two false-positive lines
        (54, 129) a broad grep wrongly flags, and WHY they read correct in context. §5 is the catch-all."
  critical: "§4 is load-bearing: a naive 'grep partial README | grep popup' flags lines 54 + 129 as stale,
            but both are FALSE POSITIVES (line 54 lists two channels with 'or'; line 129 states the idle
            watchdog uses partials to reset the clock AND separately that stop fires a popup). The implementing
            agent MUST use the PRECISE patterns in §4 and READ any flagged line in context. The expected
            precise-pattern result is ZERO matches."

# MUST READ — the canonical notification discipline README must match (the T1.S1 fix)
- file: config.toml
  why: "Line 49: hypr_notify = true # show a hyprctl notify one-liner for start/final/stop. ... — the
        P1.M1.T1.S1 fix (commit 05fa62e) removed the stale 'partial/' so it now reads 'start/final/stop'
        (3 triggers). This is the source of truth README's notification wording must agree with. Lines 31
        (auto_stop_idle_seconds) + 50 (notify_on_final) are the other two delta knobs' canonical wording."
  critical: "Confirm with `git show 05fa62e -- config.toml` that the diff removed only 'partial/' from the
            comment (no value change). README must say start/final/stop — NOT start/partial/final/stop."

# THE SUBJECT — README.md (the file under verification)
- file: README.md
  why: "12,969 bytes. Notification discipline lives in (a) the First-run note (lines 54-56: 'Watch the tmux
        status line for live partials, or the hyprctl popups: a dot means listening, a check mark means a
        final was typed (the ✔ final popup is optional — see feedback.notify_on_final)') and (b) the
        Configuration table rows for notify_on_final (line 137: 'keep only the brief ●/■ start/stop popups')
        and notify_ms (line 138: 'hypr_notify is the master on/off switch'). The auto_stop_idle_seconds row
        is line 129. There is NO dedicated Feedback/Notifications section header — the discipline is inline."
  pattern: "Verify by grep + reading the flagged lines; do NOT restructure into a new section (Mode B =
            confirm, not redesign — delta PRD §5)."
  gotcha: "Lines 54 + 129 mention BOTH 'partial' AND a popup symbol/word — a broad grep flags them, but
           they are CORRECT (two-channel 'or' on 54; idle-watchdog 'resets the clock' on 129). See research §4."

# THE MANDATE — delta PRD §5 (README already correct; no sweep warranted)
- docfile: plan/002_61d807f18dbe/delta_prd.md
  why: "§5: 'README.md already documents both new knobs... No cross-cutting README/overview sweep is
        warranted.' This subtask is the CONFIRMATION of that claim. §6.3 caps any permitted edit (a localized
        stale-wording fix only; none expected)."
  critical: "This is a confirmation pass, NOT a rewrite. The expected outcome is zero file changes + a
            recorded verdict. Do NOT add sections / reformat / restyle."

# THE SIBLING (parallel) — confirms no overlap
- docfile: plan/002_61d807f18dbe/P1M1T2S2/PRP.md
  why: "P1.M1.T2.S2 is the fast-suite pytest regression (zero-change; captures the '265 passed' summary line).
        It does NOT touch README.md, so it cannot change this task's evidence. Fully independent."
  critical: "S2 = pytest; T3.S1 = README text verification. No overlap. If `git status` shows a README edit
            from elsewhere, that's a parallel anomaly to note, not this task's doing."

# BACKGROUND — the PRD sections that define the knobs + discipline (for wording comparison)
- file: PRD.md
  why: "§4.5 defines auto_stop_idle_seconds (forgotten-hot-mic guard, partials reset the clock, 0 disables)
        + notify_on_final. §4.6 defines the notification discipline (● listening / ✔ <text> gated by
        notify_on_final / ■ stopped; 'Partials go to the state file only'). §7.7 is the acceptance: 'README
        documents ... config tuning table ...'. README's wording should be consistent with these."
  critical: "PRD §4.6 'Partials go to the state file only' is the discipline. README must not say partials
            trigger a hyprctl popup. (It doesn't — verified.)"
```

### Current Codebase tree (relevant slice)

```bash
/home/dustin/projects/voice-typing/
├── README.md                          # 12,969 bytes; the SUBJECT of this verification.             ← (verify; edit ONLY if §5 catch-all triggers)
│   # lines 54-56  : First-run note — 'partials ... tmux ... or hyprctl popups: ●/✔' (✔ optional)
│   # line 129     : config table — auto_stop_idle_seconds (forgotten-hot-mic + ■ stop popup)
│   # line 137     : config table — notify_on_final (✔ <text>, redundant-with-typed-text)
│   # line 138     : config table — notify_ms (hypr_notify is the master on/off switch)
├── config.toml                       # line 49: hypr_notify = true # ... start/final/stop (T1.S1 fix) — the canonical discipline.
├── plan/002_61d807f18dbe/
│   ├── P1M1T2S2/PRP.md               # sibling (parallel): pytest fast-suite regression (zero-change)
│   └── delta_prd.md                  # §5 mandate (README already correct; no sweep)
# NOTE: this task is read-only verification. The only permitted edit is a one-line README stale-wording
# fix IF the precise-pattern grep (Validation L2) surfaces a real contradiction — which the research proves it does not.
```

### Desired Codebase tree with files to be added/changed

```bash
# (EXPECTED: NO changes) — verification-only. The output is the recorded verdict + grep evidence.
# (CATCH-ALL, only if Validation L2 is non-empty): README.md gets ONE localized wording edit removing a
#   stale 'partial' from a notification context. No new files; no restructure; no other file touched.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — USE PRECISE GREP PATTERNS; BROAD ONES PRODUCE FALSE POSITIVES. A naive
# `grep -i partial README.md | grep -iE 'popup|notify|hyprctl'` flags lines 54 AND 129 — but BOTH are
# CORRECT in context:
#   line 54: "Watch the tmux status line for live partials, OR the hyprctl popups" — lists TWO channels
#            (tmux=partials; hyprctl=●/✔). The next line confirms: "a dot means listening, a check mark
#            means a final was typed". NOT a misattribution.
#   line 129: "partials reset the clock while you talk ... Fires the normal ■ stop popup" — TWO separate
#            true statements: the idle-watchdog uses partials to reset its timer; auto-stop fires the stop
#            popup. NOT a claim that partials trigger a popup.
# The PRECISE stale-phrase patterns (Validation L2) are the ones that would indicate the bug — and they
# return ZERO matches. ALWAYS read a flagged line in context before declaring it stale. (research §4.)

# CRITICAL #2 — THE EXPECTED VERDICT IS "NO EDITS NEEDED". Delta PRD §5 states README already documents
# both knobs and no sweep is warranted. This PRP's research CONFIRMS that (all 3 knobs present at lines
# 56/129/137/138; notification discipline is ●/✔/■; precise stale-phrase grep = zero matches). The
# implementing agent re-confirms and records the verdict. Do NOT invent an edit to "look busy" — a no-edit
# verdict is the correct, expected outcome.

# CRITICAL #3 — THIS IS MODE B (CONFIRM), NOT A REWRITE. Do NOT add a dedicated "Feedback"/"Notifications"
# section, do NOT reformat the config table, do NOT restyle. The notification discipline correctly lives
# inline (First-run note lines 54-56 + config table rows 137/138). A cross-cutting sweep is explicitly out
# of scope (delta PRD §5). The ONLY permitted edit is a one-line stale-wording fix IF L2 is non-empty.

# CRITICAL #4 — THE CANONICAL DISCIPLINE IS config.toml LINE 49. README must agree with
# `hypr_notify = true # ... start/final/stop` (3 triggers, no partial). Confirm the T1.S1 fix landed:
# `git show 05fa62e -- config.toml` shows only the comment-line change (removed 'partial/'). If README's
# notification wording says start/final/stop (it does), it matches. (research §1.)

# GOTCHA #5 — THE ● / ✔ / ■ SYMBOLS. README uses Unicode symbols for the notification triggers: ● (U+25CF,
# start/listening), ✔ (U+2714, final), ■ (U+25A0, stop). grep for them with a UTF-8 locale
# (`grep -nE '●|✔|■' README.md`). They appear on exactly 3 lines (56, 129, 137), all in correct
# notification context. Do NOT "normalize" them to ASCII — they match the daemon's popup text + PRD §4.6.

# GOTCHA #6 — USE FULL PATHS. This machine aliases python3→uv run, pip→alias, tmux→zsh plugin. For the
# grep/read commands, run from the repo root (`cd /home/dustin/projects/voice-typing`). grep/read/tee are
# coreutils — not aliased — but invoke them deliberately. No python/pytest/uv needed for this task.

# GOTCHA #7 — DO NOT RUN PYTEST OR THE GPU/SHELL TESTS. That is P1.M1.T2.S2's (pytest) and P1.M1.T2.S1's
# (bash T4) territory. This task is README TEXT verification only — grep + read. No test execution.

# GOTCHA #8 — DO NOT TOUCH config.toml / voice_typing/ / tests/ / pyproject.toml. T1.S1 fixed config.toml
# (landed); S2 runs pytest. This task's only permitted file change is a one-line README edit (catch-all,
# not expected). Editing other files is out of scope and risks a conflict with the parallel sibling.

# GOTCHA #9 — NO dedicated Feedback/Notifications SECTION in README. grep for '^#+ .*(feedback|notif|popup)'
# returns only the inline first-run comment lines (54/56), not a section header. The discipline is
# documented inline (First-run note + Configuration table) — this is CORRECT, not a gap. Do NOT add a section.
```

## Implementation Blueprint

### Data models and structure

None. This subtask adds no code, no types, no config. The only "structure" is the **verification verdict**
(`README.md verified correct, no edits needed` / the specific one-line edit) produced by running grep +
reading the flagged lines.

### Verification Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm the canonical discipline (config.toml line 49) + README is the subject (no mutation)
  - RUN:
      cd /home/dustin/projects/voice-typing
      echo "--- config.toml line 49 (the canonical 'start/final/stop' discipline T1.S1 set) ---"
      grep -n 'hypr_notify' config.toml
      echo "--- T1.S1 fix is comment-only (removed 'partial/'; no value change) ---"
      git show 05fa62e -- config.toml | grep -E '^[+-]' | grep -vE '^[+-]{3}|^[+-]\s*#'
      # ↑ expect EMPTY (only a comment line changed) — proves the canonical discipline is 'start/final/stop'
      echo "--- README is present + the expected size ---"
      wc -c README.md
      echo "--- no uncommitted README edit from elsewhere (S2 is zero-change) ---"
      git status --short README.md || echo "(README clean)"
  - EXPECTED: config.toml hypr_notify comment says "start/final/stop"; the git-show value-filter is EMPTY
    (comment-only fix); README ~12,969 bytes; git status shows no README modification. If git status DOES
    show a README edit, a parallel anomaly occurred — note it (triage) before verifying.

Task 2: VERIFY each delta knob is documented (broad presence grep — these SHOULD all match)
  - RUN:
      cd /home/dustin/projects/voice-typing
      echo "--- (a) auto_stop_idle_seconds (config table) ---"
      grep -n 'auto_stop_idle_seconds' README.md
      echo "--- (b) notify_on_final (first-run note + config table) ---"
      grep -n 'notify_on_final' README.md
      echo "--- (c) hypr_notify master switch (config table) ---"
      grep -n 'hypr_notify' README.md
      echo "--- notification symbols (expect ● / ✔ / ■ in notification context) ---"
      grep -nE '●|✔|■' README.md
  - EXPECTED:
      auto_stop_idle_seconds → line ~129 (forgotten-hot-mic + '■ stop popup' + '0 disables').
      notify_on_final        → lines ~56 AND ~137 ('✔ <text>', 'redundant', '●/■ start/stop popups').
      hypr_notify            → line ~138 ('master on/off switch').
      ●/✔/■                  → lines ~56, ~129, ~137 (start/final/stop symbols; NO partial among them).
  - IF any knob is MISSING: that is a real docs gap — record it. (The research confirms none are missing.)
    A missing knob would warrant adding its row/line (but this is not expected — delta PRD §5 + research §2).

Task 3: VERIFY the notification discipline — PRECISE stale-phrase grep (the load-bearing gate)
  - RUN (the PRECISE patterns — Gotcha #1; these return ZERO matches on a correct README):
      cd /home/dustin/projects/voice-typing
      echo "--- precise stale-phrase check (expect ZERO matches) ---"
      if grep -niE 'partial\)|partial popup|notify on partial|start,? *partial|partial,? *final|start/partial|partial/final' README.md; then
          echo ">>> STALE WORDING FOUND — see catch-all (Task 5)"
      else
          echo "CLEAN: zero precise stale-phrase matches — README notification discipline is start/final/stop"
      fi
  - EXPECTED: "CLEAN: zero precise stale-phrase matches". This is the core gate. (research §4.)
  - DO NOT use a broad `grep partial README | grep popup` as the verdict — it false-positives on lines 54
    and 129 (Gotcha #1). If you DO run a broad grep for exploration, READ each flagged line in context:
      sed -n '52,58p' README.md    # line 54 in context (two-channel 'or' — correct)
      sed -n '129p' README.md      # line 129 in context (idle-watchdog + stop popup — correct)

Task 4: RECORD the verdict (the deliverable)
  - IF Task 2 shows all knobs present AND Task 3 is CLEAN (zero precise matches):
      Verdict = "README.md verified correct, no edits needed. All delta knobs documented (auto_stop_idle_seconds
      @L129, notify_on_final @L56+L137, hypr_notify master switch @L138); notification discipline is
      start/final/stop (●/✔/■); precise stale-phrase grep = zero matches; consistent with config.toml L49.
      Zero file changes." Record this as the task's output. DONE.
  - ELSE IF Task 3 surfaced a genuine stale-phrase match (NOT expected): proceed to Task 5 (catch-all).
  - ELSE IF Task 2 found a missing knob (NOT expected): that is a real gap — record it + flag for a follow-up
      (a missing-knob fix is broader than the catch-all and likely out of Mode-B scope; report rather than
      improvise). The research confirms no knob is missing.
  - DO NOT: invent an edit when the verdict is "correct" (Gotcha #2); run pytest (S2); touch config.toml/source/tests.

Task 5 (CATCH-ALL — only if Task 3 is non-empty; NOT expected): one-line README stale-wording fix
  - This task is reached ONLY if the precise-pattern grep found a real contradiction (e.g., a prose line
    saying hyprctl notifies on partials). The research proves this does NOT occur — so this task should
    never execute. It exists to satisfy the contract's "fix it" clause.
  - IF reached: READ the flagged line in FULL context (`sed -n '<start>,<end>p' README.md`). Confirm it
    genuinely contradicts config.toml line 49 (says partials notify) — not a false positive.
  - EDIT (use the `edit` tool, the SMALLEST change that removes the stale 'partial' from the notification
    context, preserving the rest of the line): make the line say start/final/stop, matching config.toml.
    This is ONE localized wording edit — NOT a rewrite, NOT a restructure (Mode B; delta PRD §5).
  - RECORD: "README.md edited at line <N>: removed stale 'partial' from the hyprctl-notification wording to
    match config.toml line 49 (start/final/stop). <quote the oldText → newText>."
  - DO NOT: add a section, reformat the table, or touch any line other than the flagged one.

Task 6: VALIDATE — run the Validation Loop L1–L4 below. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M1.T3.S1: verified README.md documents all delta knobs + start/final/stop
  notification discipline correctly (no edits needed)." (Or, if the catch-all fired: "...fixed stale
  partial wording at README line <N>".)
```

### Implementation Patterns & Key Details

```bash
# This subtask has NO implementation patterns — it is read-only text verification. The load-bearing facts
# (each verified in this PRP's research note):
#
# FACT 1: all 3 delta knobs are in README — auto_stop_idle_seconds @L129, notify_on_final @L56+L137,
#         hypr_notify (master switch) @L138.
# FACT 2: the notification discipline is start/final/stop (●/✔/■); partials go to the tmux status line
#         ONLY. Every 'partial' mention is tmux/status or idle-watchdog context (8 mentions, all correct).
# FACT 3: the PRECISE stale-phrase grep returns ZERO matches — README matches config.toml line 49.
# FACT 4: a BROAD grep (`partial` + `popup`) false-positives on lines 54 + 129 — both correct in context.
#         ALWAYS use the precise patterns + read flagged lines in context (Gotcha #1).
#
# THE VERDICT (the whole deliverable): README.md verified correct, no edits needed. (If the catch-all
# unexpectedly fired, the one-line edit is the deliverable instead.)
```

### Integration Points

```yaml
DELTA ACCEPTANCE (delta PRD §5 + PRD §7.7):
  - This subtask is the Mode-B changeset-level docs sweep for the idle auto-stop / notify_on_final delta.
  - PRD §7.7 acceptance ("README documents ... config tuning table ...") is certified by Task 2 (knobs present).
  - The verdict (README correct / the one-line fix) IS the acceptance evidence. Expected: zero file changes.

PARALLEL — P1.M1.T2.S2 (fast-suite pytest regression):
  - S2 is zero-change (captures the '265 passed' summary line). It does NOT touch README.md. The two tasks
    are fully independent: S2 = pytest; T3.S1 = README text verification. No coordination needed beyond
    confirming (via `git status`) that no README edit came from elsewhere.

UPSTREAM — P1.M1.T1.S1 (config.toml comment fix, COMPLETE, commit 05fa62e):
  - The source of the canonical 'start/final/stop' discipline this task verifies README against. Already
    landed. README matches it (verified).

NO INTERFACE / BEHAVIOR CHANGES:
  - README.md (expected unchanged), config.toml, voice_typing/, tests/, pyproject.toml: UNCHANGED. The
    output is a verdict (plus, only in the unexpected catch-all, a one-line README wording edit).
```

## Validation Loop

> The Validation Loop here IS the task: the gates below produce + verify the README verdict. Run from the
> repo root `/home/dustin/projects/voice-typing`. Pure text verification — no GPU/mic/daemon/pytest.

### Level 1: All delta knobs + the master switch are documented (broad presence grep)

```bash
cd /home/dustin/projects/voice-typing
echo "--- auto_stop_idle_seconds ---";   grep -n 'auto_stop_idle_seconds' README.md
echo "--- notify_on_final ---";          grep -n 'notify_on_final' README.md
echo "--- hypr_notify master switch ---"; grep -n 'hypr_notify' README.md
echo "--- notification symbols ---";     grep -nE '●|✔|■' README.md
# Expected: auto_stop_idle_seconds @~129; notify_on_final @~56 AND @~137; hypr_notify @~138;
# ●/✔/■ @~56,~129,~137 (notification context). All present = L1 PASS. (research §2/§3.)
```

### Level 2: The PRECISE stale-phrase grep returns ZERO matches (the core gate — Gotcha #1)

```bash
cd /home/dustin/projects/voice-typing
if grep -niE 'partial\)|partial popup|notify on partial|start,? *partial|partial,? *final|start/partial|partial/final' README.md; then
    echo "L2 FAIL: precise stale-phrase match — proceed to catch-all (Task 5)"
else
    echo "L2 PASS: zero precise stale-phrase matches — notification discipline is start/final/stop"
fi
# Expected: L2 PASS (zero matches). If a broad exploratory grep flagged lines 54/129, read them in context:
#   sed -n '52,58p' README.md   (line 54: two-channel 'or' — correct, NOT stale)
#   sed -n '129p' README.md     (line 129: idle-watchdog 'partials reset the clock' + stop popup — correct)
# These broad-grep hits are FALSE POSITIVES (Gotcha #1). L2's PRECISE patterns are the verdict.
```

### Level 3: README's discipline matches the canonical config.toml line 49 (consistency)

```bash
cd /home/dustin/projects/voice-typing
echo "--- config.toml canonical discipline ---"
grep -n 'hypr_notify' config.toml                       # expect: '... start/final/stop ...'
echo "--- README says start/stop (●/■) + optional final (✔); partials -> tmux only ---"
grep -nE '●.*■|■.*●|start/stop|tmux status line for live partials' README.md
echo "--- T1.S1 fix was comment-only (no parsed value changed) ---"
git show 05fa62e -- config.toml | grep -E '^[+-]' | grep -vE '^[+-]{3}|^[+-]\s*#' || echo "(comment-only: no [key]=value lines changed)"
# Expected: config.toml says 'start/final/stop'; README's ●/■ + ✔-optional wording agrees; the git-show
# value-filter is empty (comment-only fix). README is consistent with the canonical discipline.
```

### Level 4: Scope guards — expected zero file changes; read-only files untouched

```bash
cd /home/dustin/projects/voice-typing
echo "--- EXPECTED: zero changes (no-edit verdict) ---"
git status --short | grep -vE '^\?\? plan/|tasks\.json' || echo "(nothing outside plan/ + tasks.json)"
git diff --exit-code -- README.md && echo "L4 PASS: README unchanged (no-edit verdict — expected)" || echo "L4 NOTE: README was edited — confirm it was the catch-all (Task 5) one-line stale-wording fix"
echo "--- read-only / out-of-scope files UNCHANGED ---"
git diff --exit-code -- config.toml voice_typing/ tests/ pyproject.toml PRD.md plan/002_61d807f18dbe/tasks.json plan/002_61d807f18dbe/prd_snapshot.md plan/002_61d807f18dbe/delta_prd.md .gitignore && echo "L4 PASS: no source/test/config/read-only changes" || echo "L4 NOTE: tasks.json may show orchestrator bookkeeping (M) — not this subtask"
# Expected (no-edit path): git status shows ONLY plan/ (this subtask's PRP/research) + tasks.json
# (orchestrator); README + all other files unchanged. (Catch-all path: README has exactly one one-line edit;
# everything else unchanged.)
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: all 3 delta knobs + master switch present (auto_stop_idle_seconds @~129; notify_on_final @~56+~137; hypr_notify @~138); ●/✔/■ symbols on ~56/~129/~137.
- [ ] L2: PRECISE stale-phrase grep = zero matches (the core gate; broad-grep false positives on 54/129 read correct in context).
- [ ] L3: README's start/final/stop discipline matches config.toml line 49; T1.S1 fix confirmed comment-only.
- [ ] L4: expected zero file changes (no-edit verdict); read-only + source/test/config files untouched.

### Feature Validation
- [ ] Verdict recorded: `README.md verified correct, no edits needed` (expected) OR the specific one-line catch-all edit.
- [ ] The notification discipline in README is start/final/stop (●/✔/■) — partials routed to tmux status line only.
- [ ] README is consistent with the corrected config.toml (no stale `partial` in any hyprctl-notification context).
- [ ] Delta PRD §5's prediction ("README already documents both new knobs; no sweep warranted") is confirmed against the actual bytes.

### Code Quality / Scope Validation
- [ ] (Expected) ZERO file modifications — a no-edit verdict is the correct outcome (not a gap).
- [ ] (Catch-all only) the single README edit is a localized wording fix — no new section, no reformat, no restructure.
- [ ] No pytest run (P1.M1.T2.S2); no config.toml/source/test/pyproject edit; no GPU/shell test execution.
- [ ] No conflict with parallel S2 (zero-change; `git status` confirms no README edit from elsewhere).

### Documentation & Deployment
- [ ] The verdict + grep evidence are reflected in the task acceptance record (the deliverable).
- [ ] No user-facing/config/API surface change beyond the (unexpected, catch-all) one-line README wording fix.

---

## Anti-Patterns to Avoid

- ❌ Don't use a BROAD `grep partial README | grep popup` as the verdict — it false-positives on lines 54 + 129 (Gotcha #1). Use the PRECISE stale-phrase patterns (L2) and READ any flagged line in context. The expected precise result is ZERO matches.
- ❌ Don't invent an edit when README is correct — the expected verdict is "no edits needed" (delta PRD §5 + this PRP's research both confirm it). A no-edit verification is a successful outcome, not a gap. (Gotcha #2.)
- ❌ Don't rewrite/restructure README (add a Feedback/Notifications section, reformat the config table, restyle symbols). This is Mode B (confirm), not a docs redesign — delta PRD §5 explicitly rules out a cross-cutting sweep. (Gotcha #3.)
- ❌ Don't run pytest or the GPU/shell tests — that's P1.M1.T2.S2 (pytest) and P1.M1.T2.S1 (bash T4). This task is README text verification only (grep + read). (Gotcha #7.)
- ❌ Don't touch config.toml / voice_typing/ / tests/ / pyproject.toml — T1.S1 fixed config.toml (landed); S2 runs pytest. The only permitted file change is a one-line README edit (catch-all, not expected). (Gotcha #8.)
- ❌ Don't "normalize" the ●/✔/■ Unicode symbols to ASCII — they match the daemon's popup text + PRD §4.6. They appear on exactly 3 lines, all correct. (Gotcha #5.)
- ❌ Don't treat a broad-grep flag on line 54/129 as a defect without reading the context — line 54 is a two-channel "or" (tmux=partials, hyprctl=●/✔); line 129 is the idle-watchdog (partials reset the clock) + stop popup. Both are correct. (Gotcha #1; research §4.)
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `delta_prd.md`, or `.gitignore` (read-only / owned by others).

---

## Confidence Score

**9.5/10** for one-pass verification success. The verdict is already verified in this PRP's research: **README.md is correct — all three delta knobs documented (lines 56/129/137/138), notification discipline is `●`/`✔`/`■` (start/final/stop), precise stale-phrase grep = zero matches, consistent with config.toml line 49.** The grep commands (precise patterns + the false-positive analysis for lines 54/129) are given verbatim, the expected outcome (no edits) is documented with evidence, and the catch-all (one-line fix) is specified for the unexpected case the research proves does not occur. The parallel sibling P1.M1.T2.S2 is zero-change, so it cannot perturb README. The −0.5 residual is purely the small chance the implementing agent mistakes a broad-grep false positive (lines 54/129) for a real defect and makes an unnecessary edit — which Gotcha #1 + L2's precise patterns + the "read it in context" instruction guard against. No GPU, mic, daemon, pytest, or network is required.
