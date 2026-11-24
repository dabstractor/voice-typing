# PRP — P1.M7.T2.S1: README.md — ducking + bulk-delivery sections, config rows, troubleshooting

## Goal

**Feature Goal**: Bring `README.md` current with the whole Rev-3/4 delta changeset — media ducking
(P1.M2, landed and evidence-flipped to default), bulk text delivery (P1.M3–M6, landed, opt-in pending
G6), the new `[audio]` + `output.delivery` config keys, and three new troubleshooting subsections —
describing **exactly what landed, no aspirational prose**, with every unverified claim explicitly
labeled unverified per PRD §4.2sexies R.2's no-over-claim rule.

**Deliverable** (1 file MODIFIED; no other file touched):
- `README.md` — eight scoped edits (see Implementation Tasks): 2 new top-level sections, 3 new config
  table rows, 3 new troubleshooting subsections, plus four small consistency touches (First-run
  ducking sentence, six→seven commands, state.json field list, status sample delivery line).

**Success Definition**:
- (a) Every statement in the new/edited sections traces to code or a committed evidence file (the
  L2 verification greps pass); zero aspirational claims; the phrases "works on Wayland",
  "production-ready", "fully verified" appear nowhere.
- (b) The bulk-delivery section's framing matches `tests/G6_GRADUATION.md`'s `G6 DECISION:` line
  **verbatim-derived** (expected: STAY OPT-IN → opt-in + unverified framing; absent file = blocking).
- (c) Config table rows match `voice_typing/config.py` defaults exactly (L2 script asserts).
- (d) Internal anchors resolve (L1); markdown structure consistent with the existing README voice.
- (e) No edit to `tests/ACCEPTANCE.md` (P1.M7.T2.S2 owns it), `config.py`/`config.toml` (no value
  changes), any `voice_typing/` source, `PRD.md`, `tasks.json`, `.gitignore`.

## User Persona

**Target User**: (1) dustin six months from now + anyone cloning the repo (the README's own stated
audience — "exact commands, not hand-holding"); (2) an operator deciding whether to try
`delivery = "bulk-text"` who needs the honest per-terminal support matrix and the G6 status; (3) an
operator whose media paused unexpectedly while dictating (ducking is now DEFAULT — must be documented
or it reads as a bug).

**Use Case**: read the ducking section to understand/control the default pause behavior; read the
bulk section + matrix to decide whether the opt-in mode fits their terminal; use `voicectl session
[--copy]` to recover the last dictation; troubleshoot an IM-route `unsupported` state via fcitx5/seat
guidance.

**Pain Points Addressed**: (1) ducking is default-on and undocumented → user surprise; (2) bulk-text's
honest-but-complex support matrix (foot/kitty insert-only, ghostty blocked, browser correction
refused, Hyprland relay untested) lives only in lab registers — users need it in one table; (3) the
G6 assessment (parallel P1.M7.T1.S1) produces a verdict doc nobody will read unless the README points
at it; (4) R.2 forbids over-claiming — the README is where over-claiming would leak if unsupervised.

## Why

- **PRD §7 criterion 7**: "README documents: install, hotkey snippet, feedback surfaces, config tuning
  table, troubleshooting …" — the delta changeset added surfaces (ducking, delivery status, session
  recovery) and config keys that the Oct-4 README predates entirely.
- **Acceptance criterion 13's tail**: bulk-text "is opt-in and its claims are reported as unverified"
  until G6 — the README is the shipped place those claims are reported, so the no-over-claim framing
  here IS the criterion.
- **Ducking default flip (P1.M2.T4.S1)** was evidence-gated and is now user-visible default behavior;
  undocumented default behavior that pauses the user's music is indistinguishable from a bug.
- **Consumes the G6 assessment as its source of truth** (the P1.M7.T1.S1 PRP names this task as the
  consumer of `tests/G6_GRADUATION.md`) — the README turns the mechanical verdict into the shipped
  framing, keeping the derivability chain intact.
- **Scope discipline**: docs only; the consistency sweep over PRE-EXISTING drift (e.g. the
  compute_type claim vs the shipped config key) belongs to P1.M7.T2.S3 — flag, don't fix, here.

## What

