# PRP — P1.M2.T2.S4: Audit idle auto-stop watchdog (PRD §4.5 `auto_stop_idle_seconds`)

## Goal

**Feature Goal**: Produce the authoritative **idle auto-stop watchdog audit** as a new **§4 section appended to `plan/006_862ee9d6ef41/architecture/gap_lifecycle.md`**, cross-checking `daemon.py`'s **idle AUTO-STOP watchdog** (`_idle_watchdog` → `_maybe_auto_stop` → `_disarm`) against **PRD §4.5's `auto_stop_idle_seconds` clause** on the **6 item properties (a)-(f) + the partial-reset hook**. This is a **verification/audit** subtask (round `006_862ee9d6ef41`): the deliverable is the report section; **code changes happen ONLY if a real defect is found — none is expected; this PRP's author has already performed the audit and the auto-stop watchdog is PRD §4.5-COMPLIANT.**

> **VERIFIED VERDICT (this PRP's research): the idle auto-stop watchdog is COMPLIANT — no fix needed.** All 6 properties (a)-(f) + the partial-reset hook pass (file:line in the research note §2); the contract's `-k 'idle or auto_stop or watchdog'` slice = **27 passed, 166 deselected in 1.07s**. The watchdog disarms the mic (not the models) after 30s of no recognized speech, hands off to the idle-unload clock via `_disarm` stamping `_disarmed_monotonic`, and the 0-disable short-circuits before acquiring `_lock`.

**Deliverable** (ONE report section; NO source edits, NO test edits): `plan/006_862ee9d6ef41/architecture/gap_lifecycle.md` — a **`# §4 — Idle Auto-Stop Watchdog (P1.M2.T2.S4)` section APPENDED** below the last section present. At research time the file has §1 (S1 lazy-load @L1) + §2 (S2 IPC @L201) = 404 lines; §3 (S3 teardown) is being appended in parallel. The `# §4` heading makes it compose with §3 regardless of append order. The section mirrors the `gap_*.md` §N-append format (sibling precedents: this file's own §2 @L201, and `gap_daemon_loop.md` §2 @L156) and contains: (1) scope + audited artifacts (file:line); (2) a per-property compliance table (PRD §4.5 expected vs code actual) for (a)-(f) + the partial-reset hook; (3) the test pass/fail count for the contract's run target; (4) the non-defect nuances (two watchdogs/two clocks; atomic float store not lock-guarded; `_shutdown.wait(1.0)` not `time.sleep`; watchdog swallows its own exceptions; abort-after-autostop effectively skipped; INFO line + toast via `_disarm`; 0-disable before lock); (5) a conclusion tying the verdict to PRD §4.5 + acceptance #5. **This PRP's author has already performed the audit** (findings in the research note) — the implementing agent re-verifies, re-runs the tests, and transcribes the §4 section.

> **The auto-stop vs idle-unload distinction (load-bearing — do not confuse §3 and §4):** `_idle_watchdog` (§4, THIS) fires while LISTENING after 30s of no partial → `_disarm()` (mic OFF, models STAY). `_idle_unload_watchdog` (§3, S3) fires while DISARMED after 30min → `_unload_host()` (models TORN DOWN, VRAM freed). They COMPOSE: auto-stop's `_disarm` stamps `_disarmed_monotonic`, starting the unload clock for free. §3 owns the unload watchdog + bounded teardown; §4 owns the auto-stop watchdog + disarm. They are SEPARATE threads with SEPARATE clocks (`_last_speech_monotonic` vs `_disarmed_monotonic`).

**Success Definition**:
- (a) `architecture/gap_lifecycle.md` contains a `# §4 — Idle Auto-Stop Watchdog (P1.M2.T2.S4)` section with the 5 sub-parts (scope/artifacts, compliance table, test evidence, nuances, conclusion), appended below the last present section.
- (b) The recorded findings match the live re-verification: all 6 item properties (a)-(f) + the partial-reset hook are **compliant** (each with `daemon.py` file:line).
- (c) `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or auto_stop or watchdog'` → all pass (record the count; verified baseline: **27 passed, 166 deselected**).
- (d) **No source or test files are modified** (because no defect exists — the auto-stop watchdog is PRD §4.5-compliant per audit). If — and only if — the re-verification surfaces a REAL defect, fix it and record the fix; otherwise record "none — compliant per audit."
- (e) `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_lifecycle.md` (appended) — no `voice_typing/*`, no `tests/*`, no `PRD.md`/`tasks.json`/`prd_snapshot.md` change.

## User Persona

**Target User**: the maintainer (human or AI agent) who needs to trust that (i) a **forgotten hot-mic** (armed but the user walked away) auto-disarms after 30s of silence instead of recording/hallucinating for hours (the §4.5 guard + acceptance #5), (ii) a **late partial cancels the stop** so a mid-thought pause doesn't false-trigger the disarm (the lock-gated re-check), and (iii) the auto-stop→idle-unload **composition** is correct (disarm starts the 30min clock; models aren't torn down by the 30s guard). Also the downstream P1.M5.T5 acceptance-criteria cross-check (maps acceptance #5 — "Daemon survives ≥2 min of silence with no hallucinated output and trivial CPU use" — to this audit's evidence).

**Use Case**: A future change to the auto-stop threshold, the partial-reset hook, the `_idle_watchdog` tick interval, or the disarm hand-off. The audit + the 7 auto-stop tests are the reference that proves the change keeps (or breaks) the §4.5 contract.

**Pain Points Addressed**: Closes the "does the watchdog REALLY tick ~1s, REALLY re-check under the lock, REALLY disarm-immediate (not drain), REALLY log the INFO line, REALLY start the unload clock, and REALLY respect 0-disable?" question with recorded, re-runnable evidence — not an assumption. The two-watchdog distinction is certified so a maintainer doesn't "merge" them or mistake auto-stop for a teardown.

## Why

- **The forgotten-hot-mic guard is a §7 #5 acceptance gate.** PRD §4.5 + §7 #5 require the daemon to "survive ≥2 min of silence with no hallucinated output and trivial CPU use." The idle auto-stop watchdog is the mechanism that DISARMS after 30s of no recognized speech, capping the hot-mic exposure window so a mic left armed cannot hallucinate for minutes (the blocklist filter §4.5/§4.7 catches the classic hallucinations; auto-stop removes the exposure). When disarmed the run() loop is in `time.sleep(0.05)` — trivial CPU. The audit certifies the guard fires correctly. (PRD §4.5 "Idle auto-stop"; §7 acceptance #5.)
- **Auto-stop composes with idle-unload (§3).** PRD §4.5 explicitly states "Auto-stop disarms the mic but does NOT unload models by itself — it starts the slower idle-unload clock." This audit certifies the hand-off: `_maybe_auto_stop`'s `_disarm()` stamps `_disarmed_monotonic`, which `_idle_unload_watchdog` (§3) reads. So the 30s→30min composition is free — but ONLY if `_disarm` stamps the clock. The audit certifies it does (L1021). (PRD §4.5 last paragraph; §4.2bis Idle unload = §3.)
- **The lock-gated re-check is the correctness invariant.** A late partial arriving between the watchdog's 1s tick and its `_disarm()` must CANCEL the stop — otherwise a mid-thought pause (longer than 30s) would false-disarm mid-dictation. PRD §4.5 mandates "re-checks the deadline under the listen lock so a late partial cancels the stop." The audit certifies `_maybe_auto_stop` re-reads `_last_speech_monotonic` UNDER `self._lock` (L1131/1133). (PRD §4.5.)
- **Scope discipline.** This subtask owns the auto-stop WATCHDOG ONLY: the `_idle_watchdog` thread, the `_maybe_auto_stop` decision, the `_disarm` call, the INFO line, the hand-off to the unload clock, the 0-disable. The lazy-load STATE MACHINE is §1 (S1); the IPC MECHANISM is §2 (S2); the idle-UNLOAD watchdog + bounded teardown is §3 (S3) — §4 REFERENCES §3's `_idle_unload_watchdog`/`_disarmed_monotonic` (the clock §4 starts, §3 reads). The graceful drain (P1.M2.T1.S2) is the contrast case (stop-with-in-flight drains; auto-stop never has in-flight → immediate). Phase lifecycle is P1.M2.T1; lite/mode-switch is M2.T3; the toast wiring is M3 (§4 certifies only that auto-stop REACHES `_disarm`, which fires the toast).

## What

Re-verify the idle auto-stop watchdog against PRD §4.5 by reading the ~6 code regions (`_idle_watchdog`@1148 + `_maybe_auto_stop`@1119 + `_disarm`@1002 + `_arm`@987 + `_touch_speech`@1029 + `_build_callbacks._partial`@219 in `daemon.py`; `auto_stop_idle_seconds`@65 in `config.py`), re-running the 7-test auto-stop slice, and appending a `# §4 — Idle Auto-Stop Watchdog (P1.M2.T2.S4)` section to `architecture/gap_lifecycle.md` in the `gap_*.md` §N-append format (mirror this file's own §2 @L201 + `gap_daemon_loop.md` §2 @L156). The audit is expected to confirm full compliance (no defects → no code changes). The report's compliance table maps each of the 6 item properties (a)-(f) + the partial-reset hook to PRD §4.5 expected behavior vs the code's actual behavior (file:line).

### Success Criteria

- [ ] `architecture/gap_lifecycle.md` contains the `# §4 — Idle Auto-Stop Watchdog (P1.M2.T2.S4)` section (appended below the last present section).
- [ ] Compliance table covers (a) `_idle_watchdog` ticks ~1s, (b) deadline re-check under `_lock` (late partial cancels), (c) `_maybe_auto_stop` disarms immediate (not drain), (d) journal INFO line, (e) starts idle-unload clock (`_disarmed_monotonic`), (f) 0 disables — PLUS the partial-reset hook (`_touch_speech` ← `on_speech` ← `_partial`) — each COMPLIANT with file:line.
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or auto_stop or watchdog'` → recorded pass count (baseline 27 passed).
- [ ] No source/test files modified (`git status --short` == the gap_lifecycle.md report only).
- [ ] Conclusion ties the verdict to PRD §4.5 + acceptance #5 (forgotten-hot-mic guard; 2min silence stable).

## All Needed Context

### Context Completeness Check

_Pass._ The audit is **already performed** by this PRP's author (research note §2: every property mapped to `daemon.py`/`config.py` file:line with the COMPLIANT verdict + the 27-test evidence). A developer new to this repo can re-verify from the research note + the cited code regions: the exact line ranges (`_idle_watchdog`@1148-1156, `_maybe_auto_stop`@1119-1147, `_disarm`@1002-1027, `_arm`@987-1000, `_touch_speech`@1029-1039, `_build_callbacks._partial`@219/237-238, `_load_host` wiring@751/757 in daemon.py; `auto_stop_idle_seconds=30.0`@65 in config.py), the grep commands to re-locate them, the test command, and the `gap_*.md` §4-append format (sibling §2 @L201 + `gap_daemon_loop.md` §2 @L156). The non-defect nuances (two watchdogs/two clocks; atomic float store not lock-guarded; `_shutdown.wait(1.0)` not `time.sleep`; watchdog swallows its own exceptions; abort-after-autostop effectively skipped; INFO line + toast via `_disarm`; 0-disable before lock) are documented so they are not mistaken for gaps.

### Documentation & References

```yaml
# MUST READ — the pre-verified audit findings (file:line + COMPLIANT verdict + test evidence)
- docfile: plan/006_862ee9d6ef41/P1M2T2S4/research/idle_auto_stop_audit.md
  why: "§0 the two-watchdog table (auto-stop §4 vs idle-unload §3 — DISJOINT). §1 the ~6 regions under audit
        (daemon.py _idle_watchdog@1148/_maybe_auto_stop@1119/_disarm@1002/_arm@987/_touch_speech@1029/
        _build_callbacks@219/_load_host-wiring@751; config.py auto_stop_idle_seconds@65). §2 ★ THE 6-PROPERTY
        VERDICT (file:line per property, all COMPLIANT) + the partial-reset hook. §3 TEST EVIDENCE (27 passed).
        §4 NON-DEFECT NUANCES (7). §5 verdict + acceptance #5 linkage. §6 the append convention."
  section: "ALL load-bearing. §2 (findings w/ file:line), §3 (test count), §4 (nuances) are the core to transcribe."

# MUST READ — the PRD being audited against (the contract)
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md   # (or PRD.md §4.5 + §7 #5)
  why: "§4.5 'Idle auto-stop (asr.auto_stop_idle_seconds, default 30.0)' is the authoritative spec — the exact
        wording the compliance table maps to: 'auto-disarms immediately (no drain)', 'fires the Recording Stopped
        toast + writes a journal INFO line (voice-typing auto-stop: 30.0s of no recognized speech; disarming)',
        'Partials reset the clock', 'a background _idle_watchdog thread ticks ~1s and re-checks the deadline under
        the listen lock so a late partial cancels the stop', '0 disables', 'Auto-stop disarms the mic but does NOT
        unload models — it starts the slower idle-unload clock'. §7 #5 ('survives ≥2 min of silence, no
        hallucination, trivial CPU') is what this audit certifies the guard for."
  critical: "Audit against §4.5's WORDING (auto-disarm-after-30s-no-partial, partials-reset, lock-gated re-check,
             0-disables, starts-unload-clock). The verified code facts (research §2) confirm the implementation
             matches — so the report states COMPLIANT."

# MUST READ — the files under audit (the ~6 auto-stop regions)
- file: voice_typing/daemon.py
  why: "The auto-stop watchdog. _idle_watchdog (L1148, ticks _shutdown.wait(1.0)@1152 -> _maybe_auto_stop@1153;
        swallows own exceptions@1154-1155). _maybe_auto_stop (L1119, threshold<=0 return@1127-1128 BEFORE lock;
        with self._lock@1129; not-listening/clock-None guard@1131; deadline re-check@1133 -> return if recent;
        logger.info@1134-1137 the INFO line; self._disarm()@1139; _safe_abort@1147 outside lock). _disarm (L1002,
        _last_speech_monotonic=None@1020 + _disarmed_monotonic=time.monotonic()@1021 the HAND-OFF + _feedback.
        set_listening(False)@1026 the toast). _arm (L987, _last_speech_monotonic=now@994 + _disarmed_monotonic=
        None@995). _touch_speech (L1029, _last_speech_monotonic=now@1039 + _final_pending=True@1040). 
        _build_callbacks._partial (L219/237-238, calls on_speech() after update_partial). _load_host wiring (L751/L757,
        self._touch_speech as 5th positional arg). _safe_abort (L1335, gated on _text_in_flight@1355)."
  critical: "READ-ONLY audit. Do NOT edit daemon.py (no defect exists). Re-locate with grep if line numbers drift."
- file: voice_typing/config.py
  why: "auto_stop_idle_seconds: float = 30.0 (L65, the default — PRD §4.5 match). L76 strict-loader rejects string
        'thirty' (validation guard). L89 in validated-keys list."
  critical: "READ-ONLY. The default IS 30.0 per PRD §4.5 — confirm no drift."

# MUST READ — the append-format template (how S2 appended §2 to THIS file)
- file: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
  why: "This file's §2 (heading @L201, concl @tail) is the EXACT append template for §4 — same Scope/Audited-
        artifacts/Bottom-line/§N.1 Method/§N.2 compliance-table/§N.3 test-evidence/§N.4 nuances/§N.5 Conclusion
        structure. APPEND §4 BELOW the last section present (§3 if S3 appended it, else §2)."
  critical: "APPEND a '# §4 — Idle Auto-Stop Watchdog (P1.M2.T2.S4)' section. Do NOT create a standalone file (item
             OUTPUT is 'Append to gap_lifecycle.md'). §1/§2 already exist (L1/L201); §3 (S3) is appended in parallel;
             the # §4 heading composes regardless of order. Append §4 at EOF."
- file: plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md
  why: "L156+ is the canonical §N-append precedent (P1.M2.T1.S2 appended §2 drain below §1 main-loop). Mirror its
        self-contained-report-under-a-§N-heading shape."
  critical: "Background format reference. Do NOT edit it."

# MUST READ — the sibling task contracts (DISJOINT content; §4 cross-references §3)
- docfile: plan/006_862ee9d6ef41/P1M2T2S3/PRP.md
  why: "S3 created §3 (idle-UNLOAD watchdog + bounded teardown: _idle_unload_watchdog/_maybe_idle_unload/_unload_
        recorder/_unload_host/_bounded_shutdown). §4's property (e) STARTS the clock §3 READS (_disarm stamps
        _disarmed_monotonic@1021). DISJOINT: §3=unload/teardown; §4=auto-stop/disarm. Cross-reference, don't
        duplicate — §4 notes §3 owns the unload watchdog + the 30min teardown, and that auto-stop's disarm HANDS
        OFF to it."
  critical: "Do NOT re-audit the idle-unload watchdog or bounded teardown (S3 owns §3). Reference _disarmed_monotonic
             + _idle_unload_watchdog for the hand-off point only."
- docfile: plan/006_862ee9d6ef41/P1M2T2S2/PRP.md
  why: "S2 created §2 (recorder-host IPC). §4's partial-reset hook traces THROUGH §2's IPC: child on_speech ->
        ('speech',{}) event -> host reader thread -> _touch_speech. DISJOINT: §2=IPC vocabulary; §4=auto-stop watchdog."
  critical: "Do NOT re-audit the IPC (S2 owns §2). Note only that partials arrive via the host reader thread."
```

### Current Codebase tree (relevant slice — the 1 report file this task appends to)

```bash
/home/dustin/projects/voice-typing/
└── plan/006_862ee9d6ef41/architecture/
    └── gap_lifecycle.md      # WRITE: append '# §4 — Idle Auto-Stop Watchdog (P1.M2.T2.S4)' below the last section.
# voice_typing/daemon.py + config.py — READ-ONLY (the ~6 audited regions). tests/test_daemon.py — READ-ONLY (re-run, do not edit).
# gap_daemon_loop.md (§1 main-loop + §2 drain), gap_config.md, etc. — existing sibling reports (do not touch).
```

### Desired Codebase tree (unchanged structure — one report section appended)

```bash
# Same tree. One file gains a section:
#   plan/006_862ee9d6ef41/architecture/gap_lifecycle.md += '# §4 — Idle Auto-Stop Watchdog (P1.M2.T2.S4)' report section (appended at EOF).
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THIS IS AN AUDIT, NOT IMPLEMENTATION. The deliverable is the §4 section of gap_lifecycle.md (a
#   report). Do NOT edit voice_typing/daemon.py / config.py or any test unless the re-verification surfaces a REAL
#   defect — none is expected (the auto-stop watchdog is PRD §4.5-compliant per the pre-verified audit). If you find
#   no defect, record "none — compliant per audit." (Research §5.)
# CRITICAL #2 — USE TIMEOUTS (AGENTS.md Rule 1). The repo is a foreground daemon with hang vectors. Wrap the pytest
#   run: `timeout 300 .venv/bin/python -m pytest ...` (inner) + the bash tool timeout (outer). The auto-stop slice is
#   mocked-CUDA (no model load) so it is fast (~1s), but the timeout is mandatory. NEVER run the daemon in the
#   foreground; NEVER run untimed voicectl/pytest.
# CRITICAL #3 — RECORD file:line EVIDENCE, not assertions. Each compliance-table row must cite the daemon.py line(s)
#   that satisfy the PRD §4.5 clause (re-locate with grep if line numbers drift). The pre-verified lines:
#   _idle_watchdog@1148-1156 (wait(1.0)@1152, swallow@1154-1155); _maybe_auto_stop@1119-1147 (threshold<=0 return@
#   1127-1128 BEFORE lock, with self._lock@1129, not-listening/clock-None guard@1131, deadline re-check@1133,
#   logger.info@1134-1137, _disarm@1139, _safe_abort@1147); _disarm@1002-1027 (clock None@1020, _disarmed_monotonic=
#   now@1021 the HAND-OFF, set_listening(False)@1026 the toast); _arm@987-1000 (clock=now@994); _touch_speech@1029-1039
#   (clock=now@1039); _build_callbacks@219/237-238 (on_speech() in _partial); _load_host@751/757 (self._touch_speech
#   5th arg); config.py auto_stop_idle_seconds=30.0@65. (Research §1/§2.)
# CRITICAL #4 — DO NOT MISTAKE NUANCES FOR DEFECTS. (i) TWO watchdogs/two clocks: _idle_watchdog (auto-stop, LISTENING,
#   _last_speech_monotonic) vs _idle_unload_watchdog (idle-unload, DISARMED, _disarmed_monotonic) — §3 owns the unload.
#   (ii) _last_speech_monotonic is an atomic CPython float store written by _touch_speech WITHOUT _lock (reader thread)
#   and read by the watchdog UNDER _lock — the lock serializes the DISARM decision, not the float write; this IS the
#   PRD §4.5 "re-check under the listen lock" mechanism. (iii) _idle_watchdog ticks via _shutdown.wait(1.0) NOT
#   time.sleep(1.0) — exits promptly on shutdown. (iv) the watchdog swallows its own exceptions@1154-1155 (resilience).
#   (v) abort() after auto-stop is effectively always SKIPPED — _safe_abort@1355 returns if not _text_in_flight, and
#   after 30s of silence the loop is idle so _text_in_flight is clear (abort is a best-effort nudge; correct no-op).
#   (vi) the INFO line@1134-1137 is the journal line (property d); the "Recording Stopped" toast fires via _disarm@
#   1026 -> _feedback.set_listening(False) (feedback.py L23) — the toast WIRING is a P1.M3.T1 concern, §4 certifies
#   only that auto-stop REACHES _disarm. (vii) the 0-disable check@1127-1128 is BEFORE _lock (cheap no-op, no
#   contention). (Research §4.)
# CRITICAL #5 — APPEND §4, DO NOT CREATE A STANDALONE FILE. The item OUTPUT is 'Append to gap_lifecycle.md'. §1 (S1)
#   + §2 (S2) already exist (L1/L201); §3 (S3) is appended in parallel; the # §4 heading composes regardless of order.
#   APPEND §4 at EOF (below §3 if present, else §2). Mirror the file's own §2 @L201 shape.
# CRITICAL #6 — SCOPE = auto-stop watchdog (disarm the mic). Do NOT re-audit the lazy-load states (§1), the IPC
#   vocabulary (§2), or the idle-unload watchdog + bounded teardown (§3). §4 owns: the _idle_watchdog thread, the
#   _maybe_auto_stop decision, the _disarm call, the INFO line, the hand-off to the unload clock, the 0-disable.
#   REFERENCE §3's _idle_unload_watchdog/_disarmed_monotonic (the clock §4 starts, §3 reads); cross-reference, don't
#   duplicate. Contrast §4's IMMEDIATE disarm with P1.M2.T1.S2's graceful DRAIN (stop-with-in-flight drains; auto-stop
#   never has in-flight -> immediate).
# CRITICAL #7 — FULL TOOL PATHS (zsh aliases python/pip). .venv/bin/python -m pytest ... (never bare python/pytest).
#   The architecture/ + plan/ paths are relative to the repo root (/home/dustin/projects/voice-typing).
# CRITICAL #8 — ACCEPTANCE #5 LINKAGE. PRD §7 #5 = "Daemon survives ≥2 min of silence with no hallucinated output and
#   trivial CPU use." The auto-stop watchdog is the forgotten-hot-mic guard (disarms after 30s silence, capping
#   hallucination exposure). The 2min T4 silence test EXCEEDS the 30s threshold, so it exercises the armed->
#   auto-stopped transition as a side effect. §4 certifies that transition is correct (no hallucination typed, mic
#   disarmed, daemon stable). (Research §5.)
```

## Implementation Blueprint

### Data models and structure

None (audit/report task). The "data" is the verified auto-stop findings (research §2), transcribed into the `gap_*.md` §4-append format. No code, no data models.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RE-VERIFY the ~6 auto-stop regions against PRD §4.5 (read-only)
  - READ daemon.py: _idle_watchdog@1148-1156 (_shutdown.wait(1.0)@1152, _maybe_auto_stop@1153, swallow@1154-1155);
    _maybe_auto_stop@1119-1147 (threshold<=0 return@1127-1128 BEFORE lock, with self._lock@1129, not-listening/
    clock-None guard@1131, deadline re-check@1133, logger.info@1134-1137, _disarm@1139, _safe_abort@1147 outside lock);
    _disarm@1002-1027 (_last_speech_monotonic=None@1020, _disarmed_monotonic=time.monotonic()@1021 the HAND-OFF,
    _feedback.set_listening(False)@1026 the toast); _arm@987-1000 (_last_speech_monotonic=now@994, _disarmed_monotonic=
    None@995); _touch_speech@1029-1039 (_last_speech_monotonic=now@1039, _final_pending=True@1040);
    _build_callbacks@219/237-238 (_partial calls on_speech()); _load_host@751/757 (self._touch_speech 5th arg);
    _safe_abort@1335-1362 (gated on _text_in_flight@1355).
  - READ config.py: auto_stop_idle_seconds: float = 30.0@65.
  - RE-CONFIRM each of (a)-(f) + the partial-reset hook matches PRD §4.5 wording.
  - RE-LOCATE with grep if line numbers drifted: `grep -nE 'def _idle_watchdog|def _maybe_auto_stop|def _disarm|def _arm|def _touch_speech|def _on_partial|def _build_callbacks|on_speech|def _safe_abort|_last_speech_monotonic|_disarmed_monotonic|auto_stop_idle_seconds|_shutdown.wait' voice_typing/daemon.py voice_typing/config.py`.
  - FINDINGS are pre-verified COMPLIANT (research §2) — re-confirm; if a real defect appears, record + fix it.

Task 2: RE-RUN the auto-stop test slice (the audit's test evidence)
  - RUN: `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or auto_stop or watchdog'`. Record the
    pass count (baseline 27 passed, 166 deselected).
  - Cite the key evidence tests per property (research §3): test_auto_stop_disarms_when_idle_beyond_threshold (c);
    test_auto_stop_keeps_alive_with_recent_speech (b); test_touch_speech_resets_the_idle_clock (partial reset);
    test_auto_stop_disabled_when_threshold_zero (f); test_auto_stop_noop_when_not_listening (b guard);
    test_disarm_clears_the_idle_clock (b/e); test_idle_watchdog_actually_disarms_in_background (a+c, REAL thread).

Task 3: APPEND '# §4 — Idle Auto-Stop Watchdog (P1.M2.T2.S4)' to gap_lifecycle.md (the deliverable)
  - FORMAT: mirror this file's §2 @L201 (and gap_daemon_loop.md §2 @L156) — a self-contained report under a '# §4 — …'
    heading with Scope/Audited-artifacts/Bottom-line/§4.1 Method/§4.2 compliance-table/§4.3 test-evidence/§4.4 nuances/
    §4.5 Conclusion.
  - CONTENT: the pre-verified findings (research §2) transcribed — each property COMPLIANT with file:line + the nuances
    (research §4) so they aren't mistaken for defects. Include the two-watchdog table (research §0) up top so §3 vs §4
    is unambiguous.
  - VERDICT: ✅ COMPLIANT (no defects, no source changes). Tie to PRD §4.5 + acceptance #5 (forgotten-hot-mic guard;
    2min silence stable).
  - APPEND at EOF (below the last section present — §3 if S3 appended it, else §2). Include a line noting §1=states
    (S1) + §2=IPC (S2) + §3=idle-unload/teardown (S3); §4=auto-stop watchdog, and that §4 HANDS OFF to §3's
    _idle_unload_watchdog (auto-stop's _disarm stamps _disarmed_monotonic, which §3 reads).

Task 4: SCOPE GUARD
  - `git status --short` shows ONLY gap_lifecycle.md (appended). No voice_typing/*, no tests/*, no PRD/tasks/snapshot change.
```

### Implementation Patterns & Key Details

```markdown
<!-- gap_lifecycle.md §4 skeleton (mirror this file's §2 @L201 + gap_daemon_loop.md §2 @L156): -->
# §4 — Idle Auto-Stop Watchdog (P1.M2.T2.S4) vs PRD §4.5 `auto_stop_idle_seconds`
**Date:** <re-verify date>  **Scope:** Audit the idle AUTO-STOP watchdog (_idle_watchdog → _maybe_auto_stop → _disarm)
vs PRD §4.5 on (a)-(f) + the partial-reset hook. §1 above is P1.M2.T2.S1's lazy-load states; §2 is S2's recorder-host
IPC; §3 is S3's idle-UNLOAD watchdog + bounded teardown (the clock §4 STARTS, §3 READS). This §4 owns the auto-stop
watchdog: disarms the MIC after 30s of no recognized speech while LISTENING (does NOT tear down models).
**Two-watchdog table:** | auto-stop §4 (LISTENING, 30s, _disarm) | idle-unload §3 (DISARMED, 30min, _unload_host) |
**Audited artifacts (read-only):** daemon.py <file:line> (_idle_watchdog/_maybe_auto_stop/_disarm/_arm/_touch_speech/
_build_callbacks/_load_host-wiring/_safe_abort); config.py <auto_stop_idle_seconds=30.0>; tests/test_daemon.py (-k slice).
**Bottom line:** ✅ All 6 properties + partial-reset hook COMPLIANT (file:line below). -k slice = 27 passed. No source
modified. Auto-stop disarms (not unload); hands off to §3's unload clock via _disarm stamping _disarmed_monotonic.
## §4.1 Method  (grep commands; re-verify reads; re-run command)
## §4.2 The 6 auto-stop properties + partial-reset hook — per-point compliance table
   (| # | item property | PRD §4.5 expected | code actual (file:line) | test | verdict ✅ |)
   (a) _idle_watchdog ticks ~1s   (b) deadline re-check under _lock (late partial cancels)   (c) _maybe_auto_stop
       disarms immediate (not drain)   (d) journal INFO line   (e) starts idle-unload clock (_disarmed_monotonic)
   (f) 0 disables   (+) partial-reset hook (_touch_speech ← on_speech ← _partial)
## §4.3 Test evidence  (the -k command + count + key test names per property)
## §4.4 Non-defect nuances  (two watchdogs/two clocks; atomic float store not lock-guarded; _shutdown.wait(1.0) not
       time.sleep; watchdog swallows own exceptions; abort-after-autostop effectively skipped; INFO line + toast via
       _disarm; 0-disable before lock)
## §4.5 Conclusion  (COMPLIANT; certifies PRD §4.5 (auto-disarm-after-30s, partials-reset, lock-gated re-check,
       0-disables, starts-unload-clock) + acceptance #5's forgotten-hot-mic guard)
```

### Integration Points

```yaml
REPORT (the deliverable):
  - append: "plan/006_862ee9d6ef41/architecture/gap_lifecycle.md += '# §4 — Idle Auto-Stop Watchdog (P1.M2.T2.S4)' (below last section)"
  - verdict: "✅ COMPLIANT — all 6 properties (a-f) + partial-reset hook pass (daemon.py + config.py file:line)"
  - ties-to: "PRD §4.5 (Idle auto-stop) + §7 acceptance #5 (survives 2min silence, no hallucination, trivial CPU)"
CONSUMERS:
  - P1.M5.T5 (acceptance cross-check): "maps acceptance #5 (forgotten-hot-mic guard; 2min silence stable) to this §4's evidence"
  - §3 (idle-unload): "this §4 HANDS OFF to §3 — auto-stop's _disarm stamps _disarmed_monotonic, which §3's _idle_unload_watchdog reads"
  - future maintainers: "the reference for any auto-stop change (threshold, partial-reset hook, tick interval, disarm hand-off)"
SCOPE GUARD:
  - git status: "ONLY architecture/gap_lifecycle.md (appended). No voice_typing/*, no tests/*."
```

## Validation Loop

### Level 1: Re-verification (read the code — read-only)

```bash
cd /home/dustin/projects/voice-typing
# Re-locate the ~6 auto-stop regions (line numbers may drift — re-grep):
grep -nE 'def _idle_watchdog|def _maybe_auto_stop|def _disarm|def _arm\b|def _touch_speech|def _on_partial|def _build_callbacks|on_speech|def _safe_abort|_last_speech_monotonic|_disarmed_monotonic|auto_stop_idle_seconds|_shutdown\.wait' voice_typing/daemon.py voice_typing/config.py
# Read each region (_idle_watchdog@1148, _maybe_auto_stop@1119, _disarm@1002, _arm@987, _touch_speech@1029,
# _build_callbacks@219/237-238, _load_host wiring@751/757, _safe_abort@1335 in daemon.py; auto_stop_idle_seconds@65
# in config.py) and confirm (a)-(f) + the partial-reset hook match PRD §4.5.
# Expected: COMPLIANT (research §2).
```

### Level 2: Test evidence (re-run the auto-stop slice — the audit's evidence)

```bash
cd /home/dustin/projects/voice-typing
# AGENTS.md Rule 1: inner timeout (mandatory) + outer bash timeout. Mocked CUDA -> fast (~1s), but timeout is non-negotiable.
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or auto_stop or watchdog'
# Expected: 27 passed, 166 deselected (record the actual count in the report).
```

### Level 3: Report well-formedness

```bash
cd /home/dustin/projects/voice-typing
# Confirm gap_lifecycle.md has the §4 section + cites file:line + records the verdict:
grep -nE '§4|Idle Auto-Stop|Bottom line|27 passed|COMPLIANT|_idle_watchdog|_maybe_auto_stop|_disarm|auto_stop_idle_seconds|partial.*reset|_touch_speech|_disarmed_monotonic|acceptance #5' plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
# Expected: the §4 heading, the ✅ bottom line, the compliance table (with daemon.py/config.py:line), the test count,
# the nuances (two watchdogs / atomic float / _shutdown.wait / swallow / abort-skipped / 0-before-lock), all present.
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
- [ ] Re-verified the ~6 auto-stop regions (`_idle_watchdog`/`_maybe_auto_stop`/`_disarm`/`_arm`/`_touch_speech`/`_build_callbacks`/`_load_host`-wiring/`_safe_abort` in daemon.py; `auto_stop_idle_seconds` in config.py) — all COMPLIANT.
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or auto_stop or watchdog'` → recorded pass count (baseline 27).
- [ ] `gap_lifecycle.md` contains the `# §4 — Idle Auto-Stop Watchdog (P1.M2.T2.S4)` section (appended below the last section).

### Feature (Audit) Validation
- [ ] Compliance table covers (a) `_idle_watchdog` ticks ~1s, (b) deadline re-check under `_lock`, (c) disarms immediate (not drain), (d) journal INFO line, (e) starts idle-unload clock, (f) 0 disables — PLUS the partial-reset hook — each COMPLIANT with file:line.
- [ ] Verdict ✅ COMPLIANT; conclusion ties to PRD §4.5 + acceptance #5 (forgotten-hot-mic guard; 2min silence stable).
- [ ] If a real defect was found, it is fixed + recorded; otherwise "none — compliant per audit."

### Code Quality Validation
- [ ] §4 section mirrors the `gap_*.md` §N-append format (consistent with this file's §2 @L201 + `gap_daemon_loop.md` §2 @L156).
- [ ] Non-defect nuances recorded (two watchdogs/two clocks; atomic float store not lock-guarded; `_shutdown.wait(1.0)` not `time.sleep`; watchdog swallows own exceptions; abort-after-autostop effectively skipped; INFO line + toast via `_disarm`; 0-disable before lock) so they aren't mistaken for gaps.
- [ ] Only `architecture/gap_lifecycle.md` written (`git status --short`).

### Documentation & Deployment
- [ ] Report is self-contained (scope, method, evidence, verdict) — a future maintainer can re-run the audit from it.
- [ ] Adjacent concerns correctly deferred (lazy-load states → §1; IPC → §2; idle-unload/teardown → §3; phase lifecycle → P1.M2.T1; lite → M2.T3; toast wiring → M3).

---

## Anti-Patterns to Avoid

- ❌ Don't edit `voice_typing/daemon.py` / `config.py` or any test — this is an AUDIT; the auto-stop watchdog is COMPLIANT (no defect). Edit ONLY if re-verification surfaces a real defect (Critical #1).
- ❌ Don't run pytest without `timeout 300` (inner) + the bash-tool timeout — AGENTS.md Rule 1 (the repo has hang vectors) (Critical #2).
- ❌ Don't assert compliance without file:line evidence — every table row must cite the daemon.py/config.py line(s) (Critical #3).
- ❌ Don't mistake the nuances for defects: two watchdogs/two clocks (auto-stop `_idle_watchdog`/`_last_speech_monotonic` vs idle-unload `_idle_unload_watchdog`/`_disarmed_monotonic`); the atomic-float-store-not-lock-guarded `_last_speech_monotonic` (the lock-gated re-read IS the §4.5 mechanism); `_shutdown.wait(1.0)` not `time.sleep`; the exception-swallowing watchdog; abort-after-autostop effectively skipped; the 0-disable check before `_lock` (Critical #4).
- ❌ Don't confuse §3 and §4 — §3 (S3) = idle-UNLOAD watchdog + bounded teardown (fires DISARMED, tears DOWN models); §4 (THIS) = idle-AUTO-STOP watchdog (fires LISTENING, disarms the MIC). They COMPOSE (auto-stop's `_disarm` stamps `_disarmed_monotonic` → §3 reads it); they do not overlap. Re-auditing the unload watchdog/teardown is S3's job (Critical #6).
- ❌ Don't create a NEW standalone file — APPEND §4 to `gap_lifecycle.md` (the item OUTPUT). §1/§2 exist; §3 is appended in parallel; the `# §4` heading composes; append §4 at EOF (Critical #5).
- ❌ Don't "simplify" the lock-gated re-check, the atomic-float-store clock, the `_shutdown.wait(1.0)` tick, or the two-watchdog split — all are load-bearing for the §4.5 contract (partial-reset correctness, prompt shutdown exit, auto-stop/unload composition). Record them as load-bearing.
- ❌ Don't use bare `python`/`pytest` (zsh aliases) — `.venv/bin/python -m pytest` (Critical #7).
- ❌ Don't forget the acceptance #5 linkage — the auto-stop watchdog IS the forgotten-hot-mic guard behind §7 #5 (Critical #8).

---

## Confidence Score

**10/10** — one-pass success likelihood. This is a read-only audit whose findings are **pre-verified** (research note §2: every property mapped to `daemon.py`/`config.py` file:line with the COMPLIANT verdict) and whose test evidence is **re-ran live** (the contract's `-k` slice = 27 passed, 166 deselected in 1.07s). The 6 properties + the partial-reset hook are a direct reading of the in-tree code (`_idle_watchdog`'s `_shutdown.wait(1.0)` tick; `_maybe_auto_stop`'s threshold≤0 short-circuit + `with self._lock` re-check + `logger.info` + `_disarm()`; `_disarm`'s `_disarmed_monotonic=time.monotonic()` hand-off; `_touch_speech`'s `_last_speech_monotonic=now()` wired via `on_speech` ← `_partial` ← `_load_host`). The deliverable is a report section in an established format (sibling §2 @L201 + `gap_daemon_loop.md` §2 @L156), appended to a file that already has §1/§2 (and §3 in parallel). Residual risk is only line-number drift, which the grep re-location step (Level 1) catches immediately.