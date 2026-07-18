# PRP — P1.M2.T2.S3: Audit bounded teardown — killpg after join(5s), idle-unload watchdog, no 90s hang (PRD §4.2bis Idle-unload + §8 risk row)

## Goal

**Feature Goal**: Produce the authoritative **bounded-teardown audit** as a new **§3 section appended to `plan/006_862ee9d6ef41/architecture/gap_lifecycle.md`**, cross-checking the daemon-side teardown ORCHESTRATION + TIMING against **PRD §4.2bis's "Hard requirement — bounded teardown" + the §8 risk row** ("`recorder.shutdown()` hangs ~90s") on the **5 item properties (a)-(e)**. This is a **verification/audit** subtask (round `006_862ee9d6ef41`): the deliverable is the report section; **code changes happen ONLY if a real defect is found — none is expected; this PRP's author has already performed the audit and the teardown is PRD §4.2bis + §8-COMPLIANT.**

> **VERIFIED VERDICT (this PRP's research): the bounded teardown is COMPLIANT — no fix needed.** All 5 properties (a)-(e) pass (file:line in the research note); the contract's `-k 'unload or teardown or shutdown or killpg or terminate or bounded'` slice = **42 passed, 177 deselected in 2.12s**. The teardown is bounded (killpg after a 5s join, ~7s max/call, ~9s total single-flight) so it CANNOT reproduce RealtimeSTT's ~90s `recorder.shutdown()` wedge — the exact prerequisite the Idle-unload feature + acceptance #9 depend on.

**Deliverable** (ONE report section; NO source edits, NO test edits): `plan/006_862ee9d6ef41/architecture/gap_lifecycle.md` — a **`# §3 — Bounded Teardown (P1.M2.T2.S3)` section APPENDED** below §1 (S1 lazy-load) and §2 (S2 IPC, already in the file). The section mirrors the `gap_*.md` §N-append format (sibling precedents: `gap_daemon_loop.md` §2 @L156+, and this file's own §2 @L201) and contains: (1) scope + audited artifacts (file:line); (2) a per-property compliance table (PRD §4.2bis/§8 expected vs code actual) for (a)-(e); (3) the test pass/fail count for the contract's run target; (4) the non-defect nuances (two single-flight layers; `_bounded_shutdown`→`host.stop` routing; detached graceful-cmd thread; abort-before-join; lock-free pre-check; abort-outside-`_lock`; the ~9s budget math); (5) a conclusion tying the verdict to PRD §4.2bis's resolved paragraph + §8 risk row + acceptance #9. **This PRP's author has already performed the audit** (findings in the research note) — the implementing agent re-verifies, re-runs the tests, and transcribes the §3 section.

> **Append-vs-create (parallel-safe):** §1 (S1) and §2 (S2) are already in `gap_lifecycle.md` (verified — headings at L1/L201). S3 APPENDS §3 below §2. The `# §3` heading makes the three sections compose without conflict (exactly as P1.M2.T1.S2 appended §2 to the S1-created `gap_daemon_loop.md`, and S2 appended §2 here). §2's own conclusion already states "the bounded teardown TIMING … is S3" — §3 delivers exactly that, and REFERENCES §2's stop@272-329 + killpg@407 (the mechanism §3 certifies the TIMING of).

**Success Definition**:
- (a) `architecture/gap_lifecycle.md` contains a `# §3 — Bounded Teardown (P1.M2.T2.S3)` section with the 5 sub-parts (scope/artifacts, compliance table, test evidence, nuances, conclusion), appended below §2.
- (b) The recorded findings match the live re-verification: all 5 item properties (a)-(e) are **compliant** (each with `daemon.py`/`recorder_host.py` file:line).
- (c) `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q -k 'unload or teardown or shutdown or killpg or terminate or bounded'` → all pass (record the count; verified baseline: **42 passed, 177 deselected**).
- (d) **No source or test files are modified** (because no defect exists — the teardown is PRD §4.2bis + §8-compliant per audit). If — and only if — the re-verification surfaces a REAL defect, fix it and record the fix; otherwise record "none — compliant per audit."
- (e) `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_lifecycle.md` (appended) — no `voice_typing/*`, no `tests/*`, no `PRD.md`/`tasks.json`/`prd_snapshot.md` change.

## User Persona

**Target User**: the maintainer (human or AI agent) who needs to trust that (i) `recorder.shutdown()`'s ~90s wedge can NEVER recur on `quit` / idle-unload / SIGTERM (the §8 risk row + the §4.2bis idle-unload PREREQUISITE), (ii) the idle-unload watchdog tears the recorder down under the SAME single-flight lock as load so a racing arm waits (then loads fresh) instead of seeing a half-torn-down host, and (iii) `request_shutdown` kills the child group so a run() loop blocked in `host.text()` unblocks for a prompt SIGTERM exit (the BUG-1 fix). Also the downstream P1.M5.T5 acceptance-criteria cross-check (which maps acceptance #9 — "the recorder unloads (~0 VRAM) and a later arm reloads it; the teardown is bounded (completes in seconds, no 90s hang)" — to this audit's evidence).

**Use Case**: A future change to the teardown path (a new `host.stop` budget, the idle-unload threshold, the SIGTERM coordination, the killpg group targeting). The audit + the 42 teardown tests are the reference that proves the change keeps (or breaks) the bounded-teardown contract.

**Pain Points Addressed**: Closes the "is teardown REALLY bounded, REALLY single-flight-with-load, and REALLY unblocking the SIGTERM path?" question with recorded, re-runnable evidence — not an assumption. The two single-flight layers (daemon `_lock` + `RecorderHost._stop_lock`) and the detached-graceful-cmd design are certified, so a maintainer doesn't "simplify" them back into the 90s wedge.

## Why

- **The 90s wedge was the worst failure mode for a 24/7 systemd service.** RealtimeSTT's `recorder.shutdown()` hangs ~90s on every `quit` (journal: `run() loop exiting` → 90s → systemd `SIGKILL` / `Failed with result 'timeout'`). Without a bounded teardown, idle-unload would re-trigger that hang every 30 min AND block any re-arm racing it under the single-flight lock. The audit certifies the wedge is SUPERSEDED (killpg after a 5s join, never waiting on RealtimeSTT's unbounded thread joins) — the §8 risk row + the §4.2bis idle-unload prerequisite. (PRD §4.2bis "Hard requirement — bounded teardown"; §8 risk row.)
- **Idle-unload (acceptance #9) is gated on this.** The PRD explicitly makes bounded teardown a PREREQUISITE for idle-unload. This audit certifies the prerequisite is met, so acceptance #9 ("teardown is bounded — completes in seconds, no 90s hang") has recorded evidence.
- **The SIGTERM path (BUG-1) is a known historical hang.** While listening, `run()` is blocked in `host.text()` whose wait-loop only returns on a "final" event OR child death; the child's aborted `recorder.text()` doesn't always fire a final → the loop stranded → SIGKILL after `TimeoutStopSec`. The BUG-1 fix (`request_shutdown` → `_bounded_shutdown` → kill the child group) guarantees `host.text()` returns within ~0.5s. The audit certifies the fix (git `84f03e8` + e2e regression `4526870`).
- **Scope discipline.** This subtask owns the teardown TIMING/ORCHESTRATION ONLY: the daemon-side single-flight lock around teardown, the bounded budget, the idle-unload watchdog, the SIGTERM coordination. The lazy-load STATE MACHINE is §1 (S1); the recorder-host IPC MECHANISM (incl. `stop`/`_terminate_group`/`killpg`/`setsid`) is §2 (S2) — §3 REFERENCES §2's stop@272-329 + killpg@407 and certifies the daemon-side orchestration that calls them. Phase lifecycle is P1.M2.T1; lite/mode-switch is M2.T3; status (VT-001/VT-002) is M3.

## What

Re-verify the bounded teardown against PRD §4.2bis + §8 by reading the ~7 code regions (`_STOP_JOIN_TIMEOUT_S` + `stop` + `_terminate_group` + child `os.setsid` in recorder_host.py; `_idle_unload_watchdog` + `_maybe_idle_unload` + `_unload_recorder` + `_unload_host` + `_bounded_shutdown` + `shutdown` + `request_shutdown` in daemon.py), re-running the 42-test teardown slice, and appending a `# §3 — Bounded Teardown (P1.M2.T2.S3)` section to `architecture/gap_lifecycle.md` in the `gap_*.md` §N-append format (mirror this file's own §2 @L201 + `gap_daemon_loop.md` §2 @L156). The audit is expected to confirm full compliance (no defects → no code changes). The report's compliance table maps each of the 5 item properties (a)-(e) to PRD §4.2bis/§8 expected behavior vs the code's actual behavior (file:line).

### Success Criteria

- [ ] `architecture/gap_lifecycle.md` contains the `# §3 — Bounded Teardown (P1.M2.T2.S3)` section (appended below §2).
- [ ] Compliance table covers (a) stop() join(5s)+killpg, (b) `_unload_host` same single-flight lock as load, (c) idle-unload watchdog after `auto_unload_idle_seconds`, (d) bounded (never 90s), (e) `request_shutdown` kills child group to unblock text() (BUG-1) — each COMPLIANT with file:line.
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q -k 'unload or teardown or shutdown or killpg or terminate or bounded'` → recorded pass count (baseline 42 passed).
- [ ] No source/test files modified (`git status --short` == the gap_lifecycle.md report only).
- [ ] Conclusion ties the verdict to PRD §4.2bis (resolved paragraph: daemon killpg's after 5s join) + §8 risk row + acceptance #9.

## All Needed Context

### Context Completeness Check

_Pass._ The audit is **already performed** by this PRP's author (research note §2: every property mapped to `daemon.py`/`recorder_host.py` file:line with the COMPLIANT verdict + the 42-test evidence). A developer new to this repo can re-verify from the research note + the cited code regions: the exact line ranges (`_STOP_JOIN_TIMEOUT_S=5.0`@87, `stop`@272-329, `_terminate_group`@394-413, child `setsid`@446 in recorder_host.py; `_idle_unload_watchdog`@1160, `_maybe_idle_unload`@1172, `_unload_recorder`@1197, `_unload_host`@1204, `_bounded_shutdown`@1620, `shutdown`@1647, `request_shutdown`@1454 in daemon.py), the grep commands to re-locate them, the test command, and the `gap_*.md` §3-append format (sibling §2 @L201 + `gap_daemon_loop.md` §2 @L156). The non-defect nuances (two single-flight layers; `_bounded_shutdown`→`host.stop` routing; detached graceful cmd; abort-before-join; lock-free pre-check; abort-outside-`_lock`; ~9s budget math) are documented so they are not mistaken for gaps.

### Documentation & References

```yaml
# MUST READ — the pre-verified audit findings (file:line + COMPLIANT verdict + test evidence)
- docfile: plan/006_862ee9d6ef41/P1M2T2S3/research/bounded_teardown_audit.md
  why: "§0 scope (DISJOINT from §1 states / §2 IPC — §3 owns teardown TIMING/orchestration). §1 the ~7
        regions under audit (recorder_host.py _STOP_JOIN_TIMEOUT_S@87/stop@272/_terminate_group@394/setsid@446;
        daemon.py _idle_unload_watchdog@1160/_maybe_idle_unload@1172/_unload_recorder@1197/_unload_host@1204/
        _bounded_shutdown@1620/shutdown@1647/request_shutdown@1454). §2 ★ THE 5-PROPERTY VERDICT (file:line per
        property, all COMPLIANT). §3 TEST EVIDENCE (42 passed). §4 NON-DEFECT NUANCES (7: two single-flight layers;
        _bounded_shutdown->host.stop routing; detached graceful-cmd; abort-before-join; lock-free pre-check;
        abort-outside-_lock; ~9s budget math). §5 verdict + acceptance #9 linkage. §6 the append convention."
  section: "ALL load-bearing. §2 (findings w/ file:line), §3 (test count), §4 (nuances) are the core to transcribe."

# MUST READ — the PRD being audited against (the contract)
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md   # (or PRD.md §4.2bis + §8)
  why: "§4.2bis 'Hard requirement — bounded teardown' + the RESOLVED paragraph ('the daemon killpg's the child
        group after a 5s join, so VRAM is force-released regardless of recorder.shutdown()'s behavior') is the
        authoritative spec. §8 risk row 'recorder.shutdown() hangs ~90s' prescribes the mitigation (hard timeout
        + force-cleanup). §7 acceptance #9 ('the teardown is bounded — completes in seconds, no 90s hang') is
        what this audit certifies."
  critical: "Audit against §4.2bis's resolved-paragraph WORDING (killpg after 5s join) + §8's risk row. The
             verified code facts (research §2) confirm the implementation matches — so the report states
             COMPLIANT (with the two-layer single-flight + detached-cmd documented as nuances)."

# MUST READ — the files under audit (the ~7 teardown regions)
- file: voice_typing/recorder_host.py
  why: "The killpg teardown PRIMITIVE. _STOP_JOIN_TIMEOUT_S=5.0 (L87, the join budget). stop(timeout=…)(L272)
        SINGLE-FLIGHT under _stop_lock (L297): abort_event.set()@300-302 + detached 'shutdown' cmd thread@311-316
        + proc.join(timeout)@318 + (if alive) _terminate_group()@323 + join(2.0)@325 + _dead=True@327 + _proc=None@328.
        _terminate_group (L394): pgid=os.getpgid(pid)@406 + os.killpg(pgid,SIGKILL)@407 (best-effort@409). child
        os.setsid()@446 (own group leader so killpg reaches grandchildren)."
  critical: "READ-ONLY audit. Do NOT edit recorder_host.py (no defect exists). §2 already certified the IPC-level
             mechanism; §3 certifies the BUDGET + how the daemon calls it. Re-locate with grep if line numbers drift."
- file: voice_typing/daemon.py
  why: "The teardown ORCHESTRATION (§3's core). _idle_unload_watchdog (L1160, ticks _shutdown.wait(1.0)@1168 ->
        _maybe_idle_unload@1170). _maybe_idle_unload (L1172, lock-free pre-check@1181-1187 -> _unload_recorder@1188).
        _unload_recorder (L1197 alias -> _unload_host@1201). _unload_host (L1204, with self._lock@1223 == _load_host@714,
        full re-check@1224-1231, _bounded_shutdown(5.0)@1236, reset@1240-1246). _bounded_shutdown (L1620 -> host.stop@1634,
        None no-op@1632, best-effort@1635). shutdown (L1647, idempotent + _shutdown_done/_teardown_done SIGTERM coord).
        request_shutdown (L1454, BUG-1 fix: _shutdown.set@1486 -> _safe_abort@1505 -> _bounded_shutdown@1510 -> 
        _teardown_done.set@1514, claims _shutdown_done@1498-1503)."
  critical: "READ-ONLY. Do NOT edit daemon.py. These methods ARE the teardown contract §3 certifies."

