# PRP — P1.M2.T4.S1: Flip duck_mode default to "mpris" + recorded acceptance evidence

## Goal

**Feature Goal**: Land the final step of the media-ducking milestone (D1, PRD §4.2quinquies): flip
the shipped `duck_mode` default from `"off"` to `"mpris"` in config.py + config.toml LOCKSTEP (the
repo-default lockstep test adapts automatically; the ONE default-pinning test line is updated; the
26-key pin is untouched — values change, not keys), and produce **recorded acceptance evidence** for
the five §4.2quinquies acceptance scenarios via a NEW bounded, trap-guarded, harmless-target script
(`tests/d1_duck_evidence.sh`) + evidence doc (`tests/D1_DUCK_EVIDENCE.md`): music→arm→pause ≤~1 s→
resume at stop; `duck_mode="volume"` ducks to 15% and restores EXACTLY; user changes are NEVER
overridden (sovereignty); `duck_mode="off"` is byte-identical to today (zero `ducking:` journal
lines); the journal shows the engage/release lines.

**Deliverable** (2-file value flip + 1 test line + 1 new script + 1 new evidence doc):
1. `voice_typing/config.py` — `duck_mode: str = "mpris"` @226 + AudioConfig docstring update (@219-224).
2. `config.toml` — `duck_mode = "mpris"` @60 + comment rewrite (DOCS Mode A: drop the "Ships 'off'
   until the feature lands" sentence; state the landed behavior).
3. `tests/test_config.py` — line 277 default assertion `"off"` → `"mpris"` (the ONLY default-value pin).
4. `tests/d1_duck_evidence.sh` — NEW: sandboxed live-acceptance script (3 disposable daemon
   instances: default/mpris merged, volume, off; harmless targets: disposable mpv players + a
   null-sink; EXIT trap restores everything; every voicectl under `timeout 30`).
5. `tests/D1_DUCK_EVIDENCE.md` — NEW: the recorded run (per-scenario result, measured pause Δt,
   journal-line excerpts, which path — scripted/operator — produced each row).

**Success Definition**:
- (a) Lockstep green: `test_repo_config_toml_equals_defaults` passes with BOTH files flipped (it is
      the guard — red if only one flips); key-set pin still 26; `test_config.py:277` asserts "mpris".
- (b) All D1 suites green after the flip (test_config*, test_ducking) and the fast sweep shows no
      new failures vs `tests/G1_BASELINE.md`.
- (c) Evidence script exits 0 with per-scenario PASS lines; a sandbox daemon with NO `duck_mode`
      key in its config (flipped default active) pauses a playing disposable mpv at arm in < 1.5 s
      and resumes it at stop; sovereignty holds (a manually-paused second player STAYS paused;
      a mid-arm volume change to 60% is kept, not clobbered); the off-instance logs ZERO
      `ducking:` lines.
- (d) The operator's machine is exactly restored (default sink + null-sink unloaded by index,
      systemd unit restarted if it had been active, no stray daemon/mpv processes, scratch removed).
- (e) DOCS Mode A only: config.toml (+ config.py) comments updated. README/ACCEPTANCE.md rows are
      Mode B → P1.M7.T2, NOT here.

## User Persona

**Target User**: the end user — after this lands, arming dictation while music plays Just Works
(players pause at arm, resume at stop) with zero configuration; users who dislike it set
`duck_mode = "off"` for byte-identical pre-D1 behavior.

**Use Case**: user is watching/listening while dictating; media bleed (pure WER) is removed for
exactly as long as the mic is hot, then restored EXACTLY as found.

**User Journey**: music playing → hotkey → music pauses within ~1 s (journal: `ducking: paused
MPRIS player(s): …`) → dictate → stop → music resumes (journal: `ducking: resumed …`). If the user
manually resumed/changed volume mid-dictation, THEIR state wins.

**Pain Points Addressed**: closes D1 — the feature existed behind `duck_mode="off"`; this task makes
it the default WITH evidence, per PRD §4.2quinquies "default flips to 'mpris' the round this lands".

## Why

