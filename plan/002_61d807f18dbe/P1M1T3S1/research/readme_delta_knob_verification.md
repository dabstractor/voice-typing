# Research: README.md delta-knob + notification-discipline verification (VERIFIED)

**Status:** VERIFIED against `/home/dustin/projects/voice-typing/README.md` (12,969 bytes) and
`config.toml` on 2026-07-11. This note is the load-bearing evidence for `P1M1T3S1/PRP.md`.
**Task:** delta P1.M1.T3.S1 — "Verify README.md documents all delta knobs and notification discipline
correctly." This is a **confirmation pass** (delta PRD §5 predicts README is already correct).

---

## 0. VERDICT (the deliverable)

**README.md is verified CORRECT — no edits needed.** All three delta knobs are documented, the
notification discipline is `start/final/stop` (●/✔/■) with partials correctly routed to the tmux status
line (state file) ONLY, and there is ZERO contradiction with the corrected `config.toml` comment. This
matches delta PRD §5's prediction verbatim: "README.md already documents both new knobs... No
cross-cutting README/overview sweep is warranted."

The implementing agent re-confirms with the precise grep commands in §4 and records this verdict.

---

## 1. The corrected config.toml comment (the source of truth for "no partial")

`config.toml` line 49 (the P1.M1.T1.S1 fix, commit `05fa62e`):

```toml
hypr_notify = true      # show a hyprctl notify one-liner for start/final/stop. Requires Hyprland; ...
```

The stale `partial/` was REMOVED by P1.M1.T1.S1 — the comment now reads **"start/final/stop"** (3
triggers, no partial). This is the canonical notification discipline README must match. (Verified by
reading config.toml directly.) The other two delta knobs in config.toml:
- `auto_stop_idle_seconds = 30.0` — "auto-disarm ... no recognized speech ... prevents a forgotten
  hot-mic. ... 0 disables." (line 31)
- `notify_on_final = true` — "also pop a hyprctl popup for each FINALIZED utterance ('✔ <text>')? ...
  set false to keep only the brief ● start / ■ stop popups. hypr_notify=false still suppresses
  EVERYTHING." (line 50)

---

## 2. README.md — each delta knob, verified present + correct

| delta knob | README location | wording (verified) | correct? |
|---|---|---|---|
| `asr.auto_stop_idle_seconds` | line 129 (Configuration table) | "auto-disarm (stop listening) after this many seconds with no recognized speech — partials reset the clock while you talk, so it only fires when you truly go silent (a forgotten hot-mic guard, not a mid-thought cut). `0` disables. Fires the normal `■` stop popup + a journal line." | ✅ matches config.toml + PRD §4.5 |
| `feedback.notify_on_final` | line 56 (First run note) + line 137 (Configuration table) | line 137: "also pop a hyprctl popup with each final's text (`✔ <text>`). Set `false` to keep only the brief `●`/`■` start/stop popups — the text is already typed into the focused window and shown in the tmux status line, so the final popup is redundant." | ✅ matches config.toml |
| `feedback.hypr_notify` (master switch) | line 138 (Configuration table) | "...`hypr_notify` is the master on/off switch." (notify_ms row) | ✅ master-switch framing |

All three knobs are present with values + framing that match the corrected config.toml and PRD §4.5/§4.6.

---

## 3. Notification discipline — verified start/final/stop (●/✔/■), NO partial notification

README's notification symbols (grep `●|✔|■`, exactly 3 lines, all correct):
- **line 56**: "(the `✔` final popup is optional — see feedback.notify_on_final)."
- **line 129**: "Fires the normal `■` stop popup + a journal line."
- **line 137**: "Set `false` to keep only the brief `●`/`■` start/stop popups."

**Symbol → trigger mapping (consistent across README):** `●` = listening-start · `✔ <text>` = final
(gated by `notify_on_final`) · `■` = stopped. This is the 3-trigger `start/final/stop` discipline —
**no partial notification anywhere**. Partials are routed to the tmux status line (state file), which is
the correct two-channel design (PRD §4.6: "Partials go to the state file only").

