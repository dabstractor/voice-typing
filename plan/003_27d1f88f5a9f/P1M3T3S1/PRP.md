# PRP — P1.M3.T3.S1: README sweep for lazy-load + idle-unload + bounded teardown

## Goal

**Feature Goal**: Rewrite `README.md` (currently ~294 lines, stale — describes boot-time GPU residency) so it
**accurately documents the LANDED lazy-load model lifecycle** (PRD §4.2bis/§4.5/§4.9; code: M2.T1 lazy-load +
M3.T1.S1 idle-unload + M1.T1 bounded teardown, all Complete). Five concrete edits + one status-example update:
(a) add `asr.auto_unload_idle_seconds` to the config-tuning table; (b) rewrite the "Confirm the models are
resident in GPU VRAM" section to the lazy-load lifecycle; (c) add a "first arm loads models (~1-3s)" note to
the First-run section + the `loading models…` hint; (d) add a bounded-quit note (no more ~90s systemd hang);
(e) stale-phrasing sweep + status-example alignment. **No stale boot-time-residency claim remains.**

**Deliverable**: An updated `README.md` that (1) documents ~0 VRAM at boot, lazy load on first
`voicectl start`/`toggle` (~1-3s, with the `loading models… (first arm, ~1–3 s)` stderr hint), residency
until `quit` or 30-min disarmed idle (`auto_unload_idle_seconds`), reload on next arm, and the bounded ≤10s
teardown; (2) has the new config-table row; (3) has a `voicectl status` example that matches the LANDED
`ctl.py:85-93` output (`phase:` line + `models: ... (loaded|not loaded)` marker). **Optional**: a one-line
alignment to `install.sh`'s final echo (see Task 7 — contract trigger NOT met; do it only for coherence).

