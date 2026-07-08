# PRP — P1.M3.T1.S1: Update README.md sections spanning the full changeset (bugfix release)

## Goal

**Feature Goal**: Sweep `README.md` so it accurately reflects the post-bugfix state of the daemon — no stale claims about crash-loops, silent mic failures, or confusing exit codes. This is a Mode B changeset-level documentation task: the per-feature (Mode A) doc updates already landed inside the implementing subtasks, so the README is ~90% current. The job is ONE required addition (clause (c): the `install.sh` portaudio preflight is missing from the Install section) plus an accuracy/coherence verification pass over the other clauses.

**Deliverable** (ONE artifact, single-file edit):
- `README.md` — the "## Install" numbered list gains a portaudio-preflight step (clause (c), REQUIRED). All other sections are verified accurate against the actual source and left UNTOUCHED unless a verified inaccuracy is found (clauses a, b, e). Clause (d) is conditional and does NOT fire (no exit-code table exists in the README), so nothing is added for it.

**Success Definition**:
- (a) The "### Wrong microphone" + "## Logs, status, stopping" sections document `voicectl status`'s `mic:` line and the rate-limited mic-retry summary — verified accurate against `voice_typing/ctl.py` + `voice_typing/daemon.py` (already present; no change unless inaccurate).
- (b) The "## CPU-only mode" #3 + "### cuDNN load error" sections document the construction-failure→CPU fallback (degradation, not crash-loop) — verified accurate against `daemon.py:1159-1172` (already present; no change unless inaccurate).
- (c) The "## Install" numbered list NOW describes the portaudio preflight (`pacman -Q portaudio` → actionable abort; non-Arch warn-and-continue) — THE required addition.
- (d) NO exit-code table is added (the README has none; the conditional "if exit codes are documented" is unsatisfied). Verified by `grep`.
- (e) No stale claims remain (the "Restart=on-failure loops it forever" line in the Voice-activity section is about bad config keys, NOT CUDA — it is accurate and must NOT be "fixed").
- (f) No out-of-scope files: README.md is the ONLY file touched. No source code, no PRD.md/tasks.json/prd_snapshot.md/.gitignore, no install.sh/ctl.py/daemon.py. No new files.

## User Persona

**Target User**: "dustin, six months from now, and anyone who clones the repo" (README line 6). A Linux power user who wants exact commands, not hand-holding.

**Use Case**: After running `./install.sh`, the user wants to know what it did (incl. that it pre-checked portaudio) and how to diagnose mic/CUDA issues. The README is the single doc they reach for.

**User Journey**: clone → `./install.sh` (now aborts clearly if portaudio is missing, with the exact fix command) → read README to understand the mic-health line in `voicectl status`, the rate-limited journal noise, and the CUDA→CPU degradation behavior.

**Pain Points Addressed**: A user whose portaudio was missing previously hit a confusing "NOT active — check journalctl" after `uv sync` silently installed a wheel that couldn't dlopen. Now install.sh catches it up front, and the README should say so.

## Why

- **Closes the one real doc gap.** install.sh gained a portaudio preflight (P1.M2.T3.S1), but the README "Install" section still lists 6 steps that start at `uv sync` — the preflight is invisible to a reader. Clause (c) is the only REQUIRED prose change.
- **The rest is a correctness gate, not writing.** Clauses (a) mic health + rate-limit, (b) CPU fallback, were added by the implementing subtasks (Mode A). A changeset sweep must VERIFY they match the actual code (a README that misquotes a log line is worse than none). This PRP pins the verbatim source strings so the verification is deterministic.
- **Respects Mode A/Mode B boundary.** Per-feature doc updates belong to the implementing subtasks (already done). This task only sweeps cross-cutting overview docs and fills the one gap — it does not re-document features or invent new doc surfaces (e.g. an exit-code table).
- **Closes the bugfix milestone.** P1.M3 is "Changeset-Level Documentation Sync & Final Validation." This is the doc half; it must leave the README internally consistent so the release notes can point at it.

## What

