# PRP — P1.M2.T2.S2: Audit recorder-host IPC — queues, proxy, event stream (PRD §4.2bis)

## Goal

**Feature Goal**: Produce the authoritative **recorder-host IPC audit** as a new **§2 section appended to `plan/006_862ee9d6ef41/architecture/gap_lifecycle.md`**, cross-checking `voice_typing/recorder_host.py`'s IPC mechanism — `RecorderHost.spawn`/`set_microphone`/`abort`/`text`/`stop` (181-329), `_worker_main` (421-575), `_read_loop` (331-353), `_dispatch` (354-392), `_RelayFeedback` (718-750), `_RelayLatency` (760-774) — against **PRD §4.2bis's recorder-host subprocess model** on the 6 item properties (a)-(f). This is a **verification/audit** subtask (round `006_862ee9d6ef41`): the deliverable is the report section; **code changes happen ONLY if a real defect is found — none is expected; this PRP's author has already performed the audit and the IPC is PRD §4.2bis-COMPLIANT.**

> **VERIFIED VERDICT (this PRP's research): the recorder-host IPC is PRD §4.2bis COMPLIANT — no fix needed.** All 6 properties (a)-(f) pass (recorder_host.py file:line in the research note); the contract's `-k 'host or relay or queue or ipc or worker'` slice = **30 passed, 189 deselected in 1.65s**. The actual IPC vocabulary is richer/safer than the item's shorthand (documented nuances, NOT defects).

**Deliverable** (ONE report section; NO source edits, NO test edits): `plan/006_862ee9d6ef41/architecture/gap_lifecycle.md` — a **`# §2 — Recorder-Host IPC (P1.M2.T2.S2)` section APPENDED** to the file S1 (P1.M2.T2.S1, parallel) created with §1 (lazy-load). The section mirrors the `gap_*.md` format (sibling: `gap_daemon_loop.md` §2 = the P1.M2.T1.S2 drain append at L156+, the exact append template) and contains: (1) scope + audited artifacts (file:line); (2) a per-property compliance table (PRD §4.2bis expected vs code actual, recorder_host.py file:line) for (a)-(f); (3) the test pass/fail count for the contract's run target; (4) the non-defect nuances (abort-via-Event; richer evt_q vocabulary; intentional no-op relays; VT-007 sentinel; vad is_listening gate); (5) a conclusion tying the verdict to PRD §4.2bis's "arm/disarm/text/abort/shutdown proxied; partials/finals/VAD streamed back; setsid+killpg for VRAM release". **This PRP's author has already performed the audit** (findings in the research note) — the implementing agent re-verifies, re-runs the tests, and transcribes the §2 section.

> **Append-vs-create (parallel-safe):** S1 and S2 run in parallel and both target `gap_lifecycle.md`. S1 creates the file with §1 (lazy-load). S2 APPENDS §2 (IPC). If `gap_lifecycle.md` does NOT yet exist when S2 runs (S1 not landed), S2 CREATES it containing the §2 IPC section as its initial content (a self-contained report); S1's §1 is produced in parallel and merged/prepended. The `# §2` heading makes the two sections compose without conflict (exactly as P1.M2.T1.S2 appended §2 to the S1-created `gap_daemon_loop.md`).

**Success Definition**:
- (a) `architecture/gap_lifecycle.md` exists and contains a `# §2 — Recorder-Host IPC (P1.M2.T2.S2)` section with the 5 sub-parts (scope/artifacts, compliance table, test evidence, nuances, conclusion).
- (b) The recorded findings match the live re-verification: all 6 item properties (a)-(f) are **compliant** (each with recorder_host.py file:line).
- (c) `timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k 'host or relay or queue or ipc or worker'` → all pass (record the count; verified baseline: **30 passed, 189 deselected**).
- (d) **No source or test files are modified** (because no defect exists — the IPC is PRD §4.2bis-compliant per audit). If — and only if — the re-verification surfaces a REAL defect, fix it and record the fix; otherwise record "none — compliant per audit."
- (e) `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_lifecycle.md` (new or appended) — no `voice_typing/*`, no `tests/*`, no `PRD.md`/`tasks.json`/`prd_snapshot.md` change. (If S1 lands concurrently, `git status` may also show S1's work on the same file — that is expected and not a conflict.)

## User Persona

**Target User**: the maintainer (human or AI agent) who needs to trust that the recorder-host subprocess correctly proxies arm/disarm/text/abort/shutdown, streams partials/finals/VAD back to the daemon, isolates the process group for VRAM release, and never wedges the run() loop on abort — before relying on the IPC layer that the entire GPU-VRAM-reclamation model (PRD §4.2bis) depends on. Also the downstream P1.M5.T5 acceptance-criteria cross-check (which maps the lazy-load/IPC evidence to acceptance #6/#9).

**Use Case**: A future change to `recorder_host.py` (a new event, a relay method, the abort path, the killpg teardown). The audit + the 30 IPC tests are the reference that proves the change keeps (or breaks) the IPC contract.

**Pain Points Addressed**: Closes the "does the IPC REALLY proxy every command, stream every event, unblock on abort, and isolate the process group?" question with recorded, re-runnable evidence — not an assumption. The VT-007 abort-sentinel (the run()-loop-wedge fix) and the abort-via-Event design are certified, so a maintainer doesn't "simplify" them away.

## Why

- **The IPC layer is the §4.2bis foundation's spine.** Lazy load, idle-unload, and bounded teardown ALL depend on the recorder-host subprocess correctly proxying commands + streaming events + releasing VRAM via killpg. A broken IPC (a missed relay, a wedged text(), a killpg that misses grandchildren) silently breaks the entire VRAM model. The audit certifies the spine with file:line evidence.
- **The abort path is a known historical wedge.** recorder.text() blocks the child's command loop; abort must come via a SEPARATE mp.Event (not cmd_q); and `_run_text_and_emit_final` must GUARANTEE a final-sentinel on abort or the daemon's host.text() blocks forever. The audit certifies both the Event design and the VT-007 sentinel (4 dedicated tests) so the wedge can't regress.
- **The process-group isolation is the VRAM-release mechanism.** os.setsid() in the child + os.killpg in the daemon is the ONLY way to release the realtime-model CUDA context (the PRD §4.2bis rationale). The audit certifies both halves.
- **Scope discipline.** This subtask owns the IPC MECHANISM (queues, commands, events, relay, abort Event, VT-007 sentinel) ONLY. The lazy-load STATE MACHINE is S1 (§1); the bounded-teardown TIMING (join(5s)+killpg budget, idle-unload watchdog) is S3; phase lifecycle is P1.M2.T1; lite/mode-switch is M2.T3; status is M3. This audit notes those branches sit correctly relative to the IPC but defers their detail.

## What

Re-verify the recorder-host IPC against PRD §4.2bis by reading the 6 code regions (`spawn`, the command/event queue setup in `__init__`, `_worker_main` incl. `os.setsid` + the command loop + `_run_text_and_emit_final`, `_read_loop`, `_dispatch`, `_RelayFeedback`/`_RelayLatency`, `_terminate_group`), re-running the 30-test IPC slice, and appending a `# §2 — Recorder-Host IPC (P1.M2.T2.S2)` section to `architecture/gap_lifecycle.md` in the `gap_*.md` format (mirror `gap_daemon_loop.md` §2). The audit is expected to confirm full compliance (no defects → no code changes). The report's compliance table maps each of the 6 item properties (a)-(f) to PRD §4.2bis expected behavior vs the code's actual behavior (recorder_host.py file:line).

### Success Criteria

- [ ] `architecture/gap_lifecycle.md` contains the `# §2 — Recorder-Host IPC (P1.M2.T2.S2)` section (appended, or created-with-§2 if the file was absent).
- [ ] Compliance table covers (a) spawn→Process(_worker_main), (b) child os.setsid() + daemon killpg, (c) cmd_q commands (arm/disarm/text/shutdown + abort via Event + belt-and-suspenders abort cmd), (d) evt_q events (ready/error/final/partial/vad/speech/speech_end/gone), (e) text() puts text cmd + blocks on final evt, (f) _RelayFeedback/_RelayLatency relay — each COMPLIANT with recorder_host.py file:line.
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k 'host or relay or queue or ipc or worker'` → recorded pass count (baseline 30 passed).
- [ ] No source/test files modified (`git status --short` == the gap_lifecycle.md report only, modulo S1's concurrent work).
- [ ] Conclusion ties the verdict to PRD §4.2bis (proxied commands + streamed events + setsid/killpg VRAM release).

## All Needed Context

### Context Completeness Check

_Pass._ The audit is **already performed** by this PRP's author (research note §2: every property mapped to recorder_host.py file:line with the COMPLIANT verdict + the 30-test evidence). A developer new to this repo can re-verify from the research note + the cited code regions: the exact line ranges (spawn 181-228, __init__ queues 135-160, _worker_main 421-575 incl. setsid@446 + command loop@533-571 + _run_text_and_emit_final@630-677, _read_loop 331-353, _dispatch 354-392, _RelayFeedback 718-750, _RelayLatency 760-774, _terminate_group 394-413), the grep commands to re-locate them, the test command, and the `gap_*.md` §2-append format (sibling `gap_daemon_loop.md` L156+). The non-defect nuances (abort-via-Event, richer vocabulary, intentional no-op relays, VT-007 sentinel, vad gate) are documented so they are not mistaken for gaps.

### Documentation & References

```yaml
# MUST READ — the pre-verified audit findings (file:line + COMPLIANT verdict + test evidence)
- docfile: plan/006_862ee9d6ef41/P1M2T2S2/research/recorder_host_ipc_audit.md
  why: "§0 the IPC architecture (1 sentence). §1 the 2 queues + the Event (the primitives, L139-142). §2 THE
        FINDINGS: each of (a)-(f) verified COMPLIANT with exact recorder_host.py file:line (spawn@193-200,
        setsid@446 + killpg@407, cmd_q puts@233/261/309 + abort Event@146/246 + belt+suspenders abort@564,
        evt_q vocabulary@L23-31/_dispatch@354-392, text blocks@264-268 + final dispatch@369-377,
        _RelayFeedback@718-750 + _RelayLatency@750-774) + the test that proves it. §3 test evidence (30 passed).
        §4 NON-DEFECT NUANCES (abort-via-Event; richer vocabulary; intentional no-op relays; VT-007 sentinel;
        vad is_listening gate). §5 verdict COMPLIANT. §6 the append convention (§2 to gap_lifecycle.md)."
  section: "ALL load-bearing. §2 (findings w/ file:line), §3 (test count), §4 (nuances) are the core to transcribe."

# MUST READ — the PRD being audited against (the contract)
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md   # (or PRD.md §4.2bis)
  why: "§4.2bis 'Implementation note (recorder-host subprocess)' is the authoritative IPC spec: the daemon spawns
        a managed child; Arm/disarm/text/abort/shutdown are proxied over multiprocessing queues; partials/finals/
        VAD events stream back to a daemon reader thread; os.setsid in the child + os.killpg in the daemon release
        ALL VRAM. §7 acceptance #6 (un-loaded boot) + #9 (idle-unload -> reload) depend on this IPC working."
  critical: "Audit against §4.2bis's recorder-host-subprocess WORDING (proxied commands; streamed events; setsid
             + killpg). The verified code facts (research §2) confirm the implementation matches — so the report
             states COMPLIANT (with the richer-than-shorthand vocabulary documented as a nuance)."

# MUST READ — the file under audit (the 6 IPC regions)
- file: voice_typing/recorder_host.py
  why: "Module docstring (L1-60) documents the EXACT IPC PROTOCOL (cmd_queue/abort_event/event_queue vocabularies
        + the CALLBACK RELAY mapping). __init__ (L103-160): the 2 queues + the Event (L139-142). spawn (L181-228):
        Process(target=_worker_main) @193-200 + reader thread @203-205 + ready-wait @207-213. set_microphone
        (L230-235) @233; abort (L237-248) @246 (sets the Event); text (L250-271) @261 (puts text) + @264-268
        (blocks on _final_evt); stop (L272-329) @307-310 (shutdown best-effort) + @315 (join 5s) + @321
        (_terminate_group). _read_loop (L331-353); _dispatch (L354-392); _terminate_group (L394-413) @407 (killpg);
        _worker_main (L421-575) @446 (setsid) + @464-465 (relay stand-ins) + @517-531 (_abort_handler) + @533-571
        (command loop) + @564-565 (belt+suspenders abort); _run_text_and_emit_final (L630-677, the VT-007 sentinel);
        _RelayFeedback (L718-750); _RelayLatency (L760-774)."
  critical: "READ-ONLY audit. Do NOT edit recorder_host.py (no defect exists). Re-locate sites with grep if line
             numbers drift (the file is 774 lines)."

# MUST READ — the append-format template (how P1.M2.T1.S2 appended §2 to gap_daemon_loop.md)
- file: plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md
  why: "L156+ is the §2-append template: P1.M2.T1.S2 appended '# §2 — Graceful Drain (P1.M2.T1.S2): ...' BELOW
        §1 (which P1.M2.T1.S1 created). It has its own Scope/Audited-artifacts/Bottom-line/Method/compliance-
        table/test-evidence/nuances/conclusion — a SELF-CONTAINED report under a §2 heading. Mirror that structure
        for the IPC §2. The line 'appended to this report (§1 above is P1.M2.T1.S1's ... audit; this §2 owns ...)'
        is the exact convention to reuse."
  critical: "APPEND a '# §2 — Recorder-Host IPC (P1.M2.T2.S2)' section to gap_lifecycle.md. Do NOT create a NEW
             standalone file (the item OUTPUT is 'Append to gap_lifecycle.md'). If gap_lifecycle.md is absent
             (S1 parallel, not landed), create it WITH the §2 section as initial content."