# MUST READ — the append-format template (how S2 appended §2 to THIS file + how P1.M2.T1.S2 appended §2)
- file: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
  why: "This file's §2 (heading @L201, concl @tail) is the EXACT append template for §3 — same Scope/Audited-
        artifacts/Bottom-line/§N.1 Method/§N.2 compliance-table/§N.3 test-evidence/§N.4 nuances/§N.5 Conclusion
        structure. §2's conclusion already says 'the bounded teardown TIMING … is S3' — §3 delivers it. APPEND §3
        BELOW §2."
  critical: "APPEND a '# §3 — Bounded Teardown (P1.M2.T2.S3)' section. Do NOT create a standalone file (item OUTPUT
             is 'Append to gap_lifecycle.md'). §1/§2 already exist (L1/L201) — append §3 at EOF."
- file: plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md
  why: "L156+ is the canonical §N-append precedent (P1.M2.T1.S2 appended §2 drain below §1 main-loop). Mirror its
        self-contained-report-under-a-§N-heading shape."
  critical: "Background format reference. Do NOT edit it."

# MUST READ — the sibling task contracts (§1/§2 already in the file; DISJOINT content)
- docfile: plan/006_862ee9d6ef41/P1M2T2S1/PRP.md
  why: "S1 created §1 (lazy-load STATE MACHINE: unloaded/loading/loaded + single-flight lock @714). §3's property
        (b) _unload_host-uses-the-same-lock-as-load cites S1's _load_host@714/_lock@591. DISJOINT: §1=states; §3=teardown."
  critical: "Do NOT re-audit the lazy-load states (S1 owns §1). Reference _load_host@714 for the shared-lock point only."