- **PRD §4.2quinquies is normative**: "`duck_mode = "off"` … Ships "off" until implemented; default
  flips to "mpris" the round this lands." T1–T3 landed the surface, the AudioDucker (both tiers,
  failure discipline), the daemon lifecycle wiring, and (in-flight, contract) crash safety — THIS is
  that round.
- **Evidence, not vibes**: the PRD's Acceptance paragraph enumerates observable behavior (≤~1 s
  pause, exact restore, sovereignty, off = byte-identical, journal lines). The milestone closes with
  recorded, re-runnable proof (the script is checked in like `tests/e2e_virtual_mic.sh`), and
  `tests/D1_DUCK_EVIDENCE.md` becomes the input for P1.M7.T2.S2's ACCEPTANCE.md rows.
- **The flip is deliberately last**: it could not ship before the D1 tests were green (contract
  INPUT: all P1.M2.T2.*/P1.M2.T3.* green) — flipping earlier would turn the default user experience
  into the test of the feature.

## What

1. **The flip** (research §1): both config files lockstep + the single default-pin test line +
   Mode A comment rewrites; NOTHING structural (26-key pin, validation set, all other ducking tests
   construct explicit modes/fakes — verified).
2. **Evidence script** (research §2): sandboxed daemon instances (own `XDG_RUNTIME_DIR`/`XDG_CONFIG_HOME`
   → own control socket + state file; `output.backend="null"` so an automated run can NEVER type
   into the focused window; `auto_stop_idle_seconds = 0` so auto-disarm can't race the scenario),
   disposable `mpv` players fed a stdlib-`wave` silent WAV, a `module-null-sink` for the volume tier
   (restore-by-index in the trap), stop/restart of the systemd unit around the run (double-VRAM
   avoidance), PID-based daemon teardown, and a full EXIT trap.
3. **Evidence doc** (research §2/§3): per-scenario rows + measured Δt + journal excerpts + the
   operator-checklist fallback (exact expected lines) for anything not scriptable on a given host.

### Success Criteria

- [ ] `grep duck_mode config.toml voice_typing/config.py` shows `"mpris"` in BOTH; comments updated.
- [ ] `tests/test_config.py:277` asserts `"mpris"`; `test_repo_config_toml_equals_defaults` and the
      26-key pin pass unchanged structurally.
- [ ] `timeout 900 bash tests/d1_duck_evidence.sh` exits 0, all scenario PASS lines, machine restored.
- [ ] `tests/D1_DUCK_EVIDENCE.md` exists with the five §4.2quinquies acceptance rows + evidence.
- [ ] Fast sweep: no new failures vs `tests/G1_BASELINE.md`.
- [ ] README.md and tests/ACCEPTANCE.md are NOT touched (Mode B → P1.M7.T2).

## All Needed Context

### Context Completeness Check

_Pass._ The research note carries every live-verified fact with file:line: the exact flip sites
(F1), which tests adapt vs. which one line changes (F2), the full landed D1 machinery + the exact
journal-line strings the evidence greps (F3), the one-daemon-per-mode consequence and the
default/mpris scenario merge (F4), the sandbox safety requirements (F5/F6/F9/F10), the null-sink
harmless-target pattern (F7), the stop-the-unit-around-the-run precedent (F8), the scripted
sovereignty checks (F13), and the off-instance zero-lines check (F14). A fresh implementer needs
only the note + the cited files.

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/P1M2T4S1/research/default_flip_and_evidence.md
  why: "§0 F1-F14 verified facts (flip sites, journal-line strings, sandbox/safety design).
        §1 the exact edits. §2 the evidence-script phase design. §3 the operator fallback.
        §4 validation commands."
  section: "ALL."

- docfile: plan/008_a47116bb2b79/P1M2T3S2/PRP.md
  why: "The PARALLEL CONTRACT: ducking_heal.py + ExecStopPost + shutdown flush are landing
        concurrently. This task does NOT depend on them for the flip; the evidence run merely
        VERIFIES they exist (Task 1 grep). Do not duplicate or edit their deliverables."
  critical: "If T3.S2 pieces are absent at implementation time, proceed with the flip + evidence
             but note their absence in the evidence doc — do not implement them here."

- file: voice_typing/config.py
  why: "EDIT @226 (default) + docstring @219-224. READ @231 (validation set — UNCHANGED) and
        @384 (per-table overlay — why the sandbox partial config.toml works)."
  gotcha: "Flip BOTH the value and the 'ships off' docstring sentences; stale docstrings are how
           the next agent re-flips it."

- file: config.toml
  why: "EDIT @60: value + the Mode A comment (DOCS requirement of this item)."
  gotcha: "The repo config.toml is the FALLBACK; the operator's XDG copy (if present) still wins
           for the systemd daemon — note in the evidence doc that the user-visible default takes
           effect at the unit's next natural restart (or an operator restart)."

- file: tests/test_config.py
  why: "EDIT line 277 ONLY (default-value pin 'off'→'mpris'); @263 (validation-loop test) needs
        nothing — it iterates all three values."
- file: tests/test_config_repo_default.py
  why: "NO structural edit: @17 lockstep auto-adapts; @27 key-set pin untouched (26). Optional:
        comment @49 drop 'ships \"off\"'."

- file: voice_typing/audio_ducking.py   # READ-ONLY (S-frozen)
  why: "The exact journal lines the script asserts (research F3): paused/resumed MPRIS player(s),
        sink volume X% -> Y%, volume was changed mid-dictation ... keeping user value, restored
        sink volume X%."
- file: voice_typing/ducking_async.py   # READ-ONLY
  why: "AsyncDucker engage/release/flush — engage is DISPATCH (non-blocking): the ≤1 s pause
        budget is measured on the media side (playerctl poll), not the daemon side."
- file: voice_typing/daemon.py          # READ-ONLY for this task
  why: "Seams: _duck_engage @1468 (from _arm @1565), _duck_release @1489 (_disarm @1605,
        dead-host @1164, request_shutdown), off ⇒ self._ducker is None @868. The evidence proves
        the WIRING works end-to-end; no daemon edit in this task."
