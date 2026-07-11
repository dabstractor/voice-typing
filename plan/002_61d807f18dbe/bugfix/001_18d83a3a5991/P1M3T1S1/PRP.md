# PRP — P1.M3.T1.S1: Update README.md + ACCEPTANCE.md for the full changeset (bugfix release)

## Goal

**Feature Goal**: Sweep the cross-cutting overview docs (Mode B) so `README.md` and `tests/ACCEPTANCE.md` are consistent with the deployed bugfix code. The changeset's headline is **Issue 1 (Critical)**: the production daemon no longer makes runtime network calls to huggingface.co — `launch_daemon.sh` now exports `HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1`, and `test_idle_and_gpu.sh` now proves it via a NON-circular journal grep. The docs must reflect this, plus the mic-probe TTL (Issue 3, landing in parallel) and the now-true "nothing is sent to a cloud" promise.

**Deliverable** (TWO artifacts, single-file edits each):
1. `README.md` — (a) **REQUIRED**: the "Wrong microphone" claim "the probe re-runs on each arm" is going stale (P1.M2.T2.S1 adds a 30 s TTL cache) → update it. (b) **RECOMMENDED**: add one terse sentence to the intro naming the offline-enforcement mechanism (the launch wrapper sets `HF_HUB_OFFLINE=1`), which makes the existing "nothing is sent to a cloud" promise credible. (c) VERIFY lines 3 & 6 ("Fully-local", "nothing is sent to a cloud") are accurate post-fix (they are — the fix makes them true; no edit).
2. `tests/ACCEPTANCE.md` — **REQUIRED**: criterion 8 still describes the OLD CIRCULAR proof ("ran the entire test under HF_HUB_OFFLINE=1") in FOUR spots (table row, evidence-block line, PASS line, method-notes bullet). Update all four to the NON-circular proof: the test launches via `launch_daemon.sh` (production path, no pre-set env) and asserts the daemon log has ZERO `HTTP Request: GET https://huggingface.co` lines.

**Success Definition**:
- (a) README line 3 ("Fully-local voice typing") and line 6 ("nothing is sent to a cloud") are accurate post-fix — left UNCHANGED (the fix makes them true).
- (b) README intro has ONE added sentence documenting the offline-enforcement mechanism (launch wrapper `HF_HUB_OFFLINE=1`, zero runtime network, models prefetched at install). Terse, matching the README voice.
- (c) README "Wrong microphone" section no longer says "the probe re-runs on each arm"; it reflects the 30 s TTL cache (arming stays instant; restart for an immediate re-probe). [Gate: `_MIC_PROBE_TTL_S` present in daemon.py.]
- (d) ACCEPTANCE.md criterion 8 — all four stale spots updated to the non-circular proof; NO remaining "ran under HF_HUB_OFFLINE=1" / "ran the entire test under" circular framing.
- (e) ACCEPTANCE.md evidence-block `offline_env:` line matches what `test_idle_and_gpu.sh` actually emits (`via launch_daemon.sh exports (...)...; daemon.log HF-request grep: CLEAN`).
- (f) No out-of-scope files: README.md + tests/ACCEPTANCE.md ONLY. No source code, no PRD.md/tasks.json/prd_snapshot.md/.gitignore, no launch_daemon.sh/status.sh/install.sh/daemon.py (bugfix code is DONE). No new files. No docs/ or CONTRIBUTING.md exist (scan is clean).

## User Persona

**Target User**: "dustin, six months from now, and anyone who clones the repo" (README line 7-8) — a Linux power user who wants exact commands, not hand-holding. For ACCEPTANCE.md: the maintainer auditing PRD §7 definition-of-done.

**Use Case**: A reader sees "nothing is sent to a cloud" and wants to know it is actually enforced (not just asserted). A maintainer reads criterion 8 and needs the proof to be real (non-circular), not a test that passes because it set the variable itself.

**User Journey**: clone → read README intro (now names the offline mechanism + points at launch_daemon.sh) → run install.sh (offline-confirmed) → read ACCEPTANCE.md criterion 8 (non-circular journal-grep proof) → trust the "100% local" claim.

**Pain Points Addressed**: PRD Issue 1 found the README's "nothing is sent to a cloud" was FALSE as shipped (the daemon phoned home). The fix makes it true; this task documents the mechanism and corrects the circular acceptance proof so a future regression cannot hide behind a self-fulfilling test.

## Why

- **Closes the doc half of the Critical bugfix.** Issue 1's code fix (launch_daemon.sh exports) is landed; the docs still either under-claim (README: silent on the mechanism) or mis-claim (ACCEPTANCE.md: circular proof). A Critical privacy bug whose fix is not reflected in the user-facing promise + acceptance record is only half-fixed.
- **The mic-probe README claim is going stale THIS changeset.** P1.M2.T2.S1 (parallel) changes `_arm()` to TTL-cache the probe, but it is Mode A (daemon.py docstrings only) and does NOT touch README. The cross-cutting user-facing claim "the probe re-runs on each arm" is Mode B → this task. If skipped, the README ships a claim the code no longer matches.
- **The acceptance proof must be non-circular to be worth anything.** The PRD (Issue 1) explicitly calls the old criterion-8 proof "circular: it passes because the test itself supplies the variable that production omits." P1.M1.T1.S3 fixed the TEST; ACCEPTANCE.md still describes the old proof. A definition-of-done record that documents a disproven proof method undermines the release.
- **Respects Mode A / Mode B boundary.** Per-file doc updates (launch_daemon.sh comment, status.sh comment, install.sh summary, daemon.py docstrings) were Mode A, done by the implementing subtasks. This task touches ONLY the cross-cutting overview docs. It does not re-document features or edit code.

