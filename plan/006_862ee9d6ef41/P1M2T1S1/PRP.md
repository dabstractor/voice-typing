# PRP — P1.M2.T1.S1: Audit main loop — recorder is None idle, listening gate, text() blocking semantics

## Goal

**Feature Goal**: Produce an authoritative **gap report** (`plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md`) cross-checking `voice_typing/daemon.py` `VoiceTypingDaemon.run()` (+ `on_final`/`_arm`/`_disarm`) against **PRD §4.2 #1 (recorder loop) + #2 (listening gate)** on the 6 contract points — (a) recorder/host is None → sleep+continue; (b) listening set → `text(on_final)` blocks; (c) listening clear → sleep; (d) `on_final` gated on the listen flag; (e) shutdown_requested breaks the loop; (f) `recorder.shutdown()` on exit if not None — plus the test pass/fail for the `-k 'loop or idle or run or main'` slice. This is a **verification/audit** subtask: the deliverable is the report; code changes happen ONLY if a real defect is found (none is expected — the audit finds the main loop fully PRD §4.2 #1-2-compliant).

**Deliverable**: One report at `plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md` (mirroring the `gap_config.md` / `gap_textproc.md` / `gap_typing.md` / `gap_cuda_check.md` convention) containing: (a) a per-point compliance table (PRD §4.2 expected vs code actual, with daemon.py file:line); (b) the unit-test pass/fail count for the contract's run target; (c) the two architectural nuances (the `self._recorder`→`self._host` subprocess evolution; the (f) teardown delegated to bounded `shutdown()`); (d) a conclusion. **This PRP's author has already performed the audit** (findings embedded below + in the research note) — the implementing agent re-verifies and transcribes, then writes the report.