- file: tests/e2e_virtual_mic.sh        # READ-ONLY
  why: "The shape to mirror: preflight, EXIT-trap cleanup, load-module + restore-by-index,
      timeout-bounded steps, 'backend=null so an automated run can never type into the focused
      window'."
- file: tests/G1_BASELINE.md            # READ
  why: "The recorded pre-change reds — the sweep gate is 'no NEW failures', not 'all green'."
- docfile: PRD.md   # §4.2quinquies
  why: "Acceptance paragraph (the five scenarios) + Config + failure discipline (never a gate;
        bounded calls; idempotent engage/release) the script must honor."

# CONTEXT — NOT to touch:
- README.md, tests/ACCEPTANCE.md  # Mode B → P1.M7.T2 (.S1/.S2)
- voice_typing/{audio_ducking,ducking_mpris,ducking_volume,ducking_async,ducking_heal}.py,
  systemd/voice-typing.service, install.sh, feedback.py  # S1/S2/T1-owned or frozen
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/config.py        # EDIT: default @226 + docstring
config.toml                   # EDIT: @60 value + comment (Mode A)
tests/test_config.py          # EDIT: line 277 only
tests/d1_duck_evidence.sh     # CREATE (mirrors e2e_virtual_mic.sh discipline)
tests/D1_DUCK_EVIDENCE.md     # CREATE (the recorded evidence)
tests/{G1_BASELINE,ACCEPTANCE}.md  # READ (gate / NOT this task)
```

### Desired Codebase tree

```bash
# 2 value flips + 1 comment rewrite pair + 1 test line + 1 script (~150-200 lines) + 1 evidence doc.
# git status: config.toml, voice_typing/config.py, tests/test_config.py modified;
#             tests/d1_duck_evidence.sh, tests/D1_DUCK_EVIDENCE.md new. NOTHING else.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — LOCKSTEP: flip config.py AND config.toml in the SAME change; the repo-default
#   lockstep test (test_repo_config_toml_equals_defaults) is the guard. Key-set pin stays 26.
# CRITICAL #2 — tests/test_config.py:277 is the ONLY default-value pin (grep-verified); flip it to
#   "mpris". Do NOT touch @263 (validation loop) or the repo-default tests' structure.
# CRITICAL #3 — SANDBOX SAFETY (three rules): (a) sandbox config sets output.backend="null" (else
#   a recognized final types into the OPERATOR'S FOCUSED WINDOW); (b) own XDG_RUNTIME_DIR +
#   XDG_CONFIG_HOME (own socket/state — voicectl in that env cannot reach the systemd daemon);
#   (c) teardown by RECORDED PID only — NEVER `pkill -f voice-typing|recorder_host` (kills the
#   user's unit mid-script; that pattern is for wedge RECOVERY, not scripted teardown).
# CRITICAL #4 — the MPRIS tier pauses EVERY playing player: run when operator media is idle, or
#   accept transient pause/resume of it (correct behavior — note it in the evidence doc).
# CRITICAL #5 — the volume tier mutates the DEFAULT SINK: swap to a disposable null-sink first;
#   unload BY RECORDED INDEX in the trap (never `unload-module module-null-sink` — nukes ALL).
# CRITICAL #6 — daemon discipline (AGENTS.md): never foreground the daemon (setsid … &disown);
#   EVERY voicectl under `timeout 30`; script under `timeout 900`; readiness poll via
#   `timeout 15 .venv/bin/voicectl status`; stop/restart the systemd unit around the run
#   (test_idle_and_gpu.sh precedent) to avoid two CUDA model sets in VRAM.
# CRITICAL #7 — one daemon per duck_mode (ducker built at init from cfg): 3 instances — the
#   default-scenario sandbox config OMITS duck_mode (proves the flipped default), volume adds
#   "volume", off adds "off". Sandbox configs also set [asr] auto_stop_idle_seconds=0 (auto-disarm
#   would otherwise race the scenario assertions).
# CRITICAL #8 — arming pays the lazy model load (~1-3 s, GBs VRAM): the ≤1 s pause budget is
#   measured from the arm COMMAND RETURN to player Paused (engage dispatches at _arm; the load
#   precedes it) — poll playerctl at 0.1 s and record Δt; hard-assert < 1.5 s.
# GOTCHA #9 — scratch under /tmp is RAM (tmpfs): the trap rm -rf's the scratch dir; the evidence
#   doc gets a BOUNDED excerpt (`grep 'ducking:' daemon.log | head -40`), never the whole log.
# GOTCHA #10 — repo config.toml is the fallback copy; the operator's XDG copy (if any) still wins
#   for the systemd daemon — record in the evidence doc that the user-visible default lands at the
#   unit's next restart (the script restarts it as part of cleanup anyway).
```

## Implementation Blueprint

### Data models and structure

None — a value flip; the `[audio]` schema (AudioConfig @218) is T1-frozen and unchanged.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: VERIFY PRECONDITIONS
  - timeout 600 .venv/bin/python -m pytest tests/test_ducking.py tests/test_config.py
    tests/test_config_repo_default.py tests/test_feedback.py tests/test_systemd_unit.py -q  # all green
  - grep -n "set_ducked" voice_typing/feedback.py ; grep -n "_duck_engage\|_duck_release" voice_typing/daemon.py
  - grep -n "def heal" voice_typing/ducking_heal.py 2>/dev/null || note "T3.S2 in flight — proceed"
  - If the D1 suites are RED: STOP and report (the flip must not land on a broken D1).

Task 2: THE FLIP (lockstep, one commit-sized change)
  - config.py @226: duck_mode: str = "mpris" (+ trailing comment).
  - config.py AudioConfig docstring @219-224: replace the ships-off/flips-later sentences with the
    landed-state wording (research §1 item 2).
  - config.toml @60: duck_mode = "mpris" + comment rewrite (Mode A; research §1 item 3).
  - tests/test_config.py @277: assert a.duck_mode == "mpris" and a.duck_volume_pct == 15.
  - Optional: tests/test_config_repo_default.py @49 comment drop '; ships "off"'.

Task 3: CREATE tests/d1_duck_evidence.sh (research §2)
  - Phase 0 preflight + scratch + trap (research §2 Phase 0; CRITICAL #3/#5/#6).
  - Phase 1 default/mpris (merged; NO duck_mode key in sandbox config) — pause Δt, resume,
    sovereignty-via-second-player (research F13).
  - Phase 2 volume on null-sink — 40→15, user-change 60 kept, second-cycle exact restore.
  - Phase 3 off — zero "ducking:" lines across an arm/disarm cycle.
  - Print PASS/FAIL per scenario; exit non-zero on any FAIL; bounded journal excerpt to stdout.

Task 4: RUN + RECORD
  - timeout 900 bash tests/d1_duck_evidence.sh
  - Write tests/D1_DUCK_EVIDENCE.md: date, HEAD, per-scenario rows (PASS/FAIL + measured Δt +
    journal excerpts), the scripted-vs-operator path per row, restore confirmation, and (if any
    host tool was absent) the §3 operator-checklist fallback rows with the exact expected lines.

Task 5: VALIDATE + SCOPE GUARD
  - Research §4 commands; git status shows ONLY the 5 files (3 modified, 2 new).
```