## What

Two single-file edits:

**README.md** — (Task 2) add one intro sentence documenting the offline-enforcement mechanism; (Task 3) update the "Wrong microphone" mic-probe claim to reflect the 30 s TTL cache. Leave the offline promises (lines 3, 6) and the status.sh/install.sh descriptions unchanged (still accurate).

**tests/ACCEPTANCE.md** — (Task 4) update the four criterion-8 spots (table row, evidence-block line, PASS line, method-notes bullet) from the circular "ran under HF_HUB_OFFLINE=1" framing to the non-circular "production-path launch via launch_daemon.sh + zero HTTP-request log lines" framing. (Task 5, OPTIONAL) flip criterion 7 from stale "partial" (README pending) to PASS (README exists and is comprehensive).

### Success Criteria

- [ ] README intro contains a one-sentence offline-enforcement note naming `HF_HUB_OFFLINE=1` and `launch_daemon.sh`.
- [ ] `grep -n "re-runs on each arm" README.md` returns nothing (stale claim removed).
- [ ] README "Wrong microphone" section reflects the 30 s TTL cache + the restart-for-immediate-re-probe guidance.
- [ ] `grep -n "_MIC_PROBE_TTL_S" voice_typing/daemon.py` confirms the parallel TTL fix has landed (GATE for Task 3).
- [ ] README lines 3 & 6 ("Fully-local", "nothing is sent to a cloud") are UNCHANGED.
- [ ] ACCEPTANCE.md criterion 8 row describes the non-circular proof (production path via launch_daemon.sh, zero HTTP-request log lines).
- [ ] ACCEPTANCE.md evidence-block `offline_env:` line matches `test_idle_and_gpu.sh`'s actual emission (`via launch_daemon.sh exports (...)...; daemon.log HF-request grep: CLEAN`).
- [ ] ACCEPTANCE.md PASS line for criterion 8 matches `test_idle_and_gpu.sh`'s actual PASS line (`daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines`).
- [ ] `grep -nE 'ran the entire test under|ran under HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 and loaded' tests/ACCEPTANCE.md` returns nothing (circular framing gone).
- [ ] `git status --porcelain` shows ONLY `M README.md` and `M tests/ACCEPTANCE.md` (no source edits, no new files).

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research note: every edit is given as verbatim old→new text with exact anchors; the verified current state of the codebase (launch_daemon.sh:71-72 exports; test_idle_and_gpu.sh:225-234 non-circular grep + :422 evidence line + :234 PASS line) is pinned so the docs match reality; the `_MIC_PROBE_TTL_S` gate for the mic-probe edit is explicit; the README voice is pinned; and the validation greps are executable as written. No guessing.

### Documentation & References