Eight scoped edits to `README.md` (content pinned in the Blueprint):

1. **§First run** — one sentence: arming pauses playing media (MPRIS) and stop resumes it; link to the
   new ducking section.
2. **§Upgrading from Rev 1** — "six commands" → seven (`+ session`).
3. **NEW `## Media ducking while listening`** — tiers, config, sovereignty guarantees, journal lines,
   crash self-heal, `duck_mode="off"` escape hatch.
4. **NEW `## Bulk text delivery (opt-in, experimental)`** — the opt-in flag + precondition triple,
   delivery states + status lines, routes + field-class matrix (copied verbatim from the register),
   `voicectl session [--copy]`, and the EXPLICIT unverified-until-G6 framing block.
5. **§Feedback surfaces** — add `ducked` + `delivery_mode`/`delivery_state`/`delivery_reason`/
   `last_confirmed_op` to the state.json field documentation.
6. **§Configuration table** — 3 new rows: `audio.duck_mode`, `audio.duck_volume_pct`,
   `output.delivery`.
7. **NEW troubleshooting ×3** — IM seat exclusivity (fcitx5/ibus), terminal field-class matrix,
   clipboard fallback contract.
8. **§Logs, status** — status sample gains the `delivery:` line(s).

### Success Criteria

- [ ] Sections 3, 4, 7 exist with the pinned content (facts, tables, journal lines, exit codes).
- [ ] Bulk framing derived from `tests/G6_GRADUATION.md` (STAY OPT-IN → "opt-in, unverified"; FLIP →
      graduated-with-evidence framing; still no categorical "works on Wayland").
- [ ] L1 anchors + L2 claim-verification + L3 G6-framing + L4 prose-audit gates all pass.
- [ ] Zero out-of-scope edits (evidence: `git diff --stat` shows README.md only).

## All Needed Context

### Context Completeness Check

_Pass._ Every fact the implementer needs is pinned below with its source: config defaults from
`config.py`, journal lines verbatim from `tests/D1_DUCK_EVIDENCE.md`, the matrix verbatim from
`plan/008_a47116bb2b79/architecture/g3_field_matrix.md`, voicectl session semantics from `ctl.py`,
delivery-field vocabulary from `feedback.py`, and the G6-verdict dependency from the parallel task's
PRP. No prior codebase knowledge required beyond reading the files cited.

### Documentation & References