A surgical edit to `README.md`:
1. **(c, REQUIRED)** Replace the "## Install" numbered list (6 steps) with a 7-step list that prepends the portaudio preflight (described accurately per `install.sh`). Verbatim replacement in Implementation Blueprint → Task 2.
2. **(a, b, e, VERIFY)** Read the mic / rate-limit / CPU-fallback / cuDNN sections and confirm they match the verified source strings in the research note. If accurate, leave untouched. If a verified inaccuracy is found, fix it minimally to match the source. Do NOT re-edit working prose.
3. **(d, SKIP)** Do nothing — the README has no exit-code table; the conditional does not fire. Verify with `grep` after editing.

### Success Criteria

- [ ] The "## Install" section's numbered list includes a step describing the portaudio preflight: runs `pacman -Q portaudio`, on failure aborts with `sudo pacman -S --noconfirm portaudio` + "re-run ./install.sh", and non-Arch hosts (no pacman) warn-and-continue.
- [ ] `grep -niE 'portaudio' README.md` now matches in BOTH the Requirements section AND the Install section (was: Requirements only).
- [ ] The "### Wrong microphone" section documents `voicectl status`'s `mic:` line (`mic: ok` / `mic: unavailable (<reason>)`) and the probe re-runs on each arm — accurate vs `ctl.py`/`daemon.py` (already present).
- [ ] The "## Logs, status, stopping" section documents the rate-limited mic-retry summary ("roughly once per minute") — accurate vs `daemon.py` `_MicRetryRateLimitFilter` `dedup_seconds=60.0` (already present).
- [ ] The "## CPU-only mode" #3 + "### cuDNN load error" sections document construction-failure→CPU fallback — accurate vs `daemon.py:1159-1172` (already present).
- [ ] `grep -niE 'exit|rc=|\$[?]|return code' README.md` returns "(none)" BEFORE and AFTER the edit (clause (d) not over-reached; no exit-code table invented).
- [ ] The "Restart=on-failure loops it forever" line (Voice-activity section) is UNCHANGED (it refers to bad config keys, not CUDA — accurate, not stale).
- [ ] README's fenced-code-block count (`grep -c '^```'`) stays EVEN (was 30) — no broken code fences.
- [ ] README.md is the ONLY file changed (`git status --porcelain` shows `M README.md` and nothing else).

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can do it from this PRP + the research note: the ONE required edit is given verbatim (exact old→new text for the Install numbered list); the verified source strings for every claim the README makes are pinned (status format, log lines, rate-limit period, install.sh portaudio behavior); the conditional clause (d) is resolved (do nothing, with the grep proof); the style is pinned (terse, command-first); and the validation greps are executable as written. No guessing.

### Documentation & References