**Success Definition**:
- (a) `grep` proves ZERO stale boot-time-residency claims in `README.md` (the old "Confirm the models are
  resident" framing is GONE; no "models load at boot" / "always resident" implication).
- (b) README now contains: `~0 VRAM`, `phase:` (in the status example), `(loaded)`/`(not loaded)`,
  `loading models…`, `auto_unload_idle_seconds`, `idle-unload` / `idle unload`, `unloaded`, and the bounded
  teardown (≤10s / "no ~90s hang").
- (c) The config-table row for `asr.auto_unload_idle_seconds` mirrors the `auto_stop_idle_seconds` row style.
- (d) `git status --short` shows ONLY `M README.md` (+ optionally `M install.sh` if Task 7 done).
- (e) No edits to `voice_typing/*.py` (Mode A code comments are ALREADY lazy-load correct — verified),
  `config.toml` (already documents the knob — M3.T1.S1), `PRD.md`, `tasks.json`, `prd_snapshot.md`,
  `.gitignore`, or any test file. This is the docs task (Mode B).

## User Persona

**Target User**: dustin six months from now + anyone who clones the repo. A Linux power user who wants exact
commands and accurate lifecycle expectations, not hand-holding. (This README's own stated audience.)

**Use Case**: Read README to understand GPU/VRAM behavior: "does voice-typing hog my GPU at boot? when do
models load? how do I free VRAM? is `voicectl quit` slow?" — and get correct answers matching the running code.

**Pain Points Addressed**: The current README lies about the lifecycle — it frames models as always-resident
(boot-time residency) and its `voicectl status` example omits the `phase:`/`(loaded)` lines the actual CLI
prints. A reader following it would misjudge VRAM use, misread `voicectl status` output, and be surprised by
the first-arm load delay and the idle-unload.

## Why

- **This IS the docs task (Mode B).** The delta's changeset-level documentation is done here. M1.T1 (bounded
  teardown), M2.T1 (lazy load), M3.T1.S1 (idle-unload + config knob) are all LANDED and the running daemon
  behaves per PRD §4.2bis — but README still documents the OLD eager-at-boot model. PRD §7.6/§7.9 pin the
  user-visible lifecycle (un-loaded boot, ~0 VRAM until first arm, idle-unload reclaims VRAM, bounded teardown).
- **No stale claims may survive.** PRD §7.6 requires the README to document the lifecycle accurately; leaving
  "models are resident in GPU VRAM" (implying boot-time) contradicts the feature's core value prop
  ("stop taxing the GPU on boots where the feature is never used" — PRD §4.2bis).
- **Cheap, self-contained, disjoint from the parallel item.** P1.M3.T2.S2 (parallel) edits
  `tests/test_idle_and_gpu.sh` + `tests/ACCEPTANCE.md`; THIS task edits `README.md`. No conflict. No new deps.
  No production code touched.

## What

Apply the five contract edits (a–e) to `README.md`, plus align the stale status example. All text is
documentation (Mode B). The behavior being documented is LANDED — read it from the code (research §0/§1/§2),
do not re-derive or invent.

- **(a) Config table** (`## Configuration`, after the `asr.auto_stop_idle_seconds` row, README.md:~132): add a
  `| asr.auto_unload_idle_seconds | 1800.0 | … |` row mirroring the sibling row's 3-col style. State: tears
  down models to free VRAM after N seconds DISARMED (loaded, not listening); clock starts on disarm, resets on
  any arm, time listening doesn't count; `0` disables (models stay resident until `quit`); next arm reloads
  (~1-3s). Cross-reference the lifecycle section.
- **(b) GPU/lifecycle section** (rewrite "Confirm the models are resident in GPU VRAM:", README.md:~283): the
  headline rewrite. Replace the always-resident framing with the lazy-load lifecycle: ~0 VRAM at boot
  (unloaded), first `voicectl start`/`toggle` loads (~1-3s, prints `loading models… (first arm, ~1–3 s)`),
  resident until `quit` or `auto_unload_idle_seconds` (30 min default) of disarmed idle, unload frees VRAM
  (~0), next arm reloads (~1-3s). Surface the `phase:` values (unloaded→loading→idle→listening) and keep the
  `nvidia-smi` command (now used to verify the per-state VRAM, not "confirm resident").
- **(c) First-run note** (`## First run`, README.md:~49): add a short note that the first
  `voicectl toggle`/`start` each session takes ~1-3s to load the models (`voicectl` prints
  `loading models… (first arm, ~1–3 s)`); subsequent arms are instant.
- **(d) Bounded-quit note** (near "Stop or disable the daemon", README.md:~290): note that `voicectl quit`
  and `systemctl --user stop` now complete in seconds — teardown is bounded at ≤10s (worker processes
  force-terminated if `recorder.shutdown()` wedges), so the old ~90s systemd stop timeout hang is gone.
- **(e) Stale-phrasing sweep + status-example alignment**: confirm no remaining boot-time-residency drift
  (the sweep in research §3/§4 found the only stale claim is the §b framing + the status example; fix both).
  Update the `voicectl status` "Typical CUDA output" example (README.md:~266-277) to match `ctl.py:85-93`
  (add the `phase:` line + the `(loaded)` marker).
- **Optional (Task 7)**: align `install.sh`'s final echo if a small lazy-load note improves coherence — see
  the task; the contract trigger is NOT met.

### Success Criteria

- [ ] `grep -niE 'confirm the models are resident|models load at boot|always resident|resident at boot' README.md`
      → **zero hits** (the boot-time-residency framing is gone).
- [ ] `grep -niE '~0 ?VRAM|loading models|auto_unload_idle_seconds|idle-unload|unloaded|bounded' README.md`
      → hits in the config table, the lifecycle section, the First-run note, and the stop note.
- [ ] The `voicectl status` example in README shows `phase:` and `models: … (loaded)` matching `ctl.py:85-93`.
- [ ] `git status --short` → ` M README.md` only (or `+ M install.sh` if Task 7 done); NO `voice_typing/*`,
      NO `config.toml`, NO `PRD.md`, NO test files.
- [ ] Markdown renders: code fences balanced, table rows well-formed, no broken links.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior knowledge: the exact lazy-load lifecycle to document is pinned from the
LANDED code with verbatim log/CLI strings (research §0 — boot state, phases, idle-unload log, bounded-teardown
timeout); the exact `voicectl status` surface is quoted VERBATIM from `ctl.py:85-93` (research §1) so the
example matches; the config knob's default/semantics are pinned (research §2); the stale-phrasing sweep
results are enumerated line-by-line (research §3) so the implementer knows EXACTLY what is stale and what is
fine; the README section map (research §6) gives precise edit locations; the validation greps are given
(research §8). The PRD anchors (research §7) are read-only. The code-comment cross-check (research §4) proves
NO `voice_typing/*.py` edits are needed (Mode A already done).

### Documentation & References

```yaml
# MUST READ — the behavior spec (the contract this README documents). READ, do NOT edit.
- docfile: PRD.md
  why: "§4.2bis (h2.3/h3.2): the lazy-load lifecycle states (unloaded/loading/loaded-not-listening/
        loaded-listening) + Idle unload ('after auto_unload_idle_seconds of sitting disarmed ... tears the
        recorder down ... frees the ~1.5-3GB VRAM; clock starts on disarm, resets on arm; 0 disables') +
        the bounded-teardown HARD requirement ('recorder.shutdown() MUST complete in well under the
        arm-latency budget ... MUST NOT reproduce the ~90s teardown hang'). §4.5 (h2.3/h3.5): config.toml
        with auto_unload_idle_seconds=1800.0 + the idle-stop (30s) vs idle-unload (30min) composition.
        §4.9 (h2.3/h3.9): 'daemon starts not-listening and not-loaded (~0 VRAM at idle); first arm loads
        models ~1-3s'. §7.6/§7.9 (h2.6): acceptance — un-loaded boot, idle-unload reclaims VRAM, bounded
        teardown (completes in seconds, no 90s hang)."
  critical: "Do NOT edit PRD.md (forbidden). The README must MATCH the behavior described here. The
             '~1.5-3 GB' figure is the LOADED-state VRAM footprint (paid on first arm), NOT a boot cost."

# MUST READ — this task's research (the verbatim lifecycle/CLI strings + the line-by-line stale map)
- docfile: plan/003_27d1f88f5a9f/P1M3T3S1/research/readme_lazyload_sweep.md
  why: "§0 the lifecycle states table + VERBATIM log strings (success log 'voice-typing models loaded (lazy
        load complete); recorder resident' daemon.py:566; idle-unload log 'voice-typing idle-unload: %.1fs
        disarmed; unloading models' daemon.py:844; bounded teardown HARD timeout=10.0s daemon.py:1030).
        §1 the VERBATIM voicectl status block (ctl.py:85-93) + the 'loading models… (first arm, ~1–3 s)'
        stderr hint (ctl.py:133). §2 the config knob (config.py:78 default 1800.0; 0 disables). §3 the
        stale-phrasing sweep (README lines 46-47, 132, 266-277, 283, 286 — verdict per line). §4 the code-
        comment cross-check (all 'resident' uses are correct — NO voice_typing edits needed). §5 install.sh
        check (no residency blurb — optional alignment only). §6 the README section map. §8 validation greps."
  section: "ALL load-bearing. §0 (lifecycle), §1 (status surface), §3 (stale map), §6 (section map), §8 (validation)."

# MUST READ — the file being rewritten. READ IN FULL before editing.
- file: README.md
  why: "The ONLY primary deliverable. Edit sites: line 46-47 (Install 'NOT listening' — add not-loaded);
        line 49-71 (First run — add first-arm-load note); line 132 (config table — add auto_unload_idle row);
        line 266-277 (status example — add phase: + (loaded)); line 283-286 (GPU section — REWRITE to
        lifecycle); line 290-294 (stop/quit — add bounded-quit note). Keep all other sections (Requirements,
        Hotkey, tmux, CPU-only mode, Troubleshooting cuDNN/mic/wtype) UNCHANGED."
  pattern: "3-col config table (| Section.key | Default | Effect |); fenced ```bash-style code blocks; the
            'dustin six months from now' voice (exact commands, no hand-holding)."
  gotcha: "Line numbers shift as you edit — grep for the ANCHOR text (e.g. 'Confirm the models are resident',
           'auto_stop_idle_seconds', 'Typical CUDA output') rather than relying on absolute line numbers."