- docfile: plan/006_862ee9d6ef41/P1M2T2S2/PRP.md
  why: "S2 created §2 (recorder-host IPC MECHANISM: stop@272-329 + _terminate_group@394-413 + killpg@407 + setsid@446
        at the IPC level). §3 certifies the daemon-side ORCHESTRATION/TIMING that CALLS them (_unload_host/_bounded_
        shutdown/request_shutdown) — §3 REFERENCES §2's mechanism. DISJOINT: §2=IPC vocabulary; §3=teardown timing."
  critical: "Do NOT re-audit the IPC vocabulary (S2 owns §2). §2's stop/killpg findings are the mechanism; §3 owns the
             daemon orchestration + bounded budget + idle-unload watchdog + BUG-1. Cross-reference, don't duplicate."
```

### Current Codebase tree (relevant slice — the 1 report file this task appends to)

```bash
/home/dustin/projects/voice-typing/
└── plan/006_862ee9d6ef41/architecture/
    └── gap_lifecycle.md      # WRITE: append '# §3 — Bounded Teardown (P1.M2.T2.S3)' below §2 (file has §1@L1 + §2@L201).
# voice_typing/daemon.py + recorder_host.py — READ-ONLY (the ~7 audited regions). tests/test_*.py — READ-ONLY (re-run, do not edit).
# gap_daemon_loop.md (§1 main-loop + §2 drain), gap_config.md, etc. — existing sibling reports (do not touch).
```

### Desired Codebase tree (unchanged structure — one report section appended)

```bash
# Same tree. One file gains a section:
#   plan/006_862ee9d6ef41/architecture/gap_lifecycle.md += '# §3 — Bounded Teardown (P1.M2.T2.S3)' report section (appended at EOF).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS AN AUDIT, NOT IMPLEMENTATION. The deliverable is the §3 section of gap_lifecycle.md (a
#   report). Do NOT edit voice_typing/daemon.py / recorder_host.py or any test unless the re-verification surfaces
#   a REAL defect — none is expected (the teardown is PRD §4.2bis + §8-compliant per the pre-verified audit). If
#   you find no defect, record "none — compliant per audit." (Research §5.)
# CRITICAL #2 — USE TIMEOUTS (AGENTS.md Rule 1). The repo is a foreground daemon with hang vectors. Wrap the pytest
#   run: `timeout 300 .venv/bin/python -m pytest ...` (inner) + the bash tool timeout (outer). The teardown slice is
#   mocked-CUDA (no model load) so it is fast (~2s), but the timeout is mandatory. NEVER run the daemon in the
#   foreground; NEVER run untimed voicectl/pytest.
# CRITICAL #3 — RECORD file:line EVIDENCE, not assertions. Each compliance-table row must cite the daemon.py /
#   recorder_host.py line(s) that satisfy the PRD clause (re-locate with grep if line numbers drift). The pre-verified
#   lines: _STOP_JOIN_TIMEOUT_S=5.0@87, stop@272-329 (join@318, _terminate_group@323, join(2)@325), _terminate_group@394-413
#   (getpgid@406, killpg@407), child setsid@446; daemon _idle_unload_watchdog@1160, _maybe_idle_unload@1172, _unload_recorder
#   @1197, _unload_host@1204 (with self._lock@1223 == _load_host@714, re-check@1224-1231, _bounded_shutdown@1236),
#   _bounded_shutdown@1620 (->host.stop@1634), shutdown@1647, request_shutdown@1454 (BUG-1: _safe_abort@1505 + 
#   _bounded_shutdown@1510). (Research §1/§2.)
# CRITICAL #4 — DO NOT MISTAKE NUANCES FOR DEFECTS. (i) TWO single-flight layers (daemon _lock@591 for arm-vs-teardown;
#   RecorderHost._stop_lock for concurrent stop() on the SIGTERM path) — both intentional. (ii) _unload_host calls
#   _bounded_shutdown(timeout=5.0)@1236, NOT host.stop() directly — _bounded_shutdown@1620 routes to host.stop@1634
#   (pinned by test_unload_routes_through_bounded_shutdown_so_arm_wait_is_bounded). (iii) The graceful 'shutdown' cmd
#   is sent on a DETACHED thread@311-316 and NEVER waited on (the child's loop blocks in text(); a queue.put could
#   wedge) — the join+killpg is the real teardown. (iv) abort_event.set()@300-302 is called BEFORE the join (cooperative
#   unblock). (v) the idle-unload pre-check is LOCK-FREE@1183-1187 (_unload_host re-checks under _lock). (vi) request_
#   shutdown runs abort+_bounded_shutdown OUTSIDE _lock@1505/1510 (only the _shutdown_done claim is under _lock). 
#   (vii) the budget: join(5)+killpg+join(2)=~7s/call + ControlServer join(2)=~2s, single-flight => <=~9s < TimeoutStopSec=15.
#   (Research §4.)
# CRITICAL #5 — APPEND §3, DO NOT CREATE A STANDALONE FILE. The item OUTPUT is 'Append to gap_lifecycle.md'. §1 (S1)
#   + §2 (S2) already exist in the file (L1/L201); APPEND §3 below §2 at EOF. Mirror the file's own §2 @L201 shape.
# CRITICAL #6 — SCOPE = teardown TIMING/orchestration. Do NOT re-audit the lazy-load states (§1) or the IPC vocabulary
#   (§2). §3 owns: the daemon-side single-flight lock around teardown, the bounded budget, the idle-unload watchdog,
#   the SIGTERM coordination (request_shutdown/shutdown). REFERENCE §2's stop@272-329 + killpg@407 (the mechanism §3
#   certifies the timing of); cross-reference, don't duplicate.
# CRITICAL #7 — FULL TOOL PATHS (zsh aliases python/pip). .venv/bin/python -m pytest ... (never bare python/pytest).
#   The architecture/ + plan/ paths are relative to the repo root (/home/dustin/projects/voice-typing).
```

## Implementation Blueprint

### Data models and structure

None (audit/report task). The "data" is the verified teardown findings (research §2), transcribed into the `gap_*.md` §3-append format. No code, no data models.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RE-VERIFY the ~7 teardown regions against PRD §4.2bis + §8 (read-only)
  - READ recorder_host.py: _STOP_JOIN_TIMEOUT_S=5.0@87; stop@272-329 (abort_event.set@300-302, detached shutdown-cmd
    thread@311-316, proc.join(timeout)@318, _terminate_group@323, join(2.0)@325, _dead=True@327, _proc=None@328);
    _terminate_group@394-413 (getpgid@406, killpg@407); child os.setsid()@446.
  - READ daemon.py: _idle_unload_watchdog@1160 (ticks _shutdown.wait(1.0)@1168); _maybe_idle_unload@1172 (lock-free
    pre-check@1181-1187 -> _unload_recorder@1188); _unload_recorder@1197 (-> _unload_host@1201); _unload_host@1204
    (with self._lock@1223 == _load_host@714, full re-check@1224-1231, _bounded_shutdown(5.0)@1236, reset@1240-1246);
    _bounded_shutdown@1620 (->host.stop@1634, None no-op@1632); shutdown@1647 (_shutdown_done/_teardown_done coord);
    request_shutdown@1454 (_shutdown.set@1486, _safe_abort@1505, _bounded_shutdown@1510, _teardown_done.set@1514).
  - RE-CONFIRM each of (a)-(e) matches PRD §4.2bis resolved-paragraph + §8 risk row.
  - RE-LOCATE with grep if line numbers drifted: `grep -nE '_STOP_JOIN_TIMEOUT_S|def stop|def _terminate_group|os.killpg|os.setsid|def _idle_unload_watchdog|def _maybe_idle_unload|def _unload_recorder|def _unload_host|def _bounded_shutdown|def shutdown|def request_shutdown|host.stop|_teardown_done|_shutdown_done|self._lock' voice_typing/recorder_host.py voice_typing/daemon.py`.
  - FINDINGS are pre-verified COMPLIANT (research §2) — re-confirm; if a real defect appears, record + fix it.

Task 2: RE-RUN the teardown test slice (the audit's test evidence)
  - RUN: `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q -k 'unload or teardown or shutdown or killpg or terminate or bounded'`. Record the pass count (baseline 42 passed, 177 deselected).
  - Cite the key evidence tests per property (research §3): killpg _terminate_group; stop() single-flight; _unload_host
    single-flight + racing-arm-aborts-unload; the idle-unload watchdog firing; request_shutdown/shutdown SIGTERM-race
    (concurrent teardown shares ONE bounded _bounded_shutdown); test_unload_routes_through_bounded_shutdown_so_arm_wait_
    is_bounded; the BUG-1 SIGTERM e2e regression (git 4526870).

Task 3: APPEND '# §3 — Bounded Teardown (P1.M2.T2.S3)' to gap_lifecycle.md (the deliverable)
  - FORMAT: mirror this file's §2 @L201 (and gap_daemon_loop.md §2 @L156) — a self-contained report under a '# §3 — …'
    heading with Scope/Audited-artifacts/Bottom-line/§3.1 Method/§3.2 compliance-table/§3.3 test-evidence/§3.4 nuances/
    §3.5 Conclusion.
  - CONTENT: the pre-verified findings (research §2) transcribed — each property COMPLIANT with file:line + the nuances
    (research §4) so they aren't mistaken for defects.
  - VERDICT: ✅ COMPLIANT (no defects, no source changes). Tie to PRD §4.2bis resolved-paragraph (killpg after 5s join) +
    §8 risk row + acceptance #9 (bounded teardown = idle-unload prerequisite).
  - APPEND at EOF (below §2). Include a line noting §1=states (S1) + §2=IPC (S2); §3=teardown timing/orchestration, and
    that §3 references §2's stop@272-329 + killpg@407 (the mechanism §3 certifies the timing of).

Task 4: SCOPE GUARD
  - `git status --short` shows ONLY gap_lifecycle.md (appended). No voice_typing/*, no tests/*, no PRD/tasks/snapshot change.
```

