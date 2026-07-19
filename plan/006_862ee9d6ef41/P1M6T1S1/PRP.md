# PRP — P1.M6.T1.S1: Audit README.md completeness against PRD §7 #7 (+ the item's 8-point checklist)

## Goal

**Feature Goal**: **Audit** `README.md` (382 lines, already comprehensive) against PRD §7 acceptance
criterion **#7** ("README documents: install, hotkey snippet, tmux status snippet, config tuning
table, troubleshooting (cuDNN libs, PyAudio device, wtype vs ydotool), and how to switch to CPU-only
mode") AND the item's expanded 8-point checklist (a–h: install, hotkey, tmux, config-tuning table,
troubleshooting, CPU-only, first-run T5, lite mode). Verify every required surface is PRESENT +
ACCURATE by cross-checking README claims against the LIVE source (`voice_typing/config.py` schema,
`hypr-binds.conf`, `status.sh`) + the 17 `architecture/gap_*.md` audits (which already cross-read
README). **Fix any genuine gap** in README.md; record the audit verdict + evidence in `gap_readme.md`.

**Pre-verified finding (research `readme_audit_findings.md`): README is COMPLETE and ACCURATE — the
audit verdict is PASS (8/8 checklist items present + correct).** The config table has ZERO drift vs
`config.py`. The deliverable is therefore **primarily `gap_readme.md`** (the evidence dossier), with
README.md either **unchanged** (if the implementer concurs the table curation is fine) or receiving
**only optional, surgical polish** (one `feedback.hypr_notify` row — §5). Three README divergences
from the literal checklist are **CORRECT** (the codebase evolved) and MUST NOT be "fixed" (§4).