```yaml
# MUST READ — the assembled fact ledger: verified-vs-unverified table, insertion map, G6 conditional.
- file: plan/008_a47116bb2b79/P1M7T2S1/research/readme_facts_and_insertion_map.md
  why: "§1 the pinned content facts (config defaults, journal lines, exit codes, sovereignty rules);
        §2 the no-over-claim ledger (what is verified/unverified + its evidence file); §3 seat-IME
        facts with ime/manager.py line cites; §4 the 8-point insertion map incl. the compute_type
        drift FLAG (S3's scope, not ours); §5 the G6-verdict conditional; §6 the README voice rules."
  critical: "G-G6: if tests/G6_GRADUATION.md is absent at implementation time the task is BLOCKED —
             report it, never guess the verdict. G-NODRIFT: flag (commit message) but do NOT fix the
             pre-existing compute_type claim drift — that is P1.M7.T2.S3's sweep."

# MUST READ — the file being edited (structure, voice, existing anchors, insertion points).
- file: README.md
  why: "The existing section order (grep '^##' gives the map); the config-table row format
        '| `key` | `default` | desc |'; the terse exact-commands voice; existing anchors the new
        sections must cross-link consistently."
  critical: "Match the voice exactly (absolute .venv/bin/voicectl paths, 'you'-addressed, tables for
             knobs). Do not restructure existing sections — this is an additive delta."

# MUST READ — the ducking evidence (journal lines + the 12/12 record the claims cite).
- file: tests/D1_DUCK_EVIDENCE.md
  why: "The five acceptance rows + verbatim journal excerpts to copy into the ducking section; the
        107 ms pause timing; the sovereignty semantics refinement (ledger = ours; still-paused only)."
  critical: "Cite the evidence file BY PATH in the README so the claim stays derivable. Do not
             paraphrase the sovereignty rules — the three resume conditions (a)/(b)/(c) are the contract."

# MUST READ — the field-class matrix (the troubleshooting table's source, verbatim).
- file: plan/008_a47116bb2b79/architecture/g3_field_matrix.md
  why: "The measured-version table: foot 1.28.0-2 insert-only; kitty 0.51.0-1 insert-only; ghostty
        1.4.0-2 blocked (activate not_activated); Hyprland relay blocked-in-lab. Copy versions+verdicts
        verbatim into the README matrix + troubleshooting subsection."
  critical: "NEVER upgrade a row's status. The 'blocked-in-lab' nuance for Hyprland relay must survive
             (nested boot fails — live-desktop behavior untested). Versions are part of the claim."

# MUST READ — the G6 verdict (THE framing source of truth; produced by the parallel P1.M7.T1.S1).
- file: tests/G6_GRADUATION.md
  why: "Its 'G6 DECISION:' line dictates the bulk section's framing. Expected: STAY OPT-IN (unmet:
        writing-sessions) → opt-in + unverified framing + pointer to the empty sessions template as
        the outstanding input. Also cite it from the config-table delivery row."
  critical: "ABSENT FILE = BLOCKING. Derived framing only — if the decision says STAY OPT-IN the README
             must not soften it; if FLIP, the graduated claims still cite the doc."

# READ — remaining evidence the claims cite (skim for the specific lines, don't ingest whole files).
- file: plan/008_a47116bb2b79/architecture/editor_browser_row_verdicts.jsonl
  why: "The browser-correction REFUSED row ('recheck: caret moved') — the honest insert-only-at-chromium
        limit the README must state rather than hide."
- file: plan/008_a47116bb2b79/architecture/g4_clipboard_verdicts.jsonl
  why: "L1 'unprovable' (watcher active → adapter refuses) + L2-L6 verified — the clipboard-contract
        troubleshooting subsection's substance."
- file: plan/008_a47116bb2b79/architecture/pi_row_verdicts.jsonl
  why: "The pi-prompt row's versions (pi 1.0.2 / ghostty 1.4.0-arch2 / sway 1.12) for the matrix."
- file: tests/G5_TIMING_EVIDENCE.md   # IF IT EXISTS (P1.M6.T4.S1 is parallel/in-flight)
  why: "If present: cite its honest pass|fail|blocked rows in the bulk section. If absent: the README
        states G5 timing evidence is pending — never invent numbers."

# READ — code surfaces the statements must match (grep, don't full-read).
- file: voice_typing/config.py       # AudioConfig :238 (duck_mode/duck_volume_pct defaults);
  why: "config table rows must match these defaults EXACTLY; the precondition triple at :399-428
        (bulk-text requires streaming=true, graceful_stop=false, keypress_action=\"disarm\")."
- file: voice_typing/ctl.py          # session/--copy semantics (:185-190, :267, :362-430);
  why: "exit codes (0 / 1 no-session / 64 misuse), 'copied N chars', no-added-newline, clipboard
        untouched on failure — the session subsection's facts."
- file: voice_typing/feedback.py     # delivery vocab (:93-146) + ducked flag (:135);
  why: "state.json field names + the inactive|active|unsupported|fault taxonomy, verbatim."
- file: voice_typing/ime/manager.py  # :23 'user's fcitx5 is explicitly forbidden', :151 UNSUPPORTED
  why: "the seat-exclusivity troubleshooting subsection's mechanism + line-level truth."
- file: voice_typing/audio_ducking.py + systemd/voice-typing.service:59 (ExecStopPost ducking_heal)
  why: "the crash self-heal sentence; 'off' spawns no audio subprocess."
- file: plan/008_a47116bb2b79/P1M7T1S1/PRP.md
  why: "The parallel G6 task's contract — what it produces, and its explicit 'no README edits' boundary
        (no conflict with this task)."
```

### Current Codebase tree (README-relevant slice)