# MUST READ — the LANDED status surface (quote it VERBATIM into the README example). READ, do NOT edit.
- file: voice_typing/ctl.py
  why: "Lines 85-93: the EXACT voicectl status output block the README example must match. Line 84:
        loaded_marker = 'loaded' if models_loaded else 'not loaded'. Line 87: f'phase: {phase}'. Line 133:
        the 'loading models… (first arm, ~1–3 s)' stderr hint (quote it in the First-run note). Line 42:
        _LOADING_HINT_DELAY=0.3 (why the hint only fires on real first-arm loads)."
  critical: "Do NOT edit ctl.py (docs-only). The README status example is a STALE copy of the OLD ctl.py
             output — it must be updated to the CURRENT 8-line block (adds phase: + (loaded))."

# MUST READ — the LANDED lifecycle impl (the behavior to describe). READ, do NOT edit.
- file: voice_typing/daemon.py
  why: "455-469 boot state (_recorder=None, _models_loaded=False, phase='unloaded' → ~0 VRAM). 486-569
        _load_recorder single-flight (first arm ~1-3s; second arm waits, no 2nd load). 818-852 _unload_recorder
        (idle-unload → unloaded → ~0 VRAM) + the idle-unload log line 844. 1030-1079 _bounded_shutdown (HARD
        timeout=10.0s; force-terminates transcript_process+reader_process on timeout). 566 success log
        'voice-typing models loaded (lazy load complete); recorder resident'."
  critical: "Do NOT edit daemon.py (docs-only). The lifecycle prose in README must match these semantics.
             The bounded-teardown ≤10s value is the figure to cite (M1 fix for the old ~90s hang)."

# READ — the config knob (confirm default + 0-disables; do NOT edit — M3.T1.S1 owns it).
- file: voice_typing/config.py
  why: "Lines 74-89 AsrConfig: auto_unload_idle_seconds: float = 1800.0 (line 78; 0 disables). Line 76
        auto_stop_idle_seconds: float = 30.0 (the sibling row already in the README table)."
- file: config.toml
  why: "Line 37 already documents auto_unload_idle_seconds (M3.T1.S1, Mode A). The README table row is the
        GAP. Do NOT re-edit config.toml — it is already correct; this task only adds the README table row."

# READ — the parallel item's PRP (coordination: disjoint files, no conflict)
- file: plan/003_27d1f88f5a9f/P1M3T2S2/PRP.md
  why: "P1.M3.T2.S2 (parallel) edits tests/test_idle_and_gpu.sh + tests/ACCEPTANCE.md. THIS task edits
        README.md (+ optional install.sh). The files are DISJOINT — no merge conflict. This task does NOT
        touch any test file."
  critical: "Do NOT edit tests/* (S2 owns the test files). This task is README-only (Mode B docs)."

# READ — prior PRPs that document the LANDED behavior (authoritative lifecycle descriptions to mirror)
- docfile: plan/003_27d1f88f5a9f/P1M3T1S1/research/idle_unload_watchdog.md
  why: "Pins the idle-unload impl verbatim (watchdog tick, _maybe_idle_unload pre-check, _unload_recorder,
        _disarmed_monotonic wiring). The README idle-unload prose should match this."
- docfile: plan/003_27d1f88f5a9f/P1M2T1S2/research/loading_hint_client_side_design.md
  why: "Pins the 'loading models… (first arm, ~1–3 s)' client-side stderr hint design (ctl.py). The README
        First-run note quotes this exact hint."