**Every `partial` mention in README is tmux/status-line context — none is a notification trigger:**
- line 17: "tmux, optional, only for the live partials in the status line." ✅
- line 54: "Watch the tmux status line for live partials, or the hyprctl popups" ✅ (two channels)
- line 60: "live partial words appear in the tmux status line" ✅
- line 107: "status-right shows the current text (live partials while you speak...)" ✅
- line 128: "cadence of the live partial previews" ✅
- line 129: "partials reset the clock while you talk" ✅ (idle-watchdog mechanism, not a notification)
- line 132: "the fast model that produces live partials" ✅
- line 267: "partial: this is what i am say" ✅ (state.json example)

---

## 4. The grep methodology — PRECISE patterns (broad ones produce false positives)

**The catch:** a naive `grep partial README.md | grep popup` flags line 54 and line 129 as "stale" — but
both are **false positives** that read CORRECTLY in context:
- **line 54** "Watch the tmux status line for live partials, **or** the hyprctl popups" — lists TWO
  separate feedback channels (tmux=partials; hyprctl=●/✔). The next two lines confirm: "a dot means
  listening, a check mark means a final was typed". NOT a misattribution of partials to popups.
- **line 129** "partials reset the clock while you talk ... Fires the normal `■` stop popup" — two
  separate true statements: (a) the idle-watchdog uses partials to reset the timer; (b) auto-stop fires
  the stop popup. NOT a claim that partials trigger a popup.

**PRECISE stale-phrase patterns (these WOULD indicate the bug — all return ZERO matches on README):**
```bash
grep -niE 'partial\)|partial popup|notify on partial|start,? *partial|partial,? *final|start/partial|partial/final' README.md
# → no output (CLEAN)
```
The implementing agent MUST use these precise patterns (not broad `partial`+`popup` conjunctions) and
must READ any flagged line in context before declaring it stale. A broad grep that flags 54/129 is NOT
evidence of a defect.

---

## 5. The catch-all (IF a real contradiction is found — none expected)

The contract allows a fix "if README has any stale wording that contradicts the corrected config.toml."
The ONLY edits that would be in-scope are removing a stale `partial` from a hyprctl-NOTIFICATION context
(making README say start/final/stop, matching config.toml line 49). The verification found NONE, so the
expected outcome is **zero file changes** + the verdict in §0. If (unexpectedly) a precise-pattern match
surfaces, the fix is a localized wording edit to that one line — NOT a rewrite, NOT a cross-cutting sweep
(delta PRD §5 explicitly scopes this out).

---

## 6. Parallel-task awareness (no conflict)

- **P1.M1.T2.S2** (fast-suite regression, in parallel): zero-change verification (runs pytest, captures
  the summary line). It does NOT touch README.md, so it cannot change this task's evidence. No overlap.
- **P1.M1.T1.S1** (config.toml comment fix, COMPLETE, commit `05fa62e`): the source of the corrected
  "start/final/stop" discipline this task verifies README against. Already landed.
- This task (T3.S1) is read-only verification. Its only permitted output is the verdict + (unexpectedly)
  a one-line README wording fix. It does NOT run pytest, does NOT touch config.toml, does NOT modify
  source/tests.

---

## 7. Scope discipline (the contract's negative constraints)

- DO NOT rewrite README (delta PRD §5: "No cross-cutting README/overview sweep is warranted").
- DO NOT add new sections / reformat / restyle — a confirmation pass, not a docs redesign.
- DO NOT touch config.toml, voice_typing/, tests/, pyproject.toml (T1.S1/S2's territory).
- DO NOT run the pytest suite (P1.M1.T2.S2's territory) or the GPU/shell tests.
- The ONLY permitted file change is a localized stale-wording fix to README.md IF a precise-pattern
  match proves a real contradiction with config.toml line 49 — and the verification proves there is none.
