# PRP — P1.M2.T1.S2: Audit graceful drain — stop during in-flight utterance, drain watchdog, abort-on-idle

## Goal

**Feature Goal**: Produce the authoritative **graceful-drain audit** as a new **§2 Graceful Drain (P1.M2.T1.S2)** section **APPENDED** to `plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md` (which the sibling **P1.M2.T1.S1** creates with the §1 main-loop audit). The audit cross-checks `voice_typing/daemon.py`'s drain state machine — `_request_stop` (1053) / `_begin_drain` (1073) / `_complete_drain` (1084) / `_drain_timeout` (1104) / `_safe_abort` (1335) + the `run()` drain branch (850-854) + the `on_final` listen-flag gate (944-945) + the `_final_pending`/`_text_in_flight` tracking — against **PRD §4.2 #2** ("Stop is graceful (drain)") on the 6 item properties (a)-(f). This is a **verification/audit** subtask: the deliverable is the appended report section; code changes happen ONLY if a real defect is found (**none is expected — the audit finds the drain fully PRD §4.2 #2-compliant**).

**Deliverable** (one APPEND to an existing report; no new file, no source edits): a **§2 Graceful Drain** section appended to `gap_daemon_loop.md` containing: (a) a per-property compliance table (PRD §4.2 #2 expected vs code actual, with daemon.py file:line) for the 6 properties (a)-(f); (b) the unit-test pass/fail count for the contract's run target (`-k 'drain or stop or abort or graceful'`); (c) the non-blocking nuances (the 3-way "in flight" predicate; `_DRAIN_TIMEOUT_S=5.0`; the `_safe_abort` `_text_in_flight` gate; run-loop ordering; idempotent `_begin_drain`); (d) a conclusion. **This PRP's author has already performed the audit** (findings embedded below + in the research note) — the implementing agent re-verifies, re-runs the tests, and transcribes/appends the section.

**Success Definition**:
- (a) `gap_daemon_loop.md` contains a "§2 Graceful Drain (P1.M2.T1.S2)" section (appended after S1's §1 main-loop content) with the 4 sub-parts above.
- (b) The recorded findings match the live re-verification: all 6 drain properties (a)-(f) are **compliant** (each with daemon.py file:line).
- (c) `timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'drain or stop or abort or graceful'` → all pass (record the count; verified baseline: **29 passed, 164 deselected**).
- (d) **No source files are modified** (because no defect exists — the drain is PRD §4.2 #2-compliant per audit). If — and only if — the re-verification surfaces a REAL defect, fix it and record the fix; otherwise record "none — compliant per audit."
- (e) The section records the non-blocking nuances (the 3-way in-flight predicate; the 5 s watchdog; the `_safe_abort` gate) so they aren't mistaken for defects, and ties the verdict to acceptance criteria **#2** (≥3 s pause loses zero words) and **#4** (nothing typed while toggled off).

> **VERIFIED VERDICT (this PRP's research): the graceful drain is PRD §4.2 #2 COMPLIANT — no fix needed.** All 6 properties pass (daemon.py file:line below); the `-k 'drain or stop or abort or graceful'` slice = **29 passed in 0.54s**.

## User Persona

**Target User**: the maintainer (human or AI agent) who needs to trust that an explicit stop/toggle-off does NOT drop an in-flight utterance (the §1 #1 "pressing the hotkey mid-sentence does NOT drop the words already spoken" guarantee) and that nothing is typed after disarm (acceptance #4), before relying on the daemon's stop path. Also the downstream P1.M5.T5 acceptance-criteria cross-check (which maps criteria #2/#4 to this audit's evidence).
**Use Case**: A future change to the drain state machine (e.g. altering the in-flight predicate, the watchdog timeout, or the on_final gate). The §2 audit + the 29 drain tests are the reference that proves the change keeps (or breaks) PRD §4.2 #2 compliance.
**Pain Points Addressed**: Closes the "does a stop actually (a) detect an in-flight utterance, (b) let the final finish, (c) disarm after, (d) bound the wait, (e) abort immediately when idle, (f) drop straggler finals?" question with recorded, re-runnable evidence — not an assumption. (Acceptance #2 + #4 are certified by (b)+(c) + (e)+(f) respectively.)

## Why

- **The drain is the §1 #1 hotkey-mid-sentence guarantee.** PRD §1 #1: the prior WhisperX system "stopped listening as soon as it thought the user was done talking … the next few words were lost." The fix has two halves: (1) silence only segments (audited in §1 main loop) and (2) an explicit stop **drains** the in-flight final before disarming (this audit). Both must be certified by recorded evidence.
- **Nothing typed while toggled off (acceptance #4).** PRD §4.2 #2 last sentence + §8: an utterance may complete right around a stop; without the `on_final` listen-flag gate + the immediate-disarm path, a straggler final would be typed after disarm. The audit certifies both the gate (f) and the not-in-flight immediate disarm+abort (e).
- **A stop can never hang.** PRD §4.2 #2: "A bounded drain watchdog (a few seconds) aborts the rare case where no final ever fires, so a stop can never hang." The audit certifies the `_drain_timeout` watchdog (d) + the `_DRAIN_TIMEOUT_S=5.0` bound.
- **Scope discipline.** This subtask owns the 6 drain properties ONLY. The main loop's basic 6 points are §1 (P1.M2.T1.S1); the dead-host recovery (`_handle_dead_host`) is P1.M2.T2.S1; the bounded teardown (`shutdown()`/`_bounded_shutdown`) is P1.M2.T2.S3. This audit notes those branches sit correctly relative to the drain but defers their detail to those siblings.

## What

An audit (read-only + test-run), producing an **appended §2 section** in `gap_daemon_loop.md`. No user-visible behavior change, no config/API surface (DOCS: none — internal lifecycle logic). The audit verifies the 6 drain properties (a)-(f), runs the targeted tests, records findings.

### Success Criteria

- [ ] `gap_daemon_loop.md` contains the appended "§2 Graceful Drain (P1.M2.T1.S2)" section (after S1's §1 content).
- [ ] All 6 drain properties (a)-(f) recorded COMPLIANT, each with daemon.py file:line.
- [ ] `timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'drain or stop or abort or graceful'` → pass (record count; baseline 29 passed).
- [ ] The non-blocking nuances recorded (3-way in-flight predicate; `_DRAIN_TIMEOUT_S=5.0`; `_safe_abort` `_text_in_flight` gate; run-loop ordering; idempotent `_begin_drain`).
- [ ] The verdict ties to acceptance criteria #2 (≥3 s pause loses zero words) and #4 (nothing typed while toggled off).
- [ ] No source files modified (unless a REAL defect is found — none expected).

## All Needed Context

### Context Completeness Check

_Pass._ The exact code locations (file:line) for all 6 drain properties, the test→property mapping, the verified baseline (29 passed), the non-blocking nuances, and the sibling-audit boundaries (main-loop §1 / dead-host / bounded-teardown) are all below + in the research note. An agent new to this repo can re-verify and append the report section from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the full audit evidence (6-property table + nuances + test mapping + conclusion)
- docfile: plan/006_862ee9d6ef41/P1M2T1S2/research/drain_audit_findings.md
  why: "§0 the drain state-machine one-paragraph map (stop/toggle -> _request_stop -> branch). §1 the 6-property
        compliance table with daemon.py file:line. §2 the nuances (3-way in-flight predicate; _DRAIN_TIMEOUT_S=5.0;
        _safe_abort _text_in_flight gate; run-loop ordering; idempotent _begin_drain; auto-stop bypasses drain).
        §3 test->property mapping. §4 conclusion (ties to acceptance #2/#4)."
  section: "§1 (the table) + §2 (the nuances) are load-bearing for the report section."

# MUST READ — the file this task APPENDS to (S1 creates §1; this task appends §2)
- docfile: plan/006_862ee9d6ef41/P1M2T1S1/PRP.md
  why: "S1 (parallel, 'Implementing') CREATES gap_daemon_loop.md with the §1 main-loop audit (the 6 basic-loop
        contract points + 40-passed baseline). S1's PRP explicitly says 'The graceful drain (the _drain/
        _complete_drain branch) is P1.M2.T1.S2' and its research §3 notes the drain branch @850-854 exists but
        defers detail to THIS task. So: if S1 has landed, gap_daemon_loop.md EXISTS -> APPEND §2. Confirm the file
        exists before appending; if S1 has NOT yet landed, create gap_daemon_loop.md with a minimal header so §2
        is appendable (S1's §1 is then inserted above — coordinate, but do NOT duplicate S1's §1 content)."
  critical: "Do NOT duplicate §1 (the main-loop 6 points) — that is S1's deliverable. This task appends §2 (the
             drain 6 properties) ONLY. Different contract points (basic loop vs drain), different properties."

# THE AUDIT SUBJECT (the drain state machine)
- file: voice_typing/daemon.py
  why: "_request_stop @1053 (the branch: in-flight -> _begin_drain @1066; else _disarm+_safe_abort @1067-1069;
        the in-flight predicate @1065 host is not None AND _text_in_flight.is_set() AND _final_pending).
        _begin_drain @1073 (_drain=True @1078 + Timer(_DRAIN_TIMEOUT_S, _drain_timeout) @1079-1081; idempotent
        @1076-1077). _complete_drain @1084 (_drain=False @1096, _disarm @1097, cancel timer @1098-1101).
        _drain_timeout @1104 (Timer thread; if _drain+host+_text_in_flight @1112 -> _safe_abort @1117).
        _safe_abort @1335 (gated on _text_in_flight @1358; never re-raises). run() drain branch @850-854
        (if self._drain: _complete_drain(); continue — BEFORE the _listening re-entry). on_final gate @944-945
        + _final_pending=False @954. _final_pending set by _touch_speech @1040. _DRAIN_TIMEOUT_S=5.0 @138.
        stop() @1388->_request_stop @1391; toggle()-off @1393->_request_stop @1410(normal)/@1438(lite)."
  critical: "Map each drain property to these file:lines. The 'in flight' predicate is a 3-way AND (host +
             _text_in_flight + _final_pending) — the precise realization of PRD §4.2 #2's 'speech occurred since
             the last final and the loop is blocked in text()'. _maybe_auto_stop calls _disarm DIRECTLY (not
             _request_stop) — by design (idle auto-stop => nothing to drain); note it."

# THE PRD CONTRACT
- file: PRD.md
  why: "§4.2 #2 'Stop is graceful (drain)' — the full drain contract (in-flight -> let text() return the natural
        final -> disarm; not-in-flight -> immediate disarm + abort; bounded watchdog; on_final gated on listen flag).
        §1 #1 'pressing the hotkey mid-sentence does NOT drop the words already spoken (§4.2 #2).' §7 acceptance #2
        (>=3s pause loses zero words) + #4 (nothing typed while toggled off) — this audit certifies both."

# THE TESTS (the contract's run target)
- file: tests/test_daemon.py
  why: "The -k 'drain or stop or abort or graceful' slice = 29 tests. Key drain covers: test_stop_drains_when_
        utterance_in_flight + test_toggle_off_drains_when_utterance_in_flight (a,b,c); test_drain_timeout_aborts_
        blocked_text + test_request_shutdown_unblocks_loop_when_abort_does_not_fire_final (d); test_stop_disarms_
        immediately_when_idle + test_stop_aborts_immediately_when_text_idle_no_speech + test_stop_skips_abort_when_
        no_text_in_flight + test_stop_while_run_loop_idle_does_not_abort_and_does_not_hang (e); test_on_final_gate_
        when_not_listening (f, in the -k 'loop...' set); test_stop_never_calls_recorder_shutdown (stop != teardown).
        See research §3 for the full mapping."

# THE AUDIT CONVENTION (mirror this report structure)
- docfile: plan/006_862ee9d6ef41/architecture/gap_cuda_check.md
  why: "The prior cuda_check gap report — same shape: per-point compliance table with file:line, live test result
        + count, non-blocking nuances recorded as design-not-defect, conclusion. Mirror its section ordering for
        the §2 drain content. (S1's §1 in gap_daemon_loop.md follows the same convention.)"

# PARALLEL CONTEXT — P1.M2.T1.S1 (main-loop audit; CREATES the file this task appends to)
- docfile: plan/006_862ee9d6ef41/P1M2T1S1/PRP.md
  why: "S1 audits run()/on_final/_arm/_disarm against §4.2 #1-2 (basic loop) and CREATES gap_daemon_loop.md. This
        task APPENDS §2 to that file. No content overlap (basic loop 6 points vs drain 6 properties). Confirm S1's
        file exists before appending."
```

### The 6 drain properties — verified findings (transcribe into the §2 section)

| # | Property (PRD §4.2 #2 / item) | Code actual (daemon.py) | Verdict |
|---|---|---|---|
| (a) | `_request_stop` checks if speech is in flight | `_request_stop()` 1065 `if self._host is not None and self._text_in_flight.is_set() and self._final_pending:` | ✅ COMPLIANT (3-way AND = "loop in text() AND speech since last final") |
| (b) | in flight → `_begin_drain` sets flag; loop lets `text()` return the natural final | 1066 `_begin_drain()`; `_begin_drain` 1078 `self._drain=True` + watchdog Timer 1079-1081; run loop 850-854 `if self._drain: self._complete_drain(); continue` (BEFORE the `_listening` re-entry) | ✅ COMPLIANT |
| (c) | `_complete_drain` disarms after the final | `_complete_drain()` 1084: 1096 `_drain=False` → 1097 `_disarm()` → 1098-1101 cancel the watchdog Timer | ✅ COMPLIANT |
| (d) | bounded watchdog aborts if no final fires (few seconds) | `_drain_timeout()` 1104 on the Timer thread (`Timer(_DRAIN_TIMEOUT_S=5.0, …)` 1079/138): 1112 `if self._drain and self._host is not None and self._text_in_flight.is_set():` → 1117 `self._safe_abort()` | ✅ COMPLIANT (`_DRAIN_TIMEOUT_S=5.0`) |
| (e) | NOT in flight → immediate disarm + abort | `_request_stop()` else 1067-1069: `with self._lock: self._disarm()` + 1069 `if self._host is not None: self._safe_abort()` | ✅ COMPLIANT |
| (f) | `on_final` checks the listen flag before typing ("gate inside on_final too") | `on_final()` 944-945 `if not self._listening.is_set(): return` (FIRST statement) + 954 `self._final_pending=False` | ✅ COMPLIANT (PRD §4.2 #2 last sentence / §8 race row) |

**Test baseline**: `timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'drain or stop or abort or graceful'` → **29 passed, 164 deselected in 0.54s**.

### Current Codebase tree (relevant slice — read-only audit + one appended report section)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/daemon.py   # READ-ONLY audit subject: _request_stop @1053, _begin_drain @1073, _complete_drain @1084,
│                            #   _drain_timeout @1104, _safe_abort @1335, run() drain branch @850-854, on_final @942-945.
├── tests/test_daemon.py     # READ + RUN: the -k 'drain or stop or abort or graceful' slice (29 tests).
└── plan/006_862ee9d6ef41/
    ├── architecture/gap_daemon_loop.md   # ← APPEND §2 (S1 creates the file + §1; this task appends §2).
    └── P1M2T1S2/{PRP.md, research/drain_audit_findings.md}   # this PRP + the evidence (already written).
# No source edits. No new tests (the audit RUNS existing tests, doesn't add them). No new report FILE (append only).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — APPEND TO gap_daemon_loop.md, do NOT create a new file and do NOT duplicate §1. S1 (P1.M2.T1.S1)
#   CREATES gap_daemon_loop.md with the §1 main-loop audit (the 6 basic-loop points + 40-passed baseline). This task
#   APPENDS a "## 2. Graceful Drain (P1.M2.T1.S2)" section with the DRAIN 6 properties (a)-(f). Different contract
#   points (basic loop vs drain). If S1 has not yet landed the file, create it with a minimal top header (title +
#   "## 1. Main Loop" placeholder) so §2 is appendable — but do NOT write S1's §1 content (S1 owns it).

# CRITICAL #2 — THE "IN FLIGHT" PREDICATE IS A 3-WAY AND, not just _text_in_flight. _request_stop @1065 checks
#   `self._host is not None and self._text_in_flight.is_set() and self._final_pending`. _text_in_flight = the run
#   loop is blocked inside text() (set @865/cleared @869); _final_pending = speech occurred since the last final
#   (set by _touch_speech @1040, cleared in on_final @954). The AND prevents a 5s drain when the loop is in text()
#   but nothing was said (idle re-listen) -> stop stays responsive. Record this as the precise realization of PRD
#   §4.2 #2's wording; do NOT flag the 3rd term (_final_pending) as "extra".

# CRITICAL #3 — _DRAIN_TIMEOUT_S = 5.0s (daemon.py:138) is the bounded watchdog window. PRD §4.2 #2 says "a few
#   seconds"; 5.0 is comfortably above the <=1.5s final-latency target (PRD §6) so a normal final always lands
#   before the watchdog, while bounding the worst case. Record the value; do NOT flag it as "too long" or "too short".

# CRITICAL #4 — _safe_abort IS _text_in_flight-GATED (daemon.py:1335/1358). abort() runs ONLY when a thread is
#   blocked in text(); when the loop is idle in sleep(0.05) it is SKIPPED (would hang forever on
#   was_interrupted.wait()). This is the validation Issue 1 fix — correct, not just safe. Record as a nuance, NOT a
#   defect. (abort() never re-raises either.)

# CRITICAL #5 — RUN-LOOP ORDERING: the `if self._drain:` check (@850-854) PRECEDES `if self._listening.is_set():`
#   (@856) so a drained session disarms instead of re-listening. This IS the "lets text() return the natural final
#   ... after which the loop disarms" guarantee. Do NOT flag the early drain check as "skipping the listen gate".

# CRITICAL #6 — _maybe_auto_stop (the 30s idle auto-stop) calls _disarm() DIRECTLY, NOT _request_stop(). By design:
#   idle auto-stop only fires when there is NO speech, so there is never anything to drain. Record this (it is NOT
#   a missing-drain gap); the drain applies to explicit stop/toggle-off only (PRD §4.2 #2 "an explicit stop/toggle-off").

# CRITICAL #7 — THIS IS AN AUDIT, NOT AN IMPLEMENTATION. The deliverable is the appended §2 section. Do NOT modify
#   daemon.py unless the re-verification surfaces a REAL defect (none expected — the drain is compliant). Editing
#   source to "simplify" the drain (e.g. dropping _final_pending, or calling _disarm from _request_stop on the
#   in-flight path) would REGRESS the design — do not.

# GOTCHA #8 — WRAP THE TEST RUN IN timeout (AGENTS.md: every non-trivial command needs a functional timeout). Use
#   `timeout 150 .venv/bin/python -m pytest ...` (inner) AND set the bash tool timeout above it.

# GOTCHA #9 — FULL PATHS in every bash command (zsh aliases: python3->uv run). .venv/bin/python, never bare python/pytest/uv.
```

## Implementation Blueprint

### Data models and structure

None. No source/schema change. This is a read-only audit producing a Markdown report section (appended to an existing report).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RE-VERIFY the 6 drain properties against the live code (read daemon.py)
  - OPEN voice_typing/daemon.py. For each of (a)-(f), confirm the file:line in the findings table:
    _request_stop @1053 (predicate @1065, branch @1066/1067-1069); _begin_drain @1073 (_drain=True @1078,
    Timer @1079-1081, idempotent @1076-1077); _complete_drain @1084 (_drain=False @1096, _disarm @1097,
    cancel @1098-1101); _drain_timeout @1104 (Timer thread, guard @1112, _safe_abort @1117); _safe_abort @1335
    (_text_in_flight gate @1358); run() drain branch @850-854 (before _listening @856); on_final gate @944-945 +
    _final_pending=False @954; _DRAIN_TIMEOUT_S=5.0 @138; _final_pending set by _touch_speech @1040.
  - CONFIRM the entry points: stop() @1388->_request_stop @1391; toggle()-off @1393->_request_stop @1410/@1438;
    _maybe_auto_stop calls _disarm() directly (NOT _request_stop) — by design.
  - EXPECTED: all 6 properties match the findings table (COMPLIANT). If any does NOT (line drifted, logic changed),
    record the discrepancy and STOP — that is a real finding to report (not a silent "looks fine").

Task 2: RUN the contract's test target (the evidence)
  - RUN: `cd /home/dustin/projects/voice-typing && timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'drain or stop or abort or graceful'`
  - EXPECTED: 29 passed, 164 deselected (the verified baseline; re-run if the count differs — record the ACTUAL count).
    If any FAIL, that is a real defect — record it (do NOT mask it as "compliant").

Task 3: APPEND the "## 2. Graceful Drain (P1.M2.T1.S2)" section to plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md
  - PRECONDITION: gap_daemon_loop.md exists (S1 creates it with §1). If it does NOT exist yet (S1 not landed), create
    it with a minimal top header so §2 is appendable, but do NOT write S1's §1 content (S1 owns it).
  - APPEND (verbatim structure; transcribe the verified findings):
      "## 2. Graceful Drain (P1.M2.T1.S2) — stop during in-flight utterance, drain watchdog, abort-on-idle"
      - Scope paragraph: the drain state machine (_request_stop/_begin_drain/_complete_drain/_drain_timeout/
        _safe_abort + run() drain branch + on_final gate) vs PRD §4.2 #2; the 6 properties (a)-(f).
      - Per-property compliance TABLE (the 6-row table above: PRD §4.2 #2 expected vs code actual vs verdict,
        with file:line).
      - Test result: the `-k 'drain or stop or abort or graceful'` count (29 passed, 164 deselected) + the
        test->property mapping (research §3).
      - Non-blocking nuances (record so they aren't mistaken for defects): (i) the 3-way in-flight predicate
        (host + _text_in_flight + _final_pending); (ii) _DRAIN_TIMEOUT_S=5.0; (iii) _safe_abort _text_in_flight
        gate (validation Issue 1); (iv) run-loop ordering (drain check before _listening re-entry); (v) idempotent
        _begin_drain; (vi) _maybe_auto_stop bypasses drain (idle => nothing to drain).
      - Conclusion: COMPLIANT on all 6 properties; no fix needed; certifies acceptance #2 (>=3s pause loses zero
        words — the drain types the in-flight final before disarming) + #4 (nothing typed while toggled off — the
        on_final gate + immediate-disarm path).
  - WHY: the §2 section is the acceptance artifact for this audit subtask; P1.M5.T5 (acceptance cross-check)
    references it for criteria #2/#4.
  - DO NOT: modify daemon.py (CRITICAL #7); duplicate S1's §1 (CRITICAL #1); flag the nuances as defects
    (CRITICAL #2-#6); invent tests.

Task 4: VALIDATE — confirm the §2 section is appended + the test command still passes + no source changed.
  - Run the Validation Loop L1-L3 below. No git commit unless the orchestrator directs it.
  If asked, message: "P1.M2.T1.S2: audited the graceful drain — PRD §4.2 #2 COMPLIANT on all 6 properties (gap_daemon_loop.md §2)".
```

### Implementation Patterns & Key Details

```python
# AUDIT PATTERN (not code — a verification runbook). Read the drain state machine, map each property to file:line,
# run the drain tests, transcribe the findings into gap_daemon_loop.md §2. No source edits unless a REAL defect surfaces.
# The "in flight" predicate is a 3-way AND (CRITICAL #2). _DRAIN_TIMEOUT_S=5.0 (CRITICAL #3). _safe_abort is
# _text_in_flight-gated (CRITICAL #4). The run-loop drain check precedes the _listening re-entry (CRITICAL #5).
# _maybe_auto_stop bypasses drain by design (CRITICAL #6). APPEND §2, don't duplicate §1 (CRITICAL #1).
```

### Integration Points

```yaml
CONSUMED (read-only):
  - voice_typing/daemon.py drain state machine: _request_stop/_begin_drain/_complete_drain/_drain_timeout/
    _safe_abort/run() drain branch/on_final gate (the audit subject).
  - tests/test_daemon.py -k 'drain or stop or abort or graceful' (the evidence; 29 tests).

PRODUCED:
  - plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md  §2 Graceful Drain (appended — mirrors gap_cuda_check.md
    structure; S1 owns §1).

DOWNSTREAM (sibling audits / acceptance that reference this one):
  - P1.M2.T1.S1 (main loop): CREATES gap_daemon_loop.md + §1; this task appends §2 to it. Coordinate on file existence.
  - P1.M5.T5 (acceptance cross-check): maps acceptance #2 (>=3s pause loses zero words) + #4 (nothing typed while
    toggled off) to THIS audit's evidence.

PARALLEL — P1.M2.T2.S1 (dead-host recovery): owns _handle_dead_host (noted in the run loop @840-846, separate from
  the drain branch). No overlap with the drain 6 properties.

UNCHANGED: ALL source files (daemon.py, tests, config, etc.) — this is a read-only audit. No new tests (runs
  existing ones). No new report FILE (append §2 only).
```

## Validation Loop

> Full paths + a functional `timeout` on every command (AGENTS.md — GOTCHA #8/#9). Run from
> `/home/dustin/projects/voice-typing`. pytest is the runner (NO ruff/mypy). All gates are read/run-only.

### Level 1: the §2 section is appended + well-formed

```bash
cd /home/dustin/projects/voice-typing
F=plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md
test -f "$F" && echo "L1 PASS: report file exists" || echo "L1 FAIL: report missing"
grep -qiE '2\. Graceful Drain|drain watchdog|in-flight utterance|_request_stop|_complete_drain' "$F" && echo "L1 PASS: §2 drain section present" || echo "L1 FAIL: §2 missing"
grep -qiE '_DRAIN_TIMEOUT_S|_text_in_flight|_final_pending|in flight|nuance' "$F" && echo "L1 PASS: drain nuances recorded" || echo "L1 FAIL: nuances missing"
grep -qiE 'acceptance.*(#[234]|#2|#4)|loses zero words|nothing typed while toggled off' "$F" && echo "L1 PASS: ties to acceptance #2/#4" || echo "L1 WARN: acceptance tie not explicit"
# Expected: the file exists with the §2 drain section + the nuances + the acceptance tie + the conclusion.
```

### Level 2: the contract's test target passes (the evidence)

```bash
cd /home/dustin/projects/voice-typing
timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'drain or stop or abort or graceful'
# Expected: 29 passed, 164 deselected (the verified baseline; record the ACTUAL count in the §2 section). Any FAIL is
# a real defect — record it in the report (do not claim compliant).
```

### Level 3: no source modified (it's an audit) + scope guard

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: gap_daemon_loop.md is the only repo-tracked change attributable to this task (new if S1 hadn't created it,
# or modified via the append). NO voice_typing/daemon.py, NO tests/, NO other source. (P1.M2.T1.S1 may also touch
# gap_daemon_loop.md — its §1; coordinate so both §1 and §2 land.) If daemon.py appears modified, STOP — the audit
# must not change source unless a real defect was found AND recorded.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: `gap_daemon_loop.md` has the appended "§2 Graceful Drain" section with the 6-property table + nuances + conclusion.
- [ ] L2: `timeout 150 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'drain or stop or abort or graceful'` → pass (record count; baseline 29).
- [ ] L3: `git status` shows no source changes (daemon.py/tests/config untouched); only the report section was appended.

### Feature Validation
- [ ] All 6 drain properties (a)-(f) recorded COMPLIANT with daemon.py file:line.
- [ ] The non-blocking nuances recorded (3-way in-flight predicate; `_DRAIN_TIMEOUT_S=5.0`; `_safe_abort` gate; run-loop ordering; idempotent `_begin_drain`; auto-stop bypass).
- [ ] Verdict ties to acceptance #2 (≥3 s pause loses zero words) + #4 (nothing typed while toggled off).
- [ ] Verdict: COMPLIANT — no fix needed (or, if a real defect was found, it's recorded + fixed).

### Code Quality Validation
- [ ] §2 mirrors the `gap_<area>.md` convention (table + test count + nuance + conclusion) and sits after S1's §1.
- [ ] Findings match the live re-verification (file:line + test count).
- [ ] Full paths + functional `timeout` on every command.

### Scope Boundary Validation
- [ ] No daemon.py / source changes (read-only audit) unless a real defect was found.
- [ ] §1 (main loop) NOT duplicated — S1 owns it; this task appends §2 (drain) only.
- [ ] Dead-host detail deferred to P1.M2.T2.S1; bounded teardown to P1.M2.T2.S3 (noted, not audited here).
- [ ] No conflict with the parallel P1.M2.T1.S1 (main-loop audit — same file, different section/contract).

---

## Anti-Patterns to Avoid

- ❌ Don't create a NEW report file or duplicate §1 — S1 creates `gap_daemon_loop.md` + §1 (main loop); this task APPENDS §2 (drain) only. Different contract points. (CRITICAL #1.)
- ❌ Don't flag the 3-way in-flight predicate (`_text_in_flight` AND `_final_pending`) as "extra/over-engineered" — it's the precise realization of PRD §4.2 #2's wording and keeps stop responsive when the loop is in `text()` but idle. (CRITICAL #2.)
- ❌ Don't flag `_DRAIN_TIMEOUT_S=5.0` as too long/short — it's above the ≤1.5 s final-latency target and bounds the worst case ("a few seconds"). (CRITICAL #3.)
- ❌ Don't flag the `_safe_abort` `_text_in_flight` gate as a defect — it's the validation Issue 1 fix (abort only when a thread is in `text()`; never hangs when idle). (CRITICAL #4.)
- ❌ Don't flag the run-loop ordering (`if self._drain:` before `if self._listening:`) as "skipping the listen gate" — it IS the drain-then-disarm guarantee. (CRITICAL #5.)
- ❌ Don't flag `_maybe_auto_stop` calling `_disarm()` directly (not `_request_stop`) as a missing-drain gap — idle auto-stop means nothing to drain. (CRITICAL #6.)
- ❌ Don't modify `daemon.py` to "simplify" the drain — this is an audit; the drain is compliant. (CRITICAL #7.)
- ❌ Don't run pytest without a functional `timeout` (AGENTS.md; GOTCHA #8).
- ❌ Don't use bare python/pytest/uv (zsh aliases — GOTCHA #9).
- ❌ Don't claim "compliant" if a test fails — record the failure as a real defect.

---

## Confidence Score

**10/10** for one-pass success. This is a read-only audit whose findings are already verified: all 6 drain properties map to specific daemon.py file:lines (`_request_stop` @1053/1065-1069; `_begin_drain` @1073/1078-1081; `_complete_drain` @1084/1096-1101; `_drain_timeout` @1104/1112-1117; `_safe_abort` @1335/1358; run-loop drain branch @850-854; on_final gate @944-945; `_DRAIN_TIMEOUT_S=5.0` @138), the `-k 'drain or stop or abort or graceful'` slice is **29 passed in 0.54s** (re-ran live), and the non-blocking nuances (3-way in-flight predicate; `_text_in_flight`-gated abort; run-loop ordering; auto-stop bypass) are documented. The implementing agent re-verifies the file:line + re-runs the test command + transcribes the findings into `gap_daemon_loop.md` §2 — no judgment calls, no source edits, no residual uncertainty. The only coordination point is that S1 must have created `gap_daemon_loop.md` (§1) first; if not, create a minimal header and append §2 (S1's §1 is then inserted above — no content overlap).