### Implementation Patterns & Key Details

```bash
# Sandbox daemon launch + readiness + teardown (CRITICAL #3/#6):
export XDG_RUNTIME_DIR="$SB/run" XDG_CONFIG_HOME="$SB/cfg"
mkdir -p "$XDG_RUNTIME_DIR/voice-typing" "$XDG_CONFIG_HOME/voice-typing"
printf '[output]\nbackend = "null"\n\n[asr]\nauto_stop_idle_seconds = 0.0\n' \
  > "$XDG_CONFIG_HOME/voice-typing/config.toml"        # Phase 1: NO duck_mode key
setsid .venv/bin/voice-typing-daemon >>"$SB/daemon.log" 2>&1 &disown
DPID=$!
until timeout 15 .venv/bin/voicectl status >/dev/null 2>&1; do sleep 0.2; done
timeout 30 .venv/bin/voicectl start      # arm — engage dispatches at _arm
# trap: timeout 30 .venv/bin/voicectl quit || kill -TERM $DPID; sleep 1; kill -KILL $DPID 2>/dev/null

# Pause-latency probe (CRITICAL #8):
T0=$(date +%s%N)
until [ "$(playerctl -p "$P1" status 2>/dev/null)" = "Paused" ]; do sleep 0.1; done
DT_MS=$(( ($(date +%s%N) - T0) / 1000000 ))            # assert < 1500; record in the doc

# Journal assertions (exact strings, audio_ducking.py @129/@146/@158/@170/@173):
grep -m1 "ducking: paused MPRIS player(s):" "$SB/daemon.log"
grep -m1 "ducking: resumed MPRIS player(s):" "$SB/daemon.log"
```