```yaml
# MUST READ — the file being edited (README). Clause (a) lines 3/6, (b) intro, (c) Wrong microphone.
- file: README.md
  why: "The file being edited. Lines 3 & 6 (offline promises) verified accurate post-fix — leave
        them. Intro paragraph (lines 1-6) gets the one-sentence offline-enforcement note (Task 2).
        'Wrong microphone' section (line 227: 'the probe re-runs on each arm') gets the TTL update
        (Task 3). 'tmux status line' + 'Install' sections unchanged (status.sh output unaffected by
        Issue 2; install steps not in this task's scope)."
  critical: "README voice (line 7-8): terse, command-first, no hand-holding. Match it EXACTLY. Do NOT
             restate bugfix Issue numbers in README prose (it is user-facing, not a changelog). Lines
             3 & 6 must stay byte-identical."

# MUST READ — the file being edited (ACCEPTANCE). Criterion 8 has 4 stale spots (Task 4).
- file: tests/ACCEPTANCE.md
  why: "The file being edited. Criterion 8 row + evidence-block `offline_env:` line + PASS line +
        'Notes on the method' bullet ALL describe the OLD circular proof (the test pre-set
        HF_HUB_OFFLINE). Update to the non-circular proof (Task 4). 'How to reproduce' + regenerate
        instructions stay accurate (no change). Criterion 7 'partial' is stale-but-optional (Task 5)."
  critical: "The evidence-block line + PASS line MUST match what test_idle_and_gpu.sh actually emits
             (test_idle_and_gpu.sh:422 and :234 — verbatim in research §3.1). Do NOT invent a new
             format; mirror the test. ACCEPTANCE.md may reference 'bugfix Issue 1' (it already uses
             'this task — direct evidence' framing) but must describe the PROOF MECHANISM."

# MUST READ — verified changeset state + the verbatim edits + the non-circular proof source strings
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/P1M3T1S1/research/readme_acceptance_changeset_sweep.md
  why: "§1 the landing-status table (Issues 1/2/4 LANDED; Issue 3 IN PARALLEL). §2 README state
        (2.1 promises already correct; 2.2 the intro note; 2.3 the REQUIRED Wrong-microphone TTL
        update + the _MIC_PROBE_TTL_S gate; 2.4/2.5 status.sh/install.sh need NO README change).
        §3 the FOUR ACCEPTANCE.md stale spots with verbatim current text + the exact new strings the
        test emits (3.1 spot-by-spot, 3.2 the non-circular proof mechanics). §4 the docs scan (no
        docs/CONTRIBUTING; criterion 7 optional). §5 style+scope. §6 validation greps."
  section: "ALL load-bearing. §2.3 (mic-probe gate), §3 (the four ACCEPTANCE spots), §1 (landing state)."

# MUST READ — the parallel task contract (the mic-probe TTL that makes the README claim stale).
- file: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/P1M2T2S1/PRP.md
  why: "P1.M2.T2.S1 adds _MIC_PROBE_TTL_S=30.0 and TTL-caches _refresh_mic_status; _arm() respects
        the TTL. It is Mode A (daemon.py docstrings + _arm inline comment) and does NOT edit README.
        So the README's 're-runs on each arm' claim is a cross-cutting overview doc → THIS Mode B
        task owns it. The Task-3 edit is derived from this PRP's behavior contract (probe ≤ once /
        30s; __init__ force-probes; restart re-probes immediately)."
  critical: "Treat the PRP as a CONTRACT. The Task-3 README edit depends on _MIC_PROBE_TTL_S landing;
             GATE on `grep -n _MIC_PROBE_TTL_S voice_typing/daemon.py` before finalizing. Do NOT edit
             daemon.py yourself (P1.M2.T2.S1 owns it; this task is docs-only)."

# SHOULD READ — the test whose output ACCEPTANCE.md mirrors (the non-circular proof + evidence format).
- file: tests/test_idle_and_gpu.sh
  why: "Source of truth for ACCEPTANCE.md's criterion-8 evidence. Line 94 LAUNCH=launch_daemon.sh
        (production path); lines 53-55 G-OFFLINE (do NOT pre-set HF_HUB_OFFLINE); lines 225-234 the
        non-circular grep (FAIL on any 'HTTP Request: GET https://huggingface.co'); line 234 the PASS
        line; lines 410-423 the === ACCEPTANCE EVIDENCE === block emission (line 422 is the new
        offline_env value)."
  critical: "ACCEPTANCE.md's evidence-block + PASS line must mirror these verbatim. The test does NOT
             pre-set the offline vars (that was the circular bug); the proof is the log grep. Do NOT
             edit the test (P1.M1.T1.S3 owns it; this task is docs-only)."

# SHOULD READ — the landed Issue 1 fix (the mechanism the README intro note documents).
- file: voice_typing/launch_daemon.sh
  why: "Source of truth for the README intro note's claim. Lines 71-72: export HF_HUB_OFFLINE=1 /
        TRANSFORMERS_OFFLINE=1, before exec'ing python. The comment at :62/:68 explains the rationale
        (ZERO network / avoids LocalEntryNotFoundError). This is the 'launch wrapper' the README note
        names."
  critical: "Do NOT edit launch_daemon.sh (P1.M1.T1.S1 owns it; DONE). The README note must match:
             'the launch wrapper (launch_daemon.sh) sets HF_HUB_OFFLINE=1' is accurate. Verify lines
             71-72 are present before writing the note."

# CONTEXT — PRD Issue 1 (the Critical defect this changeset fixes). READ-ONLY.
- docfile: plan/002_61d807f18dbe/bugfix/001_18d83a3a5991/prd_snapshot.md
  why: "§2.1/§3.0 Issue 1: production daemon made runtime network calls (violated PRD §1 '100% local'
        + criterion 7.8); the README 'nothing is sent to a cloud' promise was false as shipped; the
        test_idle_and_gpu.sh criterion-8 proof was circular. Confirms WHY the docs must change."
  critical: "The PRD is the authority on the defect + the circular-proof problem. Do NOT edit the PRD
             (forbidden). The docs task reflects the fix, not the PRD text."
```

### Current Codebase tree (state at P1.M3.T1.S1 start — Issues 1/2/4 LANDED, Issue 3 parallel)

```bash
$ ls -1   # the only files this task touches:
README.md                    # <-- EDIT (intro offline note; Wrong-mic TTL)
tests/ACCEPTANCE.md          # <-- EDIT (criterion 8 x4 spots; criterion 7 optional)
# Supporting (READ-ONLY, do NOT edit — bugfix code is DONE):
voice_typing/launch_daemon.sh   # Issue 1 fix (offline exports) — landed; README note names it
voice_typing/status.sh          # Issue 2 fix (exit 0) — landed; README status.sh desc unaffected
voice_typing/daemon.py          # Issue 3 fix (TTL) — PARALLEL (P1.M2.T2.S1); GATE on _MIC_PROBE_TTL_S
install.sh                      # Issue 4 fix (offline grep) — landed; README Install unchanged here
tests/test_idle_and_gpu.sh      # Issue 1 non-circular proof — landed; ACCEPTANCE.md mirrors its output
PRD.md                          # READ-ONLY (forbidden)
# No docs/, no CONTRIBUTING.md, no CHANGELOG.md (scan clean).
```