**Success Definition**:
- (a) `plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md` exists with the sections above.
- (b) The recorded findings match the live re-verification: all 6 contract points (a)-(f) are **compliant** (each with daemon.py file:line).
- (c) `timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'loop or idle or run or main'` → all pass (record the count; verified baseline: **40 passed, 153 deselected**).
- (d) **No source files are modified** (because no defect exists — the main loop is PRD §4.2 #1-2-compliant per audit). If — and only if — the re-verification surfaces a REAL defect, fix it and record the fix; otherwise record "none — compliant per audit."
- (e) The report records the two non-blocking architectural nuances (the `self._host` subprocess evolution; the delegated bounded teardown) so they aren't mistaken for defects.

> **VERIFIED VERDICT (this PRP's research): the daemon main loop is PRD §4.2 #1-2 COMPLIANT — no fix needed.** All 6 contract points pass (daemon.py file:line below); the `-k 'loop or idle or run or main'` slice = **40 passed in 1.30s**.

## User Persona

**Target User**: the maintainer (human or AI agent) who needs to trust that the listen-forever loop faithfully implements the WhisperX-flaw fix (silence only segments, never ends the session; on_final is gated so a stop-drop doesn't type stragglers) before relying on the daemon's core transcription loop. Also the downstream P1.M2.T1.S2 (graceful-drain audit — which depends on this loop's `_drain`/`_text_in_flight` ordering) and P1.M2.T2 (recorder-host lifecycle — the child that `self._host` proxies to).
**Use Case**: A future change to `run()` (e.g. altering the loop branches, the on_final gate, or the teardown hand-off). The gap report + the loop tests are the reference that proves the change keeps (or breaks) PRD §4.2 #1-2 compliance.
**Pain Points Addressed**: Closes the "does the loop actually (a) idle when no models, (b) block on text() when listening, (c) sleep when not, (d) gate on_final, (e) exit on shutdown, (f) tear down the recorder on exit?" question with recorded, re-runnable evidence — not an assumption. (The §1 #1 "never stops listening on silence" + #2 "gate inside on_final too" guarantees are certified by (b)+(c)+(d).)

## Why

- **The WhisperX-flaw fix is the project's headline invariant.** PRD §1 #1: the prior system "stopped listening as soon as it thought the user was done talking." This loop's `(b) text() blocks + (c) silence only sleeps + text()-return-is-segmentation` is THE fix. It must be certified by recorded evidence, not assumed.
- **The on_final gate (d) is the stop-drop race guard.** PRD §4.2 #2 / §8: an utterance may complete right around a stop; without the `if not self._listening.is_set(): return` gate, a straggler final would be typed after disarm. The audit certifies the gate exists + is the first thing on_final does.
- **The architecture evolved; the contract wording didn't.** The contract + PRD pseudocode say `self._recorder`/`recorder.text()`, but the shipped loop uses `self._host` (a RecorderHost subprocess — the daemon process no longer holds the recorder directly). The audit MAPS the contract's `recorder` terminology to the actual `self._host` code so the compliance finding is accurate, and records the evolution as a nuance (not a defect).
- **Scope discipline.** This subtask owns the 6 basic-loop contract points ONLY. The graceful drain (the `_drain`/`_complete_drain` branch) is P1.M2.T1.S2; the dead-host recovery (`_handle_dead_host`) is P1.M2.T2.S1; the bounded teardown (`shutdown()`/`_bounded_shutdown`) is P1.M2.T2.S3. This audit notes those branches EXIST in the loop ordering but defers their detail to those siblings.

## What

An audit (read-only + test-run), producing `gap_daemon_loop.md`. No user-visible behavior change, no config/API surface (DOCS: none — internal lifecycle logic). The audit verifies the 6 properties, runs the targeted tests, records findings.

### Success Criteria

- [ ] `gap_daemon_loop.md` exists at `plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md`.
- [ ] All 6 contract points (a)-(f) recorded COMPLIANT, each with daemon.py file:line.
- [ ] `timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'loop or idle or run or main'` → pass (record count; baseline 40 passed).
- [ ] The two nuances recorded (`self._host` evolution; delegated bounded teardown).
- [ ] No source files modified (unless a REAL defect is found — none expected).

## All Needed Context

### Context Completeness Check

_Pass._ The exact code locations (file:line) for all 6 properties, the test→property mapping, the verified baseline (40 passed), the two architectural nuances, and the sibling-audit boundaries (drain/dead-host/bounded-teardown) are all below + in the research note. An agent new to this repo can re-verify and transcribe the report from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the full audit evidence (6-point table + nuances + test mapping + conclusion)
- docfile: plan/006_862ee9d6ef41/P1M2T1S1/research/gap_daemon_loop_findings.md
  why: "§0 the self._recorder→self._host nuance (the KEY mapping). §1 the 6-point compliance table with daemon.py
        file:line. §2 the (f) delegated-teardown nuance. §3 the additional loop behaviors (dead-host/drain/_text_in_flight
        — note, don't flag). §4 run()'s boot setup. §5 test→property mapping. §6 conclusion."
  section: "§1 (the table) + §0/§2 (the nuances) are load-bearing for the report."

# THE AUDIT SUBJECT (the loop + on_final/_arm/_disarm)
- file: voice_typing/daemon.py
  why: "run() @797 — the while loop @834: dead-host check @840-846; host-None idle @847-848 (point a); drain @856-860
        (S2's scope); listening→text() @856/867 (point b); not-listening→sleep @870-871 (point c); shutdown guard @834
        (point e); post-loop log @873. on_final() @942 — the _listening gate @944-945 (point d). _arm() @987 sets
        _listening; _disarm() @1002 clears it. The teardown (point f) is in shutdown()/_bounded_shutdown() (~504-512),
        NOT inline in run() — invoked by main()'s finally + on_quit."
  critical: "The loop uses self._host (NOT self._recorder). self._host is None ≡ 'no recorder loaded'. A _LegacyRecorderHostAdapter
             (654) wraps injected recorders so self._host is uniform — unit tests exercise the SAME loop. Map the contract's
             'recorder' wording to self._host in every finding."

# THE PRD CONTRACT
- file: PRD.md
  why: "§4.2 #1 the recorder-loop pseudocode (recorder is None → sleep; listening → text(on_final); shutdown → recorder.shutdown())
        + 'CRITICAL: the loop never exits on silence. text() returning is normal segmentation, not session end.' §4.2 #2 the
        listening gate + 'on_final is gated on the listen flag so any final arriving after disarm is dropped.' §1 #1 the
        WhisperX flaw this fixes."

# THE TESTS (the contract's run target)
- file: tests/test_daemon.py
  why: "The -k 'loop or idle or run or main' slice = 40 tests. Key covers: test_run_loop_not_listening_does_not_call_text @1337
        (c); test_run_loop_calls_text_when_listening_then_exits_on_shutdown @1371 (b,e); test_on_final_gate_when_not_listening @641
        (d); test_fresh_daemon_not_listening @633 + test_run_closes_capture_stream_at_boot_while_not_listening @1350 (boot);
        test_request_shutdown_* @988/1001/1129 + test_main_* @2200+ (e,f); test_shutdown_delegates_to_bounded_shutdown @1856 (f);
        test_stop_while_run_loop_idle_does_not_abort_and_does_not_hang @1023 + test_stop_while_text_in_flight_aborts_and_unblocks_loop
        @1081 (the _text_in_flight guard). See research §5 for the full mapping."

# THE AUDIT CONVENTION (mirror this report structure)
- docfile: plan/006_862ee9d6ef41/P1M1T4S1/PRP.md
  why: "The prior cuda_check audit PRP — same shape: Goal=produce gap_<area>.md, embed the verified-compliant findings,
        Success=report exists + findings match re-verification + test baseline count + no source modified (compliant).
        Mirror its report sections (per-point table, live result, test count, nuance, conclusion)."

# PARALLEL CONTEXT — P1.M1.T4.S1 (cuda_check audit; NO overlap)
- docfile: plan/006_862ee9d6ef41/P1M1T4S1/PRP.md
  why: "M1.T4.S1 (Implementing) audits cuda_check.py + daemon _resolve_device_config against §4.4 — produces gap_cuda_check.md.
        It does NOT touch run()/on_final/_arm/_disarm. No overlap (different audit subject; this is §4.2 #1-2, that is §4.4)."
```

### The 6 contract points — verified findings (transcribe into the report)

| # | Contract (PRD §4.2) | Code actual (daemon.py) | Verdict |
|---|---|---|---|
| (a) | recorder is None → sleep+continue | `run()` @847-848 `if self._host is None: time.sleep(0.05); continue` | ✅ COMPLIANT (`self._host is None` ≡ no recorder) |
| (b) | listening set → text(on_final) blocks | `run()` @856 `if self._listening.is_set():` → @867 `self._host.text(self.on_final)` (in `_text_in_flight` set/clear @863-868) | ✅ COMPLIANT |
| (c) | listening clear → sleep (never exit on silence) | `run()` @870-871 `else: time.sleep(0.05)` | ✅ COMPLIANT (WhisperX-flaw fix) |
| (d) | on_final gated on the listen flag | `on_final()` @944-945 `if not self._listening.is_set(): return` (first thing; outside the on_final_lock) | ✅ COMPLIANT (§4.2 #2 / §8) |
| (e) | shutdown_requested breaks loop | `run()` @834 `while not self._shutdown.is_set():` → @873 log "run() loop exiting" | ✅ COMPLIANT |
| (f) | recorder.shutdown() on exit if not None | DELEGATED to `shutdown()`→`_bounded_shutdown()` (~504-512) invoked by `main()` finally + on_quit — NOT inline in run() | ✅ COMPLIANT-WITH-NUANCE (§nuances) |

**Test baseline**: `timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'loop or idle or run or main'` → **40 passed, 153 deselected in 1.30s**.

### Current Codebase tree (relevant slice — read-only audit)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/daemon.py   # READ-ONLY audit subject: run() @797, on_final @942, _arm @987, _disarm @1002, shutdown @~910.
├── tests/test_daemon.py     # READ + RUN: the -k 'loop or idle or run or main' slice (40 tests).
└── plan/006_862ee9d6ef41/
    ├── architecture/gap_daemon_loop.md   # ← CREATE (the report; mirror gap_cuda_check.md structure).
    └── P1M2T1S1/{PRP.md, research/gap_daemon_loop_findings.md}   # this PRP + the evidence (already written).
# No source edits. No new tests (the audit RUNS existing tests, doesn't add them).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE LOOP USES self._host, NOT self._recorder. The contract + PRD pseudocode say "recorder"/"self._recorder",
#   but the shipped loop uses self._host (a RecorderHost subprocess; daemon.py:575 "self._host replaces self._recorder"). A
#   _LegacyRecorderHostAdapter (654) wraps injected recorders so self._host is uniform. Map "recorder is None" → "self._host
#   is None" in EVERY finding — do NOT report a phantom "self._recorder missing" gap.

# CRITICAL #2 — POINT (f) IS COMPLIANT-VIA-DELEGATION, not a gap. run() does NOT call recorder.shutdown() inline; it hands off
#   to shutdown() (bounded: hard timeout + killpg force-cleanup), invoked by main()'s finally + on_quit. This is STRONGER than
#   the PRD's inline pseudocode (it eliminates the ~90s SIGKILL hang). Record as a nuance, NOT a defect.

# CRITICAL #3 — DO NOT FLAG the dead-host branch (@840-846), the drain branch (@856-860), or _text_in_flight (@863-868) as gaps.
#   They are intentional behaviors owned by sibling audits (P1.M2.T2.S1 dead-host; P1.M2.T1.S2 drain; validation Issue 1
#   _text_in_flight). Note they EXIST in the loop ordering; defer detail to those siblings.

# CRITICAL #4 — THIS IS AN AUDIT, NOT AN IMPLEMENTATION. The deliverable is gap_daemon_loop.md. Do NOT modify daemon.py unless
#   the re-verification surfaces a REAL defect (none expected — the loop is compliant). Editing source to "match the PRD
#   pseudocode" (e.g. inlining recorder.shutdown() into run()) would REGRESS the bounded-teardown design — do not.

# GOTCHA #5 — WRAP THE TEST RUN IN timeout (AGENTS.md: every non-trivial command needs a functional timeout). Use
#   `timeout 150 .venv/bin/python -m pytest ...` (inner) AND set the bash tool timeout above it. test_daemon.py is the fast
#   mocked suite (no CUDA) but the repo rule is non-negotiable.

# GOTCHA #6 — FULL PATHS in every bash command (zsh aliases: python3->uv run). .venv/bin/python, never bare python/pytest/uv.
```

## Implementation Blueprint

### Data models and structure

None. No source/schema change. This is a read-only audit producing a Markdown report.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RE-VERIFY the 6 contract points against the live code (read daemon.py)
  - OPEN voice_typing/daemon.py. For each of (a)-(f), confirm the file:line in the findings table (run @797-873; on_final @942-945;
    _arm @987; _disarm @1002; shutdown/_bounded_shutdown ~910/504-512). Note self._host (not self._recorder) at each site (CRITICAL #1).
  - CONFIRM the 3 additional branches exist but are out of scope: dead-host @840-846, drain @856-860, _text_in_flight @863-868.
  - EXPECTED: all 6 points match the findings table (COMPLIANT). If any does NOT (line drifted, logic changed), record the
    discrepancy and STOP — that is a real finding to report (not a silent "looks fine").

Task 2: RUN the contract's test target (the evidence)
  - RUN: `cd /home/dustin/projects/voice-typing && timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'loop or idle or run or main'`
  - EXPECTED: 40 passed, 153 deselected (the verified baseline; re-run if the count differs — record the ACTUAL count). If any
    FAIL, that is a real defect — record it (do NOT mask it as "compliant").

Task 3: WRITE plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md (the deliverable)
  - SECTIONS (mirror gap_cuda_check.md / the prior audit convention):
      1. Title + scope (PRD §4.2 #1-2; the 6 contract points; the run() + on_final/_arm/_disarm subject).
      2. Per-point compliance TABLE (the 6-row table above: PRD expected vs code actual vs verdict, with file:line).
      3. Test result: the `-k 'loop or idle or run or main'` count (40 passed, 153 deselected) + the test→property mapping
         (research §5) — which tests cover which point.
      4. Architectural nuances (NON-blocking — record so they aren't mistaken for defects):
         (i) self._recorder → self._host: the loop proxies to a RecorderHost subprocess; a _LegacyRecorderHostAdapter wraps
             injected recorders so self._host is uniform (semantically identical to PRD §4.2 #1; only the attribute + process
             boundary changed).
         (ii) Point (f) teardown is DELEGATED to bounded shutdown() (hard timeout + killpg), not inline in run() — stronger
              than the PRD pseudocode (eliminates the 90s hang). Audited in detail in P1.M2.T2.S3.
         (iii) The loop also contains a dead-host branch (P1.M2.T2.S1) + a drain branch (P1.M2.T1.S2) + _text_in_flight
               tracking — noted present, detail deferred to those sibling audits.
      5. Conclusion: COMPLIANT on all 6 points; no fix needed; the main loop faithfully implements the WhisperX-flaw fix
         (§1 #1) + the on_final stop-drop gate (§4.2 #2).
  - WHY: the report is the acceptance artifact for this audit subtask; downstream tasks (P1.M2.T1.S2 drain; P1.M2.T2 lifecycle)
    reference it.
  - DO NOT: modify daemon.py (CRITICAL #4); inline recorder.shutdown() into run(); flag the nuances as defects; invent tests.

Task 4: VALIDATE — confirm the report exists + the test command still passes + no source changed.
  - Run the Validation Loop L1-L3 below. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M2.T1.S1: audited the daemon main loop — PRD §4.2 #1-2 COMPLIANT on all 6 points (gap_daemon_loop.md)".
```

### Implementation Patterns & Key Details

```python
# AUDIT PATTERN (not code — a verification runbook). Read the loop, map each contract point to file:line, run the tests,
# transcribe the findings into gap_daemon_loop.md. No source edits unless a REAL defect surfaces.
# The contract's "recorder" → actual self._host (CRITICAL #1). (f) is delegated teardown (CRITICAL #2). The 3 extra branches
# are sibling-audit scope (CRITICAL #3).
```

### Integration Points

```yaml
CONSUMED (read-only):
  - voice_typing/daemon.py run()/on_final/_arm/_disarm/shutdown (the audit subject).
  - tests/test_daemon.py -k 'loop or idle or run or main' (the evidence; 40 tests).

PRODUCED:
  - plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md (the report — mirrors gap_cuda_check.md).

DOWNSTREAM (sibling audits that reference this one):
  - P1.M2.T1.S2 (graceful drain): depends on this audit's confirmation that the _drain/_complete_drain branch sits correctly
    in the loop ordering (between the host-None check and the listening re-entry).
  - P1.M2.T2.S1 (dead-host recovery): owns the _handle_dead_host branch this audit notes.
  - P1.M2.T2.S3 (bounded teardown): owns the shutdown()/_bounded_shutdown detail this audit references for point (f).

PARALLEL — P1.M1.T4.S1 (cuda_check audit → gap_cuda_check.md): NO overlap (§4.4 vs §4.2 #1-2; different audit subject).

UNCHANGED: ALL source files (daemon.py, tests, config, etc.) — this is a read-only audit. No new tests (runs existing ones).
```

## Validation Loop

> Full paths + a functional `timeout` on every command (AGENTS.md — CRITICAL #5/#6). Run from
> `/home/dustin/projects/voice-typing`. pytest is the runner (NO ruff/mypy). All gates are read/run-only.

### Level 1: the report exists + is well-formed

```bash
cd /home/dustin/projects/voice-typing
F=plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md
test -f "$F" && echo "L1 PASS: report exists" || echo "L1 FAIL: report missing"
grep -qiE 'compliant|§4.2|contract point|run\(\)' "$F" && echo "L1 PASS: report has the compliance table" || echo "L1 FAIL"
grep -qiE 'self._host|self._recorder|nuance|delegated|bounded' "$F" && echo "L1 PASS: nuances recorded" || echo "L1 FAIL: nuances missing"
# Expected: the report exists with the per-point table + the two nuances + the conclusion.
```

### Level 2: the contract's test target passes (the evidence)

```bash
cd /home/dustin/projects/voice-typing
timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'loop or idle or run or main'
# Expected: 40 passed, 153 deselected (the verified baseline; record the ACTUAL count in the report). Any FAIL is a real
# defect — record it in the report (do not claim compliant).
```

### Level 3: no source modified (it's an audit) + scope guard

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: ONLY plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md (new) — NO voice_typing/daemon.py, NO tests/, NO other
# source. (P1.M1.T4.S1 may add gap_cuda_check.md in parallel — separate file.) If daemon.py appears modified, STOP — the
# audit must not change source unless a real defect was found AND recorded.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `gap_daemon_loop.md` exists with the 6-point compliance table + the two nuances + the conclusion.
- [ ] L2: `timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'loop or idle or run or main'` → pass (record count; baseline 40).
- [ ] L3: `git status` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md` (no source changes).

### Feature Validation
- [ ] All 6 contract points (a)-(f) recorded COMPLIANT with daemon.py file:line.
- [ ] The `self._host` evolution + the delegated-teardown nuances recorded (not flagged as defects).
- [ ] Verdict: COMPLIANT — no fix needed (or, if a real defect was found, it's recorded + fixed).

### Code Quality Validation
- [ ] Report mirrors the `gap_<area>.md` convention (table + test count + nuance + conclusion).
- [ ] Findings match the live re-verification (file:line + test count).
- [ ] Full paths + functional `timeout` on every command.

### Scope Boundary Validation
- [ ] No daemon.py / source changes (read-only audit) unless a real defect was found.
- [ ] Drain detail deferred to P1.M2.T1.S2; dead-host to P1.M2.T2.S1; bounded teardown to P1.M2.T2.S3 (noted, not audited here).
- [ ] No conflict with the parallel P1.M1.T4.S1 (cuda_check audit — different subject/file).

---

## Anti-Patterns to Avoid

- ❌ Don't report a phantom "self._recorder missing" gap — the loop uses `self._host` (a RecorderHost subprocess); the contract's `recorder` wording maps to it (CRITICAL #1).
- ❌ Don't flag point (f) as a gap because `run()` doesn't inline `recorder.shutdown()` — it delegates to bounded `shutdown()` (stronger; CRITICAL #2).
- ❌ Don't flag the dead-host/drain/`_text_in_flight` branches as gaps — they're sibling-audit scope (CRITICAL #3).
- ❌ Don't modify `daemon.py` to "match the PRD pseudocode" (e.g. inlining shutdown) — that REGRESSES the bounded-teardown design (CRITICAL #4). This is an audit.
- ❌ Don't run pytest without a functional `timeout` (AGENTS.md; CRITICAL #5).
- ❌ Don't use bare python/pytest/uv (zsh aliases — CRITICAL #6).
- ❌ Don't claim "compliant" if a test fails — record the failure as a real defect.
- ❌ Don't duplicate the drain/dead-host/bounded-teardown audits (P1.M2.T1.S2 / P1.M2.T2.S1 / P1.M2.T2.S3 own them).

---

## Confidence Score

**10/10** for one-pass success. This is a read-only audit whose findings are already verified: all 6 contract points map to specific daemon.py file:lines (run @834/847-848/856/867/870-871/873; on_final @944-945; _arm @987; _disarm @1002; teardown delegated to shutdown @~910/504-512), the `-k 'loop or idle or run or main'` slice is **40 passed in 1.30s** (re-ran live), and the two architectural nuances (`self._host` evolution; delegated bounded teardown) are documented. The implementing agent re-verifies the file:line + re-runs the test command + transcribes the findings table into `gap_daemon_loop.md` — no judgment calls, no source edits, no residual uncertainty. The only "deviation" from the contract wording (self._recorder → self._host) is a documented architectural evolution, not a defect.