# MUST READ — the parallel task contract (S1 creates §1 of the SAME file; DISJOINT content)
- docfile: plan/006_862ee9d6ef41/P1M2T2S1/PRP.md
  why: "S1 (P1.M2.T2.S1) creates gap_lifecycle.md with §1 (the lazy-load STATE MACHINE audit). S2 (THIS) appends
        §2 (the IPC audit). The two sections are DISJOINT content (states+single-flight vs queues+events+relay)
        under distinct headings — they compose without conflict. S1 explicitly DEFERS the IPC to 'S2'."
  critical: "Do NOT audit the lazy-load state machine here (S1 owns §1). Your §2 owns the IPC MECHANISM only. If
             you re-verify and find the file already has §1, append §2 below it; if absent, create with §2."
```

### Current Codebase tree (relevant slice — the 1 report file this task writes)

```bash
/home/dustin/projects/voice-typing/
└── plan/006_862ee9d6ef41/architecture/
    └── gap_lifecycle.md      # WRITE: append '# §2 — Recorder-Host IPC (P1.M2.T2.S2)' (or create-with-§2 if absent).
# voice_typing/recorder_host.py — READ-ONLY (the 6 audited regions). tests/test_recorder_host.py + test_daemon.py — READ-ONLY (re-run, do not edit).
# gap_daemon_loop.md (§1 main-loop + §2 drain), gap_config.md, gap_textproc.md, etc. — existing sibling reports (do not touch).
```

### Desired Codebase tree (unchanged structure — one report section appended)

```bash
# Same tree. One file gains a section:
#   plan/006_862ee9d6ef41/architecture/gap_lifecycle.md += '# §2 — Recorder-Host IPC (P1.M2.T2.S2)' report section.
# (If S1 hasn't created the file yet, this task creates it with the §2 section as its initial content.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS AN AUDIT, NOT IMPLEMENTATION. The deliverable is the §2 section of gap_lifecycle.md (a
#   report). Do NOT edit voice_typing/recorder_host.py or any test unless the re-verification surfaces a REAL
#   defect — none is expected (the IPC is PRD §4.2bis-compliant per the pre-verified audit). If you find no defect,
#   record "none — compliant per audit." (Research §5.)
# CRITICAL #2 — USE TIMEOUTS (AGENTS.md Rule 1). The repo is a foreground daemon with hang vectors. Wrap the pytest
#   run: `timeout 300 .venv/bin/python -m pytest ...` (inner) + the bash tool timeout (outer). test_recorder_host.py
#   + test_daemon.py are mocked-CUDA (no model load) so the slice is fast (~1.7s), but the timeout is mandatory.
#   NEVER run the daemon in the foreground; NEVER run untimed voicectl/pytest.
# CRITICAL #3 — RECORD file:line EVIDENCE, not assertions. Each compliance-table row must cite the recorder_host.py
#   line(s) that satisfy the PRD clause (re-locate with grep if line numbers drift). The pre-verified lines: spawn
#   Process@193-200, setsid@446, killpg@407, cmd_q puts@233/261/309, abort Event@146/246, _dispatch@354-392,
#   text-block@264-268, final-dispatch@369-377, _RelayFeedback@718-750, _RelayLatency@750-774. (Research §2.)
# CRITICAL #4 — DO NOT MISTAKE NUANCES FOR DEFECTS. (i) abort is a dedicated mp.Event (L146), NOT primarily a cmd_q
#   command — ("abort",{}) on cmd_q (L564) is belt-and-suspenders; the Event design is STRONGER. (ii) The evt_q
#   vocabulary is RICHER than the item's shorthand: "ready" = device+loaded; "vad"{phase} = vad_start+vad_stop;
#   plus extras "speech"/"speech_end"/"gone". (iii) _RelayFeedback.set_models_loaded/record_final/set_listening
#   are INTENTIONAL no-ops (daemon-owned transitions), not missing relays. (iv) _run_text_and_emit_final's VT-007
#   abort-sentinel (L630-677) GUARANTEES a ("final",{text:""}) on abort so host.text() can't wedge — do NOT
#   'simplify' it. (v) the "vad" dispatch is_listening gate (L380-388) is P1.M2.T1's phase-lifecycle concern.
#   (Research §4.)
# CRITICAL #5 — APPEND §2, DO NOT CREATE A STANDALONE FILE. The item OUTPUT is 'Append to gap_lifecycle.md'. S1
#   creates the file with §1 (lazy-load); S2 appends §2 (IPC). Mirror gap_daemon_loop.md's L156+ §2-append format.
#   If gap_lifecycle.md is absent when you run (S1 parallel), create it WITH the §2 section as initial content
#   (self-contained report); S1's §1 merges/prepends. (Research §6.)
# CRITICAL #6 — FULL TOOL PATHS (zsh aliases python/pip). .venv/bin/python -m pytest ... (never bare python/pytest).
#   The architecture/ + plan/ paths are relative to the repo root (/home/dustin/projects/voice-typing).
```

## Implementation Blueprint

### Data models and structure

None (audit/report task). The "data" is the verified IPC findings (research §2), transcribed into the `gap_*.md` §2-append format. No code, no data models.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RE-VERIFY the 6 IPC regions against PRD §4.2bis (read-only)
  - READ recorder_host.py: module docstring (L1-60, the IPC PROTOCOL); __init__ queues+Event (L135-160); spawn
    (L181-228); set_microphone (L230-235); abort (L237-248); text (L250-271); stop (L272-329); _read_loop
    (L331-353); _dispatch (L354-392); _terminate_group (L394-413); _worker_main (L421-575, incl. setsid@446 +
    relay stand-ins@464-465 + _abort_handler@517-531 + command loop@533-571); _run_text_and_emit_final (L630-677);
    _RelayFeedback (L718-750); _RelayLatency (L760-774). Re-confirm each of (a)-(f) matches PRD §4.2bis.
  - RE-LOCATE with grep if line numbers drifted: `grep -nE 'def spawn|def set_microphone|def abort|def text|
    def stop|def _read_loop|def _dispatch|def _terminate_group|def _worker_main|os.setsid|os.killpg|_cmd_q.put|
    _abort_event|_RelayFeedback|_RelayLatency|def _run_text_and_emit_final' voice_typing/recorder_host.py`.
  - FINDINGS are pre-verified COMPLIANT (research §2) — re-confirm; if a real defect appears, record + fix it.