```bash
README.md                  # ← MODIFY (454 lines; sections: …Streaming dictation / Backspace-cancel /
                           #    Feedback surfaces / Configuration (+table) / CPU-only / Troubleshooting
                           #    (cuDNN, Wrong mic, wtype-vs-ydotool) / Logs-status / Model lifecycle)
config.toml                # ships [audio] duck_mode="mpris", duck_volume_pct=15; output.delivery="stream-edit"
voice_typing/{config,ctl,feedback,audio_ducking,ducking_*,bulk_controller,bulk_delivery,
              clipboard_target,pi_editor,session_recovery}.py, voice_typing/ime/   # landed surfaces
systemd/voice-typing.service   # ExecStopPost=… python -m voice_typing.ducking_heal (:59)
tests/D1_DUCK_EVIDENCE.md  tests/ACCEPTANCE.md  tests/G1_BASELINE.md   # evidence (ACCEPTANCE = S2's, DON'T EDIT)
plan/008_a47116bb2b79/architecture/{g3_field_matrix.md, g2_gate_record.md,
              pi_row_verdicts.jsonl, editor_browser_row_verdicts.jsonl, g4_clipboard_verdicts.jsonl}
tests/G6_GRADUATION.md     # produced by PARALLEL P1.M7.T1.S1 — the framing source (blocking if absent)
```

### Desired tree

```bash
README.md                  # modified in place — the ONLY file this task touches
# no new files; research notes already live in plan/008_a47116bb2b79/P1M7T2S1/research/
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (G-G6) — the G6 dependency. tests/G6_GRADUATION.md is produced by the PARALLEL task
#   P1.M7.T1.S1. If it is absent when implementation starts: STOP and report the blocker. Never guess
#   the verdict; never write "until G6" boilerplate that contradicts what the doc actually decided.

# CRITICAL #2 (G-NO-OVERCLAIM) — R.2's rule, enforced. Never write "works on Wayland", never upgrade a
#   matrix row, never state speech-to-visible latency numbers unless tests/G5_TIMING_EVIDENCE.md holds
#   them, never imply operator acceptance. "A passing transport probe NEVER flips any of these to
#   'passed'." Label everything pending as unverified WITH its outstanding input named.

# CRITICAL #3 (G-SCOPE) — tests/ACCEPTANCE.md is P1.M7.T2.S2's; config.py/config.toml values are
#   frozen (the G6 task owns any flip); the compute_type claim drift in "Voice-activity constants are
#   NOT config keys" is P1.M7.T2.S3's sweep. FLAG the drift in the commit message; fixing it here
#   steals S3's item and risks lockstep-test breakage.

# CRITICAL #4 (G-ANCHORS) — GitHub anchors are lowercase-hyphenated headings. New sections'
#   cross-links (e.g. #media-ducking-while-listening, #bulk-text-delivery-opt-in-experimental) must
#   match the EXACT headings; existing links to edited sections must keep resolving (L1 grep).

# CRITICAL #5 (G-MATRIX-VERBATIM) — field-class matrix rows carry VERSIONS as part of the claim
#   (foot 1.28.0-2, kitty 0.51.0-1, ghostty 1.4.0-2, Hyprland 0.57.2). Copy them; a versionless
#   "ghostty: blocked" claim is exactly the drift R.2 forbids. ghostty's status changed between the
#   PRD's 1.3.1 finding and the 1.4.0 re-run — document the CURRENT register, not the PRD's history.

# CRITICAL #6 (G-DUCK-DEFAULT) — duck_mode default is "mpris" (flipped WITH evidence, commit 22009a0).
#   Do not document it as opt-in or default-"off": the First-run surprise ("my music paused") is the
#   #1 reason this section exists. "off" is the documented escape hatch restoring pre-D1 byte-identical.

# CRITICAL #7 (G-VOICE) — match the existing README voice: absolute .venv/bin/voicectl paths, terse
#   prose, tables for knobs, journal-line excerpts in fenced blocks, every claim tied to a knob/file/
#   log line. No marketing, no "simply", no emoji.

# CRITICAL #8 (G-STATE-FIELDS) — the state.json field list must gain EXACTLY: "ducked" (bool),
#   "delivery_mode", "delivery_state", "delivery_reason", "last_confirmed_op" — names verbatim from
#   feedback.py; the taxonomy is inactive|active|unsupported|fault.
```

## Implementation Blueprint

### Content blocks to pin into the README (facts locked; prose in the existing voice)