### Implementation Patterns & Key Details

```markdown
<!-- gap_lifecycle.md §3 skeleton (mirror this file's §2 @L201 + gap_daemon_loop.md §2 @L156): -->
# §3 — Bounded Teardown (P1.M2.T2.S3) vs PRD §4.2bis Idle-unload (resolved) + §8 risk row
**Date:** <re-verify date>  **Scope:** Audit the teardown TIMING/orchestration (daemon-side single-flight lock,
bounded join(5s)+killpg budget, idle-unload watchdog, SIGTERM BUG-1 coordination) vs PRD §4.2bis on (a)-(e). §1
above is P1.M2.T2.S1's lazy-load states; §2 is P1.M2.T2.S2's recorder-host IPC (stop@272-329 + killpg@407 — the
MECHANISM this §3 certifies the TIMING of); this §3 owns the daemon orchestration that CALLS them.
**Audited artifacts (read-only):** recorder_host.py <file:line> (stop/_terminate_group/_STOP_JOIN_TIMEOUT_S/setsid);
daemon.py <file:line> (_idle_unload_watchdog/_maybe_idle_unload/_unload_recorder/_unload_host/_bounded_shutdown/
shutdown/request_shutdown); tests/test_daemon.py + test_recorder_host.py (-k slice).
**Bottom line:** ✅ All 5 properties COMPLIANT (file:line below). -k slice = 42 passed. Teardown bounded (~7s/call,
~9s total single-flight < TimeoutStopSec=15) — CANNOT reproduce the ~90s wedge. No source modified.
## §3.1 Method  (grep commands; re-verify reads; re-run command)
## §3.2 The 5 teardown properties — per-point compliance table
   (| # | item property | PRD §4.2bis/§8 expected | code actual (file:line) | test | verdict ✅ |)
   (a) stop() join(5s)+killpg   (b) _unload_host same single-flight lock as load   (c) idle-unload watchdog after
       auto_unload_idle_seconds   (d) bounded (never 90s)   (e) request_shutdown kills child group -> unblocks text() (BUG-1)
## §3.3 Test evidence  (the -k command + count + key test names per property; git 84f03e8 BUG-1 + 4526870 e2e)
## §3.4 Non-defect nuances  (two single-flight layers; _bounded_shutdown->host.stop routing; detached graceful cmd;
       abort-before-join; lock-free pre-check; abort-outside-_lock; ~9s budget math)
## §3.5 Conclusion  (COMPLIANT; certifies the §4.2bis resolved-paragraph killpg-after-5s-join + the §8 risk-row
       mitigation + acceptance #9's "bounded, no 90s hang" prerequisite)
```

