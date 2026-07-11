# PRP — P1.M1.T2.S1: Verify test_idle_and_gpu.sh (T4) does not break with auto_stop_idle_seconds=30 default

## Goal

**Feature Goal**: **Verify** (not implement) that the existing `tests/test_idle_and_gpu.sh` (PRD §6 **T4** — 120 s armed-idle hallucination/CPU guard) still passes now that idle auto-stop (`asr.auto_stop_idle_seconds`, default `30.0`) is active and will auto-disarm the daemon ~30 s into T4's 120 s silence window. The delta PRD §4 explicitly flags this as *"the one real interaction to verify."* The contract's research note predicts T4 is unaffected; this subtask confirms that prediction against the actual code and records the verdict.

**Deliverable**: A **documented verdict** (text / passed check) confirming T4's interaction with auto-stop is sound. **No file changes** unless the verification contradicts the research — in which case the ONLY permitted non-comment edit is relaxing a single `listening==true` assertion (delta PRD §6.3). Based on the verification below, **all three findings confirm → verdict is "T4 passes, no modification needed" → zero file changes.**

**Success Definition**:
- (a) Re-read `tests/test_idle_and_gpu.sh` and confirm the three contract findings (see What) against the actual code.
- (b) Reach and record the verdict: **"T4 passes, no modification needed"** (the expected outcome — all three findings hold).
- (c) Zero modifications to `test_idle_and_gpu.sh`, `daemon.py`, `config.py`, `ctl.py`, or `config.toml`.
- (d) The verdict is captured in this PRP's Verdict section (authoritative) and reflected in the task acceptance evidence.