```yaml
# MUST READ — the authoritative behavior spec (the contract for this doc task)
- file: README.md
  why: "The file being edited. Clause (c) edits the '## Install' numbered list (~lines 28-38).
        Clauses (a)/(b)/(e) VERIFY the mic, rate-limit, CPU-fallback, cuDNN, and Voice-activity
        sections against the source. Clause (d) grep-proves no exit-code table exists."
  critical: "README voice (line 6-7): terse, command-first, no hand-holding, for a Linux power
             user. Match it EXACTLY in added prose. Do not restate bugfix Issue numbers — the
             README is user-facing, not a changelog (write 'install.sh checks for portaudio',
             NOT 'Issue 6 fixed')."

# MUST READ — verified ground truth + the verbatim Install replacement + clause-by-clause status
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M3T1S1/research/readme_changeset_sweep.md
  why: "§1 the clause-by-clause status table (a/b done+verify, c GAP→fill, d conditional skip,
        e sweep). §2 the VERIFIED source strings the README must match (status format §2.1/§2.2;
        CUDA fallback log lines §2.3; mic rate-limit strings + the 60s dedup §2.4; mic probe on
        arm §2.5; install.sh portaudio behavior §2.6). §3 the accuracy check for a/b. §4 the
        exact portaudio-preflight prose points. §5 why clause (d) does nothing. §6 the stale-claim
        hunt (the 'Restart=on-failure loops forever' line is NOT stale). §7 style + scope. §8 the
        validation approach (no pytest for markdown; grep + manual read)."
  section: "ALL load-bearing. §2 (ground truth), §4 (the edit), §5 (clause d skip), §6 (e sweep)."

# MUST READ — the portaudio preflight behavior being documented (install.sh ~lines 48-62). READ, do NOT edit.
- file: install.sh
  why: "The source of truth for clause (c). Verbatim behavior: `if ! command -v pacman` → warn +
        continue; `elif ! pacman -Q portaudio` → stderr 'install.sh: portaudio not installed
        (PyAudio system dependency). Run: sudo pacman -S --noconfirm portaudio, then re-run
        ./install.sh' + exit 1. Runs BEFORE '[1/7] uv sync'."
  critical: "The README prose MUST capture three things (from this file): (1) it runs
             `pacman -Q portaudio`; (2) on failure it ABORTS (exit 1) with the exact
             `sudo pacman -S --noconfirm portaudio` command + 're-run ./install.sh'; (3) non-Arch
             hosts (no pacman) WARN and CONTINUE. Do NOT edit install.sh — it is DONE; this task
             only documents it."

# SHOULD READ — status output format (verifies the README's 'Typical CUDA output' block). READ, do NOT edit.
- file: voice_typing/ctl.py
  why: "format_result() (~lines 60-95) emits the status block lines: listening/partial/last/
        uptime/device (...)/models (...)/mic: ok | mic: unavailable (<error>). The README's block
        matches EXACTLY — confirms clause (a). The JSON fields are mic_ok/mic_error; the HUMAN line
        is `mic:` — the README correctly uses the human form (do not change `mic:` to `mic_ok:`)."
  critical: "Do NOT edit ctl.py (P1.M2.T4.S1 already landed: _EX_USAGE=64, nargs='?'). This task
             only VERIFIES the README against it. The README has NO exit-code table (clause d skip)."

# SHOULD READ — the log strings + rate-limit + CUDA-fallback source. READ, do NOT edit.
- file: voice_typing/daemon.py
  why: "Verbatim strings to verify the README against: §2.3 'CUDA recorder construction failed
        (%s); falling back to CPU (...) — degraded but functional' (line 1159-1160) +
        'daemon started in degraded CPU mode (construction-failure fallback)' (line 1172);
        §2.4 _MicRetryRateLimitFilter dedup_seconds=60.0/summary_every=20 (line 1028) +
        'Microphone still unavailable after {count} retry attempts (last error: {error})'
        (lines 996-997); §2.5 _arm() calls _refresh_mic_status() (line 546)."
  critical: "Do NOT edit daemon.py. The README quotes these with `...` elision (acceptable); a
             minor nit is the README drops the '(construction-failure fallback)' suffix on the
             second string — fixing that is OPTIONAL, not required."

# CONTEXT — the parallel sibling (disjoint: edits ctl.py + test_voicectl.py, NOT README).
- file: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T4S1/PRP.md
  why: "P1.M2.T4.S1 (exit-code-64 remap) edits voice_typing/ctl.py + tests/test_voicectl.py ONLY.
        Its research EXPLICITLY says 'README is OUT of scope; changeset README sync is
        P1.M3.T1.S1' — i.e. THIS task. Confirms (1) the 64-exit-code work is DONE (ctl.py already
        has _EX_USAGE=64/nargs='?'), and (2) clause (d)'s 'if exit codes are documented' conditional
        was designed to be checked HERE, and since the README has no exit-code table, it does not
        fire. No file overlap (README.md vs ctl.py/test_voicectl.py)."
  critical: "Do NOT duplicate the exit-code work or add an exit-code table to the README (the
             conditional does not fire; the table belongs in ctl.py docstrings, already done)."
```

### Current Codebase tree (state at P1.M3.T1.S1 start)

```bash
$ ls -1   # the only file this task touches:
README.md                     # <-- EDIT (clause (c) Install list; verify a/b/e; skip d)
# Supporting (READ-ONLY, do NOT edit):
install.sh                    # source of truth for the portaudio preflight (clause c)
voice_typing/ctl.py           # source for status output format (clause a)
voice_typing/daemon.py        # source for log strings + rate-limit + CUDA fallback (clauses a/b)
PRD.md                        # READ-ONLY (forbidden)
plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M2T4S1/PRP.md   # parallel sibling (disjoint)
```

### Desired Codebase tree with files to be added

