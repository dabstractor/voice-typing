# PRP — P1.M5.T3.S1: Audit T3 E2E script (`tests/e2e_virtual_mic.sh`) — null-sink setup, daemon tmux backend, drain assertion, cleanup trap

## Goal

**Feature Goal**: Produce a **complete static audit** of `tests/e2e_virtual_mic.sh` (364 lines) against
**PRD §6 T3** (Full E2E with virtual mic + tmux) and the work-item's **9 sub-checks (a)–(i)**, by
reading the script + cross-checking every claim against the LIVE source it drives (config.py /
launch_daemon.sh / ctl.py / daemon.py / typing_backends.py / the sibling `tests/test_idle_and_gpu.sh`),
then recording a per-check PASS/GAP matrix, the 2 confirmed gaps, the minor observations, and an
explicit **safe-to-run verdict**. **The script is NOT executed** — it rebinds the user's global default
audio source (`pactl set-default-source`) per AGENTS.md + the work-item's explicit "do NOT run it
unless explicitly required." The audit is STATIC.

**Verified baseline (research, this round — NO audio mutation, NO script run):**
- **7 of 9 checks PASS** (a,b,c,d,e,f,h + the trap completeness half of i). The null-sink setup,
  tmux-session/cat>file, pw-cat playback, state.json partial-polling, the post-disarm gate assertion,
  and the EXIT-trap cleanup (restore source + unload by INDEX + kill tmux + bounded daemon kill) are
  all correct + robust, verified against LIVE source.
- **GAP (g) — drain assertion [MEDIUM]:** PRD §6 T3 step 4 clause 3 ("assert the in-flight utterance's
  final IS typed after `voicectl stop`") is **NOT exercised**. The script plays PAUSE+MULTI to
  completion, polls `capture-pane` until all 5 finals match, THEN stops — so nothing is in flight at
  stop time and the daemon's drain guard (daemon.py:1065 `_text_in_flight AND _final_pending`) never
  fires. Criterion 4 asserts the **gate** (`before==after`), which is the *opposite* of a drain
  assertion. Drain LOGIC is unit-test-covered (P1.M2.T1.S2) — this is a real-audio E2E coverage gap.
- **GAP (i, timeout half) — voicectl control calls NOT wrapped in `timeout` [HIGH]:** 5 of 6 voicectl
  control calls are unwrapped (preflight `status`, ready-loop `status`, post-ready `status`, `start`,
  `stop`). Only `timeout 5 voicectl quit` in cleanup is wrapped. **ctl.py:112 has NO socket read
  timeout** ("makefile raises if socket has a timeout") → a wedged daemon hangs `voicectl` FOREVER.
  `voicectl start` is the worst: `start()`→`_load_host()` is SYNCHRONOUS on the cold model load
  (minutes; forever if the recorder-host spawn deadlocks). **The sibling `tests/test_idle_and_gpu.sh`
  explicitly codifies the fix** (`VOICECTL_TIMEOUT=30` + a `voicectl()` wrapper fn, lines 151-157 +
  353-357, with the exact "would hang voicectl FOREVER" rationale) — e2e_virtual_mic.sh does not apply
  it. Violates AGENTS.md Rule 1 ("voicectl always under timeout 30") + the work-item (i).
- **Safe-to-run verdict: CONDITIONALLY YES** — the `trap cleanup EXIT` is robust + idempotent (fires
  on pass/fail/Ctrl-C, restores the user's source FIRST, unloads by index, kills tmux + the daemon
  bounded 5s→SIGTERM→8s→SIGKILL, verifies no `vt_test` trace), and preflight refuses if a daemon is
  running. **Caveat:** the missing voicectl timeouts mean a wedged daemon during start/stop hangs the
  script until a manual Ctrl-C (which DOES trigger cleanup). Safe-but-not-unattended-safe.

**Deliverable** (1 artifact — CREATE; **NO source/test/script edit** — this is a REPORT item):
- `plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md` — a self-contained audit report with: the 9-check (a–i)
  PASS/GAP matrix (each row = check → script line → LIVE-source evidence → verdict), the 2 gaps
  (drain + voicectl-timeout) with PRD citation + recommended fixes, the minor observations, and the
  safe-to-run verdict. No existing `gap_e2e.md` at that path. (Source-side `architecture/gap_*.md`
  reports already exist for the modules — this is the TEST-SCRIPT-side audit.)

**Success Definition**:
- (a) The full `tests/e2e_virtual_mic.sh` is read + every PRD §6 T3 claim cross-checked against the
  LIVE source modules it drives (config.py, launch_daemon.sh, ctl.py, daemon.py, typing_backends.py,
  test_idle_and_gpu.sh). Findings recorded with exact script line numbers + source citations.
- (b) The 9-check matrix (a–i) is COMPLETE; each row has a verdict (PASS/GAP) + the script line + the
  LIVE-source evidence that proves the verdict (no inference, no hand-waving).
- (c) The 2 gaps are recorded with: PRD §6 T3 clause citation, WHY the script misses it, what WOULD
  test it, and the recommended fix (for a downstream REMEDIATION task — NOT applied here).
- (d) The safe-to-run verdict is explicit: YES/conditional/NO + the one caveat (voicectl timeouts) +
  the fact the trap is robust. The script is NOT run during this item.
- (e) Scope respected: ONLY `tests/e2e_virtual_mic.sh` is audited. The T6 GPU script
  (`tests/test_idle_and_gpu.sh`) is read ONLY as the timeout-discipline comparison (sibling task
  P1.M5.T3.S2 owns its full audit). NO source/test/script file is edited.

## User Persona

**Target User**: Internal — the plan orchestrator + downstream leaves:
1. **P1.M5.T3.S2** (audit the T6 GPU lifecycle script, `test_idle_and_gpu.sh`) — this item establishes
   the **timeout-discipline comparison** that S2 will rely on (S2's script DOES wrap voicectl;
   e2e_virtual_mic.sh does NOT). S2 should NOT re-derive the ctl.py no-socket-timeout fact.
2. **P1.M5.T5.S1** (acceptance-criteria cross-check) consumes this audit as the **evidence-quality
   gate** for Acceptance **#2** (drain / ≥3 s pause loses zero words) and **#4** (nothing typed while
   toggled off): the E2E proves #4 (the gate) but only *partially* proves #2's drain clause — the
   report flags exactly which clause is unit-test-only so the cross-check doesn't over-credit the E2E.
3. **A downstream REMEDIATION task** (if one is opened for the 2 gaps) reads this report as the spec:
  the exact voicectl calls to wrap + the sibling precedent to copy; the drain test shape needed.
4. **Operators/reviewers** read `gap_e2e.md` to decide whether the E2E is safe to run for real-model
  acceptance evidence, and what to fix first if it isn't.

**Use Case**: The compliance round (006) audited every module (the `architecture/gap_*.md` reports) +
converted the unit audits into "tests pass" (P1.M5.T1.*). THIS item audits the **real-audio E2E shell
script** — the only artifact that can prove criteria 2/3/4 against a real mic + real CUDA + tmux. The
audit determines: (1) does the script correctly stand up the null-sink + monitor + tmux backend + the
5 canonical utterances? (2) does it assert the right things? (3) is its cleanup trap safe? (4) is it
safe to run, or does it need a timeout fix first?

**Pain Points Addressed**: (1) The E2E is the highest-stakes test in the repo — it rebinds the user's
GLOBAL default audio source (`pactl set-default-source`) and loads CUDA models for minutes. An audit
must confirm the cleanup trap restores the source on ANY exit (the PRD §6 T3 step 5 hard rule) BEFORE
anyone runs it. (2) It surfaces the 2 gaps (drain coverage + voicectl timeout) as explicit findings so
the acceptance cross-check credits them correctly rather than treating the E2E as a black box. (3) It
catches a hang vector (unwrapped voicectl) that AGENTS.md Rule 1 + the sibling script both say must be
bounded — before a run wedges the session.

## Why