> **VERDICT (pre-verified by this PRP's research; implementer re-confirms via the gates): T4 PASSES, NO MODIFICATION NEEDED.** All three findings hold against the current code (evidence in Context + Validation Loop). This subtask therefore produces a passed-check, not a code change.

## User Persona

Not applicable. This is an internal test-suite consistency verification with no user-facing surface (the bugfix contract §5 "DOCS: none"). The user benefit (the auto-stop forgotten-hot-mic guard shipping safely without breaking the idle-hallucination acceptance test) is realized by the prior D1 commit; this subtask only certifies the test still proves the property.

## Why

- **Delta PRD §4 is the mandate.** The delta PRD states: *"PRD T4 holds 120 s of armed silence … With D1 now active (default `auto_stop_idle_seconds=30.0`), the daemon will auto-disarm ~30 s into that window. This is correct new behavior, but it raises two questions the implementing agent must confirm by re-reading the current `test_idle_and_gpu.sh`."* This subtask IS that confirmation. It is *"the single most likely place the prior D1 commit left a latent test inconsistency, so it must be checked, not assumed."*
- **Certify the acceptance test still tests what it claims.** T4 is PRD §6's hallucination guard (criterion 5) — it MUST keep asserting "no finals typed across 120 s of silence" + "no crash" + "CPU < 25%." If auto-stop silently disarmed mid-window and a `listening==true` assertion existed at the end, T4 would go red for a *correct* behavior — a false failure that would block the delta or, worse, tempt someone to disable auto-stop. Verifying the test has no such assertion prevents both.
- **Cheap, deterministic, no GPU/mic.** The verdict follows from static analysis of the test + the daemon's dispatch/idle-watchdog logic (all verified below with line numbers). The heavy empirical run (3–4 min, quiet room, GPU) is OPTIONAL corroboration, not required to reach the verdict.
- **Scope discipline.** This subtask verifies T4 ONLY. It does NOT run the full pytest regression (that is the sibling P1.M1.T2.S2), does NOT sync README (P1.M1.T3.S1), and does NOT re-implement auto-stop (shipped in the prior `367b774` commit).

## What

Re-read `tests/test_idle_and_gpu.sh` and confirm the three contract findings. Each maps to precise code evidence (gathered in Context):

- **Finding (a)** — the test's temp config override does **not** set `auto_stop_idle_seconds`, so `[asr]` inherits the dataclass default `30.0` (config.py:58). → The auto-stop watchdog IS active during T4's window (this is the premise, not a problem).
- **Finding (b)** — the test does **not** assert `listening==true` at the end of the 120 s window. The only `listening` assertion is the **pre-window** `listening: off` un-armed-boot check (criterion 6); the post-window block asserts typed-text-unchanged / `last_final`-unchanged / `kill -0` / CPU < 25%.
- **Finding (c)** — the `voicectl stop` issued **after** the window (T6 section) does not fail when the daemon is already auto-disarmed: the control-socket `stop` dispatch (daemon.py:946-948) **always** replies `{"ok": true, ...}` (no "already stopped" guard), `_disarm()` is idempotent, and `ctl.py` maps that to **exit 0** — so the test's `|| die "voicectl stop failed"` never fires.

**Decision logic** (verbatim from the contract):
- If **all three** confirm → document verdict **"T4 passes, no modification needed"** in the acceptance evidence. **No code change.** ← (this is the verified outcome)
- If the test **does** assert `listening==true` (contradicting research) → relax that **single** assertion and add a comment on the modified line explaining the auto-stop interaction. This is the **only** permitted non-comment edit (delta PRD §6.3).

### Success Criteria

- [ ] Finding (a) confirmed: `grep -n 'auto_stop_idle_seconds' tests/test_idle_and_gpu.sh` returns **no match inside the temp-config heredoc** (the override sets only `[output]`+`[feedback]`); `config.py:58` default is `30.0`.
- [ ] Finding (b) confirmed: no `listening: on` / `listening==true` assertion exists in the post-`sleep "$IDLE_SECS"` block of `test_idle_and_gpu.sh`.
- [ ] Finding (c) confirmed: the daemon's `stop` dispatch returns `{"ok": True, ...}` unconditionally (daemon.py:946-948); `_disarm()` is idempotent; `ctl.py` returns exit 0 for an ok stop reply.
- [ ] Verdict recorded: **"T4 passes, no modification needed."**
- [ ] Zero file modifications (no edit to `test_idle_and_gpu.sh`, `daemon.py`, `config.py`, `ctl.py`, `config.toml`, `README.md`, or any test).
- [ ] No out-of-scope work (no full pytest run — that's P1.M1.T2.S2; no README sync — that's P1.M1.T3.S1).

## All Needed Context

### Context Completeness Check

_Pass._ This is a verification task; the verdict is determined by reading three specific code locations. All three findings are pre-verified below against the actual repo with exact line numbers (current as of this PRP). A developer new to this codebase can re-confirm each finding from the cited evidence alone and reproduce the verdict. No GPU, mic, daemon, or network is required to reach the verdict.

### Documentation & References

```yaml
# MUST READ — the mandate + the decision logic for this subtask
- docfile: plan/002_61d807f18dbe/delta_prd.md
  why: §4 "One interaction to verify" is the SOURCE of this task — it names the auto-stop/T4
       interaction and prescribes the exact decision ("If T4 already accounts for this, no change
       is needed — just note it in the acceptance evidence"). §6.3 caps any edit at a single
       assertion relaxation. §3.1 frames test_idle_and_gpu.sh as "verification (reference, do not
       re-implement)".
  critical: "§6.3: 'If §4 requires a T4 assertion relaxation, that change is the only permitted
            non-comment edit and is called out explicitly.' Since NO relaxation is needed (findings
            a/b/c all hold), there are ZERO file changes."

# MUST READ — the test under verification
- file: tests/test_idle_and_gpu.sh
  why: The artifact being verified. 415 lines. The temp-config heredoc (~lines 118-125) sets ONLY
        [output]+[feedback]. The idle window (~lines 178-195): cpu0/wall0 → voicectl start → capture
        before → sleep $IDLE_SECS → cpu1/wall1 → capture after → 3 assertions (typed/last_final
        unchanged, kill -0, CPU<25%). The post-window voicectl stop (~line 213, T6 section).
  pattern: "G-CONFIG comment explicitly states '[asr]/[filter]/[log] inherit dataclass defaults
            (== repo config.toml) -> same production ASR'. So auto_stop_idle_seconds=30.0 IS active."
  gotcha: "There is NO 'listening: on' assertion after the 120s window. The ONLY listening assertion
           is the PRE-window 'grep -q ^listening: off' (criterion 6, un-armed boot)."

# Finding (a) evidence — the inherited default
- file: voice_typing/config.py
  why: Line 58: `auto_stop_idle_seconds: float = 30.0` — the AsrConfig dataclass default. The test's
        temp config has no [asr] section, so this default applies → 30.0.
  critical: "30.0 is the active value during T4. (Repo config.toml:36 is also 30.0, but the test
            doesn't read repo [asr] — it inherits the dataclass default, which is the same 30.0.)"

# Finding (a) corroboration — the auto-disarm path is real and uses the normal stop path
- file: voice_typing/daemon.py
  why: _maybe_auto_stop() (~581-600) disarms via _disarm() (the SAME path as a manual stop) when
        now - _last_speech_monotonic > threshold; _idle_watchdog() (~602-612) ticks ~1 s. Started by
        run() at line 466. _arm() sets _last_speech_monotonic (559); _disarm() clears it (567).
  critical: "Auto-disarm is NOT a crash, types nothing, sets last_final to nothing, and uses ~0 CPU.
            That is exactly why T4's three assertions still hold after the ~30s disarm."

# Finding (c) evidence — the load-bearing one: stop-when-already-stopped returns ok
- file: voice_typing/daemon.py
  why: ControlServer._dispatch (lines 946-948): `if cmd == "stop": self._daemon.stop(); return
        {"ok": True, **self._daemon.status_snapshot()}`. There is NO 'already stopped' guard — the
        reply is ALWAYS ok:True. self._daemon.stop() -> _disarm() is IDEMPOTENT (clears an already-
        cleared Event, re-calls set_microphone(False)/abort()/set_listening(False) — none raise).
  critical: "The reply is {'ok': true, 'listening': false} when already auto-disarmed. ctl.py maps
            that to exit 0. The test's '|| die' does NOT fire."

# Finding (c) corroboration — voicectl's exit-code mapping
- file: voice_typing/ctl.py
  why: format_result (lines 40-86): ok:True → not the error branch (54-55); not shutting_down (56-57);
        for stop/start/toggle → line 86 `return f\"listening: {...}\", 0` → exit code 0. The header
        docstring (lines 7-9) codifies: 0 = success (daemon replied ok:true), 1 = logical failure.
  critical: "voicectl stop returns exit 0 whenever the daemon replies ok:true — which it always does
            for stop. So 'voicectl stop ... || die' is safe regardless of armed/disarmed state."

# Finding (c) test precedent — idempotent commands are already an established, tested pattern
- file: tests/test_control_socket.py
  why: Line 123-125 `test_dispatch_start_stop_set_listening` asserts `_disp({"cmd":"stop"})["listening"]
        is False`; line 213 `test_start_is_idempotent`. The dispatch's uniform ok:true payload is
        already locked in by these tests.
  critical: "stop-returns-ok-when-not-listening is already covered by the fast pytest suite — this is
            not a novel claim, it's the documented dispatch contract."

# The sibling PRP (parallel) — confirms no overlap
- docfile: plan/002_61d807f18dbe/P1M1T1S1/PRP.md
  why: P1.M1.T1.S1 removes 'partial/' from the hypr_notify COMMENT in config.toml:49. It touches
        ONLY config.toml (a comment) and does not affect test_idle_and_gpu.sh, daemon auto-stop,
        ctl exit codes, or the [asr] section. T2.S1 and T1.S1 are fully independent.
  critical: "No conflict. T2.S1 verifies a test + daemon logic; T1.S1 edits a config comment. The
            test's temp config sets hypr_notify=false anyway, so the comment fix is irrelevant to T4."
```

### Current Codebase tree (relevant slice — T1.S1 comment fix may be landing in parallel)

```bash
/home/dustin/projects/voice-typing/
├── tests/
│   └── test_idle_and_gpu.sh     # ← VERIFY (re-read; NO modification). 415 lines.
├── voice_typing/
│   ├── config.py                # line 58: auto_stop_idle_seconds: float = 30.0 (the inherited default)
│   ├── daemon.py                # _dispatch stop @946-948 (always ok:True); _maybe_auto_stop/_idle_watchdog
│   └── ctl.py                   # format_result @40-86 (ok:True stop -> exit 0)
└── config.toml                  # line 36: auto_stop_idle_seconds = 30.0 (NOTE: T1.S1 edits line 49's
                                 #   hypr_notify COMMENT only — unrelated to T4; no conflict.)
# NO files are modified by this subtask. The deliverable is a verdict (passed check).
```

### Desired Codebase tree with files to be added/changed

```bash
# (no changes) — verdict-only subtask.
# If (and only if) finding (b) had been contradicted, the single permitted edit would be to
# tests/test_idle_and_gpu.sh (relax one listening assertion + add a comment). Findings confirm
# that is NOT needed → ZERO file changes.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — THIS IS A VERIFICATION, NOT AN IMPLEMENTATION. The default outcome is ZERO file
# changes. Do NOT "improve" the test, add assertions, or tweak the idle window. The contract +
# delta PRD §6.3 permit exactly ONE edit (relaxing a listening==true assertion) and ONLY if finding
# (b) is contradicted. It is NOT contradicted → do not edit anything.

# CRITICAL #2 — AUTO-STOP IS ACTIVE DURING T4 (that's the premise). The test's temp config has no
# [asr] section → inherits config.py:58 default auto_stop_idle_seconds=30.0. So the daemon WILL
# auto-disarm ~30s into the 120s window. This is correct; T4's assertions are unaffected (auto-
# disarm types nothing, doesn't set last_final, doesn't crash, ~0 CPU). Do NOT try to disable
# auto-stop in the test — that would be an out-of-scope product change and is explicitly optional
# per delta PRD §4.2 ("a test-only choice, not a product requirement").

# CRITICAL #3 — STOP IS IDEMPOTENT AT BOTH LAYERS. _disarm() is idempotent (clears an already-cleared
# Event); ControlServer._dispatch returns ok:True for stop unconditionally (no "already stopped"
# guard); ctl.py maps ok:True stop -> exit 0. So 'voicectl stop ... || die' NEVER fires on an already-
# auto-disarmed daemon. This is the load-bearing fact for finding (c). (Already covered by
# test_control_socket.py:123-125 + test_start_is_idempotent.)

# GOTCHA #4 — the heavy empirical run is OPTIONAL. Reaching the verdict requires ONLY static analysis
# (read the test + the cited daemon/ctl lines). Running ./tests/test_idle_and_gpu.sh is ~3-4 min,
# needs a QUIET room (ambient speech would create a real final and spuriously fail "no finals"),
# a free GPU, and no daemon already running (the preflight refuses otherwise). It is acceptable
# corroboration if conditions permit, but it is NOT required to pass this subtask and should NOT be
# forced in a noisy/headless environment where it would produce a false negative.

# GOTCHA #5 — DO NOT confuse "auto-stop disarms the daemon" with "the test fails." T4's CPU
# assertion (T4-c) measures avg CPU over the FULL 120s window. Auto-disarm at ~30s means ~90s of
# the window the daemon is NOT running VAD/realtime inference → CPU is LOWER, not higher. So T4-c
# (<25% of one core) becomes EASIER to satisfy with auto-stop, not harder.

# GOTCHA #6 — the post-run STATUS_RUN is ECHOED, not asserted. Around the systemd-unit grep section,
# 'STATUS_RUN="$("$VOICECTL" status)"' is captured and printed ('echo "voicectl status (post-run):";
# echo "$STATUS_RUN"') but it is NOT grep'd/asserted for any listening value. So a 'listening: off'
# there (from auto-stop) is fine.

# GOTCHA #7 — FULL PATHS in any bash command (this machine aliases python3→uv run, pip→alias,
# tmux→zsh plugin). The greps/reads in the Validation Loop use plain grep/read (no venv needed).
# If you DO run the heavy test, invoke /usr/bin/tmux and .venv/bin/voicectl explicitly (the script
# itself already does).

# GOTCHA #8 — DO NOT touch tests/test_idle_and_gpu.sh's 120s window (IDLE_SECS=120). PRD §6 T4
# fixes it at exactly 120s. The delta does not relax that. Auto-stop firing at ~30s is fine; the
# window length is unchanged.
```

## Implementation Blueprint

### Data models and structure

None. This subtask adds no code, no types, no config. The only "structure" is the **verdict** (a one-line determination: PASS / relax-one-assertion), reached by confirming the three findings.

### Verification Tasks (ordered by dependencies)

```yaml
Task 1: CONFIRM Finding (a) — auto_stop_idle_seconds is NOT in the test's temp config → inherits 30.0
  - RUN:
      cd /home/dustin/projects/voice-typing
      echo "--- the test's temp config heredoc sets ONLY [output]+[feedback] (no [asr], no auto_stop) ---"
      sed -n "/cat > \"\$WORK\/config\/voice-typing\/config.toml\"/,/^EOF\$/p" tests/test_idle_and_gpu.sh
      echo "--- confirm NO auto_stop_idle_seconds anywhere in the test ---"
      if grep -q 'auto_stop_idle_seconds' tests/test_idle_and_gpu.sh; then
          echo "NOTE: auto_stop_idle_seconds IS referenced in the test (inspect context)"; grep -n 'auto_stop_idle_seconds' tests/test_idle_and_gpu.sh
      else
          echo "PASS (a-1): test never sets auto_stop_idle_seconds → [asr] inherits dataclass default"
      fi
      echo "--- the inherited default ---"
      grep -n 'auto_stop_idle_seconds: float' voice_typing/config.py
  - EXPECTED: the heredoc contains only [output] (backend/tmux_target) + [feedback] (state_file/
    hypr_notify=false); grep finds ZERO auto_stop_idle_seconds in the test; config.py:58 shows
    `auto_stop_idle_seconds: float = 30.0`. → 30.0 is active during T4. FINDING (a) CONFIRMED.
  - If (unexpectedly) the test DID set auto_stop_idle_seconds=0 in its override, that is ALSO fine
    (delta PRD §4.2 explicitly permits it as "a test-only choice") — record that the test deliberately
    disables auto-stop and T4 is unaffected either way. (Current code: it does NOT.)

Task 2: CONFIRM Finding (b) — no listening==true assertion at the end of the 120s window
  - RUN:
      cd /home/dustin/projects/voice-typing
      echo "--- the ONLY listening assertion in the test (should be the PRE-window un-armed boot) ---"
      grep -nE "listening: (on|off)|listening.*==.*[Tt]rue|is_listening" tests/test_idle_and_gpu.sh
      echo "--- show the post-window assertion block (after 'sleep \"\$IDLE_SECS\"') ---"
      awk '/sleep "\$IDLE_SECS"/{flag=1} flag{print NR": "$0} /^# --- T6 GPU/{exit}' tests/test_idle_and_gpu.sh | head -40
  - EXPECTED: the only `listening:` line is the PRE-window `grep -q '^listening: off'` (criterion 6,
    un-armed boot). The post-`sleep "$IDLE_SECS"` block asserts: typed_before==typed_after AND
    last_final_before==last_final_after; kill -0 $DAEMON_PID; awk CPU<25%. NONE assert listening==true.
    FINDING (b) CONFIRMED.
  - This is the branch point for the contract's "ONLY permitted non-comment edit." If a
    listening==true assertion WERE found here, relax it + add a comment (delta PRD §6.3). It is NOT
    found → no edit.

Task 3: CONFIRM Finding (c) — voicectl stop returns ok/exit-0 even when already auto-disarmed
  - RUN:
      cd /home/dustin/projects/voice-typing
      echo "--- the post-window voicectl stop line (T6 section) ---"
      grep -n '"\$VOICECTL" stop' tests/test_idle_and_gpu.sh
      echo "--- daemon dispatch: stop ALWAYS replies ok:True (no 'already stopped' guard) ---"
      sed -n '940,960p' voice_typing/daemon.py
      echo "--- _disarm() is idempotent (clears an already-cleared Event; never raises) ---"
      sed -n '/def _disarm/,/def [a-z_]/p' voice_typing/daemon.py | head -12
      echo "--- ctl.py: ok:True stop -> exit 0 ---"
      sed -n '54,86p' voice_typing/ctl.py
  - EXPECTED:
      * test line: `"$VOICECTL" stop >/dev/null || die "voicectl stop failed"`
      * daemon.py:946-948: `if cmd == "stop": self._daemon.stop(); return {"ok": True, **self._daemon.status_snapshot()}`
      * _disarm(): self._listening.clear() (idempotent), set_microphone(False), abort(), set_listening(False) — none raise.
      * ctl.py:86: `return f"listening: {...}", 0` → exit 0.
    → voicectl stop returns exit 0 on an already-disarmed daemon; the `|| die` never fires.
    FINDING (c) CONFIRMED. (Corroborated by tests/test_control_socket.py:123-125 + test_start_is_idempotent.)

Task 4: REACH + RECORD the verdict
  - IF Task 1 + Task 2 + Task 3 all CONFIRM (the expected + verified outcome):
      Verdict = "T4 passes, no modification needed." Record it (this PRP's Verdict section below is
      authoritative; reflect it in the task acceptance evidence). NO file changes.
  - ELSE (Task 2 contradicted — a listening==true assertion exists post-window):
      Relax that SINGLE assertion (e.g. remove/comment the `grep -q '^listening: on'`-style check, or
      change it to tolerate off) and add a one-line comment: "# auto_stop_idle_seconds=30 (inherited)
      disarms ~30s into this window; do not assert listening==true here (delta PRD §4/§6.3)." This is
      the ONLY permitted non-comment edit. Re-run Task 2 to confirm the relaxation. (Not needed per
      current code.)
  - DO NOT: run the full pytest suite (P1.M1.T2.S2's job), edit daemon.py/config.py/ctl.py/config.toml,
    change IDLE_SECS, disable auto-stop, or sync README (P1.M1.T3.S1's job).

Task 5 (OPTIONAL, empirical corroboration only — NOT required to pass this subtask):
  - IF a quiet room + free GPU + no running voice-typing daemon:
        cd /home/dustin/projects/voice-typing
        systemctl --user stop voice-typing 2>/dev/null || true
        ./tests/test_idle_and_gpu.sh
  - EXPECTED: script prints "[PASS] criterion 5 (no hallucination) ... no finals typed, last_final
    unchanged across 120s", "[PASS] criterion 5 (no crash)", "[PASS] criterion 5 (CPU)", then
    "[PASS] criterion 6/T6 (GPU residency)", and "=== IDLE+GPU PASS (criteria 5, 6, 8) ==="; exit 0.
    (Auto-stop fires a journal INFO line ~30s in; the script does not assert against it → green.)
  - If the environment is noisy/headless, SKIP this — the verdict already follows from Tasks 1-3.
    A false negative here (ambient speech → a real final) would NOT invalidate the verdict.
```

### Implementation Patterns & Key Details

```bash
# This subtask has NO implementation patterns — it is a read-only verification. The three load-bearing
# facts (each verified against the actual code) are:
#
# FACT 1 (finding a): the test's temp config heredoc sets ONLY [output]+[feedback]; [asr] inherits
#   config.py:58 `auto_stop_idle_seconds: float = 30.0`. Auto-stop IS active during T4.
#
# FACT 2 (finding b): the post-sleep(120s) block asserts typed-text-unchanged + last_final-unchanged +
#   kill -0 + CPU<25%. It does NOT assert listening==true. The only listening check is the PRE-window
#   `grep -q '^listening: off'` (criterion 6 un-armed boot).
#
# FACT 3 (finding c): ControlServer._dispatch 'stop' (daemon.py:946-948) ALWAYS returns {"ok":True,...};
#   _disarm() is idempotent; ctl.py:86 returns exit 0 for an ok stop reply. So the test's
#   `"$VOICECTL" stop >/dev/null || die "voicectl stop failed"` (T6 section, post-window) never fires
#   on an already-auto-disarmed daemon.
#
# WHY auto-stop doesn't disturb T4's three assertions:
#   (a) no finals typed     — auto-disarm fires the ■ stopped popup + a journal line; it does NOT call
#                             on_final/textproc/type_text → capture-pane + last_final unchanged. ✓
#   (b) no crash            — _disarm() never raises; the daemon stays alive (kill -0 passes). ✓
#   (c) CPU < 25% of a core — ~90s of the 120s window the daemon is NOT running VAD/realtime inference
#                             (it's disarmed) → avg CPU is LOWER with auto-stop, not higher. ✓
```

### Integration Points

```yaml
DELTA ACCEPTANCE (delta PRD §6.2 — "the existing test suite still passes"):
  - This subtask certifies the T4 half of §6.2 ("./tests/test_idle_and_gpu.sh still passes — confirming
    §4's T4 interaction is sound"). The pytest half of §6.2 is the sibling P1.M1.T2.S2.
  - The verdict is recorded in this PRP's Verdict section + the task acceptance evidence. No repo file
    is modified (delta PRD §6.3: only a single assertion-relaxation would be permitted, and none is needed).

DOWNSTREAM — P1.M1.T2.S2 (full pytest fast suite regression):
  - S2 runs `.venv/bin/python -m pytest tests/ -v` (197 tests) to confirm D1/D2/D3 stay green. S1's
    verdict (T4 sound) is SEPARATE: S1 is about the heavy bash T4; S2 is about the fast pytest suite.
    S1 produces no file change that S2 needs to account for (zero modifications → nothing to regress).

DOWNSTREAM — P1.M1.T3.S1 (README changeset-level sync, Mode B):
  - The delta PRD §5 judges Mode B "Does not apply" for this comment-only delta (README already
    documents both knobs). S1's verdict (T4 sound) does NOT change documented user behavior, so it
    imposes no README edit. If S1 had needed an assertion relaxation, T3.S1 would note the auto-stop
    interaction in README — but it doesn't.

NO INTERFACE / BEHAVIOR CHANGES:
  - test_idle_and_gpu.sh: UNCHANGED. daemon.py / config.py / ctl.py / config.toml: UNCHANGED.
  - auto_stop_idle_seconds default (30.0) is already shipped; this subtask only certifies a test
    tolerates it.
```

## Validation Loop

> The verdict follows from STATIC analysis (Tasks 1-3). No GPU/mic/daemon is required. The heavy
> empirical run (Level 4) is OPTIONAL corroboration. Full paths where invoked; the greps are plain.

### Level 1: Finding (a) — auto_stop is inherited (active), not overridden in the test

```bash
cd /home/dustin/projects/voice-typing
echo "--- temp-config heredoc (should show ONLY [output]+[feedback]) ---"
sed -n "/cat > \"\$WORK\/config\/voice-typing\/config.toml\"/,/^EOF\$/p" tests/test_idle_and_gpu.sh
echo "--- auto_stop_idle_seconds occurrences in the test (expect: NONE) ---"
n=$(grep -c 'auto_stop_idle_seconds' tests/test_idle_and_gpu.sh); echo "count=$n"
[ "$n" -eq 0 ] && echo "L1 PASS (a): test does not set auto_stop_idle_seconds" || echo "L1 NOTE: present — inspect"
echo "--- inherited default ---"
grep -n 'auto_stop_idle_seconds: float = 30.0' voice_typing/config.py && echo "L1 PASS (a): default=30.0 → active during T4"
# Expected: heredoc has only [output]+[feedback]; 0 occurrences of auto_stop_idle_seconds in the test;
# config.py:58 = 30.0. → 30.0 is the active value. Finding (a) CONFIRMED.
```

### Level 2: Finding (b) — no listening==true assertion after the 120 s window

```bash
cd /home/dustin/projects/voice-typing
echo "--- every 'listening:' / listening-assertion line in the test ---"
grep -nE "listening: (on|off)|is_listening|listening.*[Tt]rue" tests/test_idle_and_gpu.sh
echo "--- the post-window assertion block (after sleep, before T6) ---"
awk '/sleep "\$IDLE_SECS"/{f=1} f{print NR": "$0} /T6 GPU|GPU residency/{if(f)exit}' tests/test_idle_and_gpu.sh | head -45
# Expected: the ONLY listening assertion is the PRE-window 'grep -q "^listening: off"' (criterion 6).
# The post-sleep block asserts: typed/last_final UNCHANGED, kill -0, CPU<25%. No listening==true.
# Finding (b) CONFIRMED → the "ONLY permitted edit" branch is NOT triggered.
```

### Level 3: Finding (c) — voicectl stop is safe on an already-auto-disarmed daemon

```bash
cd /home/dustin/projects/voice-typing
echo "--- post-window voicectl stop line ---"
grep -n '"\$VOICECTL" stop' tests/test_idle_and_gpu.sh
echo "--- dispatch: stop ALWAYS ok:True ---"
sed -n '946,948p' voice_typing/daemon.py
echo "--- _disarm idempotency (clears an already-cleared Event) ---"
sed -n '/def _disarm(self)/,/set_listening(False)/p' voice_typing/daemon.py
echo "--- ctl.py stop -> exit 0 ---"
sed -n '85,86p' voice_typing/ctl.py
echo "--- corroborating fast-suite coverage (already green) ---"
grep -nE 'test_dispatch_start_stop_set_listening|test_start_is_idempotent' tests/test_control_socket.py
# Expected: stop dispatch returns {"ok": True, **status_snapshot()} unconditionally; _disarm clears the
# Event (idempotent) and never raises; ctl.py line 86 returns exit 0; test_control_socket.py already
# locks in "_disp({'cmd':'stop'})['listening'] is False". → '|| die' never fires. Finding (c) CONFIRMED.
```

### Level 4: Verdict recorded (the deliverable)

```bash
cd /home/dustin/projects/voice-typing
echo "=== T4 / AUTO-STOP INTERACTION VERDICT ==="
echo "Finding (a): auto_stop_idle_seconds NOT set in test temp config → inherits 30.0 (ACTIVE). CONFIRMED."
echo "Finding (b): NO listening==true assertion after the 120s window. CONFIRMED."
echo "Finding (c): voicectl stop returns ok/exit-0 even when already auto-disarmed. CONFIRMED."
echo "VERDICT: T4 passes, no modification needed. ZERO file changes."
echo "=== END VERDICT ==="
# Expected: all three CONFIRMED; VERDICT = "T4 passes, no modification needed"; no file touched.
git status --short   # must show NO modifications attributable to this subtask (only possibly the
                     # parallel T1.S1 config.toml comment edit, which is a different subtask/file).
```

### Level 5: OPTIONAL empirical corroboration (skip in noisy/headless envs)

```bash
cd /home/dustin/projects/voice-typing
# ONLY if: quiet room + free GPU + no running voice-typing daemon. ~3-4 min. NOT required for the verdict.
systemctl --user stop voice-typing 2>/dev/null || true
./tests/test_idle_and_gpu.sh; echo "exit=$?"
# Expected (pass): "[PASS] criterion 5 (no hallucination) ... no finals typed, last_final unchanged
# across 120s", "[PASS] criterion 5 (no crash)", "[PASS] criterion 5 (CPU)", "[PASS] criterion 6/T6",
# "=== IDLE+GPU PASS (criteria 5, 6, 8) ===", exit 0. The journal shows an auto-stop INFO line ~30s in
# (harmless — the test never asserts against it). A failure here caused by AMBIENT SPEECH is a false
# negative (test precondition: quiet room) and does NOT invalidate the static verdict.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1 (a): test temp config sets only `[output]`+`[feedback]`; 0 `auto_stop_idle_seconds` in the test; `config.py:58` = `30.0`.
- [ ] L2 (b): only `listening` assertion is the PRE-window `listening: off` boot check; no `listening==true` post-window.
- [ ] L3 (c): `stop` dispatch (daemon.py:946-948) always `ok:True`; `_disarm` idempotent; ctl.py:86 exit 0.
- [ ] L4: verdict recorded — "T4 passes, no modification needed"; zero file changes.
- [ ] L5 (optional): empirical `./tests/test_idle_and_gpu.sh` PASS (only if environment permits).

### Feature Validation
- [ ] All three contract findings confirmed against the actual code (not assumed).
- [ ] Verdict matches the verified outcome: PASS, no modification.
- [ ] The "ONLY permitted non-comment edit" branch (relax a `listening==true` assertion) was NOT triggered.
- [ ] T4's three properties (no finals / no crash / CPU<25%) each independently withstand auto-disarm (auto-disarm types nothing, never raises, lowers CPU).

### Code Quality / Scope Validation
- [ ] ZERO file modifications (`test_idle_and_gpu.sh`, `daemon.py`, `config.py`, `ctl.py`, `config.toml`, `README.md`, any test).
- [ ] No out-of-scope work: no full pytest run (P1.M1.T2.S2), no README sync (P1.M1.T3.S1), no auto-stop re-implementation.
- [ ] No conflict with the parallel T1.S1 (config.toml:49 comment fix — different file, unrelated to T4).
- [ ] PRD.md, tasks.json, prd_snapshot.md, delta_prd.md, .gitignore NOT modified (read-only).

### Documentation & Deployment
- [ ] Verdict documented in this PRP's Verdict section (authoritative) + reflected in task acceptance evidence.
- [ ] No user-facing/config/API surface change (contract §5 "DOCS: none").
- [ ] No README edit warranted (delta PRD §5 Mode B "Does not apply"; S1's verdict changes no documented behavior).

---

## Verdict (the deliverable)

**T4 PASSES — NO MODIFICATION NEEDED.** All three contract findings are confirmed against the current code:

1. **(a)** `tests/test_idle_and_gpu.sh`'s temp config heredoc sets **only** `[output]`+`[feedback]`; the `[asr]` section is absent → `auto_stop_idle_seconds` inherits the `AsrConfig` dataclass default `30.0` (`voice_typing/config.py:58`). Auto-stop **is active** during T4's 120 s window (the premise, not a problem).
2. **(b)** The test asserts **no** `listening==true` after the 120 s window. The only `listening` assertion is the **pre-window** `grep -q '^listening: off'` un-armed-boot check (criterion 6). The post-`sleep "$IDLE_SECS"` block asserts typed-text-unchanged + `last_final`-unchanged + `kill -0` + CPU < 25%.
3. **(c)** The post-window `"$VOICECTL" stop >/dev/null || die "voicectl stop failed"` is safe on an already-auto-disarmed daemon: `ControlServer._dispatch` (`daemon.py:946-948`) returns `{"ok": True, ...}` for `stop` unconditionally (no "already stopped" guard), `_disarm()` is idempotent, and `ctl.py:86` maps an `ok:True` stop reply to **exit 0** — so `|| die` never fires.

**Why each T4 assertion holds after the ~30 s auto-disarm:** auto-disarm fires the `■ stopped` popup + a journal `INFO` line and flips `listening=false`; it does **not** call `on_final`/`textproc`/`type_text` (→ no finals typed, `last_final` unchanged ✓), never raises (→ daemon alive ✓), and stops VAD/realtime inference (→ CPU is **lower** over the 120 s window, not higher ✓).

**Outcome:** ZERO file changes. No assertion relaxation was needed (the "only permitted non-comment edit" branch was not triggered). The delta's T4 interaction (delta PRD §4) is sound.

---

## Anti-Patterns to Avoid

- ❌ Don't edit `tests/test_idle_and_gpu.sh`, `daemon.py`, `config.py`, `ctl.py`, or `config.toml` — this is a verification, not an implementation. The verified outcome is ZERO file changes. The ONLY permitted edit (a single `listening==true` relaxation) is NOT triggered.
- ❌ Don't disable auto-stop in the test (`auto_stop_idle_seconds=0`) — delta PRD §4.2 calls that an optional "test-only choice, not a product requirement"; the default config already works. Changing it is unnecessary scope.
- ❌ Don't shorten the 120 s window (`IDLE_SECS=120`) — PRD §6 T4 fixes it; auto-stop firing at ~30 s is fine and does not relax the window.
- ❌ Don't run the heavy `./tests/test_idle_and_gpu.sh` in a noisy/headless environment and treat a failure as invalidating the verdict — ambient speech creates real finals (false negative). The verdict follows from the static analysis (Tasks 1-3); the empirical run is optional corroboration.
- ❌ Don't conflate "auto-stop disarms the daemon" with "T4 fails" — auto-disarm makes the CPU assertion EASIER (less inference work), and the other two assertions are unaffected (Gotcha #5).
- ❌ Don't run the full pytest suite here — that is the sibling P1.M1.T2.S2 (this subtask is the bash-T4 verification only).
- ❌ Don't sync README here — that is P1.M1.T3.S1, and delta PRD §5 judges Mode B "Does not apply" for this delta anyway.
- ❌ Don't re-implement auto-stop, `notify_on_final`, or `record_final`→`partial` (all shipped in prior commits `367b774`/`3913106`; this is spec-sync verification only).
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `delta_prd.md`, or `.gitignore` (read-only / owned by others).

---

## Confidence Score

**9.5/10** for one-pass verification success. This is a read-only verification whose verdict is already determined by three specific code locations, each **verified verbatim in this PRP**: (a) the temp-config heredoc (only `[output]`+`[feedback]`) + `config.py:58` default `30.0`; (b) the absence of any `listening==true` assertion in the post-`sleep "$IDLE_SECS"` block (the only `listening` check is the pre-window `listening: off`); (c) `ControlServer._dispatch` `stop`→`{"ok":True,...}` (`daemon.py:946-948`), idempotent `_disarm()`, and `ctl.py:86` exit-0 mapping — corroborated by the already-green `tests/test_control_socket.py:123-125` + `test_start_is_idempotent`. The decision logic is binary and both branches are specified (no-edit vs. single-assertion-relaxation). The −0.5 residual is purely environmental: the OPTIONAL heavy empirical run (Level 5) can produce a false negative in a noisy room (ambient speech → a real final), which is why it is explicitly marked optional and why the verdict does NOT depend on it. No GPU, mic, daemon, or network is required to reach the documented verdict; the implementing agent re-confirms via three deterministic greps and records "T4 passes, no modification needed."