### Integration Points

```yaml
REPORT (the deliverable):
  - append: "plan/006_862ee9d6ef41/architecture/gap_lifecycle.md += '# §3 — Bounded Teardown (P1.M2.T2.S3)' (below §2)"
  - verdict: "✅ COMPLIANT — all 5 properties (a-e) pass (daemon.py + recorder_host.py file:line)"
  - ties-to: "PRD §4.2bis resolved-paragraph (daemon killpg's after 5s join) + §8 risk row + acceptance #9 (bounded)"
CONSUMERS:
  - P1.M5.T5 (acceptance cross-check): "maps acceptance #9 ('teardown bounded, no 90s hang') to this §3's evidence"
  - §2 (IPC): "this §3 references §2's stop@272-329 + killpg@407 (the mechanism §3 certifies the timing of)"
  - future maintainers: "the reference for any teardown-path change (host.stop budget, idle-unload threshold, SIGTERM coord, killpg targeting)"
SCOPE GUARD:
  - git status: "ONLY architecture/gap_lifecycle.md (appended). No voice_typing/*, no tests/*."
```

## Validation Loop

### Level 1: Re-verification (read the code — read-only)

```bash
cd /home/dustin/projects/voice-typing
# Re-locate the ~7 teardown regions (line numbers may drift — re-grep):
grep -nE '_STOP_JOIN_TIMEOUT_S|def stop\b|def _terminate_group|os\.killpg|os\.getpgid|os\.setsid|def _idle_unload_watchdog|def _maybe_idle_unload|def _unload_recorder|def _unload_host|def _bounded_shutdown|def shutdown\b|def request_shutdown|host\.stop\(|_teardown_done|_shutdown_done' voice_typing/recorder_host.py voice_typing/daemon.py
# Read each region (recorder_host stop@272-329, _terminate_group@394-413, _STOP_JOIN_TIMEOUT_S@87, child setsid@446;
# daemon _idle_unload_watchdog@1160, _maybe_idle_unload@1172, _unload_recorder@1197, _unload_host@1204,
# _bounded_shutdown@1620, shutdown@1647, request_shutdown@1454) and confirm (a)-(e) match PRD §4.2bis + §8.
# Expected: COMPLIANT (research §2).
```

