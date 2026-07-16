# PRP — P1.M2.T2.S1: README.md lite-mode sections + tests/ACCEPTANCE.md T7 cross-check

## Goal

**Feature Goal**: Complete the cross-cutting documentation sweep for lite mode (PRD §4.2ter) so `README.md` and `tests/ACCEPTANCE.md` accurately reflect the implemented feature with **zero drift**. The per-file Mode-A doc edits (P1.M1.*, Complete) already landed most of the lite docs (config-table `lite_model` row, the Hotkey section's both-binds explanation, the `mode:` status line). This task adds the **two missing pieces** — a discoverable "Lite mode" subsection (b) and a lite note in Model-lifecycle (d) — and cross-checks `ACCEPTANCE.md` by adding the lite-mode acceptance #10 row (+ #9 for table contiguity) and fixing the self-contradictions that creates.

**Deliverable** (markdown edits to 2 files; no source, no tests, no new files):
1. `README.md` — (R1) add a `## Lite mode` subsection after the Hotkey section; (R2) add a lite sentence to "### Model lifecycle & VRAM".
2. `tests/ACCEPTANCE.md` — (A1) intro `1–8`→`1–10`; (A2) regenerate list `5 / 6 / 8`→`5 / 6 / 8 / 9 / 10`; (A3) add criteria rows #9 (idle-unload) + #10 (lite); (A4) evidence header `5, 6, 8, 9`→`5, 6, 8, 9, 10`; (A5, secondary) fix #7's stale task reference.

**Success Definition**:
- (a) README has a dedicated `## Lite mode` subsection (what it is, `toggle-lite`/`start-lite`/SUPER+ALT+F, ~half VRAM + faster finals + lower accuracy, one-reload switch cost, shared drain/auto-stop/idle-unload, `mode:`/`state.json`/⚡ visibility).
- (b) README "Model lifecycle & VRAM" notes lite uses ~half VRAM + idle-unload tears down either mode.
- (c) ACCEPTANCE.md criteria table is contiguous 1–10 with a #10 lite row whose text matches PRD §7 #10 + the verified behavior; #9 (idle-unload) row added (evidence = existing T6(d-gone) block).
- (d) ACCEPTANCE.md's intro/evidence-header "1–8"/"5, 6, 8, 9" claims are updated to include 9/10 (no self-contradiction).
- (e) No drift: every lite fact stated matches the verified implemented behavior (config key `asr.lite_model`, commands `toggle-lite`/`start-lite`, keybind SUPER+ALT+F, `mode` in `state.json`, `mode:` status line, ⚡ prefix, one-reload switch).
- (f) No out-of-scope files: no source (`daemon.py`/`ctl.py`/`feedback.py`/`config.py`/`status.sh`/`hypr-binds.conf`), no test files (`test_feed_audio.py`/`test_idle_and_gpu.sh` are P1.M2.T1.S1, parallel), no `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`/`pyproject.toml`/`uv.lock`. DOCS: this IS the documentation task (Mode B).

## User Persona

**Target User**: dustin (six months from now) / a cloner — the README's stated audience. They need to discover that lite mode exists, when to use it, how to arm it, and its tradeoffs, without reading source.

**Use Case**: The user wants to dictate a short snippet (URL, shell command) where the big model's latency isn't worth it; they consult the README to find the fast mode.

**Pain Points Addressed**: today the lite-mode explanation is buried inside the Hotkey section (bind-contextual), with no discoverable "Lite mode" section, and the Model-lifecycle section reads as if only normal mode exists. ACCEPTANCE.md's criteria table stops at #8, so the lite acceptance criterion (#10) — the feature's definition-of-done — is undocumented.

## Why

- **Docs must not drift from shipped behavior.** The lite feature is complete (P1.M1.*); the README is ~80% there but missing the canonical discoverable section + the lifecycle note, and ACCEPTANCE.md is missing the #10 acceptance row. A maintainer reading either gets an incomplete picture. (Mode B = the cross-cutting doc task.)
- **The item explicitly flagged the concurrent-edit risk** ("RE-VERIFY what README already says about lite — a concurrent process may have started it"). Verified: the concurrent Mode-A process DID land the config-table row + Hotkey prose. This task adds only the missing cross-cutting pieces, avoiding duplication.
- **ACCEPTANCE.md #10 is the lite feature's definition-of-done** (PRD §7 #10). Without it, the acceptance doc is stale (covers 1–8 while the PRD now has 1–10). Adding it (pointing to T7, the parallel evidence task) closes the loop; P1.M2.T3.S1 flips #10 to PASS.
- **Cheap, additive, parallel-safe.** Two markdown files. The content states verified behavior (§2 of the research note — read from the code). Disjoint from the parallel T7 test task (which touches test files only).

## What

Add the two missing README pieces (Lite mode subsection + lifecycle note) and bring ACCEPTANCE.md's criteria table + intro/header in sync with PRD §7 #1–10 (add #9 + #10 rows, fix the "1–8"/"5, 6, 8, 9" claims). All content matches the verified implemented interfaces. Mark #10 "pending T7" (the evidence is the parallel test task; do not pre-claim PASS).

### Success Criteria

- [ ] README has a `## Lite mode` section (between Hotkey and tmux-status-line).
- [ ] README "Model lifecycle & VRAM" mentions lite (~half VRAM) + idle-unload applies to either mode.
- [ ] ACCEPTANCE.md criteria table has contiguous rows 1–10 (adds #9 idle-unload PASS + #10 lite pending-T7).
- [ ] ACCEPTANCE.md #10 row text matches PRD §7 #10 (toggle-lite uses only lite_model; large never loads; ~half VRAM; toggle normal; one bounded reload; status + state.json report mode; both honor drain).
- [ ] ACCEPTANCE.md intro says "criteria 1–10"; regenerate list + evidence header include 9/10.
- [ ] No drift from verified behavior (config key, commands, keybind, state field, status line, ⚡, switch cost).
- [ ] `git status --short` == `README.md` + `tests/ACCEPTANCE.md` only.

## All Needed Context

### Context Completeness Check

_Pass._ A developer new to this repo can implement it from this PRP + the research note. The decisive fact — **the README is already ~80% updated by a concurrent Mode-A process; this task adds only (b)+(d)+ACCEPTANCE #10** — is documented with a per-sub-item status table (research §1). Every lite fact the docs must state is **verified against the live source** with line numbers (research §2 — no drift). The exact content to insert is given verbatim. The **concurrent-editing caveat** (README Hotkey wording shifted between reads; re-verify anchors semantically) is documented (research §4). The parallel-task boundary (P1.M2.T1.S1 edits test files, not README/ACCEPTANCE) is documented (research §5).

### Documentation & References

```yaml
# MUST READ — what's already done, what's missing, verified behavior, concurrent-edit caveat
- docfile: plan/004_607e9cca32b7/P1M2T2S1/research/readme_lite_acceptance.md
  why: "§1 STATUS TABLE: (a) config-table lite_model + (c) Hotkey both-binds ALREADY DONE by the
        concurrent Mode-A process; (b) Lite mode subsection + (d) lifecycle note MISSING. §2 VERIFIED
        behavior (config.py:54 lite_model; ctl.py:35 toggle-lite/start-lite; feedback.py:99/145 mode+
        set_mode; daemon.py:980/1501; status.sh:40 ⚡; hypr-binds.conf SUPER+ALT+F). §3 the content to
        ADD. §4 CONCURRENT-EDIT CAVEAT (re-verify anchors). §5 parallel boundary."
  section: "ALL load-bearing. §1 (what's done), §2 (drift prevention), §4 (re-verify anchors)."

# MUST READ — the PRD lite-mode spec (the authoritative behavior the docs must match)
- docfile: plan/004_607e9cca32b7/prd_snapshot.md   # (or PRD.md §4.2ter / §4.5 / §4.10 / §7)
  why: "§4.2ter is the lite-mode spec (single lite_model for partials+finals; large never loads;
        toggle-lite/start-lite; SUPER+ALT+F; one-reload switch; mode in state.json/status; ⚡ prefix;
        both modes share drain/auto-stop/idle-unload). §4.5 config (lite_model default small.en).
        §4.10 hypr-binds (SUPER+ALT+F). §7 acceptance #10 (the lite definition-of-done text)."
  critical: "Match §4.2ter + §7 #10 EXACTLY in the docs. The verified code facts (research §2) confirm
             the implementation matches the PRD — so the docs can state the PRD behavior as-is."

# MUST READ — the file being edited (current README — what's already there, anchor locations)
- file: README.md
  why: "The config table HAS the asr.lite_model row (✅ done). The '## Hotkey (Hyprland)' section HAS
        both binds + lite prose (✅ done). The status example HAS 'mode: normal'. MISSING: a '## Lite
        mode' section (insert after Hotkey, before '## tmux status line') + a lite sentence in
        '### Model lifecycle & VRAM' (after 'so later arms are instant.')."
  critical: "README is under CONCURRENT Mode-A editing — re-verify each anchor against the LIVE file
             before applying (research §4). Insert CONTENT is stable; anchor whitespace/wording may drift."

# MUST READ — the file being edited (ACCEPTANCE.md — stale 1–8 table)
- file: tests/ACCEPTANCE.md
  why: "The criteria table has rows 1–8 ONLY (PRD §7 now has 1–10). The evidence block already references
        'criteria 5, 6, 8, 9' (so #9 evidence exists but its table row is missing). Add #9 (idle-unload,
        PASS — evidence = existing T6(d-gone) block) + #10 (lite, pending T7). Fix the intro 'criteria
        1–8' + '5 / 6 / 8' + evidence-header '5, 6, 8, 9' to include 9/10."
  critical: "Mark #10 'pending T7' (the evidence is the PARALLEL task P1.M2.T1.S1 — do NOT pre-claim PASS;
             P1.M2.T3.S1 flips it). #9 is genuinely PASS (T6(d-gone) already passes). Do NOT touch the
             evidence BLOCK contents (regenerated by test_idle_and_gpu.sh)."

# MUST READ — the parallel task contract (DISJOINT files — no conflict)
- docfile: plan/004_607e9cca32b7/P1M2T1S1/PRP.md
  why: "P1.M2.T1.S1 (T7) edits tests/test_feed_audio.py (lite tests) + tests/test_idle_and_gpu.sh (T7
        section). It does NOT touch README.md or ACCEPTANCE.md. Your #10 row POINTS TO T7 as its evidence
        source. Disjoint — no merge conflict."
  critical: "Do NOT edit test_feed_audio.py or test_idle_and_gpu.sh (P1.M2.T1.S1 owns them). Your #10
             ACCEPTANCE row references them by command name only."
```

### Current Codebase tree (relevant slice — the 2 files this task edits)

```bash
/home/dustin/projects/voice-typing/
├── README.md               # EDIT (R1: +## Lite mode; R2: +lifecycle lite note).
└── tests/
    └── ACCEPTANCE.md       # EDIT (A1-A5: +criteria #9/#10, fix 1-8/5,6,8,9 claims, #7 stale ref).
# Source files (config.py/ctl.py/feedback.py/daemon.py/status.sh/hypr-binds.conf) + test files
# (test_feed_audio.py/test_idle_and_gpu.sh) — UNCHANGED. The lite feature is implemented (P1.M1.*).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE README IS ALREADY ~80% DONE (concurrent Mode-A process). The config-table
#   asr.lite_model row AND the Hotkey section's both-binds + lite prose are ALREADY PRESENT. Do NOT
#   re-add them (duplication). This task adds ONLY: (b) a '## Lite mode' subsection + (d) a lifecycle
#   lite note. Verify each before editing (research §1 status table).
# CRITICAL #2 — README IS UNDER CONCURRENT EDITING. The Hotkey wording shifted between two reads
#   ("If SUPER+ALT+D/F is inert…" -> "If a bind is inert…"). So the oldText anchors in this PRP are a
#   SNAPSHOT. RE-READ the live README and locate each anchor SEMANTICALLY before applying. The CONTENT
#   to insert is stable (verified behavior); only surrounding anchor text may drift. (Research §4.)
# CRITICAL #3 — NO DRIFT: state every lite fact from the VERIFIED code, not memory. config key is
#   asr.lite_model (NOT lite-model); commands are toggle-lite/start-lite; keybind SUPER+ALT+F -> toggle-lite;
#   state.json HAS a "mode" field (feedback.py:99); status renders "mode:"; tmux ⚡ in lite; switch = one
#   ~1-3s reload. (Research §2.) Do NOT invent a config key / command / field that the code doesn't have.
# CRITICAL #4 — ACCEPTANCE #10 IS "pending T7", NOT "PASS". The evidence (T7) is the PARALLEL task
#   P1.M2.T1.S1 (not yet landed). Marking #10 PASS now would be a false claim. P1.M2.T3.S1 flips it to
#   PASS after running T7. #9 (idle-unload) IS genuinely PASS (T6(d-gone) already passes). (Research §3.3.)
# CRITICAL #5 — ADD #9 AND #10 (not just #10). The criteria table currently ends at #8; the evidence
#   block already references criterion 9. Adding #10 alone leaves an 8->10 gap (looks like a typo). #9's
#   evidence is the existing T6(d-gone) block. (Research §3.3.)
# CRITICAL #6 — FIX THE SELF-CONTRADICTIONS the #10 addition creates: intro "criteria 1-8" -> "1-10";
#   "Regenerate the 5 / 6 / 8 block" -> "5 / 6 / 8 / 9 / 10"; evidence header "criteria 5, 6, 8, 9" ->
#   "5, 6, 8, 9, 10". Otherwise the doc contradicts itself. (Research §3.3.)
# CRITICAL #7 — DO NOT TOUCH SOURCE OR TEST FILES. config.py/ctl.py/feedback.py/daemon.py/status.sh/
#   hypr-binds.conf are the implemented feature (P1.M1.*, done). test_feed_audio.py/test_idle_and_gpu.sh
#   are P1.M2.T1.S1 (parallel). This task = README.md + tests/ACCEPTANCE.md ONLY.
# CRITICAL #8 — DOCS TASK: no pytest gate (no code changes). Validation = edits apply to the live file +
#   markdown well-formed + no drift (§2). The fast suite is unaffected (run only to confirm no accidental
#   edit touched a test). .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q.
```

## Implementation Blueprint

### Data models and structure

None (documentation only). The two artifacts are markdown files. The "data" is the verified lite-mode behavior (research §2), restated accurately in prose.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT README.md — add '## Lite mode' subsection (Edit R1)
  - INSERT: a '## Lite mode' section AFTER '## Hotkey (Hyprland)' (BEFORE '## tmux status line').
  - CONTENT: verbatim in Edit R1 below (what/how/tradeoff/switch-cost/shared/visibility + cross-links).
  - ANCHOR (snapshot — RE-VERIFY live): the paragraph ending '…or rebind to a free combo in `hypr-binds.conf`.'
    followed by a blank line + '## tmux status line'. Insert the new section between them.
  - Do NOT duplicate the Hotkey section's bind prose (cross-link it instead).

Task 2: EDIT README.md — Model lifecycle lite note (Edit R2)
  - INSERT: one sentence in '### Model lifecycle & VRAM' after '…so later arms are instant.'
    (lite ~half VRAM; idle-unload tears down either mode; next arm reloads in requested mode).
  - ANCHOR (snapshot — RE-VERIFY): 'first arm the recorder stays **resident** (~1.5-3 GB VRAM) so later
    arms are\ninstant. It is torn down on' — insert the lite sentence between 'instant.' and 'It is torn down'.

Task 3: EDIT tests/ACCEPTANCE.md — add criteria #9 + #10 rows (Edit A3)
  - INSERT: two table rows after the #8 row, BEFORE '### Evidence block — criteria 5, 6, 8, 9 …'.
  - #9 idle-unload: status PASS (evidence = existing T6(d-gone) block). #10 lite: status 'pending T7'
    (evidence = test_feed_audio.py lite tests + test_idle_and_gpu.sh T7 section; P1.M2.T3.S1 flips to PASS).
  - CONTENT: verbatim in Edit A3 below.

Task 4: EDIT tests/ACCEPTANCE.md — fix the self-contradictions (Edits A1, A2, A4)
  - A1: intro 'criteria 1–8' -> 'criteria 1–10'.
  - A2: 'Regenerate the **5 / 6 / 8** block' -> '**5 / 6 / 8 / 9 / 10**'.
  - A4: evidence header 'criteria 5, 6, 8, 9' -> '5, 6, 8, 9, 10'.

Task 5 (secondary): EDIT tests/ACCEPTANCE.md — fix #7 stale task reference (Edit A5)
  - The #7 row says 'the README is task **P2.M1.T2.S1** (pending)' — stale (the README exists; that task
    name is from an old plan). Update to: README complete (lite via P1.M2.T2.S1); only the commit
    (P1.M2.T3.S1) is pending. Low-risk accuracy fix.
```

### Edits — verbatim content + anchors (RE-VERIFY anchors live — Critical #2)

#### Edit R1 — `README.md` new `## Lite mode` section

Insert between the end of the Hotkey section and `## tmux status line`. **Anchor (snapshot)**: the line `or rebind to a free combo in \`hypr-binds.conf\`.` then a blank line then `## tmux status line`.

`oldText` (snapshot — re-verify):
```
or rebind to a free combo in `hypr-binds.conf`.

## tmux status line
```
`newText`:
```
or rebind to a free combo in `hypr-binds.conf`.

## Lite mode

A second arming mode for short, speed-critical snippets (URLs, shell commands, quick
replies) where latency matters more than accuracy. Lite mode loads **only** `asr.lite_model`
(default `small.en`) and uses it for both live partials AND finals — the large
`distil-large-v3` never loads — so it takes ~half the VRAM and produces markedly faster
finals, at lower accuracy. Arm it with `voicectl toggle-lite` / `start-lite`, or the
**SUPER+ALT+F** keybind (`voicectl stop` disarms either mode). Arming the *other* mode while
one is resident tears the recorder down and respawns it (~1–3 s reload, same as a cold first
arm) — so switching modes costs one reload. Both modes share the graceful drain on stop
(§4.2 #2), the 30 s auto-stop, and idle-unload. The armed mode shows in `voicectl status`
(`mode:`), `state.json` (`mode`), and the tmux status line (a `⚡` prefix in lite). See
[Hotkey](#hotkey-hyprland) for the binds and [Model lifecycle & VRAM](#model-lifecycle--vram).

## tmux status line
```

#### Edit R2 — `README.md` Model lifecycle lite note

**Anchor (snapshot — re-verify)**: the sentence `…so later arms are\ninstant. It is torn down on`.

`oldText` (snapshot — re-verify):
```
first arm the recorder stays **resident** (~1.5-3 GB VRAM) so later arms are
instant. It is torn down on `quit`/shutdown AND after
```
`newText`:
```
first arm the recorder stays **resident** (~1.5-3 GB VRAM) so later arms are
instant. In **lite mode** the resident set is just `small.en` (~half the VRAM of normal);
idle-unload tears down whichever mode is resident, and the next arm reloads in whatever mode
that arm requests. It is torn down on `quit`/shutdown AND after
```

#### Edit A1 — `tests/ACCEPTANCE.md` intro `1–8` → `1–10`

`oldText`: `This document records the verified evidence for PRD §7 criteria 1–8. It is the human-readable`
`newText`: `This document records the verified evidence for PRD §7 criteria 1–10. It is the human-readable`

#### Edit A2 — `tests/ACCEPTANCE.md` regenerate list

`oldText`: `Regenerate the **5 / 6 / 8** block by running \`./tests/test_idle_and_gpu.sh\` and pasting its`
`newText`: `Regenerate the **5 / 6 / 8 / 9 / 10** block by running \`./tests/test_idle_and_gpu.sh\` and pasting its`

#### Edit A3 — `tests/ACCEPTANCE.md` add criteria rows #9 + #10

Insert the two rows immediately after the `| 8 | …` row and BEFORE the `### Evidence block` header.

`oldText` (snapshot — re-verify the #8 row tail + the header):
```
| 8 | No network access needed at runtime (models cached by install) | **PASS (this task — direct evidence)** | `./tests/test_idle_and_gpu.sh` — the test launches the daemon via the **production path** (`launch_daemon.sh`, no pre-set env) and asserts the daemon log has ZERO `HTTP Request: GET https://huggingface.co` lines, a non-circular proof that the deployed unit is offline (the offline vars come from the wrapper, not from the test). (Block below.) |

### Evidence block — criteria 5, 6, 8, 9 (verbatim from a passing `./tests/test_idle_and_gpu.sh`)
```
`newText`:
```
| 8 | No network access needed at runtime (models cached by install) | **PASS (this task — direct evidence)** | `./tests/test_idle_and_gpu.sh` — the test launches the daemon via the **production path** (`launch_daemon.sh`, no pre-set env) and asserts the daemon log has ZERO `HTTP Request: GET https://huggingface.co` lines, a non-circular proof that the deployed unit is offline (the offline vars come from the wrapper, not from the test). (Block below.) |
| 9 | After `auto_unload_idle_seconds` of disarmed idle, the recorder unloads (~0 VRAM via `nvidia-smi`) and a later arm reloads; teardown is bounded (seconds, no 90 s hang) | **PASS** | `./tests/test_idle_and_gpu.sh` — T6(d): daemon tree ABSENT after idle-unload (`total=0`), then PRESENT again after a re-arm reload. Bounded teardown via the recorder-host child process-group SIGKILL (P1.M3.T2.S2 re-plan). (Block below.) |
| 10 | **Lite mode (§4.2ter):** `toggle-lite` arms in lite using ONLY `lite_model` (large model never loads — ~half the VRAM on `nvidia-smi`); `toggle` arms normal; switching costs one bounded reload; `status` + `state.json` report `mode`; both modes honor the graceful drain | pending T7 | `uv run pytest tests/test_feed_audio.py -v` (lite tests: one-model `use_main_model_for_realtime`, accuracy ≥70%, lite latency < normal) + `./tests/test_idle_and_gpu.sh` T7 section (`toggle-lite`→`mode: lite`, `toggle`→reload→`mode: normal`, optional lite VRAM < normal). T7 is task **P1.M2.T1.S1** (parallel); **P1.M2.T3.S1** flips this to PASS. |

### Evidence block — criteria 5, 6, 8, 9, 10 (verbatim from a passing `./tests/test_idle_and_gpu.sh`)
```
> Edit A3 also performs Edit A4 (the evidence-header `5, 6, 8, 9` → `5, 6, 8, 9, 10`) in the same oldText/newText, since they are adjacent. If applying A3 and A4 as separate edits, ensure the header line is updated exactly once.

#### Edit A5 (secondary) — `tests/ACCEPTANCE.md` #7 stale task reference

`oldText` (snapshot — re-verify): `| 7 | Everything committed to git; README documents: install, hotkey snippet, tmux status snippet, config tuning table, troubleshooting (cuDNN libs, PyAudio device, wtype vs ydotool), and how to switch to CPU-only mode. | partial | \`git status\` — implementation committed on \`main\`; the README is task **P2.M1.T2.S1** (pending), which will document install, the hotkey snippet, the tmux status snippet, the config tuning table, troubleshooting (cuDNN libs, PyAudio device, wtype vs ydotool), and CPU-only mode. |`

`newText`:
`| 7 | Everything committed to git; README documents: install, hotkey snippet, tmux status snippet, config tuning table, troubleshooting (cuDNN libs, PyAudio device, wtype vs ydotool), and how to switch to CPU-only mode | partial | \`git status\` — README is complete (install, hotkey+lite binds, tmux, config table incl. \`lite_model\`, troubleshooting, CPU-only mode, lite-mode section + lifecycle note via **P1.M2.T2.S1**); the implementation + these doc edits are committed to \`main\` by **P1.M2.T3.S1**. |`

> **If the #7 row's oldText has drifted** (concurrent edit), apply this semantically: replace the stale "the README is task **P2.M1.T2.S1** (pending), which will document …" clause with "README is complete (… incl. lite-mode via **P1.M2.T2.S1**); committed by **P1.M2.T3.S1**." Keep the criterion text + the `partial` status (the commit is still pending P1.M2.T3.S1).

### Implementation Patterns & Key Details

```markdown
<!-- (1) The Lite mode section is the CANONICAL discoverable explanation; Hotkey stays bind-focused. -->
## Lite mode
... what it is / how to arm / tradeoff / switch cost / shared behavior / visibility ...
See [Hotkey](...) and [Model lifecycle & VRAM](...).   <!-- cross-link, don't duplicate -->

<!-- (2) Model lifecycle gets ONE additive lite sentence (don't rewrite the section). -->
... resident (~1.5-3 GB VRAM) so later arms are instant. In **lite mode** the resident set is
just `small.en` (~half the VRAM of normal); idle-unload tears down whichever mode is resident ...

<!-- (3) ACCEPTANCE #10 states the PRD §7 #10 contract + points to T7 (parallel) as evidence;
         status "pending T7" (NOT PASS) — P1.M2.T3.S1 flips it. -->
| 10 | Lite mode (§4.2ter): toggle-lite arms in lite using ONLY lite_model ... | pending T7 | ... |
```

### Integration Points

```yaml
README.md:
  - add section: "## Lite mode (after Hotkey) — canonical lite explanation + cross-links"
  - augment: "### Model lifecycle & VRAM — one lite sentence (~half VRAM; idle-unload either mode)"
ACCEPTANCE.md:
  - add rows: "criteria #9 (idle-unload, PASS) + #10 (lite, pending T7) — contiguous 1-10 table"
  - fix claims: "intro 1-8 -> 1-10; regenerate list + evidence header include 9/10"
  - fix stale: "#7 row P2.M1.T2.S1 -> README complete (lite via P1.M2.T2.S1); commit pending P1.M2.T3.S1"
CONSUMERS:
  - P1.M2.T3.S1 (final verify): "runs T7, flips ACCEPTANCE #10 to PASS, then git commits README + ACCEPTANCE"
  - the human reader: "discovers lite mode in the README; sees the lite acceptance criterion in ACCEPTANCE"
```

## Validation Loop

### Level 1: Syntax & Style (markdown well-formedness)

```bash
cd /home/dustin/projects/voice-typing
# Confirm the new README section + table rows render (no broken markdown):
grep -n "^## Lite mode\|asr.lite_model\|toggle-lite\|⚡" README.md            # the Lite section + existing refs
grep -n "^| 9 \|^| 10 \|pending T7\|criteria 1–10\|5 / 6 / 8 / 9 / 10" tests/ACCEPTANCE.md   # the new rows + fixed claims
# Optional markdown lint (if available):
#   (no project markdown linter configured; visual check that headings/tables are well-formed)
```

### Level 2: Drift Check (no code, but verify docs match the implementation)

```bash
cd /home/dustin/projects/voice-typing
# Every lite fact the docs state must match the code (research §2):
grep -n "lite_model" voice_typing/config.py            # asr.lite_model, default small.en
grep -n "toggle-lite\|start-lite" voice_typing/ctl.py  # the commands exist
grep -n '"mode"' voice_typing/feedback.py              # state.json has "mode"
grep -n "mode:" voice_typing/ctl.py                    # status renders mode:
grep -n "⚡" voice_typing/status.sh                     # tmux ⚡ prefix
grep -n "toggle-lite" hypr-binds.conf                  # SUPER+ALT+F bind
# Expected: every fact stated in the new README/ACCEPTANCE text is present in the code. Zero drift.
```

### Level 3: Non-Regression (no test files touched — confirm)

```bash
cd /home/dustin/projects/voice-typing
# This task touches ONLY README.md + tests/ACCEPTANCE.md (no .py, no .sh). Confirm the fast suite
# is unaffected (it should be identical to baseline — a safety check, not a feature gate):
.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: 0 failed (same as baseline — no test file was modified).
```

### Level 4: Creative & Domain-Specific

```bash
# Render check (optional): view the README in a markdown viewer (or `mdcat`/`glow` if installed) to
# confirm the new '## Lite mode' section sits cleanly between Hotkey and tmux-status, the lifecycle
# note reads naturally, and the ACCEPTANCE table rows align. No automated gate — docs task.
```

## Final Validation Checklist

### Technical Validation
- [ ] `grep "^## Lite mode" README.md` → the section exists; `grep "In \*\*lite mode\*\* the resident" README.md` → the lifecycle note exists.
- [ ] `grep "^| 10 " tests/ACCEPTANCE.md` → the lite row exists; `grep "criteria 1–10" tests/ACCEPTANCE.md` → intro fixed.
- [ ] Level 2 drift check: every lite fact in the new prose is present in the code.
- [ ] Level 3: `.venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed (baseline unchanged).

### Feature Validation
- [ ] README `## Lite mode` states: single `lite_model` for partials+finals; large never loads; `toggle-lite`/`start-lite`/SUPER+ALT+F; ~half VRAM + faster finals + lower accuracy; one-reload switch; shared drain/auto-stop/idle-unload; `mode:`/`state.json`/⚡.
- [ ] README Model lifecycle notes lite ~half VRAM + idle-unload either mode.
- [ ] ACCEPTANCE #10 text matches PRD §7 #10; status `pending T7` (NOT PASS); evidence points to T7 (P1.M2.T1.S1).
- [ ] ACCEPTANCE #9 (idle-unload) added, status PASS (existing T6(d-gone) evidence).
- [ ] ACCEPTANCE intro/regenerate/evidence-header claims include 9/10.

### Code Quality Validation
- [ ] No duplication of the already-present config-table `lite_model` row or Hotkey lite prose.
- [ ] Only `README.md` + `tests/ACCEPTANCE.md` modified (`git status --short`).
- [ ] No source/test files touched; markdown well-formed.

### Documentation & Deployment
- [ ] README cross-links (Hotkey, Model lifecycle) use the existing heading anchors.
- [ ] ACCEPTANCE #10 marks `pending T7` honestly (P1.M2.T3.S1 flips to PASS).
- [ ] No external docs files (this IS the Mode-B doc task).

---

## Anti-Patterns to Avoid

- ❌ Don't re-add the config-table `lite_model` row or rewrite the Hotkey section's lite prose — they're ALREADY there (concurrent Mode-A process). Add only (b)+(d) (Critical #1).
- ❌ Don't trust the PRP's `oldText` blindly — README is under concurrent editing; RE-VERIFY each anchor against the live file (Critical #2).
- ❌ Don't state a lite fact the code doesn't support — use the verified facts (asr.lite_model, toggle-lite/start-lite, SUPER+ALT+F, `mode` in state.json, `mode:` status, ⚡, one-reload switch). No `lite-model` / `lite` command / invented field (Critical #3).
- ❌ Don't mark ACCEPTANCE #10 `PASS` — T7 (the evidence) is the parallel task P1.M2.T1.S1, not yet landed. Mark `pending T7`; P1.M2.T3.S1 flips it (Critical #4).
- ❌ Don't add #10 alone — add #9 too (contiguous 1–10 table; #9 evidence already exists) (Critical #5).
- ❌ Don't leave the "criteria 1–8" / "5, 6, 8, 9" claims stale after adding 9/10 — fix them or the doc self-contradicts (Critical #6).
- ❌ Don't touch source or test files (Critical #7). Don't edit the ACCEPTANCE evidence BLOCK contents (regenerated by test_idle_and_gpu.sh).
- ❌ Don't invent a pytest gate — this is a docs task; the suite is a non-regression safety check only (Critical #8).
