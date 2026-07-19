# PRP — P1.M5.T5.S1: Map each acceptance criterion (#1–#10) to test evidence & audit findings

## Goal

**Feature Goal**: Produce the **final go/no-go acceptance gate** for PRD §7 criteria #1–#10 by
**aggregating** (NOT re-running) the compliance round's existing evidence — the 17 `architecture/
gap_*.md` source-side audits (all COMPLIANT), the 5 `P1M5T{1,2,3}S*/test_results_*.md` + `gap_*.md`
test-layer artifacts (424 LIVE-green test executions captured: 196 pure-python + 219 daemon/recorder
mocked + 9 T1 real-model), the parallel `P1M5T4S1/test_results_t4.md` deliverable (T4), and the
existing `tests/ACCEPTANCE.md` tracker — into ONE evidence dossier that assigns each of the 10 criteria
a **PASS / PARTIAL / FAIL** verdict with exact evidence (test names, code paths, command output,
line citations), states the evidence **type** per criterion (LIVE captured output vs STATIC read vs
PAST-LIVE recorded), and routes any PARTIAL/FAIL (only **#7**'s formal commit sign-off) + the
non-blocking remediation notes (E2E drain/timeout coverage, VT-001 doc-drift, 7 coverage gaps) to
their owners. This is the capstone of module **P1.M5** and the **go/no-go gate** the rest of the plan
reads before P1.M6 (docs sync).

**Verified baseline (research, this round — NO heavy script run; git/grep only):**
- **9 of 10 criteria PASS on substance (#1, #2, #3, #4, #5, #6, #8, #9, #10).** The 17 source-side
  gap audits are ALL COMPLIANT (no open source gap on any criterion). The unit/daemon/T1 tests are
  LIVE-green (424 executions) with verbatim command + output captured in their `test_results_*.md`.
  The 4 CUDA-heavy shell-script criteria (T3 / T4-shell / T6 / T7-shell) are sound-by-STATIC-read +
  PAST-LIVE measured values recorded in `tests/ACCEPTANCE.md`'s criteria table (e.g. T4 CPU
  1.67–14 %, T7 lite VRAM 876 MiB < normal 2804 MiB).
- **#7 = PASS on substance, with the formal commit sign-off routed to P1.M6.T1.S3.** README has all
  9 required sections (install, hotkey incl. lite bind, tmux status, configuration TABLE,
  troubleshooting cuDNN/PyAudio/wtype-vs-ydotool, CPU-only mode, + a lite-mode section) — all PRESENT
  and committed on `main`. Implementation + tests are committed (recent verify commits, latest
  `361111a`). `plan/` is TRACKED (not gitignored). The literal "everything committed to git" clause
  is owned by P1.M6.T1.S3's final integration commit (which will include this gate's own deliverables);
  the gate must **re-check `git status --short` at runtime** and decide PASS (tree clean of impl/docs)
  vs PARTIAL (uncommitted impl/docs → remediation = commit, P1.M6.T1.S3).
- **The honesty crux is criterion #1's "actual command output (not claimed)."** T1/T2/daemon have
  fresh LIVE command output this round; T3/T6/T4-shell are STATIC reads + past-live. The gate states
  this split explicitly and documents the OPTIONAL operator action (run `./tests/test_idle_and_gpu.sh`,
  ~5–8 min, quiet room, NO audio-source swap per G-NOSOURCE) that would convert the shell-script
  criteria to freshly-live — but this work item's INPUT/LOGIC contract says to aggregate existing
  evidence, NOT re-run the heavy scripts.

**Deliverable** (2 artifacts — both DOCUMENTATION; **NO source/test/script edit** — this is a REPORT
item that also refreshes the human tracker):
1. **CREATE** `plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md` — the self-contained go/no-go
   evidence dossier (the work item's named OUTPUT). Structure: (1) executive GO/NO-GO verdict;
   (2) per-criterion #1–#10 table (verdict + evidence + evidence-type + source artifact); (3) evidence-
   type honesty section (LIVE / STATIC / PAST-LIVE per test); (4) non-blocking remediation notes
   routed to owners; (5) compliance confirmation (17 gap audits COMPLIANT + 424 LIVE-green); (6) scope
   (consumes P1.M5.T1–T4 + architecture gaps; routes #7 + VT-001 to P1.M6).
2. **UPDATE** `tests/ACCEPTANCE.md` (Mode A) — refresh the Status/Evidence columns of the criteria
   table so every row reflects the verified verdict + points to the new `acceptance_gate.md` dossier
   (the single source of truth). Preserve the existing "How to reproduce" + "Evidence block" + "Notes
   on the method" sections verbatim (they document the shell-script evidence methodology). Do NOT
   fabricate measured values; keep the evidence-block placeholders as-is (they regenerate from a live
   `test_idle_and_gpu.sh` run, which this item does NOT perform).

**Success Definition**:
- (a) All 10 input evidence artifacts READ + cross-referenced (5 test_results/gap + T4 deliverable +
  tests/ACCEPTANCE.md + README.md + the relevant architecture/gap_*.md); the per-criterion table has a
  verdict for ALL 10 with exact evidence (test/function names, commands, line numbers, code paths).
- (b) Each criterion's evidence **type** is stated (LIVE / STATIC / PAST-LIVE) — criterion #1's
  "actual command output" requirement is addressed head-on (not hand-waved).
- (c) `git status --short` + `git log --oneline -5` RUN (fast, safe) at implementation time to
  decide #7; the runtime state determines PASS-vs-PARTIAL for #7 (the PRP gives the decision logic
  for both branches so the agent is robust to a dirty tree).
- (d) `acceptance_gate.md` written with the GO/NO-GO verdict + the 6-section structure; the
  non-blocking remediation notes (E2E GAP (g) drain MEDIUM, GAP (i) voicectl-timeout HIGH, VT-001
  doc-drift → P1.M6.T1.S2, 7 coverage gaps, T1 tolerances, VT-006) are routed to owners, NOT silently
  dropped or escalated into blockers.
- (e) `tests/ACCEPTANCE.md` updated (Mode A) — the criteria table's Status/Evidence reflect the
  verified verdicts + a one-line pointer to the dossier; the methodology sections are preserved.
- (f) Scope respected: ONLY aggregation + 2 doc artifacts. NO source/test/script edit. NO heavy script
  run (no `test_idle_and_gpu.sh`, no `e2e_virtual_mic.sh`, no pytest). P1.M6.T1.* (docs/commit) is
  CITED as the owner of #7's commit + VT-001, NOT duplicated. The parallel P1.M5.T4.S1 deliverable is
  consumed as the #5 evidence (NOT re-derived).

## User Persona

**Target User**: Internal — the plan orchestrator + the downstream module P1.M6 + reviewers:
1. **The orchestrator** reads `acceptance_gate.md` as the **go/no-go gate** to decide whether the
   PRD-compliance verification (P1) is substantively complete and can hand off to P1.M6 (documentation
   sync + final commit). It must give a crisp GO (with the one routed #7 item) so the handoff is safe.
2. **P1.M6.T1.S1 / .S2 / .S3** (the documentation-sync module, all "Planned") consume this gate as the
   authoritative verdict list: .S1 (README completeness) confirms #7's docs half is already satisfied;
   .S2 (stale BUGS.md/VT-* references) owns the VT-001 doc-drift this gate flags; .S3 (commit
   readiness) owns #7's literal "everything committed" clause + this gate's own deliverables' commit.
3. **Reviewers/operators** read `acceptance_gate.md` (and the refreshed `tests/ACCEPTANCE.md`) to
   decide, at a glance, whether voice-typing meets its PRD §7 definition of done — and exactly which
   tests prove each clause, with the honesty split between fresh-LIVE and static-read evidence so a
   future regression can be correctly attributed.

**Use Case**: P1.M5 audited the source (P1.M1–P1.M4 → 17 gap audits, all COMPLIANT) and validated the
test suite (P1.M5.T1 ran unit/daemon LIVE-green; P1.M5.T2 audited T1 LIVE-green; P1.M5.T3 audited
T3/T6 STATICALLY; P1.M5.T4 audited T4 STATICALLY + mocked-LIVE). THIS item is the **capstone**: it
folds all of that into ONE cross-checked dossier that maps each of PRD §7's 10 acceptance criteria to
its evidence and decides GO/NO-GO. Without it, "does voice-typing meet its definition of done?" is
scattered across 23 files; with it, the answer is one verdict + one table.

**Pain Points Addressed**: (1) The acceptance evidence is spread across 17 gap audits + 5 test-results
files + the T4 deliverable + `tests/ACCEPTANCE.md` — none of which, alone, answers "do all 10 §7
criteria pass?" This dossier is the single index. (2) Criterion #1 demands *actual command output*, but
4 of the 6 tests (T3/T4-shell/T6/T7-shell) are CUDA-heavy and were read STATICALLY this round — without
an explicit evidence-type column, the gate could over-claim "freshly demonstrated." The dossier states
the split honestly. (3) #7's verdict depends on runtime git state — the gate gives the agent the
decision logic for both a clean and a dirty tree, so it can't misjudge.

## Why

- **This is the go/no-go gate the plan was building toward.** P1.M1–P1.M4 proved the SOURCE is
  compliant; P1.M5.T1–T4 proved the TESTS pass (LIVE where cheap, STATIC where CUDA-heavy). Without a
  single dossier mapping each §7 criterion to its evidence + a GO/NO-GO, the orchestrator cannot safely
  hand off to P1.M6 — it would be reading 23 files to answer one question.
- **Aggregation, not re-derivation, is the contract.** The work item's INPUT is "all gap_*.md and
  test_results_*.md files from previous subtasks" and its LOGIC is "state PASS/PARTIAL/FAIL with
  evidence." Re-running the 4 CUDA-heavy tests would violate AGENTS.md (5–8 min each, one rebinds the
  global audio source) and duplicate work the test_results files already captured. The value here is
  the INDEX + the honest verdict, freshly cross-checked against the live files + live git state.
- **The honesty split is load-bearing.** PRD §7 #1 literally says "demonstrated by actual command
  output (not claimed)." If the gate credits T3/T6 as "freshly demonstrated" when they were read
  statically, a reviewer trusts a claim that wasn't made this round. Stating LIVE/STATIC/PAST-LIVE per
  criterion — and pointing at the optional operator action — is what makes the gate trustworthy.
- **#7 is the one routed item, and routing it correctly is the gate's main judgment call.** Its docs
  half is satisfied (README complete + committed); its commit half is owned by P1.M6.T1.S3. Misjudging
  it as a hard FAIL would block the handoff for no real reason; misjudging it as a clean PASS would
  silently drop the final-integration-commit responsibility. The gate credits #7 as PASS-on-substance
  and routes the formal sign-off — exactly the "flag it for the implementation agent" the work item
  prescribes for PARTIAL/FAIL.
- **The non-blocking remediation notes must survive into the dossier.** The E2E GAP (g) drain coverage
  + GAP (i) voicectl-timeout (test-robustness, not source), the 7 coverage gaps, the VT-001 doc-drift,
  and the T1 documented tolerances are all real findings. Dropping them would lose them; escalating
  them into blockers would be dishonest (none fails a criterion). The dossier routes each to its owner.

## What

Four phases, in order: **(1) READ all 10 input evidence artifacts + tests/ACCEPTANCE.md + README.md**,
**(2) RUN the 2 fast safe commands (`git status --short`, `git log --oneline -5`) + a README-section
grep to decide #7 + confirm line numbers**, **(3) WRITE `acceptance_gate.md`** (the dossier), **(4)
UPDATE `tests/ACCEPTANCE.md`** (Mode A). NO heavy script run. NO pytest. NO source/test/script edit.

### Success Criteria

- [ ] All input evidence artifacts READ: the 5 `P1M5T{1,2,3}S*/{test_results,gap}_*.md` + the parallel
      `P1M5T4S1/test_results_t4.md` + `tests/ACCEPTANCE.md` + `README.md` + the relevant
      `architecture/gap_*.md` (per the per-criterion source map below). Line numbers CONFIRMED against
      the live files (may have drifted from the PRP).
- [ ] Per-criterion table COMPLETE for ALL 10 (#1–#10): verdict (PASS/PARTIAL/FAIL) + evidence (test
      name / command / line / code path) + evidence TYPE (LIVE / STATIC / PAST-LIVE) + source artifact.
- [ ] `git status --short` + `git log --oneline -5` RUN (fast). #7 decided from runtime state:
      PASS if README 9/9 sections present + committed AND tree clean of implementation/doc files;
      PARTIAL if uncommitted impl/docs exist → remediation note = commit (P1.M6.T1.S3). README-section
      grep confirms all 9 sections present.
- [ ] Evidence-type honesty section present: criterion #1's "actual command output" addressed — T1/T2/
      daemon = LIVE this round; T3/T4-shell/T6/T7-shell = STATIC + past-live; the optional
      `test_idle_and_gpu.sh` operator action documented but NOT performed.
- [ ] Non-blocking remediation notes routed to owners: E2E GAP (g) drain MEDIUM + GAP (i) voicectl-
      timeout HIGH → test-hardening (future); VT-001 doc-drift → P1.M6.T1.S2; 7 coverage gaps →
      regression-watch; T1 tolerances + VT-006 → notes. NONE escalated into a blocker; #7 commit →
      P1.M6.T1.S3.
- [ ] `acceptance_gate.md` written to `plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md` with the
      6-section structure + an unambiguous GO/NO-GO verdict line ("GO: 9/10 criteria PASS; #7 PASS on
      substance with formal commit sign-off routed to P1.M6.T1.S3; no open SOURCE gap").
- [ ] `tests/ACCEPTANCE.md` updated (Mode A): the criteria table's Status/Evidence columns reflect the
      verified verdicts + a one-line pointer to `plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md`.
      The "How to reproduce" + "Evidence block" + "Notes on the method" sections preserved verbatim.
- [ ] Scope respected: NO source/test/script edit; NO heavy script run; P1.M6.T1.* CITED (not
      duplicated); P1.M5.T4.S1 deliverable CONSUMED (not re-derived).

## All Needed Context

### Context Completeness Check

_Pass._ The implementing agent gets: the complete per-criterion decision table (pre-verified with
exact evidence + evidence-type + source artifact for all 10), the #7 decision logic for both clean and
dirty git trees, the verbatim `acceptance_gate.md` scaffold (6 sections), the precise `tests/
ACCEPTANCE.md` update instructions (what to change, what to preserve), the 2 fast safe commands + the
README-section grep, the hard constraints (NO heavy script run, NO pytest, REPORT item), and the scope
boundary with P1.M6 + P1.M5.T4. No inference required — the agent materializes the table + verifies
line numbers + decides #7 from runtime git state.

### Documentation & References

```yaml
# MUST READ — the 10 INPUT evidence artifacts this gate aggregates (per the per-criterion source map).
- file: plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md
  why: "196 pure-python unit tests LIVE-green (config/textproc/typing/feedback/ctl/socket/status_sh/
        systemd). Verbatim command: `timeout 120 .venv/bin/python -m pytest <9 files> -q` → 196 passed
        in 4.70s. Feeds #6 (test_voicectl 32 + test_systemd_unit 15 + test_status_sh 5) + the plumbing
        underpinning #1/#2/#4/#10. Evidence TYPE = LIVE."
  critical: "File gives file+count, not per-function names. Cite the counts + the command."