```bash
README.md                     # MODIFIED: Install numbered list gains a portaudio-preflight step
                              #   (clause c). All other sections verified + left intact unless
                              #   a verified inaccuracy is found (clauses a/b/e). No exit-code
                              #   table added (clause d conditional does not fire).
# NOTHING ELSE. No new files. No source edits. No PRD/tasks/.gitignore changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE README IS ~90% DONE; DON'T OVER-EDIT. Clauses (a) mic health + rate-limit and
#   (b) CPU construction-failure fallback ALREADY landed (Mode A, in the implementing subtasks) and
#   are VERIFIED accurate against ctl.py/daemon.py. The ONLY required prose addition is clause (c)
#   (portaudio preflight in the Install list). Clauses (a)/(b)/(e) are a VERIFICATION pass: read,
#   confirm accuracy, leave untouched unless you find a genuine inaccuracy. Re-editing working prose
#   risks regressions and is out of scope. (Research §1, §3.)

# CRITICAL #2 — CLAUSE (d) DOES NOT FIRE. The item's clause (d) is conditional: "IF exit codes are
#   documented, note usage errors now exit 64". `grep -niE 'exit|rc=|\$[?]|return code' README.md`
#   returns "(none)" — the README documents voicectl status OUTPUT but never its exit codes. So the
#   conditional is unsatisfied → DO NOTHING for (d). Do NOT invent an exit-code table (out of scope;
#   the 64 contract lives in ctl.py docstrings, already updated by P1.M2.T4.S1). After editing,
#   re-run the grep to prove you did not over-reach. (Research §5.)

# CRITICAL #3 — THE "Restart=on-failure loops it forever" LINE IS NOT STALE. README ~line 143
#   (Voice-activity section) says a stray config key makes the daemon "fail to load and systemd's
#   Restart=on-failure loops it forever." This is about a BAD CONFIG KEY (TypeError from the config
#   loader), which WOULD still crash-loop. The bugfix CPU fallback is for CUDA CONSTRUCTION failure,
#   NOT config errors. These are different failure modes. Do NOT "fix" this line — it is accurate.
#   (Research §6.)

# CRITICAL #4 — THE PORTAUDIO PREFLIGHT HAS THREE PARTS (install.sh). The clause-(c) prose MUST
#   capture all three, or it is inaccurate: (1) runs `pacman -Q portaudio` (Arch-specific); (2) on
#   failure ABORTS (exit 1) with the exact command `sudo pacman -S --noconfirm portaudio` + tells
#   the user to re-run `./install.sh`; (3) non-Arch hosts (no pacman) WARN and CONTINUE (no abort).
#   Omitting the non-Arch warn-and-continue would imply install.sh hard-fails on every non-Arch box.
#   (Research §2.6, §4; install.sh ~lines 48-62.)

# CRITICAL #5 — portaudio IS COMPLEMENTARY, NOT DUPLICATIVE, to the Requirements bullet. README
#   line 18 (Requirements) says: "`portaudio` (PyAudio build dep). Check it with `pacman -Q
#   portaudio`." That is the "you need this" statement. The new Install step is "install.sh verifies
#   it for you." Keep BOTH — they are complementary, not redundant. Do NOT delete the Requirements
#   bullet. (Research §4.)

# CRITICAL #6 — MATCH THE README's VOICE OR THE EDIT WILL LOOK INCONSISTENT. README line 6-7:
#   "for two readers: dustin, six months from now, and anyone who clones the repo … assumes a Linux
#   power user who wants exact commands, not hand-holding." TERSE, command-first, no marketing
#   language, no hand-holding, no exclamation marks, no em-dash spam (the existing README uses plain
#   hyphens + short sentences). The added portaudio step must read like the surrounding steps. (Research §7.)

# CRITICAL #7 — NO CHANGELOG VOICE. The README is user-facing, not a release-notes file. Do NOT
#   write "Issue 6 fixed", "this was a bug", "previously install.sh skipped…". Describe BEHAVIOR:
#   "install.sh checks for portaudio and aborts with the install command if it is missing." (Research §7.)