**Block A — §First run addition (1 sentence + link):**
> Arming also pauses any playing MPRIS media (music/video) and your stop resumes it — media ducking
> is on by default; see [Media ducking while listening](#…) or set `duck_mode = "off"`.

**Block B — §Upgrading from Rev 1:** six → seven commands; `session` recovers the last completed
dictation (link to the bulk section's recovery subsection — note recovery works in BOTH delivery modes).

**Block C — `## Media ducking while listening` (pinned facts):**
- What: at arm, every MPRIS player in `Playing` state pauses (~100 ms after the arm returns); at every
  disarm path (stop/toggle-off, 30 s auto-stop, keypress HALT, quit — NOT Backspace-cancel) they resume.
- Sovereignty (the contract, three conditions): resume only players (a) WE paused, (b) that were
  Playing before we paused, (c) still Paused now — a player you resumed or paused yourself mid-dictation
  is never fought.
- Volume tier: `duck_mode = "volume"` ducks the default sink to `duck_volume_pct` (15) at arm; restore
  is compare-before-restore — a manual mid-dictation volume change always wins.
- `duck_mode = "off"`: byte-identical to pre-ducking behavior; no audio subprocess is ever spawned.
- Crash safety: `state.json` carries `ducked`; a daemon restart self-heals (best-effort release), and
  the systemd unit runs `ExecStopPost=… python -m voice_typing.ducking_heal`.
- Journal lines (fenced block, verbatim from tests/D1_DUCK_EVIDENCE.md — the five `ducking:` lines).
- Evidence pointer: scripted 12/12 scenarios, `tests/D1_DUCK_EVIDENCE.md` (re-runnable:
  `timeout 900 bash tests/d1_duck_evidence.sh`).

**Block D — `## Bulk text delivery (opt-in, experimental)`:**
- Framing header (G6-derived; STAY OPT-IN expected): opt-in via `output.delivery = "bulk-text"`;
  **unverified until G6** — link `tests/G6_GRADUATION.md`; name the outstanding input (operator writing
  sessions, `tests/G6_WRITING_SESSIONS.md`). Never claim speech-latency or live-desktop coverage; G5
  evidence: cite `tests/G5_TIMING_EVIDENCE.md` if present, else "pending".
- Precondition triple (load-time ValueError listing all violations): `output.streaming = true`,
  `asr.graceful_stop = false`, `cancel.keypress_action = "disarm"`.
- Model: words appear in the focused field as recognition updates arrive; a correction is ONE visible
  edit over the tool's owned range; an unchanged update emits zero edits; **no typing/backspace
  fallback ever** (the stream-edit path is unchanged and remains the default).
- Status: `voicectl status` adds `delivery: bulk-text (active|inactive|unsupported|fault)` plus
  `delivery reason:` / `delivery op:` lines when non-empty; same fields in `state.json`.
- Routes + field-class matrix (table, verbatim versions from g3_field_matrix.md + the browser limit):
  | field | status |
  |---|---|
  | GTK-class editors/fields | full (insert + atomic correction) — G3 verified |
  | pi chat prompt (extension seam) | full — verified at pi 1.0.2 in isolated Ghostty 1.4.0-arch2 / sway 1.12 |
  | browser text field (chromium-class) | insert verified; correction REFUSED (caret guard cannot confirm ownership) |
  | foot 1.28.0-2 / kitty 0.51.0-1 | insert-only |
  | ghostty 1.4.0-2 | IM route blocked → clipboard insert fallback |
  | Hyprland relay 0.57.2 | untested on the live desktop (lab boot fails) — treat as unverified |
- Clipboard fallback contract (short here, details in troubleshooting): engages only for
  ghostty-class terminals; refuses while a clipboard-history watcher is active (unprovable ⇒ refuse);
  preserves all prior formats; PRIMARY selection untouched.
- `voicectl session [--copy]`: prints the most recent COMPLETED dictation session exactly (works in
  both delivery modes); `--copy` stages it to the Wayland clipboard with no added newline and prints
  `copied N chars`; exit 1 (clipboard untouched) when none exists; `--copy` only valid with `session`
  (usage error 64); truncation reported on stderr. Recovery memory: last nonempty arm→disarm session,
  ≤ 2 sessions × 1 MiB, cleared at daemon exit.
- Takeover semantics (one paragraph): any real key/click/focus change stops delivery immediately, no
  retries, tail stays; `voicectl cancel` in bulk mode performs no physical backspace compensation.

**Block E — config table rows (format `| \`key\` | \`default\` | description |`):**
```
| `audio.duck_mode` | `"mpris"` | `"mpris"` = pause playing MPRIS players at arm, resume-at-stop only what we paused and only if still paused; `"volume"` = duck default sink to `duck_volume_pct`; `"off"` = pre-ducking behavior, no audio subprocess. |
| `audio.duck_volume_pct` | `15` | target sink volume % for the `"volume"` tier. Restore is compare-before-restore — a manual mid-dictation change wins. |
| `output.delivery` | `"stream-edit"` | `"bulk-text"` = opt-in bulk delivery (see §…; unverified until G6 — `tests/G6_GRADUATION.md`). Requires `output.streaming=true`, `asr.graceful_stop=false`, `cancel.keypress_action="disarm"` — the loader rejects other combos with a single ValueError naming all violations. |
```
Place `audio.*` as a new group mirroring config.toml's section order; `output.delivery` directly after
the `output.streaming` row.

**Block F — troubleshooting ×3:**
1. `### Bulk delivery: the input-method seat is taken (fcitx5/ibus)` — Wayland allows ONE input-method
   client per seat; a running IME (fcitx5/ibus) holds it → `voicectl status` shows
   `delivery: bulk-text (unsupported)` with the reason. Fix: stop the IME for bulk sessions or stay on
   `stream-edit` (unaffected). Compositor must also advertise `zwp_input_method_manager_v2`.
2. `### Bulk delivery: what my terminal supports` — the matrix table from Block D, plus: ghostty-class
   → clipboard fallback (and its watcher refusal); correction-refusal at chromium explained as the
   ownership guard working as designed (it keeps the committed text rather than risk an unverified edit).
3. `### Bulk delivery: the clipboard fallback contract` — engages only for ghostty-class insert;
   refuses while a clipboard-history watcher is active (partials-out-of-history is unprovable → the
   adapter declines rather than risk pollution — G4 L1 records this as the honest outcome); preserves
   every original format byte-exactly; PRIMARY selection untouched; evidence
   `plan/008_a47116bb2b79/architecture/g4_clipboard_verdicts.jsonl`.

**Block G — §Feedback surfaces:** extend the state.json field list with `ducked` + the four delivery
fields (names verbatim, one-line meaning each — from feedback.py).

**Block H — §Logs, status sample:** append to the sample output:
```
delivery: stream-edit (inactive)
```
(+ a sentence: in bulk mode the state is active/unsupported/fault and reason/op lines appear when set).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT (read-only):
  - RUN: grep -c '^## ' README.md; grep -n 'G6 DECISION' tests/G6_GRADUATION.md || echo BLOCKED
  - EXPECT: G6 decision line present (else STOP — G-G6); note tests/G5_TIMING_EVIDENCE.md presence.
  - DO NOT edit anything yet.

Task 1: MODIFY README.md — Blocks A+B (small touches), then C (ducking section).
  - INSERT C after '### Backspace-cancel…' body, before '## Feedback surfaces'.
  - VERIFY journal lines + sovereignty wording against tests/D1_DUCK_EVIDENCE.md while writing.

Task 2: MODIFY README.md — Block D (bulk section) AFTER the ducking section.
  - Derive the framing line from the G6 decision FIRST; pin the matrix table verbatim (versions!).
  - Cross-link the troubleshooting subsections instead of duplicating the matrix.

Task 3: MODIFY README.md — Blocks E–H (config rows, feedback fields, troubleshooting ×3, status sample).
  - Config rows must textually match config.py defaults (duck_mode "mpris", duck_volume_pct 15,
    delivery "stream-edit").

Task 4: VALIDATE — run the Validation Loop L1–L4; fix until green. Commit message FLAGS the
  pre-existing compute_type drift (S3's scope). If asked to commit:
  "P1.M7.T2.S1: README — media ducking + bulk-text delivery sections, config rows, troubleshooting".
```

### Integration Points

```yaml
CONSUMED (read-only): tests/G6_GRADUATION.md (framing), tests/D1_DUCK_EVIDENCE.md (ducking claims),
  plan/008…/architecture/{g3_field_matrix,pi_row_verdicts,editor_browser_row_verdicts,
  g4_clipboard_verdicts}* (matrix + routes), tests/G5_TIMING_EVIDENCE.md (IF present),
  voice_typing/{config,ctl,feedback,ime/manager,audio_ducking}.py (surfaces), systemd unit :59.
PRODUCED: README.md only. NO config/PRD/tasks.json/ACCEPTANCE.md/source changes (G-SCOPE).
DOWNSTREAM: P1.M7.T2.S2 (ACCEPTANCE rows) + S3 (consistency sweep) build on this README state.
```

## Validation Loop

> All commands from the repo root, wrapped per the repo timeout discipline (doc task: everything is
> fast, but keep the wrappers). No ruff/mypy for markdown — gates are structural greps + a
> config-defaults cross-check + the prose audit.

### Level 1: Structure & anchors

```bash
cd /home/dustin/projects/voice-typing
timeout 60 bash -c '
grep -c "^## Media ducking while listening" README.md            # expect 1
grep -c "^## Bulk text delivery" README.md                        # expect 1
grep -c "^### Bulk delivery:" README.md                           # expect 3
grep -c "audio.duck_mode\|audio.duck_volume_pct\|output.delivery" README.md   # expect >=3
# anchors resolve: every new heading has its lowercase-hyphen form used in links
python3 - <<PY
import re
t=open("README.md").read()
heads={re.sub(r"[^a-z0-9 -]","",h.lower()).strip().replace(" ","-") for h in re.findall(r"^#{2,3} (.+)$",t,re.M)}
links=re.findall(r"\]\(#([^)]+)\)",t)
missing=[l for l in links if l not in heads]
assert not missing, f"broken anchors: {missing}"
print("L1 anchors OK")
PY
'
```

### Level 2: Claim verification (every pinned fact traces to source)

```bash
cd /home/dustin/projects/voice-typing
timeout 60 bash -c '
# config table rows match config.py defaults EXACTLY:
python3 - <<PY
import re, sys
sys.path.insert(0, ".")
from voice_typing.config import AudioConfig, OutputConfig
a, o = AudioConfig(), OutputConfig()
t = open("README.md").read()
assert f"| `audio.duck_mode` | `\"{a.duck_mode}\"` |" in t, "audio.duck_mode row/default mismatch"
assert f"| `audio.duck_volume_pct` | `{a.duck_volume_pct}` |" in t, "duck_volume_pct mismatch"
assert f"| `output.delivery` | `\"{o.delivery}\"` |" in t, "output.delivery mismatch"
print("L2 config rows match config.py")
PY
# sovereignty + journal lines cite/echo the evidence file:
grep -q "D1_DUCK_EVIDENCE" README.md || { echo "FAIL: ducking evidence not cited"; exit 1; }
for s in "ducking: paused MPRIS" "ducking: restored sink volume" "keeping user value"; do
  grep -q "$s" README.md || { echo "FAIL: journal line missing: $s"; exit 1; }
done
# matrix versions verbatim:
for v in "1.28.0-2" "0.51.0-1" "1.4.0-2"; do grep -q "$v" README.md || { echo "FAIL: matrix version $v missing"; exit 1; }; done
# session semantics + precondition triple present:
grep -q "copied N chars" README.md || { echo "FAIL: session --copy semantics missing"; exit 1; }
grep -q 'keypress_action = "disarm"' README.md || { echo "FAIL: precondition triple missing"; exit 1; }
echo "L2 claims verified"
'
```

### Level 3: G6 framing + delivery-state consistency

```bash
cd /home/dustin/projects/voice-typing
timeout 60 bash -c '
dec=$(grep -o "G6 DECISION: .*" tests/G6_GRADUATION.md | head -1)
echo "G6 doc says: $dec"
case "$dec" in
  *STAY\ OPT-IN*)
    grep -q "G6_GRADUATION.md" README.md && grep -qi "unverified" README.md \
      || { echo "FAIL: stay-opt-in framing not present"; exit 1; }
    ! grep -q "delivery\` | \`\"bulk-text\"\`" README.md || { echo "FAIL: default documented as bulk-text"; exit 1; } ;;
  *FLIP*)
    grep -q "bulk-text" README.md && grep -q "G6_GRADUATION.md" README.md \
      || { echo "FAIL: flip framing incomplete"; exit 1; } ;;
  *) echo "BLOCKED: unreadable G6 decision"; exit 1 ;;