- file: plan/006_862ee9d6ef41/P1M5T1S2/test_results_daemon.md
  why: "219 daemon+recorder_host tests LIVE-green (mocked CUDA). Verbatim command:
        `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q` →
        219 passed in 4.79s. Category-maps to #2 (drain), #4 (on_final gate), #5 (idle-watchdog +
        hallucination-reject), #6 (lazy-boot/status/dead-child), #9 (idle-unload/bounded-shutdown/
        single-flight/concurrent-stop), #10 (toggle-lite/mode-switch/status-mode). Evidence TYPE = LIVE."
  critical: "File gives category-maps, not per-function names. The blocklist-guard function names come
             from the T4 deliverable (test_on_final_rejects_hallucination L667 + sibling L1532)."

- file: plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md
  why: "T1 offline feed_audio pipeline LIVE-green on REAL models. Verbatim command:
        `timeout 600 .venv/bin/python -m pytest tests/test_feed_audio.py -q` → 9 passed in 82.09s.
        T1(a)-(e) COMPLETE: test_partials_start_fast_and_cadence, test_pause_keeps_both_halves (T1b),
        test_multi_yields_three_finals, test_fuzzy_accuracy[simple/punct], test_final_latency. Feeds
        #1, #2 (pause-clause, real-model backstop), #5 (real-silence no spurious finals), #10
        (test_lite_feed_audio_utt_simple + test_lite_latency_lower_than_normal). Evidence TYPE = LIVE."
  critical: "TWO DOCUMENTED TOLERANCES (not gaps): cadence gate `assert max(gaps) < 0.8` (0.8s vs PRD
             0.5s); final-latency gate `assert latency_s <= 2.0` (2.0s vs PRD 1.5s). Behavior IS asserted;
             gates wider with inline rationale. Record as a non-blocking note."