### Level 2: Test evidence (re-run the teardown slice — the audit's evidence)

```bash
cd /home/dustin/projects/voice-typing
# AGENTS.md Rule 1: inner timeout (mandatory) + outer bash timeout. Mocked CUDA -> fast, but timeout is non-negotiable.
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q -k 'unload or teardown or shutdown or killpg or terminate or bounded'
# Expected: 42 passed, 177 deselected (record the actual count in the report).
```

### Level 3: Report well-formedness

```bash
cd /home/dustin/projects/voice-typing
# Confirm gap_lifecycle.md has the §3 section + cites file:line + records the verdict:
grep -nE '§3|Bounded Teardown|Bottom line|42 passed|COMPLIANT|killpg|join\(5|_STOP_JOIN_TIMEOUT_S|request_shutdown|BUG-1|TimeoutStopSec|_unload_host' plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
# Expected: the §3 heading, the ✅ bottom line, the compliance table (with daemon.py/recorder_host.py:line), the test
# count, the nuances (two single-flight layers / detached cmd / abort-before-join / ~9s budget), all present.
```

### Level 4: Scope guard (no unintended edits)

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: ONLY plan/006_862ee9d6ef41/architecture/gap_lifecycle.md (appended). No voice_typing/*, no tests/*,
# no PRD/tasks/snapshot.
```

## Final Validation Checklist

### Technical Validation
- [ ] Re-verified the ~7 teardown regions (recorder_host stop/_terminate_group/_STOP_JOIN_TIMEOUT_S/setsid; daemon _idle_unload_watchdog/_maybe_idle_unload/_unload_recorder/_unload_host/_bounded_shutdown/shutdown/request_shutdown) — all COMPLIANT.
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q -k 'unload or teardown or shutdown or killpg or terminate or bounded'` → recorded pass count (baseline 42).
- [ ] `gap_lifecycle.md` contains the `# §3 — Bounded Teardown (P1.M2.T2.S3)` section (appended below §2).

### Feature (Audit) Validation
- [ ] Compliance table covers (a) stop join(5s)+killpg, (b) `_unload_host` same single-flight lock as load, (c) idle-unload watchdog after `auto_unload_idle_seconds`, (d) bounded (never 90s), (e) `request_shutdown` kills child group → unblocks text() (BUG-1) — each COMPLIANT with file:line.
- [ ] Verdict ✅ COMPLIANT; conclusion ties to PRD §4.2bis (resolved paragraph: killpg after 5s join) + §8 risk row + acceptance #9.
- [ ] If a real defect was found, it is fixed + recorded; otherwise "none — compliant per audit."

### Code Quality Validation
- [ ] §3 section mirrors the `gap_*.md` §N-append format (consistent with this file's §2 @L201 + gap_daemon_loop.md §2 @L156).
- [ ] Non-defect nuances recorded (two single-flight layers; `_bounded_shutdown`→`host.stop` routing; detached graceful cmd; abort-before-join; lock-free pre-check; abort-outside-`_lock`; ~9s budget math) so they aren't mistaken for gaps.
- [ ] Only `architecture/gap_lifecycle.md` written (`git status --short`).

### Documentation & Deployment
- [ ] Report is self-contained (scope, method, evidence, verdict) — a future maintainer can re-run the audit from it.
- [ ] Adjacent concerns correctly deferred (lazy-load states → §1; IPC mechanism → §2; phase lifecycle → P1.M2.T1; lite → M2.T3; status → M3).

---

## Anti-Patterns to Avoid

- ❌ Don't edit `voice_typing/daemon.py` / `recorder_host.py` or any test — this is an AUDIT; the teardown is COMPLIANT (no defect). Edit ONLY if re-verification surfaces a real defect (Critical #1).
- ❌ Don't run pytest without `timeout 300` (inner) + the bash-tool timeout — AGENTS.md Rule 1 (the repo has hang vectors) (Critical #2).
- ❌ Don't assert compliance without file:line evidence — every table row must cite the daemon.py/recorder_host.py line(s) (Critical #3).
- ❌ Don't mistake the nuances for defects: two single-flight layers (daemon `_lock` + `RecorderHost._stop_lock`); `_unload_host`→`_bounded_shutdown`→`host.stop` routing; the detached graceful-cmd thread; abort-before-join; lock-free pre-check; abort-outside-`_lock`; the ~9s budget (Critical #4).
- ❌ Don't create a NEW standalone file — APPEND §3 to `gap_lifecycle.md` (the item OUTPUT). §1/§2 already exist; append §3 at EOF (Critical #5).
- ❌ Don't re-audit the lazy-load states (§1) or the IPC vocabulary (§2) — §3 owns teardown TIMING/orchestration and REFERENCES §2's stop/killpg mechanism; cross-reference, don't duplicate (Critical #6).
- ❌ Don't "simplify" the two single-flight layers, the detached graceful-cmd thread, or the abort-before-join — all prevent the 90s wedge / double-teardown / SIGTERM hang; record them as load-bearing.
- ❌ Don't use bare `python`/`pytest` (zsh aliases) — `.venv/bin/python -m pytest` (Critical #7).

---

## Confidence Score

**10/10** — one-pass success likelihood. This is a read-only audit whose findings are **pre-verified** (research note §2: every property mapped to `daemon.py`/`recorder_host.py` file:line with the COMPLIANT verdict) and whose test evidence is **re-ran live** (the contract's `-k` slice = 42 passed, 177 deselected in 2.12s). The 5 properties are a direct reading of the in-tree code (killpg after a 5s join in `stop`; `_unload_host`'s `with self._lock` == `_load_host`'s; the `_idle_unload_watchdog`→`_maybe_idle_unload`→`_unload_host` chain; the ~7s/call budget documented in `_bounded_shutdown`'s docstring; the BUG-1 fix in `request_shutdown` + git `84f03e8`). The deliverable is a report section in an established format (sibling §2 @L201 + `gap_daemon_loop.md` §2 @L156), appended to a file that already has §1/§2. Residual risk is only line-number drift, which the grep re-location step (Level 1) catches immediately.