- **The E2E is the only real-mic + real-CUDA + tmux proof for 3 acceptance criteria (#2, #3, #4).**
  The offline T1 test (P1.M5.T2.S1) feeds audio directly (no mic, no typing); the mocked daemon tests
  (P1.M5.T1.S2) prove lifecycle logic. Only the E2E wires the real PyAudio→null-sink-monitor path +
  the real tmux typing backend. Auditing it (not running it) is the safe way to validate it.
- **It rebinds the global audio source — the highest-stakes side effect in the repo.** Per AGENTS.md +
  the work-item, it must NOT be run during this audit. The audit's job is to confirm the cleanup trap
  (restore source + unload module + kill tmux) is robust on ANY exit BEFORE a later, explicitly-
  authorized task runs it.
- **It surfaces the voicectl-timeout gap as a hang-prevention finding.** AGENTS.md Rule 1 exists
  precisely because voicectl's control socket has no read timeout (ctl.py:112) and a wedged daemon
  hangs it forever. The sibling `test_idle_and_gpu.sh` wraps every control call in `timeout 30`;
  `e2e_virtual_mic.sh` does not (except `quit`). Finding this NOW (before a run) prevents a wedged
  session; finding it LATER (after a hang) is exactly the "session hangs forever, hard kill" scenario
  AGENTS.md was written to prevent.
- **It corrects the acceptance evidence picture.** PRD §6 T3 step 4 has 4 sub-assertions (all-segments
  fuzzy, partials, drain, gate). The E2E covers 3 of 4 (all-segments, partials, gate) — NOT the drain.
  Recording this lets P1.M5.T5.S1 credit the E2E for #4 (gate) + #2's pause-clause, but NOT #2's
  drain-clause (which stays unit-test-only), instead of over-crediting.
- **The findings are already in place** (research this round). So this item is low-risk: re-verify the
  2 gaps + the 7 passes against LIVE source, write the report. The value is the evidence artifact +
  the explicit gap flags — not heroic debugging.

## What

Three phases, in order: **(1) read the script + LIVE-source cross-check**, **(2) the 9-check (a–i)
matrix + the 2 gaps + minor observations**, **(3) the safe-to-run verdict**. Output = `gap_e2e.md`.
**The script is NOT executed** (AGENTS.md + work-item: rebinds global audio source).

### Success Criteria

- [ ] `tests/e2e_virtual_mic.sh` read end-to-end; every PRD §6 T3 claim cross-checked against the LIVE
      source module it drives (config.py:266 XDG order, launch_daemon.sh `exec "$PY"`, ctl.py:112
      no-timeout, daemon.py:1065 drain guard + start()→_load_host() sync, typing_backends.py:54/94-105
      `/usr/bin/tmux send-keys -t`, test_idle_and_gpu.sh:151-157/353-357 VOICECTL_TIMEOUT).
- [ ] 9-check matrix (a–i) COMPLETE; each row = check → script line(s) → LIVE-source evidence → verdict.
- [ ] GAP (g) drain [MEDIUM] recorded: PRD §6 T3 step 4 clause 3; WHY play-to-completion → stop lands
      with nothing in flight → drain guard never fires; criterion 4 = gate (the opposite assertion);
      drain is unit-test-covered (P1.M2.T1.S2); the test shape that WOULD cover it.
- [ ] GAP (i) voicectl timeout [HIGH] recorded: the 5/6 unwrapped control-call table; ctl.py:112
      no-socket-timeout → forever-hang; `voicectl start` blocks on `_load_host` (cold model load);
      sibling test_idle_and_gpu.sh wraps them (VOICECTL_TIMEOUT=30 + voicectl() fn); recommended fix.
- [ ] Minor observations recorded (ready-wait comment mis-attributes model-load timing; cleanup order;
      set-default-source alt approach; TMUX_TARGET bare-session rationale; fuzzy matcher) — NOT gaps.
- [ ] Safe-to-run verdict explicit (conditionally YES; trap robust; caveat = missing voicectl timeouts);
      the script NOT run during this item.
- [ ] `gap_e2e.md` written to `plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md`, self-contained, with a clear
      VERDICT ("7/9 checks PASS; 2 gaps (drain MEDIUM, voicectl-timeout HIGH); safe-to-run = conditional").
- [ ] Scope respected: ONLY e2e_virtual_mic.sh audited; test_idle_and_gpu.sh read as comparison only;
      NO source/test/script edited (REPORT item).

## All Needed Context

### Context Completeness Check

_Pass._ The implementing agent gets: the full per-check matrix (a–i) pre-verified with script line
numbers + LIVE-source citations, the 2 gaps fully analyzed (PRD clause + why-missed + fix), the
minor observations, the safe-to-run verdict, the exact source-line references to re-confirm, the
verbatim `gap_e2e.md` scaffold, and the hard constraint (do NOT run the script). No inference required.

### Documentation & References

```yaml
# MUST READ — the audit SUBJECT (read it; it is what you are auditing, not running).
- file: tests/e2e_virtual_mic.sh
  why: "The 364-line E2E script. Its G-* load-bearing invariants (G-SOURCE record-ORIG-before-switch +
        restore-by-value + unload-by-INDEX; G-ORDERING null-sink+set-default-source BEFORE daemon launch
        because RealtimeSTT opens PyAudio ONCE at construction; G-CAPTURE read typed text via
        capture-pane not cat-mid-stream; G-RUNTIME keep real XDG_RUNTIME_DIR; G-CONFIG temp
        XDG_CONFIG_HOME override [output]+[feedback]; G-TMUX-PATH /usr/bin/tmux; G-TARGET pw-cat --target
        =SINK-name, capture-pane -t=SESSION; G-PREFLIGHT refuse if a daemon runs; G-FUZZY ≥80% token
        overlap; G-POLL-TIMEOUTS 180s/90s/0.2s; G-CLEANUP-IDEMPOTENT || true in trap). These encode the
        'correct' verdict on checks a–f,h + the trap half of i."
  critical: "NOTE the script does NOT wrap its voicectl control calls in `timeout` (only `timeout 5
             voicectl quit` in cleanup). That is GAP (i). Also NOTE criterion 4 asserts the GATE
             (before==after) — NOT the drain — that is GAP (g). The ready-wait comment says 'models
             load, up to 180s' but per lazy-load models load at `voicectl start`, not the ready-wait."

# MUST READ — the LIVE source the script drives (cross-check every claim here, don't infer).
- file: voice_typing/ctl.py
  why: "Line 112: 'Uses makefile(\"r\") (NOT settimeout — makefile raises if the socket has a timeout)'.
        Line 116 sock.connect. CONFIRMS voicectl has NO read timeout → a wedged daemon hangs it FOREVER.
        This is the root of GAP (i)."
  critical: "The control socket will NEVER time out on its own — AGENTS.md Rule 1 / VOICECTL_TIMEOUT=30
             exist for exactly this reason. Unwrapped voicectl = hang vector."

- file: voice_typing/daemon.py
  why: "(1) start() → _load_host('normal') is SYNCHRONOUS (single-flight, line 722 'while self._loading')
        → `voicectl start` BLOCKS on the cold model load (minutes; forever if recorder-host spawn
        deadlocks) → unwrapped start = worst hang vector. (2) _request_stop drain guard line 1065:
        'if self._host is not None and self._text_in_flight.is_set() and self._final_pending:
        self._begin_drain()' → drain ONLY fires when an utterance is in flight at stop time. (3)
        _dispatch('start')→_arm_response / ('stop')→status_snapshot: the control handlers. (4)
        _DRAIN_TIMEOUT_S=5.0 (line 138): drain is bounded to 5s server-side (but the socket call itself
        has no timeout — a NON-drain hang still wedges voicectl)."
  critical: "These two facts together prove BOTH gaps: start blocks (i) + stop-during-idle never drains (g)."

- file: voice_typing/typing_backends.py
  why: "Line 54 `_TMUX = '/usr/bin/tmux'`; lines 94-105 TmuxBackend.type_text =
        `[_TMUX, 'send-keys', '-t', self._tmux_target, '-l', '--', text]`. CONFIRMS the daemon uses
        /usr/bin/tmux (== script TMUX_BIN) + passes cfg.output.tmux_target straight to `-t`, so the
        script's TMUX_TARGET='voicetest' (bare session name) is correct (targets the session's active
        pane). This is the 'correct' verdict on check c+d."

- file: voice_typing/config.py
  why: "Line 262-288 VoiceTypingConfig.load search order: #1 `$XDG_CONFIG_HOME/voice-typing/config.toml`
        (first EXISTING wins); line 283-288 _xdg_config_path. CONFIRMS `XDG_CONFIG_HOME='$WORK/config'`
        → reads `$WORK/config/voice-typing/config.toml` (the script's G-CONFIG override mechanism works).
        This is the 'correct' verdict on check c."

- file: voice_typing/launch_daemon.sh
  why: "Last line `exec \"$PY\" -m voice_typing.daemon \"$@\"`. CONFIRMS the launch wrapper REPLACES
        itself with python via exec → the script's `DAEMON_PID=$!` IS the python PID → `kill $DAEMON_PID`
        in the trap kills the right process. This is the 'correct' verdict on the trap's daemon-kill step."

# MUST READ — the sibling script that DOES wrap voicectl (the timeout-discipline PRECEDENT + comparison).
- file: tests/test_idle_and_gpu.sh
  why: "Lines 151-157: 'voicectl's socket readline() has NO timeout (makefile is incompatible with
        settimeout, ctl.py … the SIGTERM-path teardown stall) would hang voicectl FOREVER. Wrap the
        control commands in timeout … VOICECTL_TIMEOUT=30'. Lines 353-357: `voicectl() { timeout
        \"$VOICECTL_TIMEOUT\" \"$VOICECTL\" \"$@\"; }` — a wrapper FUNCTION applying timeout 30 to EVERY
        control call. This is the smoking gun: the discipline exists IN-REPO; e2e_virtual_mic.sh just
        does not apply it. Cite both line ranges verbatim in the GAP (i) section."
  critical: "S2 (P1.M5.T3.S2) audits this script FULLY — you read it ONLY for the voicectl-timeout
             comparison. Do NOT audit T6's GPU assertions here (out of scope; that's S2)."