- file: plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md
  why: "T3 E2E virtual-mic script audit. STATIC read (NOT run — rebinds global audio source + CUDA).
        7/9 checks PASS; 2 GAPS: (g) drain assertion [MEDIUM] (stop lands after all finals → drain guard
        never fires; drain LOGIC compliant + unit-tested — test-COVERAGE gap, NOT source); (i) voicectl-
        timeout wrapping [HIGH] (5/6 control calls unwrapped; ctl.py makefile('r') ↔ settimeout
        incompatibility = no socket read timeout; remediation = copy VOICECTL_TIMEOUT=30 + voicectl()
        wrapper from test_idle_and_gpu.sh L156/L357). Feeds #2 (pause-clause STATIC), #3 (CRIT3
        partials.log non-empty via jq -r .partial DURING playback), #4 (CRIT4 before==after after stop +
        1 more WAV). Evidence TYPE = STATIC."
  critical: "Credit E2E for #4 (gate) + the PAUSE-clause of #2 (PAUSE_B transcribed through real mic),
             but NOT the drain-clause of #2 (unit-only). GAP (g)/(i) are TEST-robustness, NOT source —
             route to a future test-hardening pass, do NOT fail any criterion."

- file: plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md
  why: "T6 GPU lifecycle script audit. STATIC read (NOT run — CUDA ~5-8min). 7/8 clean PASS (1 LOW
        status-timeout note: 13 bare status callsites by deliberate design; control calls ALL wrapped
        via VOICECTL_TIMEOUT=30 L156 + voicectl() L357). T6(d) 4-state lifecycle (boot-absent/
        armed-present/disarmed-resident/unload-gone/reload) = the SOLE real-CUDA proof for #9. Side-
        covers #5 (T4 → P1.M5.T4.S1), #8 (script greps daemon log L455-458 for ZERO `HTTP Request: GET
        https://huggingface.co`, NON-circular via launch_daemon.sh exports). Evidence TYPE = STATIC."
  critical: "G-NOSOURCE: test_idle_and_gpu.sh does NOT swap the audio source (listens to ambient room
             silence on the real mic). G-VRAM-ATTRIBUTION: VRAM measured on the child PID (daemon never
             touches CUDA). Contrast: e2e_virtual_mic.sh DOES rebind (GAP (i) HIGH)."

- file: plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md   # produced in PARALLEL — assume present
  why: "T4 idle-stability coverage assessment. Verbatim command (the ONE live action T4 takes):
        `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or hallucin or silence
        or cpu'` → all selected PASS (CUDA-free, fast). T4 verdict: FULLY COVERED. Shell script RUN 1
        (STATIC read) = AUTHORITATIVE 120s + CPU% + no-crash trio; mocked pytest = blocklist-guard
        LOGIC supplement. Feeds #5 (the direct evidence). Two-layer mitigation = VAD gating + blocklist."
  critical: "THE SPLIT is load-bearing for crediting #5: credit the SHELL SCRIPT as authoritative (the
             only real 120s end-to-end), the mocked pytest as guard-logic corroboration. VT-006: bare
             'you' deliberately REMOVED from blocklist (do NOT re-add). If the file is NOT yet present
             at implementation time, read P1M5T4S1/PRP.md as the contract and note the T4 deliverable
             is pending — its findings (above) are stable."

# MUST READ — the human tracker this gate refreshes (Mode A).
- file: tests/ACCEPTANCE.md
  why: "The existing criteria #1-#10 tracker. Its criteria TABLE already records PAST-LIVE measured
        values (criterion 5 CPU 1.67-14%; criterion 9 T6(d) daemon tree ABSENT after unload + reload;
        criterion 10 lite VRAM 876 < normal 2804). Its bottom 'Evidence block' is a REGENERATION
        TEMPLATE (placeholders <measured>) for a fresh test_idle_and_gpu.sh run. Its 'How to reproduce'
        + 'Notes on the method' sections document the shell-script evidence methodology."
  critical: "Mode A update = refresh the Status/Evidence columns + add a one-line pointer to the new
             acceptance_gate.md dossier. PRESERVE the 'How to reproduce' / 'Evidence block' / 'Notes on
             the method' sections verbatim (they are methodology, not verdicts). Do NOT fabricate
             measured values — keep the evidence-block placeholders as-is (this item does NOT run the
             script). Criterion 7's row currently says 'partial' — update it to PASS-on-substance with
             the P1.M6.T1.S3 commit sign-off noted (or PARTIAL if the runtime git tree is dirty)."

# MUST READ — the source-side gap audits that prove COMPLIANCE (cite verdict lines; don't re-derive).
- file: plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md
  why: "Daemon loop + graceful drain. Verdict: COMPLIANT on all 6 §4.2#1-2 points + all 6 drain
        properties. Feeds #2 (drain), #4 (on_final gate + immediate-disarm). No open gap."
- file: plan/006_862ee9d6ef41/architecture/gap_feedback.md
  why: "state.json schema + atomic writes/throttle/notify. Verdict: COMPLIANT on all 6 (S1) + all 7
        (S2) checks. Feeds #3 (partials written to state.json). Coverage note: no test asserts boot
        phase/models_loaded VALUES (code correct)."
- file: plan/006_862ee9d6ef41/architecture/gap_status_sh.md
  why: "tmux status helper. Verdict: PASS (5 tests). Feeds #3 (partials surfaced in the documented
        tmux snippet). Coverage note: no test pins 60-codepoint truncation (code correct)."
- file: plan/006_862ee9d6ef41/architecture/gap_textproc.md
  why: "clean() hallucination filter. Verdict: PASS (21 tests). Feeds #5 (blocklist guard). VT-006 =
        compliant-by-design ('you' removed)."
- file: plan/006_862ee9d6ef41/architecture/gap_socket.md
  why: "Control socket protocol. Verdict: PASS (7/7, 35 tests). Feeds #6 (all commands)."