```

### Current Codebase tree (state at P1.M3.T3.S1 start)

M1.T1 (bounded teardown) + M2.T1 (lazy load) + M3.T1.S1 (idle-unload + config knob) are ALL LANDED. The
daemon runs the lazy-load lifecycle. README.md is STALE (documents the old eager-at-boot model). config.toml
already documents `auto_unload_idle_seconds` (line 37). `voice_typing/*.py` code comments are ALREADY
lazy-load correct (Mode A done — research §4).

```bash
/home/dustin/projects/voice-typing/
├── README.md                 # ← EDIT (the 5 contract edits + status-example alignment). PRIMARY deliverable.
├── install.sh                # ← OPTIONAL one-line echo alignment (Task 7; contract trigger NOT met).
├── config.toml               # LANDED: line 37 documents auto_unload_idle_seconds. DO NOT EDIT (M3.T1.S1 owns it).
├── voice_typing/
│   ├── daemon.py             # LANDED: lazy load + idle-unload + bounded teardown. CONSUME (read); DO NOT EDIT.
│   ├── ctl.py                # LANDED: status renders phase + (loaded); loading models… hint. CONSUME (read); DO NOT EDIT.
│   ├── config.py             # LANDED: auto_unload_idle_seconds=1800.0 (line 78). READ only.
│   └── feedback.py           # LANDED: state.json phase/models_loaded. READ only.
├── PRD.md                    # READ-ONLY (forbidden to edit). The behavior spec.
└── tests/                    # NOT TOUCHED (parallel item P1.M3.T2.S2 owns test_idle_and_gpu.sh + ACCEPTANCE.md).
# NO voice_typing/* edits. NO config.toml edit. NO PRD.md/tasks.json edit. No new deps. No new files.
```

### Desired Codebase tree with files to be added

```bash
README.md    # MODIFIED: (a) config-table row; (b) lifecycle section rewrite; (c) first-arm-load note;
             #          (d) bounded-quit note; (e) status-example alignment (phase: + (loaded));
             #          + Install line 46-47 "not loaded (~0 VRAM)" enhancement. No stale residency framing.
install.sh   # MODIFIED (OPTIONAL, Task 7): line 174 echo enhanced to note "~0 VRAM; first start loads models".
# NOTHING ELSE. No new files. No production code. No config.toml. No tests. No PRD.md.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — THIS IS A DOCS-ONLY (Mode B) SUBTASK. The ONLY edits are README.md (+ optional install.sh).
#   The lazy-load/idle-unload/bounded-teardown BEHAVIOR is LANDED (M1.T1 + M2.T1 + M3.T1.S1 Complete). You are
#   DOCUMENTING it, not implementing it. Do NOT edit voice_typing/*.py, config.toml, PRD.md, tasks.json,
#   prd_snapshot.md, .gitignore, or any test file. (Research §0, §4; item OUTPUT/DOCS.)

# CRITICAL #2 — LINE NUMBERS SHIFT AS YOU EDIT. The line numbers in this PRP (132, 266-277, 283-286, 290-294)
#   are from the PRE-edit README. Grep for the ANCHOR TEXT to find the live location:
#     • config row:   grep -n 'auto_stop_idle_seconds' README.md
#     • status ex:    grep -n 'Typical CUDA output' README.md
#     • GPU section:  grep -n 'Confirm the models are resident' README.md
#     • stop section: grep -n 'Stop or disable the daemon' README.md
#   Edit BOTTOM-UP (stop section → GPU section → status example → config table → First-run → Install) so
#   earlier line numbers stay valid while you work. (Research §6.)

# CRITICAL #3 — QUOTE THE CLI VERBATIM. The voicectl status example MUST match ctl.py:85-93 EXACTLY:
#     listening: on
#     phase: listening
#     partial: this is what i am say
#     last: Previous sentence.
#     uptime: 42.3s
#     device: cuda (float16)
#     models: distil-large-v3 + small.en (loaded)
#     mic: ok
#   Note the NEW `phase:` line (after listening:) and the `(loaded)` marker on the models line. The loading
#   hint text is EXACTLY `loading models… (first arm, ~1–3 s)` (ctl.py:133) — use that ellipsis character.
#   (Research §1.)

# CRITICAL #4 — THE FIGURE TO CITE IS "≤10s" (not 90s). The bounded teardown (_bounded_shutdown,
#   daemon.py:1030) has a HARD timeout of 10.0s. The README bounded-quit note should say teardown completes in
#   seconds / ≤10s, and the OLD ~90s hang is gone. Do NOT say "quit takes 10s" (it's usually <1s; 10s is the
#   hard ceiling that only triggers if recorder.shutdown() wedges). (Research §0, daemon.py:1030-1079.)

# CRITICAL #5 — "~1.5-3 GB" IS THE LOADED-STATE FOOTPRINT, NOT A BOOT COST. When you mention VRAM, be clear:
#   boot = ~0 VRAM (unloaded); loaded = ~1.5-3 GB (paid on first arm / after reload). Lazy load means the
#   footprint is NOT paid at boot. Do NOT reintroduce any phrasing that implies models are resident at boot.
#   (PRD §4.2bis; research §0.)

# CRITICAL #6 — THE CONFIG ROW MUST MIRROR THE SIBLING. The `auto_unload_idle_seconds` row goes IMMEDIATELY
#   after the `auto_stop_idle_seconds` row (README.md:~132), same 3-col format, same voice. State the
#   DISARMED condition (loaded, not listening), the clock rule (starts on disarm, resets on arm, listening
#   doesn't count), the `0` disables semantics, and the reload (~1-3s). Cross-ref the lifecycle section.
#   Do NOT duplicate the whole auto_stop prose — keep it tight. (Research §2; config.toml:37 for wording.)

# GOTCHA #7 — THE CODE-COMMENT CROSS-CHECK PASSED (NO voice_typing EDITS). The research sweep (§4) confirmed
#   every `resident` / `construct once` usage in voice_typing/*.py describes POST-FIRST-ARM residency (correct),
#   NOT boot-time. Mode A already updated these. Re-run `grep -rniE 'resident|load at boot|boot-time'
#   voice_typing/*.py` to confirm, but do NOT edit code comments — that was Mode A, this is Mode B.

# GOTCHA #8 — INSTALL.SH HAS NO GPU-RESIDENCY BLURB (Task 7 is OPTIONAL). The contract trigger ("If
#   install.sh prints a GPU-residency blurb, align it too") is NOT met — install.sh never claims models are
#   resident. The only candidate is line 174's echo "running and NOT listening (no hot-mic on boot)". Enhancing
#   it to add "~0 VRAM; first voicectl start loads models (~1-3s)" is a COHERENCE nicety, not a requirement.
#   If unsure, leave install.sh untouched. (Research §5.)

# GOTCHA #9 — MARKDOWN TABLE + FENCE INTEGRITY. Adding the config row: keep the 3-col pipe format and the
#   leading/trailing pipes. The lifecycle section uses fenced code blocks for the nvidia-smi command — keep
#   fences balanced (open+close ```). The status example is a fenced block too. Run a render check (L1) after
#   edits: every ``` opened is closed; the table rows have the same column count as the header.

# GOTCHA #10 — VOICE/TENSE. The README's voice is "dustin six months from now" — exact, terse, no marketing.
#   Match the existing sentence style (e.g. the `auto_stop_idle_seconds` row's parenthetical-aside style).
#   Prefer "loads on first `voicectl start`" over "will be loaded when the user first arms". Use backticks for
#   `voicectl`, `config.toml`, `auto_unload_idle_seconds`, `nvidia-smi`, `quit`, config keys.
```

## Implementation Blueprint

### Data models and structure

No production data model. This is a single-file markdown rewrite (`README.md`) + an optional one-line shell
echo edit (`install.sh`). The "structure" is the set of precise text replacements specified below.

### Implementation Tasks (ordered by dependencies — edit BOTTOM-UP so line numbers stay valid)

```yaml
Task 0: PREFLIGHT — read the contract + the live README + the LANDED surfaces (no mutation)
  - RUN (from /home/dustin/projects/voice-typing):
      test -f README.md && echo "ok: README exists" || echo "PREFLIGHT FAIL"
      grep -n 'Confirm the models are resident' README.md          # the headline stale section (edit b)
      grep -n 'auto_stop_idle_seconds' README.md                    # the config-table anchor (edit a)
      grep -n 'Typical CUDA output' README.md                       # the stale status example (edit e)
      grep -n 'Stop or disable the daemon' README.md                # the stop/quit anchor (edit d)
      grep -n '## First run' README.md                              # the First-run anchor (edit c)
      grep -n 'running and NOT listening' README.md                 # the Install anchor (enhancement)
      sed -n '85,93p' voice_typing/ctl.py                           # the VERBATIM status block to match
      grep -n 'loading models' voice_typing/ctl.py                  # the hint text (edit c)
      grep -n 'auto_unload_idle_seconds' voice_typing/config.py     # the default + 0-disables (edit a)
      grep -n 'timeout.*10.0\|_bounded_shutdown' voice_typing/daemon.py  # the ≤10s teardown figure (edit d)
  - EXPECTED: all anchors present; ctl.py:85-93 shows the 8-line block with phase: + (loaded); config.py
    shows auto_unload_idle_seconds: float = 1800.0; daemon.py shows _bounded_shutdown with timeout=10.0.
  - DO NOT: edit anything yet, or touch any file other than README.md (+ optional install.sh later).

Task 1: REWRITE the GPU/lifecycle section (edit b) — the headline change
  - FIND: the block starting at the line matching 'Confirm the models are resident in GPU VRAM:'
          (README.md:~283) through its fenced ```nvidia-smi ...``` block (README.md:~286).
  - REPLACE it with a "## Model lifecycle & VRAM" (or keep it as prose under "Logs, status, stopping") section
    that documents:
      * Boot: daemon starts UNLOADED — no recorder, no CUDA context, ~0 VRAM. Models do NOT load at boot.
      * First arm: the first `voicectl start`/`toggle` (or hotkey) each session loads `small.en` +
        `distil-large-v3` onto the GPU (~1-3s). `voicectl` prints `loading models… (first arm, ~1–3 s)` to
        stderr while it loads; the command blocks until loaded. On total failure (CUDA + CPU fallback both
        fail) the daemon stays unloaded and the arm reports the error.
      * Resident: after that first arm the recorder stays resident (~1.5-3 GB VRAM) so the SECOND and later
        arms are instant.
      * Idle unload: after `asr.auto_unload_idle_seconds` (default 1800s = 30 min) DISARMED (loaded, not
        listening) with no re-arm, the daemon tears the recorder down → back to ~0 VRAM. The clock starts on
        disarm (manual stop, toggle-off, or the 30s auto-stop) and resets on any arm; time spent listening
        doesn't count. The next arm then reloads (~1-3s), same as a session's first arm. See `voicectl
        status` `phase:` (unloaded → loading → idle → listening) and the idle-unload journal line
        `voice-typing idle-unload: 1800.0s disarmed; unloading models`.
      * KEEP the nvidia-smi command, reframed: "Check VRAM by state" — e.g. `nvidia-smi
        --query-compute-apps=pid,used_memory --format=csv` shows nothing at boot/unloaded (~0), shows the
        daemon tree when loaded.
  - KEEP: the surrounding "On CPU fallback ..." paragraph (still accurate) and the "Stop or disable the
    daemon" subsection (Task 3 adds the bounded-quit note there).
  - NAMING/VOICE: section header lowercase-or-title to match README's existing `### Subsection` style;
    backtick commands/config keys; terse.
  - FILE: README.md
  - GOTCHA: edit this FIRST (it's near the bottom) so upper line numbers stay valid.

Task 2: ALIGN the voicectl status example (edit e) — part of "no stale claims"
  - FIND: the fenced block under "Typical CUDA output:" (README.md:~266-277) — currently missing phase: + (loaded).
  - REPLACE the example block to MATCH ctl.py:85-93 VERBATIM (add the `phase:` line after `listening:` and the
    `(loaded)` marker on the `models:` line):
        listening: on
        phase: listening
        partial: this is what i am say
        last: Previous sentence.
        uptime: 42.3s
        device: cuda (float16)
        models: distil-large-v3 + small.en (loaded)
        mic: ok
  - ADD one sentence after the block explaining the two new surface lines: "`phase:` is `unloaded` at boot
    (no models), `loading` on the first arm, then `idle`/`listening`; the `(loaded)`/`(not loaded)` marker on
    the `models:` line tells you whether models are resident."
  - UPDATE the "On CPU fallback ..." sentence (README.md:~279-282): it currently says "`models` shows
    `small.en + tiny.en`" — add that the marker stays `(loaded)` once the CPU recorder is built. Leave the
    mic sentence unchanged.
  - FILE: README.md

Task 3: ADD the bounded-quit note (edit d)
  - FIND: the "Stop or disable the daemon:" subsection (README.md:~290-294), after its fenced systemctl block.
  - ADD a short note (1-3 sentences): "`voicectl quit` and `systemctl --user stop` now complete in seconds.
    Teardown is bounded at ≤10s — if `recorder.shutdown()` wedges, the recorder's worker processes are
    force-terminated so VRAM is actually released. The old ~90s systemd stop timeout (`Failed with result
    'timeout'` / SIGKILL) is gone."
  - KEEP: the existing `systemctl --user stop` / `disable` commands.
  - FILE: README.md

Task 4: ADD the config-table row (edit a)
  - FIND: the config table row for `asr.auto_stop_idle_seconds` (README.md:~132) — 3-col `| Section.key |
    Default | Effect |`.
  - INSERT a new row IMMEDIATELY AFTER it, mirroring the style, for auto_unload_idle_seconds. Wording (tight,
    match sibling voice):
      | `asr.auto_unload_idle_seconds` | `1800.0` | after this many seconds DISARMED (models loaded, not listening), tear down the recorder to free VRAM (~0). The clock starts on disarm (manual stop, toggle-off, or the 30s auto-stop) and resets on any arm; time listening doesn't count. `0` disables (models then stay resident until `quit`). The next arm reloads (~1-3s). See Model lifecycle. |
  - VERIFY the column count matches the header (3 cols) and pipes balance.
  - FILE: README.md

Task 5: ADD the First-run first-arm-load note (edit c)
  - FIND: the "## First run" section (README.md:~49), ideally right after the fenced command block (the
    `voicectl toggle` arms / disarms block) OR right under the `## First run` header before the commands.
  - ADD a short note: "The first `voicectl toggle` (or `start`) each session takes ~1-3s to load the models —
    `voicectl` prints `loading models… (first arm, ~1–3 s)` while it loads. Subsequent arms are instant
    (models stay resident until `quit` or 30 min disarmed; see Model lifecycle & VRAM)."
  - KEEP: the existing "Expected behavior while listening" paragraph (still accurate).
  - FILE: README.md

Task 6: ENHANCE the Install line (small alignment with PRD §4.9)
  - FIND: "When install.sh finishes, the daemon is **running and NOT listening**. It never hot-mics on boot."
          (README.md:~46-47).
  - ENHANCE to add not-loaded: "When install.sh finishes, the daemon is **running, NOT listening, and NOT
    loaded** (~0 VRAM). It never hot-mics on boot and loads no models until the first `voicectl toggle`
    (~1-3s). Run `voicectl toggle` (or the hotkey) to arm the mic."
  - FILE: README.md

Task 7 (OPTIONAL): ALIGN install.sh final echo (coherence — contract trigger NOT met)
  - FIND: install.sh line ~174: `echo "daemon : running and NOT listening (no hot-mic on boot). Run 'voicectl toggle' to arm the mic."`
  - OPTIONAL enhancement (only if it improves coherence; the contract does NOT require it because install.sh
    prints NO GPU-residency blurb): add ", ~0 VRAM until first start" or similar. E.g.:
      echo "daemon : running and NOT listening (~0 VRAM; first 'voicectl toggle' loads models, ~1-3s). Run 'voicectl toggle' to arm the mic."
  - IF UNSURE, SKIP THIS TASK entirely (leave install.sh untouched). The success criteria do not require it.
  - FILE: install.sh

Task 8: VALIDATE (L1 stale-sweep + render; L2 scope guard) — iterate until clean
  - RUN the validation greps (Validation Loop L1): confirm ZERO stale boot-time-residency claims + presence of
    the new lifecycle terms. Fix any miss.
  - RUN L2 scope guard: `git status --short` shows ONLY `M README.md` (+ optional `M install.sh`).
  - RUN a render sanity check: code fences balanced, table well-formed.
  - DO NOT: run pytest/ruff/mypy/bash (no gate for a markdown docs task). DO NOT edit any forbidden file.

Task 9: CROSS-CHECK the stale-phrasing sweep (research §4) — confirm no code drift, no edit needed
  - RUN: grep -rniE 'resident|load at boot|boot-time|2\.8 GB|1\.5-3 GB|construct once|build recorder once' voice_typing/*.py
  - EXPECTED: hits are all CORRECT (post-first-arm residency / lazy-load motivation) — NOT stale boot claims.
    Mode A already fixed code comments. Do NOT edit voice_typing/*.py (out of scope). Just CONFIRM.
```

### Implementation Patterns & Key Details

```markdown
<!-- PATTERN 1 — the lifecycle section (Task 1). Frame VRAM by STATE, not as a constant. -->
At boot the daemon is **unloaded**: no recorder, no CUDA context, **~0 VRAM** — models do NOT load at boot.
The first `voicectl start`/`toggle` (or hotkey) each session loads `small.en` + `distil-large-v3` onto the
GPU (~1-3s); `voicectl` prints `loading models… (first arm, ~1–3 s)` to stderr while it loads. After that
first arm the recorder stays **resident** (~1.5-3 GB VRAM) so later arms are instant. It is torn down on
`quit`/shutdown AND after `asr.auto_unload_idle_seconds` (default 1800s = 30 min) DISARMED — so the load cost
is paid once per ~30 min of actual use, not once per boot. The clock starts on disarm and resets on any arm;
the next arm reloads (~1-3s) like a session's first arm.

`voicectl status` surfaces the lifecycle: `phase:` is `unloaded` (boot / idle-unloaded), `loading` (first arm),
`idle` (loaded, disarmed), or `listening` (armed); the `models:` line ends in `(loaded)` or `(not loaded)`.
The journal logs `voice-typing models loaded (lazy load complete); recorder resident` on load and
`voice-typing idle-unload: 1800.0s disarmed; unloading models` on idle teardown.

Check VRAM by state:

```
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

At boot / after idle-unload this lists nothing (~0 VRAM); while loaded it shows the daemon's process tree
(~1.5-3 GB).

<!-- PATTERN 2 — the config-table row (Task 1/a). 3 cols, mirrors auto_stop_idle_seconds. -->
| `asr.auto_unload_idle_seconds` | `1800.0` | after this many seconds DISARMED (models loaded, not listening), tear down the recorder to free VRAM (~0). The clock starts on disarm (manual stop, toggle-off, or the 30s auto-stop) and resets on any arm; time listening doesn't count. `0` disables (models then stay resident until `quit`). The next arm reloads (~1-3s). See Model lifecycle. |

<!-- PATTERN 3 — the bounded-quit note (Task 3). Cite ≤10s (the HARD ceiling), not a typical time. -->
`voicectl quit` and `systemctl --user stop` complete in seconds. Teardown is bounded at ≤10s — if
`recorder.shutdown()` wedges, the recorder's worker processes are force-terminated so VRAM is actually
released. The old ~90s systemd stop timeout (`Failed with result 'timeout'` / SIGKILL) is gone.
```

### Integration Points

```yaml
README.md (PRIMARY — the only required edit):
  - rewrite: "the 'Confirm the models are resident in GPU VRAM' block (~line 283) -> lazy-load lifecycle section (Task 1)"
  - align: "the 'Typical CUDA output' status example (~line 266-277) -> add phase: + (loaded) to match ctl.py:85-93 (Task 2)"
  - add: "bounded-quit note after 'Stop or disable the daemon' (~line 290, Task 3)"
  - add: "asr.auto_unload_idle_seconds row after the auto_stop_idle_seconds row (~line 132, Task 4)"
  - add: "first-arm-load note in '## First run' (~line 49, Task 5)"
  - enhance: "Install 'running and NOT listening' line (~line 46) -> add 'not loaded (~0 VRAM)' (Task 6)"
install.sh (OPTIONAL — Task 7; contract trigger NOT met):
  - optional: "line ~174 echo -> add '~0 VRAM; first start loads models' for coherence. SKIP if unsure."
CONSUMED CONTRACT (do NOT edit — LANDED + Mode A done):
  - voice_typing/*.py: "lazy-load + idle-unload + bounded teardown (M1.T1 + M2.T1 + M3.T1.S1); code comments
    already lazy-load correct (Mode A). READ only — this is Mode B docs."
  - config.toml: "line 37 already documents auto_unload_idle_seconds (M3.T1.S1). Do NOT re-edit."
  - PRD.md: "§4.2bis/§4.5/§4.9/§7.6/§7.9 — the behavior spec. READ only (forbidden to edit)."
  - tests/*: "owned by the parallel item P1.M3.T2.S2. Do NOT touch."
DEPENDENCIES: none new (markdown only). No pip/uv/shell changes.
```

## Validation Loop

> This is a MARKDOWN DOCS task. There is no compile/test/ruff/mypy/bash gate. The gates are: (L1) a grep sweep
> proving NO stale boot-time-residency claim remains AND the new lifecycle terms are present; (L2) a scope
> guard (`git status --short`); (L3) a markdown render sanity check (fences/table). All run from the repo root.

### Level 1: Stale-sweep + presence + render (the primary gate)

```bash
cd /home/dustin/projects/voice-typing

# (1) ZERO stale boot-time-residency framing (the headline success criterion):
echo "--- stale-residency check (expect NO output) ---"
grep -niE 'confirm the models are resident|models load at boot|loads at boot|always resident|resident at boot|resident in GPU VRAM at boot' README.md
# Expected: NO output. If any line matches, it's a stale claim — fix it.

# (2) The NEW lifecycle terms ARE present (expect hits):
echo "--- new-lifecycle presence check (expect hits) ---"
grep -niE '~0 ?VRAM|loading models|auto_unload_idle_seconds|idle-unload|unloaded|bounded|not loaded' README.md
# Expected: hits in the lifecycle section, config row, First-run note, Install line, and stop note.

# (3) The status example matches ctl.py (phase: + (loaded)):
echo "--- status-example alignment (expect hits) ---"
grep -nE 'phase: listening|models: distil-large-v3 \+ small\.en \(loaded\)' README.md
# Expected: both lines present in the example block.

# (4) The config-table row is present and well-formed (3 cols):
echo "--- config row check ---"
grep -n '`asr.auto_unload_idle_seconds`' README.md
# Expected: exactly one table row, with leading/trailing pipes and 2 inner pipes (3 cols).

# (5) Markdown render sanity: code fences balanced (count must be EVEN):
echo "--- fence balance (expect EVEN count) ---"
grep -c '```' README.md
# Expected: an EVEN number. If odd, a fence is unbalanced — fix it.
# Table integrity: every data row has the same pipe count as the header row (manual eyeball).

# Expected: (1) empty; (2) hits; (3) both lines; (4) one well-formed row; (5) even fence count.
```

### Level 2: Scope guard (no out-of-scope edits)

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: ONLY " M README.md" — OR " M README.md" + " M install.sh" if Task 7 was done.
# Any change to voice_typing/*, config.toml, PRD.md, tasks.json, prd_snapshot.md, .gitignore,
# pyproject.toml, uv.lock, or tests/* is a SCOPE VIOLATION.
git diff --name-only
# Expected: README.md (+ optionally install.sh). Nothing else.
```

### Level 3: Accuracy cross-check (prose matches the LANDED code)

```bash
cd /home/dustin/projects/voice-typing
# The README's lifecycle prose must match the code. Spot-check the load-bearing claims:
echo "--- idle-unload log line cited in README matches daemon.py:844 ---"
grep -F 'voice-typing idle-unload:' README.md && grep -F 'voice-typing idle-unload:' voice_typing/daemon.py
echo "--- loading hint text in README matches ctl.py:133 ---"
grep -F 'loading models' README.md && grep -F 'loading models' voice_typing/ctl.py
echo "--- bounded teardown figure: README says <=10s; daemon.py _bounded_shutdown timeout=10.0 ---"
grep -niE '≤10s|<=10s|10s|bounded' README.md && grep -nE 'timeout.*10\.0|_bounded_shutdown' voice_typing/daemon.py | head -3
# Expected: each README claim has a matching code site. The hint text matches EXACTLY.
```

### Level 4: Code-comment cross-check (research §4 — confirm NO drift, NO edit needed)

```bash
cd /home/dustin/projects/voice-typing
# Mode A already updated voice_typing/*.py comments. Confirm no stale boot-time-residency claim remains in code:
echo "--- code cross-check (expect only CORRECT post-first-arm residency phrasing) ---"
grep -rniE 'resident|load at boot|boot-time|2\.8 GB|construct once|build recorder once' voice_typing/*.py
# Expected: hits are all correct (e.g. daemon.py "constructed ONCE so models stay resident", "stays at ~0 VRAM;
#   after the first arm the recorder stays resident"). Do NOT edit these — they are Mode A correct.
# If a genuine stale boot-time claim appears (e.g. "models load at boot"), that's a Mode A regression —
# report it, but do NOT fix code comments in this Mode B task unless the contract explicitly requires it
# (the contract says "fix any remaining drift in ... voice_typing/*.py comments" — so a genuine stale claim
# MAY be fixed; but the research sweep found none).
```

## Final Validation Checklist

### Technical Validation
- [ ] L1 stale-sweep: `grep -niE 'confirm the models are resident|models load at boot|always resident|resident at boot' README.md` → **zero hits**.
- [ ] L1 presence: `~0 VRAM`, `loading models…`, `auto_unload_idle_seconds`, `idle-unload`/`idle unload`, `unloaded`, `bounded`, `not loaded` all present in README.md.
- [ ] L1 status example: `phase: listening` + `models: distil-large-v3 + small.en (loaded)` present in the example block (matches ctl.py:85-93).
- [ ] L1 config row: exactly one `asr.auto_unload_idle_seconds` table row, 3 columns, pipes balanced.
- [ ] L1 render: code fence count is EVEN; table rows have matching column counts.
- [ ] L2 scope: `git status --short` → only `M README.md` (+ optional `M install.sh`).
- [ ] L3 accuracy: README lifecycle claims (idle-unload log, loading hint, ≤10s teardown) match the code sites.

### Feature Validation
- [ ] **(a)** Config table has the `asr.auto_unload_idle_seconds` row (default 1800.0, 0-disables, disarm-clock rule, reload note).
- [ ] **(b)** The "Confirm the models are resident" framing is GONE; replaced by a lazy-load lifecycle section (~0 VRAM boot → first-arm load → resident → idle-unload → reload).
- [ ] **(c)** First-run section has the "first arm loads models (~1-3s)" note + the `loading models… (first arm, ~1–3 s)` hint.
- [ ] **(d)** Stop/quit section has the bounded-teardown note (≤10s, force-terminate, no ~90s hang).
- [ ] **(e)** Status example matches the live CLI (phase + loaded marker); no stale boot-time claim survives.
- [ ] The `voicectl status` example's new lines (`phase:`, `(loaded)`) are explained in prose.

### Code Quality Validation
- [ ] Voice matches the existing README ("dustin six months from now" — exact, terse, backticked commands/keys).
- [ ] Config-table row mirrors the `auto_stop_idle_seconds` row's 3-col style and parenthetical-asides.
- [ ] No marketing language; no reintroduced boot-time-residency implication.
- [ ] Cross-references between sections are consistent (e.g. "See Model lifecycle").

### Documentation & Deployment
- [ ] README is the single source of user-facing lifecycle truth and matches the running daemon.
- [ ] (Optional) install.sh echo aligned for coherence — or deliberately left untouched (contract trigger not met).
- [ ] No new env vars, config keys, or runtime surface introduced (this is docs only).

---

## Anti-Patterns to Avoid

- ❌ Don't edit `voice_typing/*.py`, `config.toml`, `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`, or any test file — this is docs-only (Mode B) (Critical #1). The code-comment cross-check (L4) is to CONFIRM, not to fix (Mode A already did it).
- ❌ Don't rely on absolute line numbers — they shift as you edit. Grep for the anchor text ("Confirm the models are resident", "auto_stop_idle_seconds", "Typical CUDA output", "Stop or disable the daemon") and edit BOTTOM-UP (Critical #2).
- ❌ Don't invent the `voicectl status` example — copy it VERBATIM from `ctl.py:85-93` (`phase:` line + `(loaded)` marker) (Critical #3).
- ❌ Don't say "quit takes 10s" — cite "≤10s" as the hard ceiling that only triggers if `recorder.shutdown()` wedges; typical quit is sub-second (Critical #4).
- ❌ Don't reintroduce any phrasing implying models are resident at boot — "~1.5-3 GB" is the LOADED footprint paid on first arm, not a boot cost (Critical #5).
- ❌ Don't write a verbose config-table row — mirror the sibling's tight style; state disarm-condition + clock-rule + 0-disables + reload (Critical #6).
- ❌ Don't treat install.sh as a required edit — it prints NO GPU-residency blurb; Task 7 is optional coherence only (Gotcha #8).
- ❌ Don't break markdown — keep table pipes/columns consistent and code fences balanced (Gotcha #9); run the L1 render checks.
- ❌ Don't change the README's voice — keep the "exact commands, no hand-holding" style and backtick all commands/keys/config names (Gotcha #10).

---

## Confidence Score

**9/10** for one-pass success. This is a single-file markdown rewrite (~6 small, precisely-specified text
replacements in `README.md`) plus an optional one-line shell echo. Every edit site is pinned by anchor text
with the stale-claim verdict per line (research §3), the replacement prose is given verbatim (Implementation
Patterns), and the validation is a deterministic grep sweep (L1) + scope guard (L2) + accuracy cross-check
(L3) — no flaky runtime gate. The lifecycle/CLI strings to quote are VERBATIM from the LANDED code (ctl.py
status block, the `loading models…` hint, the idle-unload log line, the ≤10s teardown timeout). The code-
comment cross-check already PASSED (Mode A done — no voice_typing edits needed), and the parallel item (S2)
owns disjoint files (tests/*), so there is no merge conflict.

The −1 reserve: the headline rewrite (Task 1) is the one piece that requires judgment on sectioning (where to
place the lifecycle prose — a new subsection vs. in-flow under "Logs, status, stopping") and on how much
detail to include without over-bloating the README. The PRP gives the verbatim prose + placement guidance
(after the status example, reframing the nvidia-smi command), bounding the judgment. The render/fence checks
catch any markdown slip. No architectural risk.