# GOTCHA #8 — THE STATUS OUTPUT IS `mic:`, NOT `mic_ok:`. The JSON protocol fields are mic_ok /
#   mic_error; the HUMAN voicectl status line is `mic: ok` / `mic: unavailable (<reason>)`. The item
#   says "mic_ok/mic_error fields" referring to the internal fields; the README correctly documents
#   the human `mic:` line. Do NOT "fix" the README to say `mic_ok:` — that would be wrong. (Research §2.1.)

# GOTCHA #9 — NO TEST FRAMEWORK APPLIES. README.md is markdown; there is no pytest/ruff/mypy gate.
#   Validation is: grep checks (portaudio now in 2 sections; exit-code grep still none; fenced-block
#   count stays EVEN) + a manual accuracy read. Do NOT invent a lint command. (Research §8.)

# GOTCHA #10 — ONE INTERNAL ANCHOR LINK MUST STAY VALID. The "## Logs, status, stopping" section
#   contains `[Wrong microphone](#wrong-microphone)`. GitHub markdown lowercases the heading and
#   replaces spaces with hyphens for anchors. Clause (c) does NOT touch the "Wrong microphone"
#   heading, so the anchor stays valid. Just do not rename that heading. (Research §8.)
```

## Implementation Blueprint

### Data models and structure

Not applicable — no code, no data models. This is a single markdown-file edit.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: PREFLIGHT — confirm the README's current state matches the research (no mutation yet)
  - RUN (from /home/dustin/projects/voice-typing):
      grep -niE 'portaudio' README.md                       # expect: ONLY line 18 (Requirements)
      grep -niE 'exit|rc=|\$[?]|return code' README.md      # expect: "(none)" — clause (d) skip proof
      grep -c '^```' README.md                              # expect: 30 (EVEN) — fence-balance baseline
      grep -nE '^#{1,3} ' README.md                         # expect: 15 headers — structure baseline
      sed -n '28,38p' README.md                             # the Install numbered list (edit anchor)
      # sanity: the source of truth exists and is unchanged:
      grep -n 'portaudio not installed' install.sh          # expect: the actionable-abort message
      grep -n 'Microphone still unavailable' voice_typing/daemon.py   # expect: the rate-limit summary
      grep -n 'falling back to CPU' voice_typing/daemon.py  # expect: the CUDA-fallback line
  - EXPECTED: portaudio in README only at line 18; exit-code grep "(none)"; 30 fences; 15 headers;
    the Install list matches the Task-2 anchor verbatim; the three source strings all present.
  - DO NOT: edit anything yet.