**Deliverable** (2 artifacts — 1 CREATE the audit dossier, 0–1 SURGICAL README edit):
1. **CREATE** `plan/006_862ee9d6ef41/P1M6T1S1/gap_readme.md` — the self-contained README-completeness
   audit dossier. Structure: (1) verdict line (PASS on §7 #7's docs half); (2) the 8-point audit
   matrix (item → README section:line → verdict → evidence/cross-check); (3) config-table ↔ config.py
   lockstep table (zero drift); (4) correct-divergences register (silero_sensitivity, first-run knobs,
   input_device_index — NOT gaps); (5) optional polish notes (routed, non-blocking); (6) scope
   (commit → S3, VT-001/stale-refs → S2, README-completeness → this task).
2. **UPDATE** `README.md` **ONLY IF** the implementer concurs §5's optional polish adds clarity —
   add ONE row to the config table for `feedback.hypr_notify` (the master on/off switch currently
   only mentioned in the `notify_ms` row). If the implementer judges the curated "Real tunable keys"
   table is fine as-is, **README stays unchanged** (a clean PASS needs no edit). NO other README edit.

**Success Definition**:
- (a) `README.md` read in full + cross-checked against `voice_typing/config.py` (all dataclass
  defaults), `hypr-binds.conf` (both binds), `status.sh` (the 2-line snippet), and the relevant
  `architecture/gap_*.md` verdicts (`gap_hypr_binds`, `gap_status_sh`, `gap_install`).
- (b) The 8-point audit matrix in `gap_readme.md` has a verdict (PASS/FAIL) for ALL 8 items, each with
  the README section heading + LIVE line number (re-grepped, not the PRP's) + a one-line evidence
  pointer (grep match / config.py line / gap_*.md verdict).
- (c) The config-table ↔ config.py lockstep table confirms ZERO default drift (re-run the comparison);
  any row found drifted is FIXED in README (the deliverable's only mandatory edit path).
- (d) The 3 correct-divergences are REGISTERED as "not gaps" with reasoning (silero_sensitivity is a
  non-config constant; first-run knobs intentionally swap silero_sensitivity → mic source for accuracy;
  input_device_index is a test kwarg, not a user config) — so a future reader doesn't "fix" them.
- (e) `gap_readme.md` written with the 6-section structure + an unambiguous verdict line. If README is
  edited, `git diff README.md` is SURGICAL (one optional row OR a verified drift fix; no reflow).
- (f) Scope respected: ONLY the README-completeness half of #7. The literal "everything committed to
  git" half → **P1.M6.T1.S3**; stale BUGS.md/VT-001 references → **P1.M6.T1.S2** (do NOT touch them
  here). NO source/test/script edit. NO pytest, NO heavy shell script (AGENTS.md).

## User Persona

**Target User**: Internal — the plan orchestrator + sibling tasks S2/S3 + future maintainers:
1. **The orchestrator** reads `gap_readme.md` as the README-completeness evidence for §7 #7's docs
   half (S3 then closes the commit half). It must give a crisp PASS so the docs module completes.
2. **P1.M6.T1.S2** (stale BUGS.md/VT-* references) consumes this audit's verdict that the README
   CONTENT is complete, so S2 can focus purely on stale-reference hygiene without re-auditing content.
3. **P1.M6.T1.S3** (commit readiness) consumes the verdict to assert #7's docs half is satisfied
   before the final integration commit.
4. **Future maintainers** read `gap_readme.md` to understand WHY the README intentionally diverges
   from the literal PRD T5 / checklist wording (the correct-divergences register prevents regressions).

**Use Case**: P1.M1–P1.M5 verified the SOURCE (17 gap audits, all COMPLIANT) + TESTS (424 LIVE-green).
The acceptance gate (P1.M5.T5.S1, parallel) maps all 10 §7 criteria to evidence and routes #7's docs
half to THIS task. This audit confirms the README — the user-facing changeset doc — covers every
required surface, so the docs module (P1.M6.T1) can close out the PRD-compliance round.

**Pain Points Addressed**: (1) #7's docs half is asserted PASS by the acceptance gate but never had a
dedicated, line-cited README audit; this is that audit. (2) The evolved PRD added lite mode, lazy
load, idle unload — without a README cross-check, a stale README could silently miss the lite-mode
section or carry a drifted config default. (3) The README's intentional divergences from PRD T5
(silero_sensitivity) are a trap for a future "fix it to match the PRD" edit that would BREAK the
README's accuracy — the register documents why they're correct.

## Why

- **This closes the docs half of acceptance #7.** The acceptance gate (P1.M5.T5.S1) routes #7's
  "README documents …" clause here; S3 owns the "everything committed" clause. Without this audit, #7
  is only half-evidenced.
- **The README is the user-facing changeset doc (Mode B).** Per the item's DOCS note, this IS the
  changeset-level documentation sync task. It must be complete + accurate or the project's definition
  of done is unmet.
- **Config-table drift is the high-value check.** A README that lists `auto_unload_idle_seconds` with
  a stale default, or omits `lite_model`, would silently mislead users. The lockstep diff vs
  `config.py` (the schema source of truth) catches exactly that — pre-verified zero-drift, but the
  implementer re-runs it to be certain.
- **The correct-divergences register prevents a regression.** PRD T5 literally says "the two tunables
  are post_speech_silence_duration, silero_sensitivity." A maintainer reading the PRD could "fix" the
  README's first-run section to add silero_sensitivity — which would be WRONG (it's not a config key;
  adding it to config.toml crash-loops the daemon). Documenting the divergence as intentional is
  itself the deliverable.

## What

Four phases, in order: **(1) READ README.md + config.py + the relevant gap_*.md**; **(2) RUN the
grep-based completeness + line-number checks + the config-table lockstep diff** (fast, safe); **(3)
WRITE `gap_readme.md`** (the dossier, with the 8-point matrix + lockstep table + divergence
register); **(4) OPTIONALLY UPDATE README.md** (one `feedback.hypr_notify` row IF concurred; else
unchanged). NO pytest, NO heavy script.

### Success Criteria

- [ ] `README.md`, `voice_typing/config.py`, `hypr-binds.conf`, `status.sh`, and the relevant
      `architecture/gap_*.md` (`gap_hypr_binds`, `gap_status_sh`, `gap_install`) READ; line numbers
      CONFIRMED live (re-grep; the PRP's numbers are a starting point, not gospel).
- [ ] `gap_readme.md` written with the 6-section structure + verdict line ("PASS: README satisfies
      PRD §7 #7's documentation clause on all 8 checklist items; config table has zero drift vs
      config.py; the 3 divergences from the literal checklist are correct-by-design (registered).").
- [ ] 8-point audit matrix COMPLETE (all 8 items, each with README section:live-line + verdict +
      evidence); config-table lockstep table confirms zero drift (or a drift is FIXED in README).
- [ ] 3 correct-divergences registered (silero_sensitivity, first-run knobs, input_device_index) so a
      future reader does not "fix" them.
- [ ] README.md edit (if any) is SURGICAL: the optional `feedback.hypr_notify` row OR a verified
      drift fix; verify with `git diff README.md`. A clean PASS needs NO README edit.
- [ ] Scope respected: NO source/test/script edit; NO pytest/heavy script; #7 commit → S3; VT-001 /
      stale-refs → S2 (not touched here).

## All Needed Context

### Context Completeness Check

_Pass._ The implementer gets: the pre-verified 8-point audit matrix (item → README section:line →
PASS verdict → evidence/cross-check), the config-table ↔ config.py lockstep table (zero drift,
re-verifiable), the 3 correct-divergences with reasoning, the optional-polish note, the verbatim
`gap_readme.md` scaffold (6 sections), the exact grep commands + the lockstep-diff snippet, and the
hard scope boundaries (commit → S3, VT-001 → S2, README-only for this task). No inference required —
the agent re-confirms line numbers live, re-runs the lockstep diff, and materializes the dossier.

### Documentation & References

```yaml
# MUST READ — the audit design + pre-verified findings (THIS is the spec for the audit).
- file: plan/006_862ee9d6ef41/P1M6T1S1/research/readme_audit_findings.md
  why: "§1 the two-layer spec (PRD §7 #7 literal + item 8-point checklist) + the scope boundary (commit→S3,
        VT-001→S2). §2 the 8-point audit matrix PRE-VERIFIED (item→README section:line→PASS→evidence). §3 the
        config-table↔config.py lockstep table (zero drift). §4 the 3 CORRECT divergences (do NOT 'fix'). §5 the
        optional polish (feedback.hypr_notify row). §6 the validation approach (grep + lockstep, no pytest)."
  critical: "The audit verdict is pre-PASS (8/8). The deliverable is gap_readme.md + an OPTIONAL README row.
             Re-grep line numbers live (they may have drifted from the PRP). Do NOT 'fix' the 3 correct
             divergences (§4) — registering them IS the task."

# MUST READ — the artifact under audit.
- file: README.md
  why: "The doc being audited. 382 lines. Headings (grep -nE '^#{1,3} ' README.md): ## Install L23, ## First
        run L50, ## Hotkey (Hyprland) L79, ## Lite mode L118, ## tmux status line L135, ## Configuration L152,
        ### Voice-activity constants are NOT config keys L184, ## CPU-only mode L202, ## Troubleshooting L229
        (### cuDNN L231, ### Wrong microphone L258, ### wtype vs ydotool L276), ## Logs, status, stopping L286,
        ### Model lifecycle & VRAM L332. The config TABLE is at ~L159–177."
  critical: "Confirm the LIVE line numbers at audit time (re-grep). All 8 checklist items map to present
             sections. Read the WHOLE file — accuracy (not just presence) is audited."

# MUST READ — the schema source of truth for the config-table lockstep check.
- file: voice_typing/config.py
  why: "The dataclass defaults the README table must match EXACTLY: AsrConfig (L48: final_model/realtime_model/
        lite_model/language/device/post_speech_silence_duration/lite_post_speech_silence_duration/
        realtime_processing_pause/auto_stop_idle_seconds/auto_unload_idle_seconds), OutputConfig (L118),
        FeedbackConfig (L127: state_file/hypr_notify/notify_ms/notify_on_final), FilterConfig (L177),
        LogConfig (L203: level). compute_type is NOT a field (derived from device — README L191 says so)."
  critical: "This is the oracle for the config-table drift check. Every README default must equal the dataclass
             default. Pre-verified zero-drift; re-run the diff to be certain."

# MUST READ — the gap audits that already cross-read README (cite verdicts; don't re-derive).
- file: plan/006_862ee9d6ef41/architecture/gap_hypr_binds.md
  why: "Cross-checked README ## Hotkey (L79/87/101/102) ↔ hypr-binds.conf ↔ install.sh = MATCH. Satisfies
        Acceptance #7 hotkey clause. Verdict: ✅. Cite its README line citations + grep commands."
- file: plan/006_862ee9d6ef41/architecture/gap_status_sh.md
  why: "Cross-checked README ## tmux status line (L135-150, snippet L141-142) ↔ status.sh = MATCH (Mode B ✅).
        Satisfies Acceptance #7 tmux clause. Cite its verdict."
- file: plan/006_862ee9d6ef41/architecture/gap_install.md
  why: "install.sh audit (PASS, 15 tests). README ## Install (L23-48) documents the 7 install.sh steps the
        audit verified. Cite for the install clause."

# MUST READ — the parallel acceptance gate (the contract this audit feeds).
- file: plan/006_862ee9d6ef41/P1M5T5S1/PRP.md
  why: "The acceptance gate that ROUTES #7's docs half to this task. It asserts README has 9/9 required
        sections present + committed (its README source-map cites the same line numbers). This audit is the
        deeper, line-cited confirmation. Its CRITICAL #4 notes #7's commit half is owned by S3 (this task
        does NOT judge commit cleanliness). Its CRITICAL #6 routes VT-001 doc-drift to S2 (NOT this task)."
  critical: "Treat this gate's README section-list as the INPUT assertion; this audit CONFIRMS it with
             evidence + adds the 8-point depth + the divergence register. Do NOT duplicate the commit/VT-001
             scope (S2/S3 own those)."

# MUST READ — the merged PRD (the oracle for #7's literal wording + T5's first-run spec).
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: "§7 #7 (the verbatim acceptance clause) = the spec; §6 T5 (the first-run guide: 'systemctl --user
        start voice-typing, voicectl toggle, speak, watch tmux status, voicectl toggle' + 'the two tunables
        that matter (post_speech_silence_duration, silero_sensitivity)') = what README's First run must cover;
        §4.5 (config schema) = the lockstep oracle's second source. The delta_prd.md confirms silero_use_onnx
        → silero_backend='auto' + constants-not-config (why the T5 'silero_sensitivity' mention is now stale)."

# Background — the files README documents (spot-check accuracy against these).
- file: hypr-binds.conf
  why: "The sourced binds. README L101-102 must quote them VERBATIM (`bind = CTRL SUPER ALT, D, exec,
        $HOME/.local/bin/voicectl toggle` + `bind = SUPER ALT, D, exec, $HOME/.local/bin/voicectl toggle-lite`).
        gap_hypr_binds.md already confirmed the match."
- file: voice_typing/status.sh
  why: "The tmux helper. README L141-142 must reference it (NOT inline jq). gap_status_sh.md confirmed."

# Hard rules.
- file: AGENTS.md
  why: "This task runs ONLY grep + a python one-liner lockstep diff (fast, safe). NO pytest, NO heavy shell
        script (test_idle_and_gpu.sh / e2e_virtual_mic.sh are forbidden unless explicitly required)."
```

### Current Codebase tree (relevant slice — state at P1.M6.T1.S1)

```bash
/home/dustin/projects/voice-typing/
├── README.md                         # ← AUDIT (+ optional 1-row edit). 382 lines, comprehensive.
├── voice_typing/config.py            # the schema oracle for the config-table lockstep check (READ ONLY)
├── hypr-binds.conf                   # spot-check the hotkey binds README quotes (READ ONLY)
├── voice_typing/status.sh            # spot-check the tmux snippet README quotes (READ ONLY)
└── plan/006_862ee9d6ef41/
    ├── architecture/gap_*.md         # 17 source audits; gap_hypr_binds/gap_status_sh/gap_install cross-read README (READ ONLY)
    ├── P1M5T5S1/PRP.md (+ acceptance_gate.md when S1 lands)  # the gate that routes #7-docs here (READ ONLY)
    └── P1M6T1S1/
        ├── PRP.md                    # THIS file
        ├── research/readme_audit_findings.md   # the pre-verified audit matrix (this PRP's research)
        └── gap_readme.md             # ← OUTPUT #1 (NEW; the README-completeness audit dossier)
```

### Desired Codebase tree with files to be added/modified

```bash
plan/006_862ee9d6ef41/P1M6T1S1/gap_readme.md   # NEW — the README-completeness audit dossier (OUTPUT #1)
README.md                                      # MODIFY (OPTIONAL, surgical) — add ONE feedback.hypr_notify row IF concurred; else UNCHANGED
# (NO source/test/script files edited. NO pytest/heavy script. Audit + optional polish.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — the audit verdict is pre-PASS; do NOT invent gaps to justify the task. README is
#   comprehensive (8/8 checklist items present + correct, config table zero-drift vs config.py). The
#   deliverable is gap_readme.md (evidence dossier) + an OPTIONAL README row. If you find no drift and
#   judge the table curation fine, README stays unchanged and gap_readme.md records the clean PASS.
#   "Fix any gaps" means fix GENUINE gaps (a drifted default, a missing required surface) — there are
#   pre-verified NONE. Do not manufacture edits.

# CRITICAL #2 — three README divergences from the literal checklist are CORRECT; do NOT "fix" them:
#   (i)  silero_sensitivity is NOT a config key (it's a _FIXED_KWARGS constant in daemon.py). README L184
#        correctly documents it under "Voice-activity constants are NOT config keys." The checklist's (d)
#        mention predates the silero_use_onnx→silero_backend='auto' decision. Adding it to the tuning
#        table would mislead users (config.py rejects unknown keys → systemd Restart=on-failure loop).
#   (ii) First-run "two knobs": README (L75-77) says "mic default source + post_speech_silence_duration";
#        PRD T5 says "post_speech_silence_duration, silero_sensitivity." README is MORE accurate (silero
#        isn't tunable; mic source is the #1 first-run failure). Correct divergence — do NOT revert.
#   (iii) input_device_index is a RealtimeSTT TEST kwarg (T3 virtual-sink monitor), UNSET in production →
#        PipeWire default. README correctly documents the user path (default source + pactl + the mic:
#        health line). It is NOT a user config. PyAudio IS mentioned (mic health probe).
#   Registering these three as "correct-by-design, not gaps" IS part of the deliverable.

# CRITICAL #3 — re-grep README line numbers LIVE. The PRP/research cite headings at specific lines
#   (Install L23, Hotkey L79, etc.) but lines may have drifted since this PRP was written. gap_readme.md
#   must cite CURRENT line numbers from a fresh `grep -nE '^#{1,3} ' README.md`, not the PRP's.

# CRITICAL #4 — scope boundary with siblings. The literal "everything committed to git" half of #7 is
#   OWNED by P1.M6.T1.S3 (commit readiness). Stale BUGS.md / VT-001 references are OWNED by P1.M6.T1.S2.
#   This task owns ONLY the README-completeness half. Do NOT judge git cleanliness, do NOT edit
#   BUGS.md/VT-* references, do NOT create the final commit. Cite S2/S3 as owners; do not duplicate.

# CRITICAL #5 — the README table is a CURATED "Real tunable keys" set, not an exhaustive field list.
#   feedback.state_file (default "" → XDG) and feedback.hypr_notify (master on/off) are config fields
#   NOT given dedicated rows — state_file is referenced in the tmux section; hypr_notify in the notify_ms
#   row. This is intentional curation, NOT a gap. The OPTIONAL polish (§5) adds a hypr_notify row only if
#   the implementer judges it aids clarity; it is NOT required for PASS.

# CRITICAL #6 — DO NOT run pytest or heavy shell scripts. The audit uses grep + a python one-liner
#   lockstep diff only (fast, safe, no AGENTS.md timeout needed). test_idle_and_gpu.sh (~5-8 min) and
#   e2e_virtual_mic.sh (rebinds global audio) are FORBIDDEN (not relevant to a README audit anyway).

# CRITICAL #7 — the README uses /home/<you>/projects/voice-typing/ placeholders intentionally
#   (portable across users). The <you> placeholder is consistent throughout. Do NOT "fix" it to a
#   hardcoded /home/dustin path — that would reduce portability. (Confirmed in gap_hypr_binds.md.)

# CRITICAL #8 — this is a REPORT item. The writes are gap_readme.md (CREATE) and OPTIONALLY README.md
#   (one surgical row). Do NOT touch voice_typing/*.py, tests/*, *.sh, config.toml, PRD.md, tasks.json,
#   prd_snapshot.md, .gitignore, or any other plan/ file.
```

## Implementation Blueprint

### Data models and structure

N/A — no code. The "data" is the 8-point audit matrix (8 rows × {item, README section:line, verdict,
evidence}) + the config-table lockstep table (README default vs config.py default) + the 3-entry
correct-divergences register. The deliverable is a Markdown dossier (+ an optional 1-row README edit).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: READ README.md (full) + voice_typing/config.py + hypr-binds.conf + voice_typing/status.sh +
  the relevant architecture/gap_*.md (gap_hypr_binds, gap_status_sh, gap_install). CONFIRM line numbers.
  - READ README.md end-to-end (382 lines) — accuracy, not just presence, is audited.
  - READ config.py dataclasses (AsrConfig L48, OutputConfig L118, FeedbackConfig L127, FilterConfig L177,
    LogConfig L203) — the oracle for the config-table lockstep check.
  - READ hypr-binds.conf — confirm README L101-102 quotes both binds VERBATIM.
  - READ status.sh header — confirm README L141-142 references it (not inline jq).
  - READ gap_hypr_binds.md / gap_status_sh.md / gap_install.md — cite their cross-check verdicts.
  - DO NOT run pytest or any heavy script. GO to Task 2.

Task 2: RUN the grep-based completeness + line-number checks + the config-table lockstep diff.
  - `grep -nE '^#{1,3} ' README.md` — re-confirm ALL required section headings + their CURRENT line numbers.
  - 8-point completeness greps (one per checklist item; see Level-3 validation block) — confirm each
    required surface is PRESENT (e.g. `grep -n 'source = .*hypr-binds\.conf' README.md`,
    `grep -n 'set -g status-right.*status\.sh' README.md`, `grep -n 'CPU-only mode\|device = "cpu"'
    README.md`, `grep -n 'toggle-lite\|Alt+Super+D' README.md`, ...).
  - Config-table lockstep diff: extract README table rows + compare defaults to config.py (the python
    snippet in Level-3). Flag ANY drift (pre-verified: zero).
  - DECIDE: if a drift is found → it becomes the mandatory README fix. If zero drift → README unchanged
    (or the optional hypr_notify row, per Task 4). GO to Task 3.

Task 3: WRITE plan/006_862ee9d6ef41/P1M6T1S1/gap_readme.md (OUTPUT #1 — the dossier).
  - USE the verbatim 6-section scaffold in "Task 3 SOURCE" below. Fill: the verdict line; the 8-point
    audit matrix (re-confirm section:live-line + evidence from Task 2); the config-table lockstep table
    (paste the zero-drift result OR the fixed row); the 3 correct-divergences register; the optional
    polish note; the scope section (commit→S3, VT-001→S2).
  - VERDICT line: "PASS: README satisfies PRD §7 #7's documentation clause on all 8 checklist items
    (install, hotkey incl. lite bind, tmux status, config tuning table, troubleshooting cuDNN/PyAudio/
    wtype-vs-ydotool, CPU-only mode, first-run T5, lite mode). Config table has zero drift vs
    voice_typing/config.py. Three divergences from the literal checklist (silero_sensitivity,
    first-run knobs, input_device_index) are correct-by-design and registered below. <README unchanged |
    README +1 optional hypr_notify row | README +N drift fixes>."
  - DO NOT edit any source/test/script/config/PRD/tasks file. GO to Task 4.

Task 4: (OPTIONAL) UPDATE README.md — ONLY if concurred.
  - IF a config-table drift was found in Task 2 → FIX the drifted row(s) in README (mandatory).
  - ELSE IF the implementer concurs §5 adds clarity → ADD ONE row to the config table:
      `| \`feedback.hypr_notify\` | \`true\` | master on/off for ALL hyprctl popups. \`false\` suppresses
        the start/stop toasts too (notify_on_final only adds the per-final ✔ popup; this is the global
        kill switch). |`
    placed near the notify_on_final / notify_ms rows (keep the table sorted by section).
  - ELSE → README.md UNCHANGED (a clean PASS needs no edit; gap_readme.md records the verdict).
  - VERIFY: `git diff README.md` is surgical (one row OR a drift fix; NO reflow of surrounding prose,
    NO line-ending churn). If the diff is noisy, revert and leave README unchanged.
  - DO NOT touch any other file.

Task 5: (NONE) — no source/test/script changes. Verify gap_readme.md is self-contained + the README
  diff (if any) is surgical, then done.
```

#### Task 3 SOURCE — `gap_readme.md` verbatim scaffold (fill the static parts; confirm evidence/line numbers LIVE)

```markdown
# README completeness audit — P1.M6.T1.S1 (PRD §7 #7 documentation clause)

**Date:** <YYYY-MM-DD>
**Verdict:** **PASS.** README satisfies PRD §7 #7's documentation clause on all 8 checklist items.
Config table has **zero drift** vs `voice_typing/config.py`. Three divergences from the literal
checklist wording are **correct-by-design** (registered in §4 — do NOT "fix"). README was
<unchanged | updated with the optional feedback.hypr_notify row | updated to fix N config-drift row(s)>.
Scope: this audit owns ONLY #7's docs half; the "everything committed to git" half → P1.M6.T1.S3;
stale BUGS.md / VT-001 references → P1.M6.T1.S2.

## 1. Audit spec

- **PRD §7 #7 (literal):** "README documents: install, hotkey snippet, tmux status snippet, config
  tuning table, troubleshooting (cuDNN libs, PyAudio device, wtype vs ydotool), and how to switch to
  CPU-only mode."
- **Item 8-point checklist (a–h):** install (portaudio/uv sync/install.sh); hotkey (source
  hypr-binds.conf); tmux (status.sh snippet); config tuning table (post_speech_silence_duration,
  silero_sensitivity handling, lite thresholds); troubleshooting (cuDNN LD_LIBRARY_PATH, PyAudio device,
  wtype vs ydotool); CPU-only (device=cpu); first-run (T5); lite mode (toggle-lite, Alt+Super+D).

## 2. 8-point audit matrix

| # | Item | README section (live line) | Verdict | Evidence |
|---|---|---|---|---|
| a | install (portaudio + uv sync + install.sh) | `## Install` (L??) | ✅ | `./install.sh` + the 7 numbered steps incl. portaudio pacman check, uv sync; gap_install.md ✅ |
| b | hotkey (source hypr-binds.conf) | `## Hotkey (Hyprland)` (L??) | ✅ | `source = …/hypr-binds.conf` (L??) + BOTH binds verbatim (L??); gap_hypr_binds.md ✅ |
| c | tmux status (status.sh snippet) | `## tmux status line` (L??) | ✅ | 2-line snippet `set -g status-interval 1` + `status-right "#(…/status.sh)"` (L??); gap_status_sh.md ✅ |
| d | config tuning table (key knobs) | `## Configuration` (L??) | ✅ | the real TABLE (L??) + "VAD constants are NOT config keys" (L??); lockstep §3 zero-drift |
| e | troubleshooting (cuDNN + PyAudio + wtype/ydotool) | `## Troubleshooting` (L??) | ✅ | `### cuDNN` (L??) + `### Wrong microphone` (L??, mic: health line) + `### wtype vs ydotool` (L??) |
| f | CPU-only mode (device=cpu) | `## CPU-only mode` (L??) | ✅ | all 3 paths: force device=cpu, auto-fallback, construction-failure fallback |
| g | first-run (T5) | `## First run` (L??) | ✅ | systemctl start + voicectl toggle + speak + watch tmux + toggle; (see §4 divergence ii) |
| h | lite mode (toggle-lite, Alt+Super+D) | `## Lite mode` (L??) + `## Hotkey` (L??) | ✅ | single model ~half VRAM, shorter silence gate, toggle-lite, Alt+Super+D, mode: in status |

(Replace L?? with the LIVE grep'd numbers; cite the exact grep match or config.py/gap line as evidence.)

## 3. Config-table ↔ config.py lockstep (zero drift)

| README table key | README default | config.py default | Match |
|---|---|---|---|
| asr.post_speech_silence_duration | 0.6 | 0.6 | ✅ |
| asr.lite_post_speech_silence_duration | 0.5 | 0.5 | ✅ |
| … (all rows) … | | | ✅ |

(Paste the full comparison from the Task-2 lockstep snippet. Zero drift confirmed; if a row drifted,
note it + the README fix applied.)

## 4. Correct divergences (NOT gaps — do not "fix")

1. **silero_sensitivity** is a `_FIXED_KWARGS` constant in daemon.py, NOT a config key. README correctly
   documents it under "VAD constants are NOT config keys." Adding it to config.toml crash-loops the
   daemon (config rejects unknown keys). The checklist's mention predates the silero_backend='auto' move.
2. **First-run "two knobs"** = mic default source + post_speech_silence_duration (README), NOT
   post_speech_silence_duration + silero_sensitivity (PRD T5). README is more accurate + actionable.
3. **input_device_index** is a RealtimeSTT TEST kwarg (T3 virtual-sink), UNSET in production → PipeWire
   default. README documents the user path (default source + pactl + mic: health line). Not a user config.

## 5. Optional polish (non-blocking; routed)

- `feedback.hypr_notify` + `feedback.state_file` have no dedicated table rows (curated "tunable keys"
  table; both are referenced in prose). Optional: add a `feedback.hypr_notify` row for an exhaustive
  enumeration. <Applied | Not applied: reason>. Low priority; does not affect the PASS.

## 6. Scope

- **IN scope (this task):** README-completeness audit + gap_readme.md + optional README row.
- **OUT of scope (cited, not duplicated):** #7 "everything committed" → **P1.M6.T1.S3**; stale
  BUGS.md/VT-001 references → **P1.M6.T1.S2**. No source/test/script edit; no pytest/heavy script.
```

### Implementation Patterns & Key Details

```bash
# The ONLY commands this audit runs (fast, safe, no AGENTS.md timeout needed). Do NOT run pytest/scripts.
grep -nE '^#{1,3} ' README.md                       # re-confirm all section headings + LIVE line numbers

# 8-point completeness greps (one per checklist item — all must hit):
grep -nE '## Install|portaudio|uv sync|install\.sh'                README.md   # (a)
grep -nE '## Hotkey|source = .*hypr-binds\.conf|CTRL SUPER ALT, D' README.md   # (b)
grep -nE '## tmux status line|set -g status-right.*status\.sh'     README.md   # (c)
grep -nE '## Configuration|post_speech_silence_duration|lite_post_speech' README.md  # (d)
grep -nE '## Troubleshooting|cuDNN|Wrong microphone|wtype vs ydotool' README.md  # (e)
grep -nE '## CPU-only mode|device = "cpu"'                         README.md   # (f)
grep -nE '## First run|systemctl --user start voice-typing|voicectl toggle' README.md  # (g)
grep -nE '## Lite mode|toggle-lite|Alt\+Super\+D'                  README.md   # (h)

# Config-table lockstep diff (extract README table defaults; compare to config.py):
grep -nE '^\| `(asr|output|feedback|filter|log)\.' README.md       # the README table rows
# then cross-check each default against `grep -nE '^\s+\w+: .*= ' voice_typing/config.py`

# If README is edited, verify the diff is SURGICAL (one row; no reflow):
git -C /home/dustin/projects/voice-typing diff --stat -- README.md   # expect a tiny change
git -C /home/dustin/projects/voice-typing diff -- README.md          # eyeball: one row, no prose churn
```

### Integration Points

```yaml
DELIVERABLE #1 (the audit dossier):
  - create: "plan/006_862ee9d6ef41/P1M6T1S1/gap_readme.md"
  - pattern: "Self-contained README-completeness audit (the verbatim 6-section scaffold in Task 3 SOURCE)."
  - consume_by: "P1.M5.T5.S1 acceptance gate (confirms #7 docs half); P1.M6.T1.S2/S3 (sibling owners);
                 the orchestrator + future maintainers (the divergence register prevents regressions)."

DELIVERABLE #2 (optional README polish):
  - edit: "README.md (OPTIONAL, surgical)"
  - pattern: "Add ONE feedback.hypr_notify row to the config table IF concurred; OR fix a verified
              config-drift row; ELSE leave UNCHANGED. Verify git diff is surgical (no reflow)."
  - consume_by: "End users (the README is the user-facing changeset doc, Mode B)."

RUN (the only live actions — fast, safe):
  - commands: "grep -nE headings; 8-point completeness greps; config-table lockstep diff; git diff README.md"
  - expected: "fast; confirms 8/8 present + zero drift; surgical/no diff on README"

DO NOT RUN:
  - commands: [".venv/bin/python -m pytest ...", "tests/test_idle_and_gpu.sh", "tests/e2e_virtual_mic.sh"]
  - reason: "A README audit needs no test run. AGENTS.md forbids the heavy scripts unless explicitly
             required; they are irrelevant here."

EDITS (1–2 — REPORT + optional polish):
  - create: "plan/006_862ee9d6ef41/P1M6T1S1/gap_readme.md"
  - edit (optional): "README.md (one surgical row OR a drift fix; else unchanged)"
  - forbidden: "voice_typing/*, tests/*, *.sh, config.toml, PRD.md, tasks.json, prd_snapshot.md, .gitignore,
                any other plan/ file, BUGS.md (S2 owns stale refs)"
```

## Validation Loop

### Level 1: Syntax & Style (N/A — Markdown docs; no code)

```bash
# Verify the dossier is written + structurally complete.
ls -la plan/006_862ee9d6ef41/P1M6T1S1/gap_readme.md
grep -c '^## ' plan/006_862ee9d6ef41/P1M6T1S1/gap_readme.md    # expect >= 6 (sections 1-6)
grep -q 'PASS' plan/006_862ee9d6ef41/P1M6T1S1/gap_readme.md && echo "verdict present"
# README edit (if any) is surgical:
git -C /home/dustin/projects/voice-typing diff --stat -- README.md   # tiny or zero
# Expected: dossier present with 6 sections + PASS verdict; README diff tiny or absent.
```

### Level 2: (N/A — no unit tests; this is a doc-audit item)

### Level 3: Static cross-check (fast, safe — confirms the dossier's claims against the LIVE README)

```bash
cd /home/dustin/projects/voice-typing

# Re-confirm ALL required README sections + LIVE line numbers (cite these in gap_readme.md, NOT the PRP's):
grep -nE '^#{1,3} ' README.md

# 8-point completeness (each MUST hit >= 1 line):
grep -cE '## Install|portaudio|uv sync' README.md                                   # (a) >=1
grep -cE 'source = .*hypr-binds\.conf|CTRL SUPER ALT, D, exec' README.md            # (b) >=1
grep -cE 'set -g status-right.*status\.sh' README.md                                # (c) >=1
grep -cE 'post_speech_silence_duration|lite_post_speech_silence_duration' README.md # (d) >=1
grep -cE 'cuDNN|Wrong microphone|wtype vs ydotool' README.md                        # (e) >=3
grep -cE 'CPU-only mode|device = "cpu"' README.md                                   # (f) >=1
grep -cE 'systemctl --user start voice-typing|voicectl toggle' README.md            # (g) >=1
grep -cE 'toggle-lite|Alt\+Super\+D' README.md                                      # (h) >=1

# Config-table lockstep (zero drift expected; this is the high-value check):
grep -nE '^\| `(asr|output|feedback|filter|log)\.' README.md   # the README table rows
# cross-check each default against:
grep -nE '^\s+(final_model|realtime_model|lite_model|language|device|post_speech_silence_duration|lite_post_speech_silence_duration|realtime_processing_pause|auto_stop_idle_seconds|auto_unload_idle_seconds|backend|tmux_target|append_space|state_file|hypr_notify|notify_ms|notify_on_final|min_chars|level):' voice_typing/config.py

# README unchanged-or-surgical (a clean PASS needs no edit):
git -C /home/dustin/projects/voice-typing status --short -- README.md   # empty (unchanged) OR README.md (1 edit)
git -C /home/dustin/projects/voice-typing diff -- README.md 2>/dev/null | head -30   # one row, no reflow
# Expected: all 8 completeness greps hit; config lockstep zero drift; README diff empty or one-row-surgical.
```

### Level 4: Domain-specific validation (documentation accuracy)

```bash
# Spot-check the two verbatim README quotes against their source files (accuracy, not just presence):
# (1) the hotkey binds README quotes must match hypr-binds.conf exactly:
diff <(grep -E '^bind = ' hypr-binds.conf) <(grep -oE 'bind = (CTRL SUPER ALT|SUPER ALT), D, exec, \$HOME/\.local/bin/voicectl (toggle|toggle-lite)' README.md) && echo "hotkey binds MATCH"
# (2) the tmux snippet must reference status.sh (not inline jq):
grep -q 'status\.sh' README.md && ! grep -q 'status-right.*jq ' README.md && echo "tmux uses status.sh (correct)"
# (3) the README hotkey section's "never edit" promise is present (Acceptance #7 never-edit clause):
grep -qE 'never (edit|modify).*hyprland\.conf|repo never edits' README.md && echo "never-edit promise present"
# Expected: hotkey binds match; tmux uses status.sh; never-edit promise present. (gap_hypr_binds/gap_status_sh
# already confirmed these; this is the README-side re-confirmation.)
```

## Final Validation Checklist

### Technical Validation

- [ ] `gap_readme.md` written with the 6-section structure + a PASS verdict line.
- [ ] 8-point audit matrix COMPLETE (all 8 items, each with README section:LIVE-line + verdict + evidence).
- [ ] Config-table ↔ config.py lockstep table confirms zero drift (or a drift is FIXED in README).
- [ ] 3 correct-divergences registered (silero_sensitivity, first-run knobs, input_device_index).
- [ ] README.md edit (if any) is SURGICAL (one optional row OR a verified drift fix); `git diff` clean.
- [ ] (No pytest / heavy script — this is a doc audit; L1 + L3 + L4 grep checks are the gates.)

### Feature Validation

- [ ] PRD §7 #7 documentation clause verified on all surfaces (install, hotkey, tmux, config table,
      troubleshooting, CPU-only mode).
- [ ] Item 8-point checklist verified (all 8 items PASS).
- [ ] First-run guide matches T5 (with the documented correct divergence on the "two knobs").
- [ ] Lite mode documented (toggle-lite, Alt+Super+D, single-model, shorter silence gate).
- [ ] README accuracy spot-checks pass (hotkey binds verbatim; tmux uses status.sh; never-edit promise).

### Code Quality Validation

- [ ] gap_readme.md is self-contained (a reader needs no other file to see the verdict + evidence).
- [ ] Line numbers in gap_readme.md are LIVE (re-grepped, not copy-pasted from the PRP).
- [ ] The correct-divergences register is clear enough to prevent a future "fix it to match the PRD" regression.

### Documentation & Deployment

- [ ] README.md (the user-facing changeset doc, Mode B) is complete + accurate after this task.
- [ ] gap_readme.md cites the sibling owners (S2 stale-refs, S3 commit) so the docs module closes cleanly.
- [ ] No new env vars / config keys / source changes (doc-audit item).

---

## Anti-Patterns to Avoid

- ❌ Don't manufacture README edits to justify the task — the audit is pre-PASS; a clean PASS needs no edit.
- ❌ Don't "fix" the 3 correct divergences (silero_sensitivity, first-run knobs, input_device_index) — they
  are correct-by-design; registering them IS the deliverable (CRITICAL #2).
- ❌ Don't cite PRP/research line numbers in gap_readme.md — re-grep README live and cite CURRENT lines.
- ❌ Don't touch the commit half of #7 (→ S3) or stale BUGS.md/VT-001 refs (→ S2) — scope boundary (CRITICAL #4).
- ❌ Don't run pytest or the heavy shell scripts — a README audit uses grep + a lockstep diff only (CRITICAL #6).
- ❌ Don't "fix" the `/home/<you>/` placeholders to a hardcoded path — they are intentional (portable) (CRITICAL #7).
- ❌ Don't rewrite/expand the README beyond the one optional row — a surgical edit only; reflow churns the diff.
- ❌ Don't add silero_sensitivity / webrtc_sensitivity / compute_type to the config table — they are NOT config
  keys (constants/derived); README L184 documents this correctly.

---

## Confidence Score

**9/10.** The audit is pre-verified: README is comprehensive (8/8 checklist items present + correct),
the config table has zero drift vs `config.py` (cross-checked row-by-row), and the hotkey/tmux sections
were already cross-verified by `gap_hypr_binds.md`/`gap_status_sh.md`. The 3 correct-divergences are
documented with reasoning that prevents regression. The only residual uncertainty (not −1): whether the
implementer concurs the optional `feedback.hypr_notify` row is worth adding — framed as a judgment call
with a clear "else leave unchanged" path, so it cannot cause a wrong outcome. The task is robust to the
parallel P1.M5.T5.S1 acceptance gate (this audit CONFIRMS its README assertion with line-cited depth;
it does not depend on the gate's own deliverables landing first — README + config.py + the gap audits
are all already live). No source/test/script edit; no heavy run; scope cleanly bounded from S2/S3.