esac
# delivery taxonomy verbatim:
for st in inactive active unsupported fault; do grep -q "$st" README.md || { echo "FAIL: state $st missing"; exit 1; }; done
echo "L3 G6 framing + taxonomy OK"
'
```

### Level 4: No-over-claim prose audit + scope

```bash
cd /home/dustin/projects/voice-typing
timeout 60 bash -c '
! grep -qiE "works on wayland|production-ready|fully verified|bulletproof" README.md || { echo "FAIL: over-claim phrase"; exit 1; }
# latency numbers only if G5 file exists AND is cited:
if grep -qE "[0-9]+ ?ms" README.md; then grep -q "G5_TIMING_EVIDENCE" README.md || { echo "FAIL: ms numbers without G5 citation"; exit 1; }; fi
# scope: README only
[ "$(git diff --name-only | grep -v "^plan/" | wc -l)" = "1" ] && git diff --name-only | grep -q "^README.md$" \
  || { echo "FAIL: out-of-scope edits"; git diff --name-only; exit 1; }
echo "L4 prose audit + scope OK"
'
```

## Final Validation Checklist

### Technical
- [ ] L1 anchors/sections; L2 facts trace (config defaults, journal lines, matrix versions, exit codes).
- [ ] L3 G6 framing matches the decision line; delivery taxonomy verbatim.
- [ ] L4 no over-claim phrases; ms-numbers only with G5 citation; `git diff` = README.md only.

### Feature
- [ ] Ducking section: default `mpris` + sovereignty (3 conditions) + `off` hatch + crash self-heal + journal lines + evidence path.
- [ ] Bulk section: opt-in flag + triple + states + matrix (versions) + session recovery + unverified-until-G6 framing.
- [ ] Config rows for `[audio]` + `output.delivery`; state.json fields documented; status sample updated.

### Code Quality (doc equivalents)
- [ ] Existing README voice/paths/table format matched; no restructuring of existing sections.
- [ ] Cross-links use valid anchors; sections cross-reference instead of duplicating.
- [ ] Pre-existing compute_type drift FLAGGED in the commit message, not fixed (S3's scope).

## Anti-Patterns to Avoid

- ❌ Don't guess the G6 verdict — read `tests/G6_GRADUATION.md`; absent file = blocked, not improvised.
- ❌ Don't over-claim: no "works on Wayland", no latency numbers without the G5 file, no upgrading a
  matrix row or softening the browser-correction refusal.
- ❌ Don't document aspirational behavior — only what the code + evidence registers show TODAY.
- ❌ Don't edit ACCEPTANCE.md (S2), config values (G6 task owns the flip), source files, or PRD/tasks.json.
- ❌ Don't fix the pre-existing compute_type/other drift — flag it; S3 owns the sweep.
- ❌ Don't strip versions from matrix claims, and don't "improve" the sovereignty conditions' wording.
- ❌ Don't restructure existing sections or rewrite the README's voice — additive delta only.

---

## Confidence Score

**8/10.** Every fact is pinned to a line-cited source (config.py defaults, ctl.py exit codes,
feedback.py vocab, ime/manager.py exclusivity, verbatim journal lines and matrix versions from the
committed registers), the framing dependency is made mechanical (L3 derives it from the G6 doc's
decision line, blocking on absence), and the validation loop greps the exact strings the Blueprint
pins — so "done" is checkable, not vibes. The −2: (1) the parallel G6 task may land after this PRP is
handed off — mitigated by the blocking gate, but a late verdict forces a re-read/re-frame pass; (2)
prose quality in the existing README's voice is judged, not mechanically gated — mitigated by pinned
content blocks + the Block-level voice rules (G-VOICE/G-ANCHORS) and by L4's phrase audit.