### Integration Points

```yaml
CONFIG:
  - config.py/config.toml: duck_mode default "off" -> "mpris" (the ONLY schema change; lockstep).
TESTS:
  - tests/test_config.py:277 value pin updated; NO other structural test change.
EVIDENCE (new):
  - tests/d1_duck_evidence.sh + tests/D1_DUCK_EVIDENCE.md (consumed later by P1.M7.T2.S2 rows).
NOT TOUCHED: README.md, tests/ACCEPTANCE.md (Mode B, P1.M7.T2); ducking modules + daemon +
  feedback + systemd unit + install.sh (S1/S2/T1-owned or frozen); PRD.md/tasks.json.
```

## Validation Loop

### Level 1: Unit gates after the flip

```bash
cd /home/dustin/projects/voice-typing
timeout 600 .venv/bin/python -m pytest tests/test_config.py tests/test_config_repo_default.py tests/test_ducking.py -q
# Expected: green — lockstep adapts (BOTH files flipped), key-set pin 26, :277 now "mpris".
```

### Level 2: Fast sweep vs baseline

```bash
timeout 600 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q
# Expected: no NEW failures vs tests/G1_BASELINE.md (recorded pre-change reds stay red-free-of-new).
```

### Level 3: Live acceptance evidence (the deliverable gate)