### Desired Codebase tree with files to be added

```bash
README.md                    # MODIFIED: +1 intro sentence (offline mechanism); Wrong-mic claim → TTL.
tests/ACCEPTANCE.md          # MODIFIED: criterion 8 ×4 spots → non-circular proof; criterion 7 optional.
# NOTHING ELSE. No new files. No source edits. No PRD/tasks/.gitignore changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE "Wrong microphone" CLAIM IS GOING STALE THIS CHANGESET. README line 227 says
#   "the probe re-runs on each arm". P1.M2.T2.S1 (parallel) adds a 30s TTL cache (_MIC_PROBE_TTL_S)
#   so _arm() does NOT re-probe within the window. P1.M2.T2.S1 is Mode A (daemon.py docstrings) and
#   does NOT edit README. So updating this cross-cutting user-facing claim is THIS task's job.
#   GATE: `grep -n "_MIC_PROBE_TTL_S" voice_typing/daemon.py` MUST return a hit before you finalize
#   Task 3. If it does not, the parallel task has not landed — STOP and flag (do not edit README to a
#   state the code does not yet match). (Research §1, §2.3.)

# CRITICAL #2 — ACCEPTANCE.md HAS FOUR STALE CRITERION-8 SPOTS, NOT ONE. The circular framing appears
#   in (1) the table row, (2) the evidence-block `offline_env:` line, (3) the PASS line, (4) the
#   "Notes on the method" bullet. Updating only the obvious table row leaves three circular claims.
#   All four are verbatim-old→new in Task 4. (Research §3.1.)

# CRITICAL #3 — THE EVIDENCE LINE + PASS LINE MUST MATCH test_idle_and_gpu.sh's ACTUAL EMISSION. Do
#   NOT invent a format. The test now emits (test_idle_and_gpu.sh:422):
#     offline_env: via launch_daemon.sh exports (HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1); daemon.log HF-request grep: CLEAN
#   and (test_idle_and_gpu.sh:234):
#     [PASS] criterion 8 (no-network guard): daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines (production path offline)
#   ACCEPTANCE.md is the PASTE TARGET for that block — mirror it. (Research §3.1, §3.2.)

# CRITICAL #4 — THE OFFLINE PROMISES (README lines 3 & 6) ARE ALREADY CORRECT — LEAVE THEM. Pre-fix
#   they were false (the daemon phoned home); post-fix (launch_daemon.sh exports) they are true. The
#   item: "If they already state the right thing, no edit needed." Editing them would risk weakening
#   a correct, load-bearing promise. (Research §2.1.)

# CRITICAL #5 — THE NON-CIRCULAR PROOF IS "PRODUCTION PATH + LOG GREP", NOT "RAN OFFLINE". The old
#   proof was circular because the TEST set HF_HUB_OFFLINE itself. The new proof: the test launches
#   via launch_daemon.sh (which exports the vars), does NOT pre-set them, and greps the daemon log for
#   'HTTP Request: GET https://huggingface.co' — FAIL if any. The ACCEPTANCE.md wording must convey
#   "production path via launch_daemon.sh, offline vars from the wrapper, zero HTTP-request log lines"
#   — NOT "the test ran the daemon offline". (Research §3.2; test_idle_and_gpu.sh:53-55, 225-234.)

# CRITICAL #6 — DO NOT EDIT THE BUGFIX CODE. This is Mode B docs. launch_daemon.sh, status.sh,
#   daemon.py, install.sh, test_idle_and_gpu.sh are ALL DONE (or, for daemon.py, in parallel). Edit
#   ONLY README.md + tests/ACCEPTANCE.md. Any change to source/test/bash = scope violation.

# CRITICAL #7 — README VOICE: TERSE, COMMAND-FIRST, NO MARKETING, NO HAND-HOLDING. README line 7-8:
#   "assumes a Linux power user who wants exact commands, not hand-holding." The added intro sentence
#   and the Wrong-mic rewrite must read like the surrounding prose. No exclamation marks, no em-dash
#   spam, no "exciting". Do NOT write "Issue 1 fixed" in README prose (user-facing, not a changelog).
#   (Research §5.)

# GOTCHA #8 — NO docs/, CONTRIBUTING.md, OR CHANGELOG.md EXIST. The "scan for other overview docs"
#   clause (c) finds nothing beyond README.md + ACCEPTANCE.md. Do not create any. (Research §4.)

# GOTCHA #9 — CRITERION 7 IS STALE-BUT-OUT-OF-SCOPE. ACCEPTANCE.md criterion 7 says "partial / the
#   README is task P2.M1.T2.S1 (pending)". The README now EXISTS and is comprehensive, so "partial" is
#   stale. BUT criterion 7 is about README completeness, not offline/status.sh/mic, so it is borderline
#   for this task. OPTIONAL (Task 5): flip to PASS with evidence the README covers
#   install/hotkey/tmux/config/troubleshooting/CPU-only (verifiably true). Not required by the contract.
#   (Research §4.)

# GOTCHA #10 — NO TEST FRAMEWORK APPLIES. README.md + ACCEPTANCE.md are markdown; no pytest/ruff/mypy
#   gate. Validation is grep checks (stale claims gone; non-circular framing present; evidence matches
#   the test) + `git status --porcelain` (only the two docs). Do NOT invent a lint command. (Research §6.)
```