# MUST READ — AGENTS.md (the hard rules; the timeout rule binds this audit directly).
- file: AGENTS.md
  why: "Rule 1 (two timeouts on EVERY non-trivial command; 'voicectl always under timeout 30. The
        control socket will never time out on its own'). The hang-vectors table row for voicectl. Rule 2
        (never foreground the daemon — this audit doesn't run anything anyway). The 'e2e_virtual_mic.sh'
        row in the hang-vectors table: 'rebinds the global default audio source via pactl … If aborted
        between load-module and the trap, the user's mic stays pointed at a test sink.' This is WHY the
        script must NOT be run during the audit."
  critical: "Do NOT run the script. If you did run it and it wedged, the AGENTS.md Cleanup block
             (timeout 30 voicectl quit; systemctl --user stop; pkill; pactl set-default-source restore)
             is the recovery — but you should not need it. The audit is STATIC."

# MUST READ — the merged PRD (the spec the script encodes; the oracle for each verdict).
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: "§6 T3 (Full E2E with virtual mic + tmux) = the 5-step spec being audited; §4.2 #2 (graceful
        drain) = the clause GAP (g) misses; §4.2bis (lazy load) = why the ready-wait comment is
        inaccurate + why start() blocks; §4.3 (typing backends, tmux send-keys -t) = the c/d verdict;
        §4.8 (voicectl) + §4.6 (state.json partials) = the f verdict. §7 #2/#3/#4 = the acceptance
        clauses this E2E is evidence for (with the drain caveat). When judging whether the script
        'covers' a clause, the PRD wording is the source of truth."

# MUST READ (cross-ref, cite-don't-re-audit) — the prior drain audit (drain logic is unit-covered).
- file: plan/006_862ee9d6ef41/P1M2T1S2/research/drain_audit_findings.md
  why: "The drain LOGIC was already audited (graceful stop, _DRAIN_TIMEOUT_S watchdog, abort-on-idle).
        GAP (g) is NOT 'drain is broken' — it is 'the E2E does not exercise the drain path with real
        audio'. Cite this to show drain is unit-test-covered (test_daemon.py mocked) so the gap is
        E2E-coverage-only, not a missing feature."

# External — the virtual-mic pattern (validates the 'correct' verdict on checks a–f).
- url: https://luke.hsiao.dev/blog/pipewire-virtual-microphone/
  why: "Luke Hsiao 'Pipewire virtual microphone': `pactl load-module module-null-sink sink_name=...` →
        the sink auto-creates a `.<name>.monitor` source → record from the monitor. This is the
        canonical PipeWire virtual-mic E2E pattern. Confirms the script's null-sink + set-default-source
        vt_test.monitor + pw-cat --target vt_test approach is the standard idiom (checks a,b,e)."
- url: http://www.benashby.com/resources/pipewire-virtual-devices/
  why: "'PipeWire Virtual Devices' guide: null sinks + monitors + loopbacks. Reinforces the
        record-original-source-before-set-default-source + restore-in-trap idiom (checks a + i trap)."

# Cross-ref — the source-side audits (this is the TEST-SCRIPT-side audit; don't re-audit source).
- file: plan/006_862ee9d6ef41/architecture/gap_socket.md      # control-socket no-timeout is audited here (source side)
- file: plan/006_862ee9d6ef41/architecture/gap_voicectl.md    # voicectl CLI / socket readline audited here
- file: plan/006_862ee9d6ef41/architecture/gap_typing.md      # TmuxBackend /usr/bin/tmux audited here
- file: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md   # lazy load / drain audited here
  why: "These already audited the SOURCE. This item audits the TEST SCRIPT that DRIVES that source.
        Cite them (e.g. 'per gap_socket.md, the control socket has no read timeout') rather than
        re-deriving. Don't duplicate their findings into gap_e2e.md beyond the one-line citations."
```

### Current Codebase tree (relevant slice — state at P1.M5.T3.S1)

```bash
tests/
├── e2e_virtual_mic.sh          (364 lines) ← IN SCOPE: the AUDIT SUBJECT (READ ONLY; do NOT run)
│                                  drives a real PipeWire null-sink + monitor + CUDA daemon + tmux backend
├── test_idle_and_gpu.sh        (T4+T6)    ← comparison-only read (sibling P1.M5.T3.S2 audits it fully);
│                                  cite its VOICECTL_TIMEOUT=30 + voicectl() wrapper fn as the timeout precedent
├── make_test_audio.sh          (generator)← read to confirm the 5 canonical refs the script fuzzy-matches
├── out/utt_{pause,multi,simple}.wav        # the WAVs the script plays (don't play them — just confirm they're named right)
└── (unit tests)                           OUT — P1.M5.T1.* (mocked + pure-Python) + P1.M5.T2.S1 (T1 offline)
voice_typing/
├── ctl.py                      # send_command: makefile('r'), NO settimeout (line 112) ← root of GAP (i)
├── daemon.py                   # start()→_load_host() sync (blocks); _request_stop drain guard (line 1065)
├── typing_backends.py          # TmuxBackend: _TMUX='/usr/bin/tmux', send-keys -t (lines 54,94-105)
├── config.py                   # load() XDG search order #1 (line 262-288)
└── launch_daemon.sh            # exec "$PY" → $! IS python PID (last line)
plan/006_862ee9d6ef41/
├── P1M5T3S1/gap_e2e.md                       # ← OUTPUT (NEW; this item creates it)
├── P1M5T3S1/research/e2e_script_audit.md     # ← this PRP's research (already written; feed into the report)
├── architecture/gap_{socket,voicectl,typing,lifecycle}.md   # source-side audits (cite, don't re-derive)
└── P1M2T1S2/research/drain_audit_findings.md                # drain is unit-covered (cite for GAP g)
```

### Desired Codebase tree with files to be added/modified

```bash
plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md   # NEW — the audit report (the SOLE deliverable)
# (NO source/test/script files edited. This is a REPORT item — audit only, no run, no edit.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DO NOT RUN e2e_virtual_mic.sh during this item. It runs `pactl set-default-source
#   vt_test.monitor` (rebinds the user's GLOBAL default audio source) + loads CUDA models for minutes.
#   AGENTS.md + the work-item explicitly say "do NOT run it unless explicitly required". The audit is
#   STATIC: read the script + the LIVE source it drives, record findings. If you accidentally started
#   it, hit Ctrl-C IMMEDIATELY (its EXIT trap restores the source) and run the AGENTS.md Cleanup block.