Task 2: EDIT README.md — clause (c): the Install numbered list portaudio-preflight step (REQUIRED)
  - FILE: README.md
  - ANCHOR (the numbered list under "## Install", README ~lines 28-38):
        1. `uv sync` (creates or refreshes `.venv/`).
        2. A CUDA smoke that prints `VERDICT=cuda-ok` or `VERDICT=cpu-fallback-required`.
        3. Prefetches the whisper models into `~/.cache/huggingface` (warn-only on miss).
        4. Installs, daemon-reloads, enables, and restarts the systemd user unit.
        5. Copies `config.toml` to `~/.config/voice-typing/config.toml` if absent (never
           overwrites an existing one).
        6. Prints the usage line, the tmux snippet, the Hyprland source line, and the logs
           command.
  - REPLACE WITH (prepend the portaudio preflight as step 1; renumber 1→7; keep the existing 6
    items' wording unchanged):
        1. Checks that `portaudio` (PyAudio's system dependency) is installed. On Arch it runs
           `pacman -Q portaudio`; if that fails it aborts with the exact
           `sudo pacman -S --noconfirm portaudio` command and asks you to re-run `./install.sh`.
           Hosts without `pacman` get a warning and continue (install portaudio yourself).
        2. `uv sync` (creates or refreshes `.venv/`).
        3. A CUDA smoke that prints `VERDICT=cuda-ok` or `VERDICT=cpu-fallback-required`.
        4. Prefetches the whisper models into `~/.cache/huggingface` (warn-only on miss).
        5. Installs, daemon-reloads, enables, and restarts the systemd user unit.
        6. Copies `config.toml` to `~/.config/voice-typing/config.toml` if absent (never
           overwrites an existing one).
        7. Prints the usage line, the tmux snippet, the Hyprland source line, and the logs
           command.
  - USE the `edit` tool with the EXACT oldText/newText above (the 6-item list is unique in the file).
  - ACCURACY CHECK for the new step 1 (all three parts from install.sh §2.6): (1) `pacman -Q
    portaudio`; (2) abort + `sudo pacman -S --noconfirm portaudio` + re-run; (3) non-Arch warn +
    continue. (Gotcha #4.)
  - DO NOT: touch the Requirements portaudio bullet (line 18 — complementary, Gotcha #5); change
    any other section in this task; add an exit-code table (clause d, Gotcha #2).

Task 3: VERIFY clauses (a), (b), (e) — read-only accuracy pass (NO edit unless inaccurate)
  - READ the following README sections and confirm they match the verified source strings in
    research §2. If they match, DO NOTHING. If you find a VERIFIED inaccuracy, fix it minimally
    to match the source (use `edit` with the smallest possible oldText/newText).
  - (a) MIC: "### Wrong microphone" (~line 202) must show `mic: ok` / `mic: unavailable (<reason>)`
        + "the probe re-runs on each arm". "## Logs, status, stopping" (~line 237) rate-limit para
        must say the traceback logs once then a WARNING summary "roughly once per minute".
        SOURCE: ctl.py format_result; daemon.py _MicRetryRateLimitFilter dedup_seconds=60.0; _arm()
        calls _refresh_mic_status (line 546). EXPECTED: accurate, no change.
  - (b) CPU FALLBACK: "## CPU-only mode" #3 (~line 160) + "### cuDNN load error" degradation para
        (~line 197) must describe construction-failure→CPU (degraded, not crash-loop) + the log
        lines + `voicectl status` shows `device: cpu (int8)`.
        SOURCE: daemon.py lines 1159-1172. EXPECTED: accurate (minor OPTIONAL nit: the README
        drops '(construction-failure fallback)' from the second log string — fixing is OPTIONAL).
  - (e) STALE HUNT: confirm the "Restart=on-failure loops it forever" line (~line 143) is about
        BAD CONFIG KEYS (accurate, NOT stale — Gotcha #3) and is UNCHANGED. Confirm no claim of
        "silent mic failure" or "CUDA crash-loop" remains (they are now the degradation/mic-health
        narratives). EXPECTED: nothing to change.
  - IF Task 3 made NO edits: that is the EXPECTED outcome (the README is already accurate). Do not
    manufacture edits to justify the task.

Task 4: VALIDATE (no file change beyond Task 2/3 — see Validation Loop)
  - Run the grep checks (portaudio now 2 sections; exit-code grep still none; fences still EVEN;
    headers still 15; anchor link intact) + a manual accuracy read.
  - `git status --porcelain` must show ONLY `M README.md`.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M3.T1.S1: README changeset sweep — Install section documents the portaudio preflight; mic/
    CPU-fallback sections verified accurate against source".
```

### Implementation Patterns & Key Details

```markdown
<!-- PATTERN: the Install list describes USER-VISIBLE behavior, not implementation. Each step is
     one imperative sentence (sometimes two) with the exact command in backticks. The new portaudio
     step follows the same shape as "A CUDA smoke that prints VERDICT=...". -->
1. Checks that `portaudio` (PyAudio's system dependency) is installed. On Arch it runs
   `pacman -Q portaudio`; if that fails it aborts with the exact
   `sudo pacman -S --noconfirm portaudio` command and asks you to re-run `./install.sh`.
   Hosts without `pacman` get a warning and continue (install portaudio yourself).

<!-- PATTERN: when VERIFYING (Task 3), compare README prose to the verbatim source string. If they
     agree (modulo `...` elision), LEAVE IT. The README quotes:
       "CUDA recorder construction failed (...); falling back to CPU ... — degraded but functional"
     and the source (daemon.py:1159) is:
       "CUDA recorder construction failed (%s); falling back to CPU (...) — degraded but functional"
     These AGREE. Do not edit. -->

<!-- GOTCHA: do NOT convert the README's `mic:` line to `mic_ok:`. The protocol field is mic_ok; the
     human status line is `mic: ok`. The README is correct. -->

<!-- GOTCHA: do NOT add a "voicectl exit codes" section/table. The README has none; clause (d)'s
     conditional does not fire. The 64-exit-code contract is documented in ctl.py docstrings. -->
```

### Integration Points

```yaml
NO code/config/protocol integration points.
  - This task edits a single markdown file. No source, no config.toml, no socket/protocol change.
  - DOCUMENTATION ONLY: README.md is the sole output. It is consumed by humans (the clone-and-run
    path) and referenced by the bugfix release notes.
SIBLING (parallel, disjoint): P1.M2.T4.S1 edits voice_typing/ctl.py + tests/test_voicectl.py — NO
  file overlap with README.md. Its exit-code work is DONE; this task does NOT re-document it.
```

## Validation Loop

> No test framework applies to a markdown file (Gotcha #9). Validation is grep checks + a manual
> accuracy read. Run from `/home/dustin/projects/voice-typing`. Use the `edit` tool for the change.

### Level 1: Structure intact (grep checks)

```bash
cd /home/dustin/projects/voice-typing
echo "--- headers (expect 15, same set as pre-edit) ---"
grep -nE '^#{1,3} ' README.md | wc -l        # expect 15
echo "--- fenced blocks (expect EVEN, was 30) ---"
test $(( $(grep -c '^```' README.md) % 2 )) -eq 0 && echo "OK: balanced fences" || echo "FAIL: unbalanced fences"
echo "--- internal anchor link intact ---"
grep -n 'wrong-microphone' README.md          # expect the link in Logs section; heading unchanged
# Expected: 15 headers; balanced fences (count is even); the [Wrong microphone](#wrong-microphone)
#   link is present and the '### Wrong microphone' heading is unchanged.
```

### Level 2: Clause-specific checks

```bash
cd /home/dustin/projects/voice-typing
echo "--- (c) portaudio now in BOTH Requirements AND Install ---"
grep -niE 'portaudio' README.md              # expect >=2 matches: line ~18 (Requirements) + the new Install step
echo "--- (d) exit-code grep STILL none (did NOT over-reach) ---"
grep -niE 'exit|rc=|\$[?]|return code' README.md && echo "FAIL: added exit-code text (clause d over-reach)" || echo "OK: no exit-code table (clause d correctly skipped)"
echo "--- (e) stale-claim line UNCHANGED ---"
grep -n 'Restart=on-failure loops it forever' README.md   # expect the line still present (it is accurate, about config keys)
# Expected: portaudio in 2+ sections; exit-code grep "(none)"; the Restart=on-failure line intact.
```

### Level 3: Accuracy read (manual)

```bash
cd /home/dustin/projects/voice-typing
# Read the edited Install section and the verified sections side-by-side with the source:
sed -n '20,42p' README.md                     # the Install section (new portaudio step must be accurate)
# Cross-check the new step's three claims against install.sh:
grep -nE 'pacman -Q portaudio|sudo pacman -S --noconfirm portaudio|non-Arch|re-run' install.sh
# Cross-check the README's quoted log lines against daemon.py (clauses a/b accuracy):
grep -nE 'falling back to CPU|degraded CPU mode|Microphone still unavailable' voice_typing/daemon.py
# Expected: every claim in the README's new portaudio step has a matching verbatim line in install.sh;
#   the mic/CPU-fallback sections' quoted strings match daemon.py (modulo `...` elision).
```

### Level 4: Scope guard

```bash
cd /home/dustin/projects/voice-typing
echo "--- ONLY README.md changed ---"
git status --porcelain                        # expect: " M README.md" and nothing else
# Any change to install.sh / voice_typing/* / PRD.md / tasks.json / .gitignore is a SCOPE VIOLATION.
# (The parallel P1.M2.T4.S1 touches ctl.py + test_voicectl.py — those are NOT this task's changes; if
#  they appear in git status it is the sibling task, expected, not a violation by THIS task.)
echo "--- no new files ---"
git status --porcelain | grep '^??' && echo "FAIL: untracked files created (out of scope)" || echo "OK: no new files"
# Expected: only " M README.md" (this task). Sibling untracked/modified files, if any, belong to
#   P1.M2.T4.S1 — not this task's concern.
```

## Final Validation Checklist

### Technical Validation

- [ ] `grep -nE '^#{1,3} ' README.md | wc -l` → 15 (structure intact).
- [ ] `grep -c '^```' README.md` is EVEN (fences balanced; was 30).
- [ ] `[Wrong microphone](#wrong-microphone)` link present; `### Wrong microphone` heading unchanged.
- [ ] `git status --porcelain` shows ONLY `M README.md` from this task (no new files).

### Feature Validation

- [ ] **(c)** Install section's numbered list has a portaudio-preflight step with all three parts: `pacman -Q portaudio`; abort + `sudo pacman -S --noconfirm portaudio` + re-run; non-Arch warn-and-continue.
- [ ] **(c)** `grep -niE 'portaudio' README.md` matches in BOTH Requirements AND Install.
- [ ] **(a)** Wrong-microphone + Logs sections document the `mic:` line + rate-limited summary — accurate vs ctl.py/daemon.py (left intact or minimally fixed).
- [ ] **(b)** CPU-only-mode #3 + cuDNN sections document construction-failure→CPU fallback — accurate vs daemon.py:1159-1172 (left intact or minimally fixed).
- [ ] **(d)** `grep -niE 'exit|rc=|\$[?]|return code' README.md` → "(none)" (no exit-code table invented).
- [ ] **(e)** "Restart=on-failure loops it forever" line UNCHANGED (accurate; about config keys, not CUDA).

### Code Quality Validation

- [ ] Added prose matches the README's terse, command-first voice (no marketing, no hand-holding, no changelog voice).
- [ ] No bugfix Issue numbers / "this was a bug" language in the README (user-facing, not release-notes).
- [ ] The `mic:` line was NOT changed to `mic_ok:` (human form is correct).
- [ ] The Requirements portaudio bullet (line 18) was NOT deleted (complementary to the new Install step).
- [ ] Verified-accurate sections were left UNTOUCHED (no gratuitous re-editing).

### Documentation & Deployment

- [ ] README is internally consistent (no stale crash-loop / silent-mic / confusing-exit claims).
- [ ] The Install list now matches what `install.sh` actually does (portaudio preflight first).
- [ ] No new env vars / config keys / user-facing surfaces introduced (pure doc).

---

## Anti-Patterns to Avoid

- ❌ Don't rewrite the whole README — it is ~90% done; the only REQUIRED addition is the portaudio preflight (clause c). Re-editing accurate prose risks regressions.
- ❌ Don't add an exit-code table — clause (d) is conditional and the README has no exit-code documentation. The 64 contract lives in ctl.py docstrings (already done by P1.M2.T4.S1).
- ❌ Don't "fix" the "Restart=on-failure loops it forever" line — it is about bad config keys (TypeError), which still crash-loop; it is accurate, not stale.
- ❌ Don't change `mic:` to `mic_ok:` — `mic:` is the human voicectl status line; `mic_ok` is the internal JSON field. The README is correct.
- ❌ Don't delete the Requirements portaudio bullet — it complements the new Install step.
- ❌ Don't omit any of the portaudio preflight's three behaviors (`pacman -Q`; abort + exact command + re-run; non-Arch warn-and-continue) — an incomplete description is inaccurate.
- ❌ Don't write changelog voice ("Issue 6 fixed", "previously install.sh skipped…") — the README is user-facing; describe behavior.
- ❌ Don't edit any file other than README.md — this is Mode B docs; the bugfix code is DONE.
- ❌ Don't invent a lint/test command for markdown — validation is grep checks + a manual accuracy read.
- ❌ Don't manufacture edits for clauses (a)/(b) if they are already accurate — verification can conclude "no change needed"; that is the expected outcome.

---

**Confidence Score: 9/10** for one-pass success. The task is small and fully bounded: ONE required verbatim edit (the Install numbered list, with the exact old→new text and the three accuracy points pinned to install.sh), plus a read-only verification pass with the source strings quoted verbatim. The conditional clause (d) is resolved with a grep proof; the "don't touch the accurate prose / don't fix the non-stale Restart line" guardrails prevent the two most likely over-reach failures. The −1 reserves: a docs task's correctness is ultimately a human judgment call on phrasing, and an implementer could still over-edit working prose or paraphrase the portaudio behavior loosely — but the grep gates (portaudio in 2 sections, exit-code grep still none, fences balanced, only README.md modified) will catch scope/structure regressions deterministically.