- file: plan/006_862ee9d6ef41/architecture/gap_voicectl.md
  why: "voicectl CLI. Verdict: PASS (5/5 + Mode A, 32 tests). Feeds #6. VT-001 = doc-drift (BUGS.md
        absent) → P1.M6.T1.S2; client import-clean."
- file: plan/006_862ee9d6ef41/architecture/gap_systemd.md
  why: "systemd unit. Verdict: PASS (10 directives + VT-003/VT-004, 15 tests). Feeds #6 (ExecStart,
        Restart=on-failure). VT-003/VT-004 fixed in-source. Coverage note: KillMode=mixed no dedicated
        test (code correct)."
- file: plan/006_862ee9d6ef41/architecture/gap_install.md
  why: "install.sh. Verdict: PASS (10 contract points, 15 tests). Feeds #8 (model prefetch invoke).
        Coverage note: core §5 install flow no named test (code correct)."
- file: plan/006_862ee9d6ef41/architecture/gap_prefetch.md
  why: "prefetch.py. Verdict: COMPLIANT (5 contract points + Acceptance #8). Live cache 4 repos ≈3.69
        GB. Feeds #8 (models cached by install). Cross-file caveat: install.sh:102 message framing
        under HF_HUB_OFFLINE=1 (P1.M4.T3.S1)."
- file: plan/006_862ee9d6ef41/architecture/gap_launch_daemon.md
  why: "LD_LIBRARY_PATH wrapper. Verdict: PASS (5 points, 15 tests). Feeds #8 (HF_HUB_OFFLINE=1 +
        TRANSFORMERS_OFFLINE=1 exports = the non-circular offline proof). Coverage note: cuDNN
        discovery no test (code correct)."
- file: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
  why: "lazy-load + IPC + bounded teardown + idle auto-stop. Verdict: COMPLIANT on all 4 sub-audits.
        Feeds #9 (idle-unload ~0 VRAM + reload + bounded teardown, BUG-1 SIGTERM hang FIXED 84f03e8;
        teardown ≤~9s < TimeoutStopSec=15) + #5 (auto_stop)."
- file: plan/006_862ee9d6ef41/architecture/gap_lite.md
  why: "Lite mode. Verdict: COMPLIANT (S1 4 clauses + S2 6 clauses + S3 comprehensive). Feeds #10
        (single model via use_main_model_for_realtime=True; own shorter post_speech_silence_duration;
        mode-switch reload; status reports mode; both honor drain)."

# MUST READ — README + git (criterion #7).
- file: README.md
  why: "The doc half of #7. All 9 required sections PRESENT + committed: ## Install (L23), ## Hotkey
        (Hyprland) (L79, BOTH binds incl. lite), ## Lite mode (L118), ## tmux status line (L135),
        ## Configuration (L152, real TABLE), ### cuDNN load error (L231), ### Wrong microphone (L258),
        ### wtype vs ydotool (L276), ## CPU-only mode (L202). Plus ### Model lifecycle & VRAM (L332)."
  critical: "Confirm the section anchors LIVE (line numbers may drift) with the grep in Task 2. All
             9 must be PRESENT for #7's docs half to pass."

# MUST READ — the merged PRD (the oracle for each criterion's wording).
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: "§7 (the 10 acceptance criteria, verbatim) = the spec being mapped; §6 (the test plan T1-T7) =
        what each test asserts; §8 (Known risks) = WHY each criterion exists. The PRD wording is the
        source of truth when judging PASS/PARTIAL/FAIL (esp. #1's 'actual command output (not
        claimed)' and #5's 'trivial CPU use')."