# CRITICAL #2 — voicectl has NO socket read timeout (ctl.py:112). This is the root of GAP (i). The
#   sibling test_idle_and_gpu.sh wraps every control call in `timeout 30` (VOICECTL_TIMEOUT=30 +
#   voicectl() fn) for exactly this reason. e2e_virtual_mic.sh does not (except `quit`). Any voicectl
#   command YOU run during the audit (e.g. to check `voicectl status` for a running daemon) MUST be
#   wrapped: `timeout 15 .venv/bin/voicectl status`. AGENTS.md Rule 1 is non-negotiable.

# CRITICAL #3 — `voicectl start` is SYNCHRONOUS on the model load (daemon.py start()→_load_host()).
#   This is why the script's `"$VOICECTL" start >/dev/null` (unwrapped) is the worst hang vector: it
#   blocks for the cold cuDNN/cuBLAS init + 2 model loads (minutes), and FOREVER if the recorder-host
#   spawn deadlocks (the "deadlock on the recorder/GIL" AGENTS.md warns about). Don't conflate this
#   with the ready-wait (which only polls the socket, fast) — the load happens at `start`, not before.

# CRITICAL #4 — GAP (g) is NOT "drain is broken". The drain LOGIC is sound + unit-tested (test_daemon.py,
#   audited in P1.M2.T1.S2). GAP (g) is "the E2E does not EXERCISE the drain path with real audio",
#   because its play-to-completion design means `voicectl stop` lands with nothing in flight
#   (daemon.py:1065 `_text_in_flight AND _final_pending` both clear). Frame it as a coverage gap, not a
#   defect. Also NOTE criterion 4's PASS condition (before==after) is the OPPOSITE of a drain assertion.

# CRITICAL #5 — zsh aliases `tmux`/`python`/`pytest`. The script correctly uses /usr/bin/tmux (TMUX_BIN)
#   + .venv/bin/{python,voicectl}. If you run any helper command during the audit, use the full paths.
#   (You shouldn't need to run anything audio-related; static read only.)

# CRITICAL #6 — distinguish the 9 checks (a–i) from the PRD §6 T3 4-sub-assertion step-4. The work-item's
#   (a)–(i) map to setup + cleanup; PRD step 4's 4 sub-assertions map to the ASSERTION block:
#     step4.1 all-segments fuzzy (incl post-pause) → check (g)-adjacent, covered (ALLREFS_OK + CRIT2_OK)
#     step4.2 partials in state.json → covered (CRIT3_OK) [== work-item check (f)]
#     step4.3 drain (in-flight final typed after stop) → NOT covered [== work-item check (g) = GAP]
#     step4.4 nothing typed post-disarm → covered (CRIT4_OK) [== work-item check (h)]
#   Record BOTH framings in the report (the a–i matrix AND the step-4 sub-assertion map) so the
#   acceptance cross-check (P1.M5.T5.S1) can credit each acceptance clause precisely.

# CRITICAL #7 — this is a REPORT item. It does NOT fix the script or any source. The 2 gaps get a
#   "recommended fix (for a downstream remediation task)" note; you do NOT apply it. The ONLY edits
#   you make are to `plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md` (CREATE). Do NOT touch
#   tests/e2e_virtual_mic.sh, any voice_typing/*.py, PRD.md, tasks.json, prd_snapshot.md, .gitignore.

# CRITICAL #8 — scope boundary. Audit ONLY e2e_virtual_mic.sh. test_idle_and_gpu.sh is read as the
#   voicectl-timeout comparison (sibling P1.M5.T3.S2 owns its full T4/T6 audit). Do NOT audit T6's
#   nvidia-smi assertions or T4's idle-stability logic here — those are S2 / P1.M5.T4.*.
```

## Implementation Blueprint

### Data models and structure

N/A — no code models. The deliverable is one Markdown audit report. The "data" is the 9-check matrix +
the 2 gaps + the minor observations + the safe-to-run verdict.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: READ the audit subject + cross-check against LIVE source (NO run, NO audio mutation).
  - READ tests/e2e_virtual_mic.sh end-to-end (364 lines). Note its G-* invariants (G-SOURCE, G-ORDERING,
    G-CAPTURE, G-RUNTIME, G-CONFIG, G-TMUX-PATH, G-TARGET, G-PREFLIGHT, G-FUZZY, G-POLL-TIMEOUTS,
    G-CLEANUP-IDEMPOTENT) — these encode the 'correct' verdicts on the setup/cleanup checks.
  - CROSS-CHECK the 2 gaps against LIVE source (confirm, don't infer):
      GAP (i) voicectl timeout: ctl.py:112 (no settimeout; makefile('r')); daemon.py start()→_load_host()
        sync (single-flight line 722); test_idle_and_gpu.sh:151-157 + 353-357 (VOICECTL_TIMEOUT=30 +
        voicectl() fn — the precedent e2e_virtual_mic.sh does NOT use).
      GAP (g) drain: daemon.py:1065 (_request_stop drain guard: `_text_in_flight.is_set() AND
        _final_pending`); confirm the script's stop lands AFTER all 5 finals matched (nothing in flight).
  - CROSS-CHECK the 'correct' verdicts against LIVE source: config.py:262-288 (XDG order #1),
    launch_daemon.sh last line (exec "$PY" → $! = python PID), typing_backends.py:54+94-105
    (/usr/bin/tmux + send-keys -t tmux_target), daemon.py _dispatch (start/stop/status/quit handlers).
  - DO NOT run the script, do NOT run pactl, do NOT arm the mic. (If `timeout 15 .venv/bin/voicectl
    status` is needed to confirm a daemon ISN'T running, it's fine — but it's not required for the audit.)
  - GO to Task 2.

Task 2: BUILD the 9-check (a–i) matrix + the PRD §6 T3 step-4 sub-assertion map.
  - For EACH of the 9 work-item checks (a–i), record: check → script line(s) → LIVE-source evidence →
    verdict (PASS/GAP). The research §1 matrix is the pre-filled answer — CONFIRM line numbers against
    the live file (they may have drifted) and copy into the report. The 9 verdicts:
      (a) records ORIG source before switch → PASS (G-SOURCE)
      (b) loads module-null-sink → PASS (captures MODIDX index, not name)
      (c) daemon tmux backend → PASS (config.py XDG order #1; config.toml override backend=tmux)
      (d) tmux session cat>file → PASS (/usr/bin/tmux new-session; matches daemon TmuxBackend send-keys -t)
      (e) plays WAVs via pw-cat → PASS (--target vt_test = SINK name; G-TARGET)
      (f) polls state.json partials → PASS (bg jq loop → partials.log; criterion 3)
      (g) asserts drain → GAP (MEDIUM) — see Task 3
      (h) asserts nothing post-disarm → PASS (CRIT4 before==after; the on_final gate)
      (i) trap + all voicectl in timeout → PARTIAL (trap complete PASS; voicectl timeout INCOMPLETE = GAP HIGH) — see Task 3
  - BUILD the PRD §6 T3 step-4 sub-assertion map (4 clauses → which script criterion covers it):
      step4.1 all-segments fuzzy (incl post-pause) → ALLREFS_OK + CRIT2_OK [COVERED]
      step4.2 partials in state.json → CRIT3_OK [COVERED] == check (f)
      step4.3 drain (in-flight final after stop) → [NOT COVERED] == check (g) = GAP
      step4.4 nothing typed post-disarm → CRIT4_OK [COVERED] == check (h)
  - RECORD the minor observations (research §4): ready-wait comment mis-attributes model-load timing
    (load happens at `start`, not the ready-wait, per lazy-load); cleanup order (restore-then-unload,
    safe); set-default-source vt_test.monitor is the PRD-sanctioned alternative; TMUX_TARGET bare
    session name (base-index=1 rationale); fuzzy matcher (Counter multiset ≥0.80). All NOT gaps.
  - GO to Task 3.

Task 3: WRITE the 2 GAP sections + the recommended fixes (for a downstream remediation task).
  - GAP (g) drain [MEDIUM]:
      PRD clause: §6 T3 step 4 clause 3 + §4.2 #2.
      WHY missed: play-to-completion design → stop lands AFTER all 5 finals matched → nothing in flight →
        daemon.py:1065 drain guard (_text_in_flight AND _final_pending) never fires.
      criterion 4 PASS condition (before==after) is the OPPOSITE of a drain assertion (a drained final
        would make before!=after → FAIL).
      coverage elsewhere: drain LOGIC unit-tested (test_daemon.py; audited P1.M2.T1.S2) — this is an
        E2E-coverage gap, NOT a missing feature.
      the test shape that WOULD cover it: stop DURING an in-flight utterance (e.g. stop in the 3 s mid-
        utt_pause silence before PAUSE_B's final) and assert PAUSE_B IS typed despite the stop (drain).
  - GAP (i) voicectl timeout [HIGH]:
      AGENTS.md Rule 1 + work-item (i): "all voicectl calls wrapped in timeout" / "voicectl always under
        timeout 30".
      ctl.py:112 root cause: NO socket read timeout (makefile('r') incompatible with settimeout) → a
        wedged daemon hangs voicectl FOREVER.
      the 5/6 unwrapped-call table: preflight status, ready-loop status, post-ready status, start, stop
        (only `timeout 5 voicectl quit` in cleanup is wrapped).
      worst offender: `voicectl start` blocks on _load_host() cold model load (minutes; forever if
        recorder-host spawn deadlocks).
      precedent: test_idle_and_gpu.sh:151-157 + 353-357 (VOICECTL_TIMEOUT=30 + voicectl() wrapper fn).
      recommended fix: copy the VOICECTL_TIMEOUT=30 + voicectl() fn pattern from test_idle_and_gpu.sh,
        OR wrap each call inline (`timeout 30 "$VOICECTL" start`, etc.). (For a REMEDIATION task — NOT
        applied here; this is a REPORT item.)
  - GO to Task 4.

Task 4: WRITE the safe-to-run verdict + plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md (the SOLE deliverable).
  - VERDICT: CONDITIONALLY YES. The `trap cleanup EXIT` is robust + idempotent (fires on pass/fail/
    Ctrl-C; restores source FIRST; unloads module BY INDEX; kills tmux; bounded daemon kill 5s quit →
    SIGTERM → 8s grace → SIGKILL; verifies no vt_test trace). Preflight refuses if a daemon runs. PRD
    §6 T3 step 5 hard rule (MUST NOT leave default source switched) is HONORED.
  - CAVEAT: the missing voicectl timeouts (GAP i) mean a wedged daemon during start/stop hangs the
    script until a manual Ctrl-C (which DOES trigger cleanup). So safe-but-not-unattended-safe. Apply
    the §3 timeout fix before any unattended/CI run.
  - CREATE plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md (NEW). Use the verbatim scaffold in "Task 4 SOURCE".
    Fill the LIVE-confirmed line numbers + the 2 gap sections + the verdict.
  - DO NOT edit the script, any source, PRD.md, tasks.json, prd_snapshot.md, .gitignore. REPORT item only.

Task 5: (NONE) — no source/test/script changes, no run. This is a static audit + documentation item.
```