## Implementation Blueprint

### Data models and structure

Not applicable — no code, no data models. Two markdown-file edits.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm the changeset state + edit anchors (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      grep -nE 'HF_HUB_OFFLINE|TRANSFORMERS_OFFLINE' voice_typing/launch_daemon.sh  # Issue 1 landed (expect :71-72)
      grep -n 'exit 0' voice_typing/status.sh                                       # Issue 2 landed (expect :47)
      grep -nE 'offline check|HTTP Request' install.sh                              # Issue 4 landed
      grep -n '_MIC_PROBE_TTL_S' voice_typing/daemon.py                             # Issue 3 GATE (MUST be present for Task 3)
      grep -n "re-runs on each arm" README.md                                       # the stale claim (Task 3 anchor)
      grep -n 'nothing is sent to a cloud' README.md                                # Task 2 anchor (the promise to follow)
      grep -nE 'ran the entire test under|ran under HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 and loaded' tests/ACCEPTANCE.md  # circular framing (Task 4)
      grep -n 'offline_env:' tests/test_idle_and_gpu.sh                             # the new evidence-line format (Task 4 source)
  - EXPECTED: launch_daemon.sh:71-72 + status.sh:47 + install.sh offline grep all present; _MIC_PROBE_TTL_S present in daemon.py (if NOT, STOP — Task 3 is blocked); the README/ACCEPTANCE anchors all match the verbatim oldText below.
  - DO NOT: edit anything yet.

Task 2: EDIT README.md — intro offline-enforcement note (RECOMMENDED; completes the offline story)
  - FILE: README.md
  - ANCHOR (the last sentence of the intro paragraph):
        tmux desktop. The recognizer runs 100% on your machine; nothing is sent to a cloud.
  - REPLACE WITH (append one sentence — keep the existing sentence byte-identical, add the new one):
        tmux desktop. The recognizer runs 100% on your machine; nothing is sent to a cloud.
        Offline mode is enforced: the launch wrapper (`launch_daemon.sh`) sets `HF_HUB_OFFLINE=1`,
        so models load from the local cache with zero runtime network calls (the install prefetches
        them).
  - USE the `edit` tool. oldText is the one existing sentence (unique); newText is it + the 3 added lines.
  - ACCURACY: matches launch_daemon.sh:71-72 (export HF_HUB_OFFLINE=1) + install.sh prefetch (README Install step 4). Terse, matches the README voice.
  - DO NOT: touch lines 3/6's existing wording; reference Issue numbers; edit any other section here.

Task 3: EDIT README.md — "Wrong microphone" mic-probe TTL (REQUIRED; depends on P1.M2.T2.S1)
  - GATE (re-run): grep -n '_MIC_PROBE_TTL_S' voice_typing/daemon.py  # MUST hit. If absent, STOP.
  - FILE: README.md
  - ANCHOR (the last sentence of the "Wrong microphone" section, spanning the line break):
        immediately, without digging into `journalctl`. After fixing the source, arm again with
        `voicectl toggle` (the probe re-runs on each arm).
  - REPLACE WITH:
        immediately, without digging into `journalctl`. After fixing the source, arm again with
        `voicectl toggle`. The mic-health probe is cached for ~30 s to keep arming instant, so for an
        immediate re-probe restart the daemon (`systemctl --user restart voice-typing`).
  - USE the `edit` tool. oldText is the 2-line sentence (unique via "the probe re-runs on each arm").
  - ACCURACY: matches the TTL contract — _arm() respects the 30s cache (arming instant, PRD §4.2);
    construction (restart) force-probes. "cached for ~30 s" + "restart for an immediate re-probe" are
    both correct. Terse, matches the README voice.
  - DO NOT: edit daemon.py (P1.M2.T2.S1 owns it); change the `mic:` line description (still accurate);
    remove the "check the mic health line FIRST" guidance (still correct).

Task 4: EDIT tests/ACCEPTANCE.md — criterion 8: four circular-proof spots → non-circular (REQUIRED)
  - FILE: tests/ACCEPTANCE.md
  - FOUR `edit` entries in ONE call (each oldText is unique). See "Task 4 SOURCE" below for the exact
    oldText→newText of all four spots: (4a) table row, (4b) evidence-block offline_env line,
    (4c) PASS line, (4d) "Notes on the method" bullet.
  - ACCURACY: 4b and 4c mirror test_idle_and_gpu.sh:422 and :234 VERBATIM (the test emits them;
    ACCEPTANCE.md is the paste target). 4a and 4d describe the non-circular proof (production path via
    launch_daemon.sh, no pre-set env, zero HTTP-request log lines).
  - DO NOT: touch criteria 1-7 rows (out of scope; criterion 7 is Task 5 optional); touch the
    "How to reproduce" section (still accurate); invent a new evidence format.

Task 5: (OPTIONAL) EDIT tests/ACCEPTANCE.md — criterion 7 "partial" → "PASS" (coherence)
  - FILE: tests/ACCEPTANCE.md
  - ONLY IF doing a thorough coherence pass. Criterion 7 row currently says "partial / the README is
    task P2.M1.T2.S1 (pending)". The README now EXISTS and is comprehensive.
  - ANCHOR (the criterion 7 row):
        | 7 | Everything committed to git; README documents install / hotkey / tmux / config / troubleshooting / CPU-only mode | partial | `git status` — implementation committed on `main`; the README is task **P2.M1.T2.S1** (pending), which will document install, the hotkey snippet, the tmux status snippet, the config tuning table, troubleshooting (cuDNN libs, PyAudio device, wtype vs ydotool), and CPU-only mode. |
  - REPLACE WITH:
        | 7 | Everything committed to git; README documents install / hotkey / tmux / config / troubleshooting / CPU-only mode | PASS | `git status` — implementation committed on `main`; README.md documents install, the Hyprland hotkey, the tmux status snippet, the config tuning table, troubleshooting (cuDNN libs, wrong microphone, wtype vs ydotool), and CPU-only mode. |
  - DO NOT: invent claims — verify the README sections exist (they do: Install, Hotkey, tmux status line, Configuration, Troubleshooting, CPU-only mode). If unsure, SKIP Task 5 (it is optional).

Task 6: VALIDATE (no file change — see Validation Loop)
  - Run the grep checks: README (offline note present; "re-runs on each arm" gone); ACCEPTANCE (circular framing gone; non-circular framing present; evidence matches the test). `git status --porcelain` = only the two docs.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M3.T1.S1: README + ACCEPTANCE changeset sweep — README documents offline enforcement + mic-probe TTL; ACCEPTANCE criterion 8 → non-circular proof".
```

#### Task 4 SOURCE — `tests/ACCEPTANCE.md` four criterion-8 edits (verbatim oldText → newText)

**4a — table row:**
- oldText:
```
| 8 | No network access needed at runtime (models cached by install) | **PASS (this task — direct evidence)** | `./tests/test_idle_and_gpu.sh` — the daemon ran the entire test under `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` and loaded the cached models (went ready + survived 120 s armed idle). (Block below.) |
```
- newText:
```
| 8 | No network access needed at runtime (models cached by install) | **PASS (this task — direct evidence)** | `./tests/test_idle_and_gpu.sh` — the test launches the daemon via the **production path** (`launch_daemon.sh`, no pre-set env) and asserts the daemon log has ZERO `HTTP Request: GET https://huggingface.co` lines, a non-circular proof that the deployed unit is offline (the offline vars come from the wrapper, not from the test). (Block below.) |
```

**4b — evidence-block `offline_env:` line (mirror test_idle_and_gpu.sh:422 verbatim):**
- oldText:
```
offline_env: HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
```
- newText:
```
offline_env: via launch_daemon.sh exports (HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1); daemon.log HF-request grep: CLEAN
```

**4c — PASS line (mirror test_idle_and_gpu.sh:234 verbatim):**
- oldText:
```
[PASS] criterion 8 (no network): daemon ran under HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 and loaded cached models
```
- newText:
```
[PASS] criterion 8 (no-network guard): daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines (production path offline)
```

**4d — "Notes on the method" criterion 8 bullet:**
- oldText:
```
- **Criterion 8** is proven by the run itself: the daemon was launched with `HF_HUB_OFFLINE=1
  TRANSFORMERS_OFFLINE=1`, which is a hard offline switch. That it went ready and survived 120 s of
  armed idle is empirical proof the models load from the local cache with zero network access.
```
- newText:
```
- **Criterion 8** is a **non-circular** proof (bugfix Issue 1): the test does NOT pre-set the offline
  env vars. It launches the daemon via `launch_daemon.sh` (the production path — the wrapper exports
  `HF_HUB_OFFLINE=1`/`TRANSFORMERS_OFFLINE=1`), then greps the daemon log for
  `HTTP Request: GET https://huggingface.co` and fails if any are found. Because the test itself does
  not supply the variable, a regression that removes the wrapper exports surfaces here. (The earlier
  "ran under HF_HUB_OFFLINE=1" framing was circular — it passed only because the test set the variable
  production omitted.)
```

### Implementation Patterns & Key Details

```markdown
<!-- PATTERN: README edits are ONE-sentence additions/rewrites that match the surrounding terse voice.
     The intro note follows "nothing is sent to a cloud." (the promise) with the MECHANISM (the launch
     wrapper enforces it). The Wrong-mic rewrite states the new behavior (cached ~30s) + the WHY
     (keep arming instant) + the workaround (restart for immediate re-probe). -->

<!-- PATTERN: ACCEPTANCE.md edits mirror what the test ACTUALLY EMITS. The evidence-block + PASS line
     are paste-targets — copy test_idle_and_gpu.sh's emission verbatim (4b from :422, 4c from :234).
     The table row (4a) + method note (4d) describe the proof in prose: "production path via
     launch_daemon.sh, no pre-set env, zero HTTP-request log lines = non-circular". -->

<!-- GOTCHA: never describe the criterion-8 proof as "the test ran the daemon offline" — that is the
     CIRCULAR framing the bugfix eliminated. Always name the mechanism: launch_daemon.sh exports the
     vars; the test does NOT pre-set them; the proof is the log grep. -->

<!-- GOTCHA: the README Wrong-mic edit is BLOCKED until _MIC_PROBE_TTL_S lands in daemon.py (P1.M2.T2.S1,
     parallel). Gate Task 3 on the grep. This task runs LAST, so it should be present. -->
```

### Integration Points

```yaml
NO code/config/protocol integration points.
  - This task edits two markdown files. No source, no config.toml, no socket/protocol change.
  - DOCUMENTATION ONLY: README.md (user-facing overview) + tests/ACCEPTANCE.md (PRD §7 evidence record).
PARALLEL (disjoint): P1.M2.T2.S1 edits voice_typing/daemon.py + tests/test_daemon.py — NO file overlap
  with README.md / tests/ACCEPTANCE.md. But Task 3 (README Wrong-mic) DEPENDS ON P1.M2.T2.S1's
  _MIC_PROBE_TTL_S landing — gate on the grep.
LANDING STATE (do NOT re-edit these — DONE): launch_daemon.sh (Issue 1), status.sh (Issue 2),
  install.sh (Issue 4), test_idle_and_gpu.sh (Issue 1 non-circular proof), daemon.py (Issue 3, parallel).
```

## Validation Loop

> No test framework applies to markdown (Gotcha #10). Validation is grep checks + `git status`. Run
> from `/home/dustin/projects/voice-typing`. Use the `edit` tool for the changes.

### Level 1: README checks

```bash
cd /home/dustin/projects/voice-typing
echo "--- (Task 2) offline-enforcement note present ---"
grep -nE 'HF_HUB_OFFLINE=1|launch wrapper|zero runtime network' README.md   # expect >=1 match in the intro
echo "--- (Task 3) stale mic-probe claim GONE ---"
grep -n "re-runs on each arm" README.md && echo "FAIL: stale claim remains" || echo "OK: stale claim removed"
grep -n "cached for ~30" README.md                                          # expect the new TTL wording
echo "--- (Task 2/3) offline promises UNCHANGED ---"
grep -nE 'Fully-local voice typing|nothing is sent to a cloud' README.md    # expect lines 3 & 6 intact
echo "--- fence balance (expect EVEN) ---"
test $(( $(grep -c '^```' README.md) % 2 )) -eq 0 && echo "OK: balanced fences" || echo "FAIL: unbalanced"
# Expected: offline note in intro; no "re-runs on each arm"; "cached for ~30" present; lines 3 & 6 intact; balanced fences.
```

### Level 2: ACCEPTANCE.md checks

```bash
cd /home/dustin/projects/voice-typing
echo "--- (Task 4) circular framing GONE ---"
grep -nE 'ran the entire test under|ran under HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 and loaded' tests/ACCEPTANCE.md && echo "FAIL: circular framing remains" || echo "OK: circular framing removed"
echo "--- (Task 4) non-circular framing present ---"
grep -nE 'production path|launch_daemon\.sh|ZERO .*HTTP Request' tests/ACCEPTANCE.md   # expect matches in the criterion-8 spots
grep -n 'via launch_daemon.sh exports' tests/ACCEPTANCE.md                              # the new evidence line (4b)
grep -n "daemon.log has ZERO 'HTTP Request" tests/ACCEPTANCE.md                         # the new PASS line (4c)
echo "--- evidence line matches the test's emission ---"
diff <(grep 'offline_env:' tests/ACCEPTANCE.md) <(grep -E '^echo "offline_env:' tests/test_idle_and_gpu.sh | sed 's/^echo "//;s/"$//') && echo "OK: ACCEPTANCE matches test emission" || echo "NOTE: formats differ — verify 4b mirrors test_idle_and_gpu.sh:422"
# Expected: circular framing gone; non-circular framing present; the evidence line matches the test.
```

### Level 3: Cross-file consistency (the docs match the deployed code)

```bash
cd /home/dustin/projects/voice-typing
echo "--- README intro note matches launch_daemon.sh reality ---"
grep -nE 'export HF_HUB_OFFLINE=1|export TRANSFORMERS_OFFLINE=1' voice_typing/launch_daemon.sh   # the mechanism the README names
echo "--- Task 3 gate: _MIC_PROBE_TTL_S landed (P1.M2.T2.S1) ---"
grep -n '_MIC_PROBE_TTL_S' voice_typing/daemon.py || echo "BLOCKED: P1.M2.T2.S1 not landed — Task 3 must not ship"
echo "--- ACCEPTANCE criterion-8 proof matches test_idle_and_gpu.sh mechanics ---"
grep -nE 'launch_daemon\.sh|HTTP Request: GET https://huggingface.co' tests/test_idle_and_gpu.sh | head
# Expected: launch_daemon.sh:71-72 exports present; _MIC_PROBE_TTL_S present; the test's grep proof present.
```

### Level 4: Scope guard

```bash
cd /home/dustin/projects/voice-typing
echo "--- ONLY the two docs changed by THIS task ---"
git status --porcelain
# Expected: " M README.md" and " M tests/ACCEPTANCE.md" (this task). daemon.py/test_daemon.py changes
# (if present) belong to the parallel P1.M2.T2.S1 — NOT this task. Any change to launch_daemon.sh /
# status.sh / install.sh / test_idle_and_gpu.sh / PRD.md / tasks.json = SCOPE VIOLATION by this task.
echo "--- no new files ---"
git status --porcelain | grep '^??' | grep -vE 'plan/' && echo "FAIL: untracked non-plan files" || echo "OK: no new non-plan files"
```

## Final Validation Checklist

### Technical Validation

- [ ] `grep -n "re-runs on each arm" README.md` → no match (stale claim removed).
- [ ] `grep -nE 'HF_HUB_OFFLINE=1' README.md` → match in the intro (offline note added).
- [ ] `grep -c '^```' README.md` → EVEN (fences balanced).
- [ ] `grep -nE 'ran the entire test under|ran under HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 and loaded' tests/ACCEPTANCE.md` → no match (circular framing gone).
- [ ] `grep -n 'via launch_daemon.sh exports' tests/ACCEPTANCE.md` → match (evidence line updated, 4b).
- [ ] `grep -n "daemon.log has ZERO 'HTTP Request" tests/ACCEPTANCE.md` → match (PASS line updated, 4c).
- [ ] `git status --porcelain` → only `M README.md` + `M tests/ACCEPTANCE.md` from this task.

### Feature Validation

- [ ] README intro has the one-sentence offline-enforcement note (launch wrapper `HF_HUB_OFFLINE=1`, zero runtime network, models prefetched).
- [ ] README "Wrong microphone" reflects the 30 s TTL cache + restart-for-immediate-re-probe (Task 3 gate: `_MIC_PROBE_TTL_S` in daemon.py).
- [ ] README lines 3 & 6 unchanged (offline promises already correct).
- [ ] ACCEPTANCE.md criterion 8 (all 4 spots) describes the NON-circular proof: production path via launch_daemon.sh, no pre-set env, zero HTTP-request log lines.
- [ ] ACCEPTANCE.md evidence-block `offline_env:` line + PASS line mirror `test_idle_and_gpu.sh`'s actual emission.

### Code Quality Validation

- [ ] README added prose matches the terse, command-first voice (no marketing, no changelog voice).
- [ ] ACCEPTANCE.md edits match the existing evidence-record style (factual, no marketing).
- [ ] The criterion-8 proof is described as "production path + log grep", NOT "ran offline" (non-circular).
- [ ] Verified-accurate sections (offline promises, status.sh/install.sh descriptions) left UNTOUCHED.
- [ ] (Optional Task 5) criterion 7 reflects that the README exists and is comprehensive.

### Documentation & Deployment

- [ ] README is internally consistent (no stale mic-probe claim; offline mechanism documented).
- [ ] ACCEPTANCE.md criterion 8 matches the deployed test's actual proof + evidence format.
- [ ] No new env vars / config keys / user-facing surfaces introduced (pure doc).

---

## Anti-Patterns to Avoid

- ❌ Don't edit any file other than README.md + tests/ACCEPTANCE.md — this is Mode B docs; the bugfix code is DONE (or, for daemon.py, in parallel). Source/test/bash edits are scope violations.
- ❌ Don't write the README Wrong-mic edit before confirming `_MIC_PROBE_TTL_S` landed in daemon.py — the edit must match the code. Gate Task 3 on the grep.
- ❌ Don't describe the criterion-8 proof as "the test ran the daemon offline" — that is the CIRCULAR framing the bugfix eliminated. Always name the mechanism: launch_daemon.sh exports the vars; the test does NOT pre-set them; the proof is the log grep.
- ❌ Don't invent a new ACCEPTANCE evidence format — mirror `test_idle_and_gpu.sh`'s actual emission (4b from :422, 4c from :234). ACCEPTANCE.md is the paste target.
- ❌ Don't update only the obvious criterion-8 table row — there are FOUR stale spots (table row, evidence line, PASS line, method-notes bullet). All four are in Task 4.
- ❌ Don't edit the offline promises (README lines 3 & 6) — they are already correct; the fix makes them true.
- ❌ Don't add bugfix Issue numbers to README prose — it is user-facing, not a changelog (ACCEPTANCE.md may reference "bugfix Issue 1" since it is an evidence record).
- ❌ Don't create docs/ or CONTRIBUTING.md — the scan is clean; no other overview docs exist.
- ❌ Don't invent a lint/test command for markdown — validation is grep checks + `git status`.
- ❌ Don't edit launch_daemon.sh / status.sh / install.sh / test_idle_and_gpu.sh to "make the docs match" — fix the DOCS to match the (already-correct) code, never the reverse.

---

**Confidence Score: 9/10** for one-pass success. The task is small and fully bounded: verbatim old→new edits for the README intro note + the Wrong-mic TTL claim + the four ACCEPTANCE criterion-8 spots, each anchored on unique text. The non-circular-proof strings are pinned to `test_idle_and_gpu.sh`'s actual emission (verified live), so ACCEPTANCE.md cannot drift from the test. The one moving part — the README Wrong-mic edit depending on the parallel P1.M2.T2.S1 — is gated explicitly (`grep _MIC_PROBE_TTL_S`), and this task runs last. The −1 reserves: a docs task's phrasing is ultimately a human judgment call, and an implementer could over-edit accurate prose or paraphrase the non-circular proof loosely — but the grep gates (stale claim gone, circular framing gone, evidence matches the test, only the two docs modified) catch structural regressions deterministically.