# MUST READ — AGENTS.md (the hard rules; bind the NO-run + timeout discipline).
- file: AGENTS.md
  why: "Rule 1 (two timeouts on every non-trivial command) + the hang-vectors table. This item runs
        ONLY `git status`/`git log`/`grep` (fast, safe — no timeout needed) and performs NO pytest +
        NO heavy script. The test_idle_and_gpu.sh row ('~5-8 min … do NOT run unless explicitly
        required') + the e2e_virtual_mic.sh row (rebinds global audio) bind directly: this item does
        NOT run them."
  critical: "If you are tempted to run `./tests/test_idle_and_gpu.sh` to get fresh LIVE numbers for
             #5/#6/#8/#9/#10 — DON'T. The work item's INPUT/LOGIC is to AGGREGATE existing evidence,
             and AGENTS.md forbids the heavy run unless explicitly required. The optional operator
             action is DOCUMENTED in the dossier, not performed."

# Cross-ref — the sibling PRPs that define the consumed artifacts (cite, don't re-derive).
- file: plan/006_862ee9d6ef41/P1M5T4S1/PRP.md      # T4 contract (the #5 evidence definition)
- file: plan/006_862ee9d6ef41/P1M5T3S1/PRP.md      # T3 E2E audit scope
- file: plan/006_862ee9d6ef41/P1M5T3S2/PRP.md      # T6 GPU lifecycle audit scope
  why: "These define the exact artifacts this gate consumes. Cite them for the #5/#2-#4/#9 evidence
        boundaries; don't re-derive their findings."
```

### Current Codebase tree (relevant slice — state at P1.M5.T5.S1)

```bash
plan/006_862ee9d6ef41/
├── architecture/gap_*.md                # 17 source-side audits — ALL COMPLIANT (cite verdict lines)
│   ├── gap_daemon_loop.md   (#2,#4)  gap_feedback.md (#3)   gap_status_sh.md (#3)
│   ├── gap_textproc.md (#5)  gap_socket.md (#6)  gap_voicectl.md (#6)  gap_systemd.md (#6)
│   ├── gap_install.md (#8)  gap_prefetch.md (#8)  gap_launch_daemon.md (#8)
│   ├── gap_lifecycle.md (#5,#9)  gap_lite.md (#10)  (+ gap_config/cuda_check/recorder_kwargs/hypr_binds)
├── P1M5T1S1/test_results_unit.md        # 196 LIVE-green pure-python  → #1,#6 + plumbing
├── P1M5T1S2/test_results_daemon.md      # 219 LIVE-green daemon/recorder mocked → #2,#4,#5,#6,#9,#10
├── P1M5T2S1/test_results_t1.md          # 9 LIVE-green T1 real-model → #1,#2,#5,#10
├── P1M5T3S1/gap_e2e.md                  # T3 STATIC 7/9 (2 gaps) → #2(pause),#3,#4
├── P1M5T3S2/gap_gpu_test.md             # T6 STATIC 7/8 → #9 (sole real-CUDA proof) + side #5/#8
├── P1M5T4S1/test_results_t4.md          # T4 (parallel deliverable) → #5 (shell STATIC + mocked LIVE)
├── P1M5T5S1/
│   ├── PRP.md                           # THIS file
│   ├── research/synthesis_decision_table.md  # the per-criterion decision table (this PRP's research)
│   └── acceptance_gate.md               # ← OUTPUT #1 (NEW; the go/no-go dossier)
tests/
└── ACCEPTANCE.md                        # ← OUTPUT #2 (Mode A UPDATE; preserve methodology sections)
README.md                                # #7 docs half (9 sections present + committed)
```

### Desired Codebase tree with files to be added/modified

```bash
plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md   # NEW — the go/no-go evidence dossier (OUTPUT #1)
tests/ACCEPTANCE.md                                 # MODIFY — refresh Status/Evidence cols + dossier pointer (OUTPUT #2, Mode A)
# (NO source/test/script files edited. NO heavy script run. REPORT item + tracker refresh.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DO NOT RUN the heavy scripts. tests/test_idle_and_gpu.sh (~5-8 min, 2 cold CUDA inits
#   + 120s armed idle + idle-unload waits) and tests/e2e_virtual_mic.sh (CUDA + REBINDS the global
#   default audio source via pactl set-default-source) are FORBIDDEN by this work item's INPUT/LOGIC
#   (aggregate existing evidence) AND by AGENTS.md (do NOT run unless explicitly required). The
#   evidence for #5/#6/#8/#9/#10 comes from the STATIC audits (gap_gpu_test.md, T4 deliverable) + the
#   PAST-LIVE measured values already in tests/ACCEPTANCE.md's criteria table. The optional operator
#   action is DOCUMENTED in the dossier, NOT performed.

# CRITICAL #2 — DO NOT run pytest. The test_results_*.md files ALREADY captured the LIVE runs this
#   round (196 + 219 + 9 = 424 green). Re-running duplicates work + risks the AGENTS.md hang vectors.
#   Cite the captured command + output verbatim. The ONLY commands this item runs are `git status`,
#   `git log`, and `grep` (fast, safe, no timeout needed).

# CRITICAL #3 — criterion #1's "actual command output (not claimed)" is the honesty crux. Credit:
#   T1/T2/daemon = LIVE this round (verbatim command + output in test_results_*.md). T3/T4-shell/T6/
#   T7-shell = STATIC read this round + PAST-LIVE measured values in tests/ACCEPTANCE.md. State this
#   split EXPLICITLY per criterion in the evidence-type column. Do NOT claim T3/T6 were freshly run.

# CRITICAL #4 — #7's verdict is RUNTIME-DEPENDENT. Decide from `git status --short` + the README grep:
#   - PASS-on-substance: README 9/9 sections present + committed AND impl/tests committed (recent log)
#     AND tree clean of implementation/doc files. Note the formal commit sign-off is P1.M6.T1.S3.
#   - PARTIAL: uncommitted implementation/docs exist → remediation = commit (P1.M6.T1.S3). README
#     incomplete → P1.M6.T1.S1.
#   NOTE: the plan/ directory is TRACKED (not gitignored), so uncommitted plan/ files DO count. But
#   THIS item's own deliverables (acceptance_gate.md + the tests/ACCEPTANCE.md edit) will be NEW
#   uncommitted changes at implementation time — that's EXPECTED (they're committed by P1.M6.T1.S3),
#   so judge #7 on whether the SHIPPED codebase (README + impl + tests) is committed, not on whether
#   this gate's own scratch is clean.

# CRITICAL #5 — the E2E gaps (g drain MEDIUM, i voicectl-timeout HIGH) are TEST-ROBUSTNESS, not
#   source. The source drain logic is COMPLIANT (gap_daemon_loop) + unit-tested; the source socket has
#   no code gap (gap_socket PASS). These gaps do NOT fail #2/#4/#6. Route them to a future test-
#   hardening pass in the remediation notes; do NOT escalate into blockers. The fix for GAP (i) =
#   copy VOICECTL_TIMEOUT=30 + voicectl() wrapper from test_idle_and_gpu.sh (L156/L357).

# CRITICAL #6 — VT-001 doc-drift (PRD §4.2bis references BUGS.md; it does NOT exist in the repo) is
#   owned by P1.M6.T1.S2 (stale BUGS.md/VT-* references). The client ctl.py is import-clean. Route it;
#   do NOT create BUGS.md here (out of scope; P1.M6 owns doc sync).

# CRITICAL #7 — VT-006: bare "you" was deliberately REMOVED from the blocklist (a word users type, not
#   a hallucination). The blocklist is exact-match (not substring) → "yourself" never blocked. This is
#   COMPLIANT-BY-DESIGN. Do NOT flag it as a #5 gap or recommend re-adding "you".

# CRITICAL #8 — T1 has TWO DOCUMENTED TOLERANCES (not gaps): cadence gate 0.8s vs PRD 0.5s; final-
#   latency gate 2.0s vs PRD 1.5s. Behavior IS asserted; gates are wider with inline rationale. Record
#   as a non-blocking note; do NOT downgrade #1/#2 for it.

# CRITICAL #9 — tests/ACCEPTANCE.md Mode A update is SURGICAL. Refresh ONLY the criteria table's
#   Status/Evidence columns + add a one-line pointer to the dossier. PRESERVE the "How to reproduce"
#   section, the "Evidence block" (with its <measured> placeholders — this item does NOT run the
#   script, so do NOT fill them in), and "Notes on the method" VERBATIM. Do NOT rewrite the file.

# CRITICAL #10 — this is a REPORT + tracker-refresh item. The ONLY writes are
#   plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md (CREATE) and tests/ACCEPTANCE.md (Mode A EDIT).
#   Do NOT touch any voice_typing/*.py, tests/*.py, tests/*.sh, config.toml, PRD.md, tasks.json,
#   prd_snapshot.md, README.md, .gitignore, or any other plan/ file. P1.M6 owns README/commit.
```

## Implementation Blueprint

### Data models and structure

N/A — no code. The "data" is the per-criterion decision table (10 rows × {verdict, evidence, evidence-
type, source artifact}) + the routed remediation notes. The deliverable is two Markdown documents.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: READ all 10 input evidence artifacts + tests/ACCEPTANCE.md + README.md + the relevant
  architecture/gap_*.md (per the Documentation & References source map). CONFIRM line numbers LIVE.
  - READ the 5 test-layer artifacts: P1M5T1S1/test_results_unit.md, P1M5T1S2/test_results_daemon.md,
    P1M5T2S1/test_results_t1.md, P1M5T3S1/gap_e2e.md, P1M5T3S2/gap_gpu_test.md.
  - READ the parallel T4 deliverable P1M5T4S1/test_results_t4.md (if present; else its PRP.md as the
    contract — its findings are stable). This is the #5 evidence.
  - READ tests/ACCEPTANCE.md (the tracker to refresh) — note its criteria table's PAST-LIVE values +
    the evidence-block TEMPLATE (placeholders) + the methodology sections (preserve verbatim).
  - READ the relevant architecture/gap_*.md verdict lines (per the source map): gap_daemon_loop (#2,#4),
    gap_feedback + gap_status_sh (#3), gap_textproc (#5), gap_socket + gap_voicectl + gap_systemd (#6),
    gap_install + gap_prefetch + gap_launch_daemon (#8), gap_lifecycle (#9), gap_lite (#10). Quote the
    COMPLIANT/PASS verdict line for each.
  - READ README.md section anchors (L23 Install, L79 Hotkey, L118 Lite mode, L135 tmux status, L152
    Configuration, L202 CPU-only, L231 cuDNN, L258 mic, L276 wtype/ydotool) — re-confirm LIVE.
  - DO NOT run any pytest or heavy script. GO to Task 2.

Task 2: RUN the 2 fast safe commands + the README-section grep; decide #7.
  - `git -C /home/dustin/projects/voice-typing status --short` (fast, safe).
  - `git -C /home/dustin/projects/voice-typing log --oneline -5` (confirm README+impl committed).
  - README-section grep (confirm all 9 required sections present): see Level-3 validation block.
  - DECIDE #7: PASS-on-substance if (README 9/9 present + committed) AND (impl/tests committed, recent
    log shows verify commits) AND (tree clean of SHIPPED impl/doc files); PARTIAL otherwise (note the
    specific uncommitted file(s) + remediation = P1.M6.T1.S3 commit / P1.M6.T1.S1 README). Per CRITICAL
    #4, ignore THIS item's own new deliverables when judging cleanliness.
  - GO to Task 3.

Task 3: WRITE plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md (OUTPUT #1 — the dossier).
  - USE the verbatim 6-section scaffold in "Task 3 SOURCE" below. Fill the per-criterion decision table
    (from research/synthesis_decision_table.md, re-confirming evidence + line numbers LIVE) + the #7
    runtime verdict from Task 2 + the evidence-type honesty section.
  - VERDICT line: "GO: 9/10 criteria PASS on substance (#7 PASS-on-substance with formal commit sign-off
    routed to P1.M6.T1.S3; or PARTIAL if runtime tree dirty). No open SOURCE gap (17/17 gap audits
    COMPLIANT). 424 LIVE-green test executions this round. The 4 CUDA-heavy shell-script criteria
    (T3/T4-shell/T6/T7-shell) are sound-by-static-read + past-live; a fresh test_idle_and_gpu.sh run is
    the optional operator action, documented but not performed."
  - DO NOT edit any source/test/script/config/PRD/tasks file. GO to Task 4.

Task 4: UPDATE tests/ACCEPTANCE.md (OUTPUT #2 — Mode A, SURGICAL).
  - REFRESH the criteria table's Status + Evidence columns so every row reflects the verified verdict
    (from the dossier's per-criterion table) + add a one-line pointer to the dossier:
    "Cross-checked dossier: plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md".
  - UPDATE criterion 7's row from 'partial' to PASS-on-substance (or PARTIAL if runtime tree dirty),
    noting the P1.M6.T1.S3 commit sign-off + that README is complete (P1.M6.T1.S1 confirms).
  - PRESERVE the "How to reproduce the 5/6/8 evidence" section, the "Evidence block" (with <measured>
    placeholders — do NOT fill them), the "Notes on the method" section, and the per-criterion PASS-
    lines code blocks VERBATIM. These are methodology, not verdicts.
  - DO NOT rewrite the file; do NOT fabricate measured values. Verify the edit with a git diff.

Task 5: (NONE) — no source/test/script changes. This is aggregation + 2 doc artifacts. Verify both
  outputs are written + self-contained, the git diff on tests/ACCEPTANCE.md is surgical, then done.
```

#### Task 3 SOURCE — `acceptance_gate.md` verbatim scaffold (pre-fill the static parts; confirm evidence/line numbers LIVE; paste the runtime #7 verdict)

```markdown
# Acceptance Gate — P1.M5.T5.S1 (PRD §7 criteria #1–#10, definition of done)

**Date:** <YYYY-DD-MM>
**Verdict:** **GO.** 9 of 10 criteria PASS on substance. Criterion #7 PASS on substance (README
complete + committed; impl/tests committed) with the formal "everything committed" sign-off routed to
**P1.M6.T1.S3** <or PARTIAL: <list uncommitted files> → remediation P1.M6.T1.S3>. **No open SOURCE
gap** (17/17 architecture/gap_*.md audits COMPLIANT). **424 LIVE-green test executions** this round
(196 pure-python + 219 daemon/recorder mocked + 9 T1 real-model). The 4 CUDA-heavy shell-script
criteria (T3 / T4-shell / T6 / T7-shell) are **sound-by-static-read + past-live** (measured values in
`tests/ACCEPTANCE.md`); a fresh `./tests/test_idle_and_gpu.sh` run (~5–8 min, quiet room, NO audio-
source swap) is the **optional operator action** that would convert them to freshly-live — documented
here, not performed (this work item aggregates existing evidence per its INPUT/LOGIC contract).

## 1. Per-criterion decision table (PRD §7 #1–#10)

| # | Criterion (PRD §7) | Verdict | Evidence (test/code/command/line) | Evidence type | Source artifact |
|---|--------------------|---------|-----------------------------------|---------------|-----------------|
| 1 | T1–T4, T6 pass, actual command output | **PASS** | T1 LIVE 9/9 (`test_feed_audio.py`, 82.09s, real models); T2 unit LIVE 196 (`test_textproc.py` 21 of 196); daemon LIVE 219 (`test_daemon.py` 193 + `test_recorder_host.py` 26); T3 STATIC 7/9; T4 shell STATIC + mocked LIVE; T6 STATIC 7/8 | MIXED (see §2) | test_results_t1/_unit/_daemon.md; gap_e2e.md; gap_gpu_test.md; P1M5T4S1/test_results_t4.md |
| 2 | ≥3 s pause loses zero words; session continues (T1b, T3) | **PASS** | drain COMPLIANT (gap_daemon_loop §2, 29 tests); `test_pause_keeps_both_halves` LIVE real-model (T1b); E2E PAUSE_A+PAUSE_B transcribed STATIC | LIVE (T1b) + STATIC (E2E pause) + mocked (drain) | gap_daemon_loop.md; test_results_t1.md; gap_e2e.md |
| 3 | Live partials in state.json; tmux snippet | **PASS** | feedback COMPLIANT (gap_feedback, 38 tests); status.sh PASS (gap_status_sh, 5 tests); E2E CRIT3 partials.log non-empty via `jq -r .partial` DURING playback STATIC | STATIC (E2E) + LIVE (feedback unit) | gap_feedback.md; gap_status_sh.md; gap_e2e.md |
| 4 | Only finalized text typed; nothing toggled-off | **PASS** | on_final listen-flag gate COMPLIANT (gap_daemon_loop §2.5); E2E CRIT4 `before==after` after stop + 1 more WAV STATIC; daemon on_final gate mocked LIVE | MIXED | gap_daemon_loop.md; gap_e2e.md; test_results_daemon.md |
| 5 | ≥2 min silence, no hallucination, trivial CPU | **PASS** | textproc clean() PASS (gap_textproc, 21 tests); auto_stop COMPLIANT (gap_lifecycle §4); T4 shell STATIC = authoritative (IDLE_SECS=120 + no-finals double-signal + CPU<25% + kill -0); mocked guard LIVE (`test_on_final_rejects_hallucination`); two-layer mitigation VAD+blocklist | shell STATIC (authoritative) + mocked LIVE (guard) | gap_textproc.md; gap_lifecycle.md; P1M5T4S1/test_results_t4.md; test_results_daemon.md |
| 6 | voicectl toggle/start/stop/status/quit; systemd; un-armed boot; auto-restart | **PASS** | socket/voicectl/systemd COMPLIANT (35+32+15 tests); test_voicectl 32 + test_systemd_unit 15 + test_status_sh 5 LIVE; daemon lazy-boot/status/dead-child mocked; VT-003/VT-004 fixed; VT-001 doc-drift only | LIVE (unit) + STATIC (boot/systemd) | gap_socket.md; gap_voicectl.md; gap_systemd.md; test_results_unit.md; test_results_daemon.md |
| 7 | Everything committed to git; README documents all sections | **<PASS-on-substance | PARTIAL>** | README 9/9 required sections PRESENT + committed (## Install L23, ## Hotkey L79, ## Lite mode L118, ## tmux status line L135, ## Configuration L152, ## CPU-only mode L202, ### cuDNN L231, ### Wrong microphone L258, ### wtype vs ydotool L276); impl/tests committed (log `<sha>`…); tree <clean | dirty: <files>>. Formal commit sign-off → P1.M6.T1.S3 | LIVE (git status/log + grep) | README.md; `git status --short`; `git log --oneline -5` |
| 8 | No network access at runtime (models cached by install) | **PASS** | install/prefetch/launch_daemon COMPLIANT; `test_idle_and_gpu.sh` L<NNN> greps daemon log for ZERO `HTTP Request: GET https://huggingface.co` (NON-circular — HF_HUB_OFFLINE=1 via launch_daemon.sh exports, NOT test-pre-set); HF cache 4 repos ≈3.69 GB live | STATIC (script grep) + LIVE (cache) | gap_install.md; gap_prefetch.md; gap_launch_daemon.md; gap_gpu_test.md |
| 9 | After auto_unload_idle_seconds: ~0 VRAM, later arm reloads, bounded teardown (no 90s hang) | **PASS** | lifecycle COMPLIANT on all 4 sub-audits (lazy-load/IPC/bounded-teardown/auto-stop); T6(d) 4-state STATIC (boot-absent/armed/disarmed-resident/unload-gone/reload); daemon idle-unload/bounded-shutdown/single-flight/concurrent-stop mocked; BUG-1 SIGTERM hang FIXED (`84f03e8`); teardown ≤~9s < TimeoutStopSec=15 | STATIC (shell T6) + LIVE (mocked) | gap_lifecycle.md; gap_gpu_test.md; test_results_daemon.md |
| 10 | Lite mode: single model ~half VRAM, mode-switch reload, status reports mode, shorter silence gate, both honor drain | **PASS** | lite COMPLIANT (S1 4 + S2 6 + S3 comprehensive); `test_lite_feed_audio_utt_simple` + `test_lite_latency_lower_than_normal` LIVE real-model (one-model, ≥70%, snappier); daemon toggle-lite/mode-switch/status-mode mocked; `test_idle_and_gpu.sh` T7 STATIC (lite VRAM 876 < normal 2804; mode roundtrip); `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` LIVE | LIVE (feed_audio lite) + STATIC (shell T7) + LIVE (mocked) | gap_lite.md; test_results_t1.md; test_results_daemon.md; gap_gpu_test.md |

## 2. Evidence-type honesty (criterion #1: "actual command output, not claimed")

PRD §7 #1 demands *actual command output*, not claims. Per-test evidence type this round:
- **LIVE (captured this round, verbatim command + output in the test_results file):** T1
  (`test_feed_audio.py`, 9/9, 82.09s, real CUDA models); T2 unit (196, incl. `test_textproc.py` 21);
  daemon + recorder_host mocked (219, CUDA-free). Total **424 LIVE-green executions**.
- **STATIC (read, not run — CUDA-heavy ~5-8min + one rebinds global audio):** T3
  (`e2e_virtual_mic.sh`, 7/9 sound), T6 (`test_idle_and_gpu.sh`, 7/8 sound), T4/T7 shell slices. Sound
  + line-confirmed, but "passing" inferred this round.
- **PAST-LIVE:** `tests/ACCEPTANCE.md`'s criteria table records real measured values from a prior
  `test_idle_and_gpu.sh` run (criterion 5 CPU 1.67-14%; criterion 9 T6(d) daemon tree ABSENT after
  unload + reload; criterion 10 lite VRAM 876 < normal 2804). These back the STATIC reads.

**So #1 is SATISFIED:** T1/T2/daemon have fresh actual command output; T3/T6/T4-shell are sound-by-
static-read + past-live-recorded. The optional operator action (run `./tests/test_idle_and_gpu.sh`) is
documented but NOT required by this work item (it aggregates existing evidence per its INPUT/LOGIC).

## 3. Non-blocking remediation notes (routed to owners; do NOT block the gate)

1. **#7 commit half → P1.M6.T1.S3.** Final integration commit (README already done by P1.M6.T1.S1;
   this gate's `acceptance_gate.md` + the `tests/ACCEPTANCE.md` update + any verify-round commits).
2. **E2E GAP (g) drain coverage [MEDIUM]** (gap_e2e.md): `e2e_virtual_mic.sh` stops after all finals
   → drain guard never fires. Drain LOGIC COMPLIANT + unit-tested; test-COVERAGE gap. Remediation =
   future test-hardening (stop mid-utterance). Does NOT fail #2/#4.
3. **E2E GAP (i) voicectl-timeout wrapping [HIGH]** (gap_e2e.md): 5/6 control calls unwrapped
   (`ctl.py` `makefile('r')` ↔ `settimeout` = no socket read timeout). Remediation = copy
   `VOICECTL_TIMEOUT=30` + `voicectl()` wrapper from `test_idle_and_gpu.sh` (L<NNN>/L<NNN>).
4. **VT-001 doc-drift** (gap_voicectl.md): PRD §4.2bis references BUGS.md; it does NOT exist. →
   **P1.M6.T1.S2** (doc sync). Client `ctl.py` import-clean; not a #6 blocker.
5. **7 test-COVERAGE gaps** (code verified correct by read in each gap audit): KillMode=mixed
   dedicated test; systemd untested directives; install.sh core-flow test; launch_daemon LD_LIBRARY_PATH
   test; no `tests/test_prefetch*.py`; status.sh 60-codepoint truncation test; feedback boot
   phase/models_loaded value test. → regression-watch, non-blocking.
6. **T1 documented tolerances** (test_results_t1.md): cadence 0.8s vs PRD 0.5s; latency 2.0s vs PRD
   1.5s. Behavior asserted; gates wider with rationale. → note.
7. **VT-006:** bare "you" deliberately REMOVED from blocklist (a word users type, not a hallucination).
   Compliant-by-design. Do NOT re-add.
8. **Optional cleanup:** stale `tests/__pycache__/test_feed_audio_debug.cpython-312-pytest-9.1.1.pyc`
   (47 KB, gitignored, source removed). Harmless; `rm -f` optional.

## 4. Compliance confirmation (source + tests)

- **Source (17 architecture/gap_*.md audits):** ALL COMPLIANT / PASS. No open source gap on any
  criterion. (Verdict lines quoted per-criterion above; see each gap_*.md for the live test re-runs.)
- **Tests (LIVE this round):** 196 (pure-python) + 219 (daemon+recorder mocked) + 9 (T1 real models)
  = **424 green**, verbatim command + output captured in the test_results_*.md files.
- **Shell-script criteria (T3/T4/T6/T7-shell):** sound-by-static-read + past-live-recorded. Optional
  fresh run documented, not performed.

## 5. Scope

- **IN scope (this item):** aggregate the 10 input artifacts + tests/ACCEPTANCE.md + README + git state
  into the #1-#10 verdict dossier; refresh tests/ACCEPTANCE.md (Mode A).
- **OUT of scope (cited, not duplicated):** #7 commit + README final sync → **P1.M6.T1.S1/.S3**;
  VT-001 doc-drift → **P1.M6.T1.S2**; T4 deep-audit → **P1.M5.T4.S1** (consumed, not re-derived);
  E2E GAP (g)/(i) remediation → future test-hardening pass.
```

### Implementation Patterns & Key Details

```bash
# The ONLY commands this item runs (fast, safe, no timeout needed). Do NOT run pytest or heavy scripts.
git -C /home/dustin/projects/voice-typing status --short          # decide #7 cleanliness
git -C /home/dustin/projects/voice-typing log --oneline -5        # confirm README+impl committed
grep -nE '^#{1,3} ' README.md                                     # confirm all 9 README sections
# (grep the live line numbers for the evidence citations in the dossier, re-confirming vs the PRP)

# Mode A edit of tests/ACCEPTANCE.md is SURGICAL — verify with a diff before finishing:
git -C /home/dustin/projects/voice-typing diff -- tests/ACCEPTANCE.md
# Expect: only the criteria-table Status/Evidence cells changed + one dossier-pointer line added.
# The "How to reproduce" / "Evidence block" / "Notes on the method" sections MUST be unchanged.
```

### Integration Points

```yaml
DELIVERABLE #1 (the dossier):
  - create: "plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md"
  - pattern: "Self-contained go/no-go evidence dossier (the verbatim 6-section scaffold in Task 3 SOURCE)."
  - consume_by: "The orchestrator (go/no-go handoff to P1.M6); P1.M6.T1.S1/.S2/.S3 (the routed owners);
                 reviewers."

DELIVERABLE #2 (tracker refresh):
  - edit: "tests/ACCEPTANCE.md"
  - pattern: "SURGICAL Mode A: refresh criteria-table Status/Evidence cols + add a one-line dossier
              pointer; PRESERVE the 'How to reproduce' / 'Evidence block' / 'Notes on the method'
              sections verbatim. Do NOT fabricate measured values (keep <measured> placeholders)."
  - consume_by: "P1.M6.T1.* (the docs/commit module) + future readers."

RUN (the only live actions — fast, safe):
  - commands: "git status --short; git log --oneline -5; grep -nE '^#{1,3} ' README.md"
  - expected: "fast; decides #7; confirms README sections + evidence line numbers"

DO NOT RUN:
  - commands: ["tests/test_idle_and_gpu.sh", "tests/e2e_virtual_mic.sh", ".venv/bin/python -m pytest ..."]
  - reason: "Heavy (CUDA ~5-8min; e2e rebinds global audio). AGENTS.md + this work item's INPUT/LOGIC
             (aggregate existing evidence) forbid them. Evidence is in the test_results_*.md + the
             past-live values in tests/ACCEPTANCE.md."

EDITS (only 2 — REPORT + tracker-refresh item):
  - create: "plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md"
  - edit:   "tests/ACCEPTANCE.md (Mode A, surgical)"
  - forbidden: "voice_typing/*, tests/*.py, tests/*.sh, config.toml, PRD.md, tasks.json, prd_snapshot.md,
                README.md, .gitignore, any other plan/ file"
```

## Validation Loop

### Level 1: Syntax & Style (N/A — Markdown docs; no code)

```bash
# Verify both deliverables are written + structurally complete.
ls -la plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md
grep -c '^## ' plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md   # expect >= 5 (sections 1-5)
grep -q '^**Verdict:**' plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md && echo "verdict present"
grep -q 'GO' plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md && echo "go/no-go present"
# tests/ACCEPTANCE.md edit is surgical:
git -C /home/dustin/projects/voice-typing diff --stat -- tests/ACCEPTANCE.md   # small change
```

### Level 2: (N/A — no unit tests; this is a report item)

### Level 3: Static cross-check (fast, safe — confirms the dossier's claims against LIVE files)

```bash
# Decide #7 (cleanliness + README + commit state).
git -C /home/dustin/projects/voice-typing status --short
git -C /home/dustin/projects/voice-typing log --oneline -5
# Confirm all 9 README sections present (criterion #7 docs half).
for s in "## Install" "## Hotkey (Hyprland)" "## Lite mode" "## tmux status line" "## Configuration" \
         "### cuDNN load error" "### Wrong microphone" "### wtype vs ydotool" "## CPU-only mode"; do
  printf '%-28s ' "$s"; grep -qF "$s" README.md && echo PRESENT || echo MISSING
done
# Confirm the input evidence artifacts exist (the dossier cites them).
ls plan/006_862ee9d6ef41/P1M5T1S1/test_results_unit.md plan/006_862ee9d6ef41/P1M5T1S2/test_results_daemon.md \
   plan/006_862ee9d6ef41/P1M5T2S1/test_results_t1.md plan/006_862ee9d6ef41/P1M5T3S1/gap_e2e.md \
   plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md
# Confirm the tests/ACCEPTANCE.md edit preserved the methodology sections.
git -C /home/dustin/projects/voice-typing diff -- tests/ACCEPTANCE.md | grep -E '^[-+]' | grep -iE 'how to reproduce|evidence block|notes on the method' \
  && echo "FAIL: methodology section changed" || echo "OK: methodology sections preserved"
# Expected: all 9 README sections PRESENT; all input artifacts exist; methodology sections unchanged.
```

### Level 4: Domain-specific validation (the dossier's internal consistency)

```bash
# Every criterion #1-#10 has a verdict row in the dossier table.
for n in 1 2 3 4 5 6 7 8 9 10; do
  grep -qE "^\| $n \|" plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md || echo "MISSING criterion #$n"
done
# No criterion is left as a bare claim without an evidence-type tag.
grep -cE 'LIVE|STATIC|PAST-LIVE' plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md   # expect >= 10
# The remediation notes route to owners (not silently dropped or escalated to blockers).
grep -E 'P1\.M6\.T1|test-hardening|regression-watch' plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md
# Expected: all 10 rows present; >=10 evidence-type tags; remediation notes routed to named owners.
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 3 static cross-check — `git status`/`log` + README grep + input-artifact existence + the
      tests/ACCEPTANCE.md methodology-preservation check all pass.
- [ ] Level 4 internal consistency — all 10 criterion rows present; ≥10 evidence-type tags;
      remediation notes routed to named owners.
- [ ] `acceptance_gate.md` written to `plan/006_862ee9d6ef41/P1M5T5S1/acceptance_gate.md` (NEW).
- [ ] `tests/ACCEPTANCE.md` Mode A edit is surgical (diff --stat small; methodology sections intact).

### Feature Validation

- [ ] Per-criterion table COMPLETE for ALL 10 with verdict + evidence + evidence-type + source artifact.
- [ ] #7 decided from RUNTIME git state (PASS-on-substance if README+impl committed & tree clean of
      shipped files; PARTIAL otherwise with the specific remediation).
- [ ] Evidence-type honesty section present — criterion #1's "actual command output" addressed; the
      LIVE/STATIC/PAST-LIVE split explicit; the optional operator action documented, not performed.
- [ ] Non-blocking remediation notes routed (E2E GAP g/i → test-hardening; VT-001 → P1.M6.T1.S2;
      7 coverage gaps → regression-watch; T1 tolerances + VT-006 → notes; #7 commit → P1.M6.T1.S3).
- [ ] GO/NO-GO verdict line is unambiguous and matches the per-criterion table.

### Code Quality Validation

- [ ] The dossier is self-contained (a reader needs no other file to understand the §7 verdict).
- [ ] Evidence/line numbers LIVE-confirmed (re-checked against the actual files, not copied blindly).
- [ ] Citations to the source-side gap audits are verdict-line quotes, not re-derived findings.
- [ ] Scope respected: P1.M6.T1.* CITED (not duplicated); P1.M5.T4.S1 deliverable CONSUMED (not
      re-derived); no source/test/script/config/PRD/tasks edit.

### Documentation & Deployment

- [ ] `tests/ACCEPTANCE.md` refresh is reproducible from the dossier (one-line pointer added).
- [ ] No measured values fabricated (evidence-block placeholders preserved).
- [ ] The dossier's GO/NO-GO is the single answer the orchestrator reads for the P1→P1.M6 handoff.

---

## Anti-Patterns to Avoid

- ❌ Don't RUN `tests/test_idle_and_gpu.sh` or `tests/e2e_virtual_mic.sh` or any pytest — they're
  CUDA-heavy / rebind global audio, and this work item's contract is to AGGREGATE existing evidence.
  The evidence is in the `test_results_*.md` files + the past-live values in `tests/ACCEPTANCE.md`.
- ❌ Don't claim T3/T6/T4-shell were "freshly demonstrated" — they were read STATICALLY this round +
  past-live-recorded. State the evidence-type honestly (criterion #1 demands actual output, not claims).
- ❌ Don't escalate the E2E GAP (g)/(i) or the 7 coverage gaps into blockers — they're test-robustness
  / coverage observations, not source defects (the source gap audits are all COMPLIANT). Route them.
- ❌ Don't judge #7 by whether THIS item's own new deliverables are committed — judge it by whether the
  SHIPPED codebase (README + impl + tests) is committed. The gate's own commit is P1.M6.T1.S3.
- ❌ Don't re-add "you" to the blocklist (VT-006) or weaken the T1 tolerance gates — both are
  compliant-by-design / documented-tolerance, not defects.
- ❌ Don't rewrite `tests/ACCEPTANCE.md` — the Mode A edit is SURGICAL (Status/Evidence columns + one
  pointer line). Preserve the methodology sections + the evidence-block placeholders verbatim.
- ❌ Don't edit any source/test/script/config/PRD/tasks/README file — this is a REPORT + tracker-refresh
  item. The ONLY writes are `acceptance_gate.md` (CREATE) + `tests/ACCEPTANCE.md` (Mode A EDIT).
- ❌ Don't duplicate P1.M6.T1.* (docs/commit) or P1.M5.T4.S1 (T4) work — CITE/CONSUME them.