#### Task 4 SOURCE — `gap_e2e.md` verbatim scaffold (pre-fill the static parts; confirm line numbers LIVE)

```markdown
# Audit — P1.M5.T3.S1: `tests/e2e_virtual_mic.sh` (PRD §6 T3 — Full E2E with virtual mic + tmux)

**Date:** <YYYY-MM-DD>
**Method:** STATIC audit (read-only). NOT run — the script runs `pactl set-default-source` (rebinds the
user's GLOBAL default audio source) + loads CUDA models for minutes (AGENTS.md + work-item: "do NOT run
it unless explicitly required"). Findings cross-checked against the LIVE source the script drives.
**Verdict:** 7/9 checks PASS; **2 gaps** — (g) drain assertion [MEDIUM], (i) voicectl-timeout wrapping
[HIGH]. **Safe to run: CONDITIONALLY** (trap is robust; caveat = missing voicectl timeouts).

## 1. The 9-check matrix (work-item contract a–i)

| # | check | script line(s) | LIVE-source evidence | verdict |
|---|---|---|---|---|
| (a) | records ORIG default source BEFORE switching | `ORIG_SRC="$(pactl get-default-source)"` (before load-module) | G-SOURCE comment; restore-by-value in trap | ✅ PASS |
| (b) | loads module-null-sink | `MODIDX="$(pactl load-module module-null-sink sink_name="$SINK" media.class=Audio/Sink)"` (`SINK=vt_test`) | captures module INDEX (not name) → safe unload | ✅ PASS |
| (c) | daemon with tmux backend | config.toml override `[output] backend="tmux"`, `tmux_target="voicetest"`; `XDG_CONFIG_HOME="$WORK/config" "$LAUNCH"` | config.py:262-288 XDG search order #1 = `$XDG_CONFIG_HOME/voice-typing/config.toml` | ✅ PASS |
| (d) | tmux session running cat>file | `"$TMUX_BIN" new-session -d -s "$TMUX_SESS" "cat > '$CAPFILE'"` (`TMUX_BIN=/usr/bin/tmux`) | typing_backends.py:54+94-105 `_TMUX='/usr/bin/tmux'`, `send-keys -t <tmux_target> -l` | ✅ PASS |
| (e) | plays WAVs via pw-cat | `pw-cat -p --target "$SINK" "$PAUSE_WAV"` (+ `$MULTI_WAV`, `$SIMPLE_WAV`) | `--target vt_test` = SINK name (G-TARGET); monitor = `vt_test.monitor` | ✅ PASS |
| (f) | polls state.json partials DURING playback | bg loop `jq -r .partial "$WORK/state.json"` → `partials.log` (150×0.2s) | criterion 3 = partials.log non-empty | ✅ PASS |
| (g) | **asserts drain (in-flight final typed after stop)** | — (criterion 4 asserts the GATE, not drain) | daemon.py:1065 drain guard needs `_text_in_flight AND _final_pending`; both clear at stop time | ⚠️ **GAP (MEDIUM)** — §2 |
| (h) | asserts nothing typed post-disarm | CRIT4_OK: `before="$typed"` → stop → play `$SIMPLE_WAV` → `after=capture_pane` → assert `before==after` | the on_final gate + disarmed mic | ✅ PASS |
| (i) | EXIT trap restores source + unloads module + kills tmux; **ALL voicectl in timeout** | `trap cleanup EXIT` (complete) | trap is complete + idempotent; **voicectl timeout INCOMPLETE** | ⚠️ **PARTIAL — trap PASS, voicectl-timeout GAP (HIGH)** — §3 |

## 2. GAP (g) — drain path NOT exercised by this E2E [MEDIUM]

**PRD clause:** §6 T3 step 4 clause 3 ("assert the in-flight utterance's final IS typed after
`voicectl stop`") + §4.2 #2 (graceful drain).

**Why missed:** the script plays `utt_pause.wav` (2 finals) THEN `utt_multi.wav` (3 finals) to
completion, polls `capture-pane` up to 90s until ALL 5 refs fuzzy-match (`break`), THEN calls
`voicectl stop`. At stop time, playback finished long ago + all 5 finals are typed → **nothing is in
flight**. daemon.py:1065 `_request_stop` begins a drain ONLY when `_text_in_flight.is_set() AND
_final_pending` — both clear here → the drain guard never fires → the graceful-drain path (§4.2 #2) is
NOT exercised with real audio.

**Conflict note:** criterion 4's PASS condition (`before==after`, "nothing typed after stop") is the
*opposite* of a drain assertion. If a final WERE drained+typed after stop, `after != before` → CRIT4
would FAIL. So the script's design measures the GATE (PRD §6 T3 step 4 clause 4 / Acceptance #4), not
the drain (clause 3).

**Coverage elsewhere:** the drain LOGIC is sound + unit-tested (test_daemon.py mocked; audited
P1.M2.T1.S2 / `research/drain_audit_findings.md`). So this is an **E2E-coverage gap**, not a missing
feature or a drain bug.

**Test shape that WOULD cover it:** stop DURING an in-flight utterance (e.g. send `voicectl stop`
inside the 3 s mid-`utt_pause.wav` silence, before PAUSE_B's final lands) and assert PAUSE_B IS typed
despite the stop (the drain lets the final model finish + on_final types it before disarm). (Fix for a
downstream remediation task — NOT applied here; this is a REPORT item.)

**Acceptance impact:** P1.M5.T5.S1 should credit the E2E for Acceptance **#4** (gate) + the
**pause-clause** of #2 (PAUSE_B transcribed), but NOT the **drain-clause** of #2 (stop-during-speech),
which stays unit-test-only.

## 3. GAP (i, voicectl-timeout half) — voicectl control calls NOT wrapped in `timeout` [HIGH]

**Requirement:** AGENTS.md Rule 1 ("voicectl always under timeout 30. The control socket will never
time out on its own") + work-item (i) ("All voicectl calls wrapped in timeout").

**Root cause:** ctl.py:112 — "Uses makefile('r') (NOT settimeout — makefile raises if the socket has a
timeout)". There is **NO read timeout**. A daemon that accepts the connection but never replies
(wedged on its control lock, mid-shutdown VRAM release, recorder-host spawn deadlock) → `voicectl`
blocks **FOREVER**.

**The 6 voicectl control calls in e2e_virtual_mic.sh:**

| call | site | wrapped in `timeout`? |
|---|---|---|
| `"$VOICECTL" status` | preflight (daemon-running check) | ❌ NO |
| `"$VOICECTL" status` | ready-wait loop (360×0.5s) | ❌ NO |
| `"$VOICECTL" status \|\| true` | post-ready echo | ❌ NO |
| `"$VOICECTL" start >/dev/null` | arm (criterion run) | ❌ NO — **blocks on cold model load (minutes); FOREVER if recorder-host spawn deadlocks** |
| `"$VOICECTL" stop >/dev/null` | disarm (criterion 4) | ❌ NO |
| `timeout 5 "$VOICECTL" quit` | cleanup() trap | ✅ YES (the ONLY one) |

**Worst offender — `voicectl start`:** daemon.py `start()` → `_load_host("normal")` is SYNCHRONOUS
(single-flight, line 722 `while self._loading`) → `voicectl start` BLOCKS for the cold cuDNN/cuBLAS
init + 2 model loads (minutes); a recorder-host spawn deadlock (the "deadlock on the recorder/GIL"
AGENTS.md warns about) → hangs forever, blocking the whole script until a manual Ctrl-C.

**In-repo precedent (the sibling script DOES wrap):** `tests/test_idle_and_gpu.sh`:
- lines 151-157: "voicectl's socket readline() has NO timeout (makefile is incompatible with
  settimeout, ctl.py … the SIGTERM-path teardown stall) would hang voicectl FOREVER. Wrap the control
  commands in timeout … `VOICECTL_TIMEOUT=30`"
- lines 353-357: `voicectl() { timeout "$VOICECTL_TIMEOUT" "$VOICECTL" "$@"; }` — a wrapper FUNCTION
  applying `timeout 30` to EVERY control call.

So the discipline exists in-repo; `e2e_virtual_mic.sh` simply does not apply it (except `quit`).

**Recommended fix (for a downstream remediation task — NOT applied here):** copy the
`VOICECTL_TIMEOUT=30` + `voicectl()` wrapper-function pattern from test_idle_and_gpu.sh, OR wrap each
call inline (`timeout 30 "$VOICECTL" start`, `timeout 30 "$VOICECTL" stop`, etc.). The ready-wait +
post-ready `status` calls can use a shorter timeout (e.g. `timeout 5`) since they should be sub-second.

## 4. Minor observations (NOT gaps — recorded for completeness)

1. **Ready-wait comment mis-attributes model-load timing:** "waiting for ready (models load, up to
   180s)" implies the ready-wait covers model load. Per §4.2bis (lazy load) + `start()`→`_load_host()`
   (synchronous), models load at `voicectl start`, NOT during the ready-wait (which only polls the
   control socket, fast). Harmless (the 180s budget is never consumed; start blocks on the load
   instead) but the comment is inaccurate.
2. **Cleanup order** = daemon-stop → restore source → unload-module(by index) → kill tmux → rm temp.
   PRD §6 T3 step 5 lists "unload module, restore default source, kill tmux"; the script does
   restore-then-unload. Either order is safe (both happen; trap idempotent + best-effort). Restoring
   the source first reconnects the user's mic ASAP — arguably better.
3. **`set-default-source vt_test.monitor`** is the PRD §6 T3 step 1 *alternative* (vs the
   `input_device_index` PyAudio-resolution path). PRD sanctions it ("Alternatively `pactl
   set-default-source vt_test.monitor` … record it first!"). Script honors both parentheticals:
   records ORIG_SRC first, restores in trap. ✅
4. **TMUX_TARGET="voicetest" bare session name** (not `voicetest:0.0`): documented rationale = this
   machine's tmux base-index=1 → first pane is `voicetest:1.0`. daemon TmuxBackend passes
   tmux_target straight to `-t` → bare session name targets the active pane. Correct.
5. **`unset TMUX TMUX_PANE TMUX_TMPDIR`** at top → daemon (launched via `$LAUNCH`, inherits env) +
   script both talk to the default tmux socket (daemon send-keys has no `-L`). ✅
6. **Fuzzy matcher** = python `Counter` multiset overlap ≥0.80, case/punct-insensitive — matches PRD
   §6 "≥80% token overlap". 5 refs PINNED verbatim from make_test_audio.sh. ✅

## 5. PRD §6 T3 step-4 sub-assertion map (4 clauses → coverage)

| PRD §6 T3 step 4 clause | script criterion | verdict |
|---|---|---|
| 4.1 all-segments fuzzy (incl post-pause half) | ALLREFS_OK + CRIT2_OK (5 refs) | ✅ COVERED |
| 4.2 partials observable in state.json DURING playback | CRIT3_OK (partials.log non-empty) | ✅ COVERED == check (f) |
| 4.3 in-flight final typed after `voicectl stop` (drain) | — (stop lands with nothing in flight) | ❌ NOT COVERED == check (g) = GAP |
| 4.4 nothing further typed while playing one more WAV after drain (gate) | CRIT4_OK (before==after) | ✅ COVERED == check (h) |

## 6. Safe-to-run verdict

**CONDITIONALLY YES**, with one caveat.

- ✅ **Cleanup trap is robust + idempotent:** `trap cleanup EXIT` fires on ANY exit (pass, fail,
  Ctrl-C). It (1) stops the daemon bounded — `timeout 5 voicectl quit` → SIGTERM the PID → 8s grace
  (16×0.5s) → SIGKILL; (2) restores the user's default source FIRST (`pactl set-default-source
  $ORIG_SRC`); (3) unloads the null-sink BY INDEX (`pactl unload-module $MODIDX` — never by name);
  (4) kills the tmux session; (5) removes temp files; (6) verifies no `vt_test` trace. The PRD §6 T3
  step 5 hard rule ("MUST NOT leave the user's default source switched") is HONORED.
- ✅ **Preflight** refuses if a daemon is already running (`voicectl status` answers OR `systemctl
  --user is-active voice-typing`) — won't collide with the user's real daemon.
- ⚠️ **Caveat:** missing voicectl timeouts (§3). A wedged daemon during `voicectl start`/`stop` hangs
  the script until a manual Ctrl-C (which DOES trigger cleanup → source restored). So
  **safe-but-not-unattended-safe**: an operator must be able to Ctrl-C it. Apply the §3 timeout fix
  before any unattended/CI run.

**Do NOT run during this audit item** (AGENTS.md: rebinds global default audio source). If a later
task is explicitly authorized to run it, apply the §3 timeout fix first.

## 7. Cross-references

- Source-side audits (cite, don't re-derive): `architecture/gap_socket.md` (no socket timeout),
  `gap_voicectl.md`, `gap_typing.md` (TmuxBackend /usr/bin/tmux), `gap_lifecycle.md` (lazy load + drain).
- Drain logic unit coverage: `P1M2T1S2/research/drain_audit_findings.md` (test_daemon.py mocked).
- T1 offline (drain's offline backstop): `P1M5T2.S1` (test_feed_audio.py).
- Timeout precedent: `tests/test_idle_and_gpu.sh:151-157,353-357` (sibling P1.M5.T3.S2 audits it fully).
- Acceptance evidence consumer: `P1.M5.T5.S1` (#2 drain-clause caveat, #4 gate).
```