Task 2: RE-RUN the IPC test slice (the audit's test evidence)
  - RUN: `timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k 'host or
    relay or queue or ipc or worker'`. Record the pass count (baseline 30 passed, 189 deselected).
  - Cite the key evidence tests in the report per property (research §3): spawn ready/error; stop killpg/noop/
    single-flight; set_microphone arm/disarm; abort Event; text blocks/dead-child/abort-sentinel; _dispatch per
    event kind; _run_text_emits_sentinel_* (VT-007).

Task 3: APPEND '# §2 — Recorder-Host IPC (P1.M2.T2.S2)' to gap_lifecycle.md (the deliverable)
  - FORMAT: mirror gap_daemon_loop.md §2 (L156+) — a self-contained report under a '# §2 — ...' heading with its own
    Scope/Audited-artifacts/Bottom-line/Method (grep+read+run)/compliance-table/test-evidence/nuances/conclusion.
  - CONTENT: the pre-verified findings (research §2) transcribed — each property COMPLIANT with recorder_host.py
    file:line + the nuances (research §4) so they aren't mistaken for defects.
  - VERDICT: ✅ COMPLIANT (no defects, no source changes). Tie to PRD §4.2bis (proxied commands + streamed events
    + setsid/killpg VRAM release).
  - APPEND: if gap_lifecycle.md exists (S1 landed §1), append §2 below it; if absent, create the file with §2 as
    its initial content (a self-contained report). Include the line '§1 above is P1.M2.T2.S1's lazy-load audit;
    this §2 owns the IPC 6 properties' (mirroring gap_daemon_loop.md L165-166).

Task 4: SCOPE GUARD
  - `git status --short` shows ONLY gap_lifecycle.md (new or appended), modulo S1's concurrent work on the same
    file. No voice_typing/*, no tests/*, no PRD/tasks/snapshot change.
```

### Implementation Patterns & Key Details

```markdown
<!-- gap_lifecycle.md §2 skeleton (mirror gap_daemon_loop.md §2 @L156+): -->
# §2 — Recorder-Host IPC (P1.M2.T2.S2) vs PRD §4.2bis
**Date:** <re-verify date>  **Scope:** Audit voice_typing/recorder_host.py IPC (spawn/__init__ queues/_worker_main/
_read_loop/_dispatch/_RelayFeedback/_RelayLatency/_terminate_group) vs PRD §4.2bis on (a)-(f). §1 above is
P1.M2.T2.S1's lazy-load audit; this §2 owns the IPC mechanism.
**Audited artifacts (read-only):** recorder_host.py <file:line>; tests/test_recorder_host.py + test_daemon.py (-k slice).
**Bottom line:** ✅ All 6 properties COMPLIANT (file:line below). -k slice = 30 passed. No source modified.
## 1. Method  (grep commands; re-verify reads; re-run command)
## 2. The 6 IPC properties — per-point compliance table
   (| # | item property | PRD §4.2bis expected | code actual (recorder_host.py:line) | test | verdict ✅ |)
   (a) spawn→Process(_worker_main)   (b) child setsid + daemon killpg   (c) cmd_q arm/disarm/text/shutdown + abort-Event
   (d) evt_q ready/error/final/partial/vad/speech/speech_end/gone   (e) text puts cmd + blocks on final evt
   (f) _RelayFeedback/_RelayLatency relay (partial/vad/speech_end) + daemon-owned no-ops
## 3. Test evidence  (the -k command + count + key test names per property)
## 4. Non-defect nuances  (abort-via-Event; richer vocabulary; intentional no-op relays; VT-007 sentinel; vad gate)
## 5. Conclusion  (COMPLIANT; certifies PRD §4.2bis proxied-commands + streamed-events + setsid/killpg VRAM release)
```

### Integration Points

```yaml
REPORT (the deliverable):
  - append: "plan/006_862ee9d6ef41/architecture/gap_lifecycle.md += '# §2 — Recorder-Host IPC (P1.M2.T2.S2)' (or create-with-§2 if absent)"
  - verdict: "✅ COMPLIANT — all 6 properties (a-f) pass (recorder_host.py file:line)"
  - ties-to: "PRD §4.2bis recorder-host subprocess (proxied commands + streamed events + setsid/killpg VRAM release)"
CONSUMERS:
  - P1.M5.T5 (acceptance cross-check): "maps criteria #6/#9 (which depend on the IPC working) to this audit's evidence"
  - S3 (P1.M2.T2.S3): "the bounded-teardown TIMING audit will reference this §2's killpg@407 + stop@272-329 findings"
  - future maintainers: "the reference for any recorder_host.py change (new event/relay/abort-path)"
SCOPE GUARD:
  - git status: "ONLY architecture/gap_lifecycle.md (new/appended), modulo S1's concurrent §1 work. No voice_typing/*, no tests/*."
```

## Validation Loop

### Level 1: Re-verification (read the code — read-only)

```bash
cd /home/dustin/projects/voice-typing
# Re-locate the 6 IPC regions (line numbers may drift — re-grep):
grep -nE 'def spawn|def set_microphone|def abort|def text\b|def stop|def _read_loop|def _dispatch|def _terminate_group|def _worker_main|def _run_text_and_emit_final|os\.setsid|os\.killpg|_cmd_q\.put|_abort_event|class _RelayFeedback|class _RelayLatency|_safe_put\(.*evt_q' voice_typing/recorder_host.py
# Read each region (spawn ~181-228, __init__ queues ~135-160, _worker_main ~421-575 incl. setsid@446 + loop@533-571,
# _read_loop ~331-353, _dispatch ~354-392, _terminate_group ~394-413, _RelayFeedback ~718-750, _RelayLatency ~760-774)
# and confirm (a)-(f) match PRD §4.2bis. Expected: COMPLIANT (research §2).
# Also confirm the module docstring's IPC PROTOCOL block (L18-31) matches the code's actual vocabulary.
```

### Level 2: Test evidence (re-run the IPC slice — the audit's evidence)

```bash
cd /home/dustin/projects/voice-typing
# AGENTS.md Rule 1: inner timeout (mandatory) + outer bash timeout. Mocked CUDA -> fast, but timeout is non-negotiable.
timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k 'host or relay or queue or ipc or worker'
# Expected: 30 passed, 189 deselected (record the actual count in the report).
```

### Level 3: Report well-formedness

```bash
cd /home/dustin/projects/voice-typing
# Confirm gap_lifecycle.md exists + has the §2 section + cites file:line + records the verdict:
grep -nE '§2|Recorder-Host IPC|Bottom line|30 passed|COMPLIANT|setsid|killpg|VT-007|abort_event|_RelayFeedback' plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
# Expected: the §2 heading, the ✅ bottom line, the compliance table (with recorder_host.py:line), the test count,
# the nuances (abort-via-Event / richer vocabulary / no-op relays / VT-007), all present.
```

### Level 4: Scope guard (no unintended edits)

```bash
cd /home/dustin/projects/voice-typing
git status --short
# Expected: ONLY plan/006_862ee9d6ef41/architecture/gap_lifecycle.md (new or appended), modulo S1's concurrent §1 work
# on the same file. No voice_typing/*, no tests/*, no PRD/tasks/snapshot.
```

## Final Validation Checklist

### Technical Validation
- [ ] Re-verified the 6 IPC regions (spawn, queues+Event, _worker_main, _read_loop, _dispatch, relay, _terminate_group) — all COMPLIANT.
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k 'host or relay or queue or ipc or worker'` → recorded pass count (baseline 30).
- [ ] `gap_lifecycle.md` contains the `# §2 — Recorder-Host IPC (P1.M2.T2.S2)` section (appended, or created-with-§2 if absent).

### Feature (Audit) Validation
- [ ] Compliance table covers (a) spawn→Process(_worker_main), (b) child setsid + daemon killpg, (c) cmd_q commands (+ abort-via-Event), (d) evt_q events, (e) text puts cmd + blocks on final, (f) relay — each COMPLIANT with recorder_host.py file:line.
- [ ] Verdict ✅ COMPLIANT; conclusion ties to PRD §4.2bis (proxied commands + streamed events + setsid/killpg VRAM release).
- [ ] If a real defect was found, it is fixed + recorded; otherwise "none — compliant per audit."

### Code Quality Validation
- [ ] §2 section mirrors the `gap_*.md` §2-append format (consistent with gap_daemon_loop.md L156+).
- [ ] Non-defect nuances recorded (abort-via-Event; richer vocabulary; intentional no-op relays; VT-007 sentinel; vad gate) so they aren't mistaken for gaps.
- [ ] Only `architecture/gap_lifecycle.md` written (`git status --short`), modulo S1's concurrent §1 work.

### Documentation & Deployment
- [ ] Report is self-contained (scope, method, evidence, verdict) — a future maintainer can re-run the audit from it.
- [ ] Adjacent concerns correctly deferred (lazy-load states → S1 §1; teardown timing → S3; phase lifecycle → P1.M2.T1; lite → M2.T3; status → M3).

---

## Anti-Patterns to Avoid

- ❌ Don't edit `voice_typing/recorder_host.py` or any test — this is an AUDIT; the IPC is COMPLIANT (no defect). Edit ONLY if re-verification surfaces a real defect (Critical #1).
- ❌ Don't run pytest without `timeout 300` (inner) + the bash-tool timeout — AGENTS.md Rule 1 (the repo has hang vectors) (Critical #2).
- ❌ Don't assert compliance without file:line evidence — every table row must cite the recorder_host.py line(s) (Critical #3).
- ❌ Don't mistake the nuances for defects: abort-via-mp.Event (not cmd_q primary); richer evt_q vocabulary ("ready"/"vad"{phase} vs "device"/"vad_start"); intentional no-op relays (set_models_loaded/record_final/set_listening); the VT-007 abort-sentinel; the vad is_listening gate (Critical #4).
- ❌ Don't create a NEW standalone file — APPEND §2 to `gap_lifecycle.md` (the item OUTPUT). If the file is absent (S1 parallel), create it WITH §2 as initial content (Critical #5).
- ❌ Don't stray into the lazy-load states (S1 §1), teardown timing (S3), phase lifecycle (P1.M2.T1), lite (M2.T3), or status (M3) audits — this §2 owns the IPC MECHANISM only.
- ❌ Don't "simplify" the VT-007 `_run_text_and_emit_final` sentinel or the abort-via-Event design — both prevent the run()-loop wedge; record them as load-bearing.
- ❌ Don't use bare `python`/`pytest` (zsh aliases) — `.venv/bin/python -m pytest` (Critical #6).