```bash
timeout 900 bash tests/d1_duck_evidence.sh
# Expected: exit 0; PASS lines for: mpris-pause<=1.5s / mpris-resume / sovereignty-player /
# volume-duck-15 / volume-user-60-kept / volume-exact-restore / off-zero-lines / default-engages.
# After: `pactl get-default-sink` == pre-run value; `systemctl --user is-active voice-typing` ==
# pre-run state; `pgrep -af "voice-typing-daemon|mpv.*vt-d1"` empty; scratch dir gone.
```

### Level 4: Documentation & scope

```bash
grep -n "duck_mode" config.toml voice_typing/config.py tests/test_config.py   # "mpris" x3
git status --short   # exactly: config.toml, voice_typing/config.py, tests/test_config.py (M);
                      #          tests/d1_duck_evidence.sh, tests/D1_DUCK_EVIDENCE.md (new)
grep -c "ducking" README.md   # 0 (README untouched — Mode B is P1.M7.T2)
```

## Final Validation Checklist

### Technical Validation
- [ ] Level 1-2 green (no new failures vs G1_BASELINE.md).
- [ ] Level 3: script exit 0, all scenario PASS, machine fully restored.
- [ ] Level 4: exactly the 5 expected files changed; README/ACCEPTANCE.md untouched.

### Feature (Acceptance-Evidence) Validation — the five §4.2quinquies rows
- [ ] Music playing → arm → pauses (measured Δt recorded, < 1.5 s) → resumes at stop (journal lines).
- [ ] duck_mode="volume": ducks to 15% and restores EXACTLY (40% cycle) on a disposable sink.
- [ ] User sovereignty: manually-paused player stays paused; mid-arm 60% volume is kept (journal line).
- [ ] duck_mode="off": zero "ducking:" journal lines across arm/disarm (byte-identical).
- [ ] The flipped DEFAULT engages with NO duck_mode key in the sandbox config (row recorded).
- [ ] tests/D1_DUCK_EVIDENCE.md records all rows + Δt + journal excerpts + the path used.

### Code Quality / Scope
- [ ] Lockstep both files; only :277 changes among tests; 26-key pin untouched.
- [ ] Script honors AGENTS.md discipline: timeout-wrapped voicectl, detached daemon, PID teardown,
      trap restores sink/unit/scratch, bounded log excerpts.
- [ ] No edits to S-owned/frozen modules, daemon.py, feedback.py, systemd unit, install.sh.

### Documentation & Deployment
- [ ] Mode A comments updated (config.toml + config.py docstring); no stale "ships off" wording.
- [ ] Evidence doc notes the operator-visible default lands at the unit's next restart.

---

## Anti-Patterns to Avoid

- ❌ Don't flip only one config file — the lockstep test is the guard, and a split default is a bug.
- ❌ Don't touch the key-set test, validation set, or any frozen ducking module — values change, not keys.
- ❌ Don't run the daemon in the foreground, skip `timeout 30` on voicectl, or teardown via
  `pkill -f voice-typing` (kills the user's unit) — follow CRITICAL #3/#6 exactly.
- ❌ Don't let the sandbox daemon type into the operator's windows — `output.backend = "null"` is
  mandatory in every sandbox config.
- ❌ Don't exercise the volume tier on the REAL default sink — null-sink swap + restore-by-index only.
- ❌ Don't unload `module-null-sink` by NAME — by recorded index only (AGENTS.md warning).
- ❌ Don't edit README.md / tests/ACCEPTANCE.md — Mode B belongs to P1.M7.T2.
- ❌ Don't implement T3.S2's heal/ExecStopPost if missing — note absence in the evidence doc and move on.
- ❌ Don't leave scratch dirs, stray mpv/daemon PIDs, or unbounded logs under /tmp (tmpfs = RAM).

---

**Confidence Score: 9/10**. The flip itself is two values + one test line, pre-verified against the
live tree (the only default pin is :277; the lockstep and key-set tests adapt structurally). The
evidence script follows the repo's own e2e discipline with every hazard pre-identified (typing
safety, default-sink mutation, dual-VRAM, PID-safe teardown, tmpfs bounds). Residual risk (−1):
the live scenarios depend on host tools (mpv/playerctl/pactl) and the in-flight T3.S2 contract —
both covered by the preflight gate and the documented operator-checklist fallback with exact
expected journal lines.