### Implementation Patterns & Key Details

```python
# The verdict logic (Task 2): for each of the 9 checks (a–i), does the script DO it correctly?
#   a–f,h + trap(i) → YES → PASS (record the script line + LIVE-source evidence).
#   g → NO (drain not exercised; play-to-completion) → GAP MEDIUM.
#   voicectl-timeout(i) → NO (5/6 unwrapped; ctl.py no socket timeout) → GAP HIGH.
# Don't invent gaps: the 7 passes ARE correct (verified against LIVE source). The 2 gaps ARE real
# (verified against ctl.py:112 + daemon.py:1065 + start()/_load_host + the sibling script).

# The drain-vs-gate distinction (Task 3 GAP g): criterion 4 PASS == before==after (GATE, nothing new
# typed post-disarm). A DRAIN assertion would be the OPPOSITE (an in-flight final IS typed post-stop).
# They cannot both be the same assertion. The script tests the gate; the drain is a SEPARATE,
# uncovered clause. Don't conflate them. The drain guard (daemon.py:1065) fires only when an
# utterance is in flight at stop — the script's design never creates that condition.

# The voicectl-timeout finding (Task 3 GAP i): the root cause is ONE fact — ctl.py:112 has no socket
# read timeout. Everything else follows: unwrapped voicectl can hang forever; start blocks on the
# model load (the worst case); the sibling script wraps precisely because of this. Cite ctl.py:112 +
# the sibling's VOICECTL_TIMEOUT=30 as the twin pillars of the finding.

# What "safe to run" means (Task 4): the cleanup TRAP is the safety mechanism (restores source on any
# exit). The trap is robust → the test is safe IF an operator can Ctrl-C a hang. The missing voicectl
# timeouts mean a hang is POSSIBLE (a wedged daemon) → not unattended-safe. The fix (§3) makes it
# unattended-safe. Do NOT overstate: the script is NOT dangerous to run (trap restores the source);
# it just doesn't honor the timeout discipline its sibling does.

# Scope discipline: read test_idle_and_gpu.sh ONLY for the voicectl-timeout comparison (lines 151-157,
# 353-357). Do NOT audit its T4 idle-stability or T6 GPU-lifecycle assertions — those belong to
# P1.M5.T3.S2 (T6) + P1.M5.T4.* (T4). Cite the sibling; don't audit it.
```

### Integration Points

```yaml
CONSUMES (read-only):
  - tests/e2e_virtual_mic.sh                                   # the audit SUBJECT (read; do NOT run)
  - tests/test_idle_and_gpu.sh                                 # comparison-only (cite VOICECTL_TIMEOUT=30 + voicectl() fn; lines 151-157,353-357)
  - tests/make_test_audio.sh                                   # confirms the 5 canonical refs the script fuzzy-matches
  - voice_typing/{ctl,daemon,typing_backends,config}.py        # LIVE source the script drives (cross-check the verdicts)
  - voice_typing/launch_daemon.sh                              # exec "$PY" → $! = python PID (trap's daemon-kill correctness)
  - plan/006_862ee9d6ef41/prd_snapshot.md                      # §6 T3 (the spec) + §4.2 #2 (drain) + §4.2bis (lazy load) + §4.3 (tmux) + §7 #2/#4
  - plan/006_862ee9d6ef41/architecture/gap_{socket,voicectl,typing,lifecycle}.md  # source-side audits (cite)
  - plan/006_862ee9d6ef41/P1M2T1S2/research/drain_audit_findings.md              # drain is unit-covered (cite for GAP g)
  - plan/006_862ee9d6ef41/P1M5T3S1/research/e2e_script_audit.md                 # THIS PRP's research (feed into the report)

PRODUCES (the SOLE output):
  - plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md                  # NEW audit report (9-check matrix + 2 gaps + minor obs + safe-to-run verdict)

FEEDS (downstream consumers):
  - P1.M5.T3.S2 (T6 GPU-lifecycle script audit)                # inherits the voicectl-timeout comparison (don't re-derive ctl.py:112)
  - P1.M5.T5.S1 (acceptance cross-check)                       # #2 drain-clause caveat (unit-only) + #4 gate (E2E-covered); credits each clause precisely
  - a downstream REMEDIATION task (if opened)                  # the 2 gaps' recommended fixes (voicectl wrapper; drain test shape)

PARALLEL-SAFE:
  - P1.M5.T2.S1 (T1 offline test, in flight) = ZERO file overlap (different subject; report goes to P1M5T3S1/).
  - P1.M5.T3.S2 (T6 script audit, planned) = ZERO overlap yet (not started); this item HANDS it the voicectl-timeout fact.
  - Shared surface = the SOURCE modules (ctl.py/daemon.py) — both items READ them (read-only); no edit conflict possible (REPORT items).
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# The deliverable is a Markdown audit report — validate structure + content, not code.
test -f plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md && echo "EXISTS"
grep -q 'P1.M5.T3.S1'           plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md && echo "titled"
grep -qi '9-check\|9 checks\|a–i\|a-i' plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md && echo "9-check matrix present"
grep -qi 'drain.*MEDIUM\|GAP.*g.*drain' plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md && echo "drain gap flagged"
grep -qi 'voicectl.*timeout\|VOICECTL_TIMEOUT\|ctl.py:112' plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md && echo "voicectl-timeout gap flagged"
grep -qi 'safe.to.run\|CONDITIONALLY' plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md && echo "safe-to-run verdict present"
# Expected: EXISTS; title + 9-check matrix + drain gap + voicectl-timeout gap + safe-to-run verdict present.
```

### Level 2: LIVE-source re-confirmation (NO run, NO audio mutation — read-only greps)

```bash
# Re-confirm the 2 gaps' root facts against the LIVE source (the agent should cite these line ranges).
cd /home/dustin/projects/voice-typing

# GAP (i) root: voicectl has NO socket read timeout.
grep -n "makefile" voice_typing/ctl.py | head -3
#   expect: line ~112 "Uses makefile(\"r\") (NOT settimeout — makefile raises if the socket has a timeout …)"

# GAP (i) precedent: the sibling script DOES wrap voicectl.
grep -n "VOICECTL_TIMEOUT\|^voicectl()" tests/test_idle_and_gpu.sh
#   expect: VOICECTL_TIMEOUT=30 + the `voicectl() { timeout … }` wrapper fn (lines ~156, ~357)

# GAP (i) worst-case: start() blocks on the model load.
grep -n "def start\|_load_host" voice_typing/daemon.py | head -4

# GAP (g) root: drain guard fires only when an utterance is in flight at stop.
grep -n "_text_in_flight.is_set() and self._final_pending\|def _request_stop\|_begin_drain" voice_typing/daemon.py | head -5

# 'correct' verdicts: TmuxBackend /usr/bin/tmux + send-keys -t ; config XDG order #1 ; launch exec.
grep -n "_TMUX = \|send-keys" voice_typing/typing_backends.py | head -3
grep -n "XDG_CONFIG_HOME" voice_typing/config.py | head -2
tail -1 voice_typing/launch_daemon.sh   # expect: exec "$PY" -m voice_typing.daemon "$@"
# Expected: every grep returns the cited line; confirms the verdicts without running anything.
```

### Level 3: Integration Testing (System Validation) — N/A (REPORT item; do NOT run the script)

```bash
# THERE IS NO Level 3 FOR THIS ITEM. The script is NOT run (rebinds global audio source; AGENTS.md).
# If you are tempted to run `voicectl status` to "check" something, wrap it: `timeout 15 .venv/bin/voicectl status`.
# The audit is STATIC. The "integration" is the LIVE-source re-confirmation in Level 2, not execution.
# (A LATER, explicitly-authorized task may run the script — after applying the §3 voicectl-timeout fix.)
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Confirm the 5 canonical refs the script fuzzy-matches are the make_test_audio.sh strings (consistency).
grep -E "PAUSE_A=|PAUSE_B=|MULTI_1=|MULTI_2=|MULTI_3=" tests/e2e_virtual_mic.sh
grep -E "SIMPLE_TEXT|PAUSE_A|PAUSE_B|MULTI_TEXTS|PUNCT_TEXT" tests/make_test_audio.sh | head -10
# Expected: the script's 5 refs match make_test_audio.sh's canonical strings (case+punct may differ
# slightly in the var names but the TEXT must be the same source of truth — don't paraphrase either).

# Confirm the script's voicectl call inventory (the GAP i evidence) — count wrapped vs unwrapped.
grep -nE 'VOICECTL" (status|start|stop|toggle|quit)|timeout .*VOICECTL' tests/e2e_virtual_mic.sh
# Expected: 6 voicectl control-call lines; only the cleanup `timeout 5 ... quit` is wrapped (5 unwrapped).
```

## Final Validation Checklist

### Technical Validation

- [ ] `gap_e2e.md` exists at `plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md`; title + verdict present.
- [ ] The 2 gaps' root facts re-confirmed against LIVE source via Level 2 greps (ctl.py:112 no-timeout;
      daemon.py:1065 drain guard; test_idle_and_gpu.sh VOICECTL_TIMEOUT=30).
- [ ] No command run the script, no `pactl` mutation, no daemon arm (audit is STATIC).

### Feature Validation

- [ ] All success criteria from "What" section met.
- [ ] 9-check matrix (a–i) complete; each row has verdict + script line + LIVE-source evidence.
- [ ] GAP (g) drain recorded with PRD clause + why-missed + test-shape-that-would-cover + unit-coverage note.
- [ ] GAP (i) voicectl-timeout recorded with the 5/6 unwrapped-call table + ctl.py:112 root + sibling
      precedent + recommended fix.
- [ ] PRD §6 T3 step-4 sub-assertion map recorded (4 clauses → coverage; clause 3 = the drain gap).
- [ ] Safe-to-run verdict explicit (conditionally YES; trap robust; caveat = missing voicectl timeouts).
- [ ] Minor observations recorded (ready-wait comment, cleanup order, set-default-source alt, TMUX_TARGET,
      fuzzy matcher) — none are gaps.
- [ ] Scope respected: ONLY e2e_virtual_mic.sh audited; test_idle_and_gpu.sh is comparison-only.

### Code Quality Validation

- [ ] `gap_e2e.md` is self-contained (matrix + 2 gaps + minor obs + step-4 map + verdict + cross-refs).
- [ ] LIVE-confirmed script line numbers recorded (re-verified, not copied blindly from this PRP).
- [ ] No source/test/script edited (REPORT item); no file created except `gap_e2e.md`.

### Documentation & Deployment

- [ ] Report placed at `plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md`.
- [ ] Feeds P1.M5.T3.S2 (voicectl-timeout fact) + P1.M5.T5.S1 (#2 drain-clause caveat, #4 gate).

---

## Anti-Patterns to Avoid

- ❌ Don't RUN `tests/e2e_virtual_mic.sh` — it runs `pactl set-default-source` (rebinds the user's GLOBAL
  default audio source) + loads CUDA models for minutes. AGENTS.md + the work-item forbid it. The audit
  is STATIC (read the script + the LIVE source). If you started it, Ctrl-C immediately (its trap
  restores the source) + run the AGENTS.md Cleanup block.
- ❌ Don't run ANY voicectl command unwrapped — ctl.py:112 has no socket read timeout; a wedged daemon
  hangs it FOREVER. If you need `voicectl status` (e.g. to confirm no daemon is running), wrap it:
  `timeout 15 .venv/bin/voicectl status` (AGENTS.md Rule 1).
- ❌ Don't conflate the drain (§4.2 #2) with the gate (criterion 4). The script tests the GATE
  (`before==after`, nothing typed post-disarm). The DRAIN (in-flight final typed post-stop) is a
  SEPARATE clause the script does NOT test — its play-to-completion design means stop lands with
  nothing in flight. GAP (g) is "drain not exercised", not "drain is broken" (drain logic is unit-tested).
- ❌ Don't "fix" the 2 gaps — this is a REPORT item. Record the recommended fix (the VOICECTL_TIMEOUT=30
  + voicectl() wrapper pattern from test_idle_and_gpu.sh; the stop-during-in-flight drain test shape)
  for a downstream REMEDIATION task. Do NOT edit tests/e2e_virtual_mic.sh or any source.
- ❌ Don't audit test_idle_and_gpu.sh's T4/T6 assertions here — that's P1.M5.T3.S2 (T6) + P1.M5.T4.*
  (T4). Read the sibling ONLY for the voicectl-timeout comparison (lines 151-157, 353-357); cite it,
  don't audit it.
- ❌ Don't invent gaps to seem thorough — 7 of 9 checks genuinely PASS (verified against LIVE source:
  config.py XDG order, launch_daemon.sh exec, typing_backends.py /usr/bin/tmux, daemon.py handlers).
  Recording accurate PASSES is as important as recording the gaps; over-reporting erodes trust.
- ❌ Don't under-report the voicectl-timeout gap either — it's HIGH severity (AGENTS.md Rule 1 + the
  sibling script both say it must be bounded; ctl.py:112 confirms the forever-hang; `voicectl start`
  blocks on the cold model load). Cite ctl.py:112 + the sibling's VOICECTL_TIMEOUT=30 as the twin pillars.
- ❌ Don't copy this PRP's expected line numbers into the report verbatim — re-confirm them against the
  LIVE file (they may have drifted) before citing.
- ❌ Don't edit PRD.md / tasks.json / prd_snapshot.md / .gitignore / source / tests / the script.
- ❌ Don't touch the parallel P1.M5.T2.S1 (T1 offline, in flight) files — different subject; this item's
  report goes to P1M5T3S1/. Shared surface = READ-ONLY source modules; no edit conflict possible.

---

## Confidence Score

**9/10** — one-pass success likelihood. The audit is ALREADY DONE (research this round): the full
364-line script read + every claim cross-checked against LIVE source (ctl.py:112 no-timeout confirmed;
daemon.py:1065 drain guard + start()→_load_host() sync confirmed; typing_backends.py:54/94-105
/usr/bin/tmux confirmed; config.py:262-288 XDG order confirmed; launch_daemon.sh `exec "$PY"` confirmed;
test_idle_and_gpu.sh:151-157/353-357 VOICECTL_TIMEOUT=30 + voicectl() fn confirmed). The 2 gaps are
rock-solid (each has a LIVE-source root fact + a PRD clause citation + an in-repo precedent). The
deliverable is a single self-contained report with a verbatim scaffold + the 9-check matrix pre-filled.
The implementing agent's only genuinely LIVE work is: re-confirm the cited line numbers + write the
report (no run, no edit). Residual -1: line numbers may have drifted slightly since the research (the
Level 2 greps catch that); and a reviewer might quibble about whether GAP (g) drain is "MEDIUM" vs
"LOW" given it's unit-test-covered — but the severity rationale (real-audio drain is the only
end-to-end proof of §4.2 #2, and the acceptance cross-check needs to know it's E2E-missing) is sound.