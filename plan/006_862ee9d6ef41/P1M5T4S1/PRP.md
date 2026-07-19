# PRP — P1.M5.T4.S1: Audit T4 coverage — idle hallucination guard, CPU sampling, crash detection

## Goal

**Feature Goal**: Produce a **complete coverage audit** of **PRD §6 T4 (Idle stability)** and its
mapping to **Acceptance #5** ("Daemon survives ≥2 min of silence with no hallucinated output and
trivial CPU use"), across its TWO possible homes — the real-CUDA shell script `tests/test_idle_and_
gpu.sh` (RUN 1) and the mocked unit suite `tests/test_daemon.py` — by (1) statically reading both
files + the mitigation source (`textproc.py`, `config.toml`, `daemon.py`), (2) **running** the
work-item's specified mocked pytest (`-k 'idle or hallucin or silence or cpu'`, which is CONFIRMED
CUDA-free via the file header + `_FakeRecorder` stubs → fast, NOT the 5-8 min heavy load), and (3)
recording a per-sub-check ((a) no-finals / (b) CPU<25% / (c) no-crash) coverage matrix with exact
script line numbers + LIVE-source evidence + a clear verdict. The full 120 s silence test lives ONLY
in the shell script (real CUDA + ambient mic); the mocked tests prove ONLY the blocklist-guard logic
— the report states this split explicitly (the work-item's "if only mocked in test_daemon.py, note the
full 120 s test is in the shell script" directive).

**Verified baseline (research, this round — NO shell-script run; the mocked pytest is RUN):**
- **T4 is FULLY covered.** All three sub-checks are asserted end-to-end in `test_idle_and_gpu.sh` RUN 1
  (L473-525): (a) no-finals via a **double-signal** — capture-pane UNCHANGED (`typed_before==
  typed_after`, L493/497/500-509) **AND** state.json `last_final` UNCHANGED (`jq -r .last_final`,
  L494/498); (b) no-crash via `kill -0 "$DAEMON_PID"` (L511-516); (c) CPU<25% via `cpu_tree_seconds()`
  (L176-211) = `/proc/<pid>/stat` utime+stime fields 14/15 summed over the PROCESS TREE ÷ `CLK_TCK`,
  compared vs `CPU_LIMIT_PCT=25` (L148), **NOT** divided by nproc. `IDLE_SECS=120` (L147). pidstat/
  sysstat is NOT installed → `/proc` is the zero-dep path satisfying PRD §6 T4's "`pidstat` OR `/proc`."
- **The mocked unit suite contributes ONLY the blocklist-guard logic proof** (fast, CUDA-free):
  `test_on_final_rejects_hallucination` (test_daemon.py L667 — feeds "thank you." → `be.typed==[]`)
  + `test_on_final_rejected_hallucination_emits_no_latency_line` (L1532). It does NOT, and cannot,
  assert 120 s / CPU % / no-crash (those require a live daemon + real mic silence). The `-k` filter
  ALSO catches idle/auto-stop/idle-unload neighbors (L767/818/3340-3414) + UNRELATED `test_cfg_to_
  kwargs_cpu_fallback*` (matched by 'cpu' but = device-resolution, not T4 runtime CPU) +
  `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` (matched by 'silence', lite not T4) — the
  report separates "T4-relevant" from "collateral matches."
- **The mitigation chain (why no-finals passes)** = two layers: (1) **VAD gating** (RealtimeSTT
  silero/webrtc, §4.4 — pure silence usually produces NO final callback); (2) **blocklist**
  (`textproc.clean()` step 3, §4.7; `config.toml` `[filter]` L62-67 drops "thank you.", "thanks for
  watching.", "bye.", "thank you for watching" on exact normalized match). **NOTE (VT-006):** bare
  "you" was REMOVED — it's a word users type, not a hallucination. T4(a)'s `last_final` UNCHANGED is a
  strong signal: it passes if either NO final was produced (VAD) OR a final was produced + rejected by
  the blocklist (clean→None→on_final early-returns) — both = "guard worked."
- **`test_daemon.py` is CONFIRMED CUDA-free** (header L1-10: "NO real RealtimeSTT / NO model load /
  NO CUDA"; `_make_daemon()` L618 wires `_FakeRecorder` L28). So the work-item's pytest command runs
  in SECONDS. AGENTS.md discipline still requires double-timeout (inner `timeout 300` + bash-tool
  `timeout` ≥ 360 s) as belt-and-suspenders + watching for an unexpected CUDA load.

**Deliverable** (1 artifact — CREATE; **NO source/test/script edit** — this is a REPORT item):
- `plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md` — a self-contained coverage-assessment report
  with: the (a)(b)(c) coverage matrix (each row = sub-check → shell-script line(s) → mocked-test
  line(s) → verdict), the mitigation-chain documentation (VAD + blocklist), the **actual mocked-pytest
  output** (run per work-item step 3, under double-timeout), the Acceptance #5 mapping, the
  "shell-script-is-authoritative; mocked-tests-are-blocklist-guard-only" split, and the correct-design
  notes (CPU window amortizes the cold-load spike; auto_stop 30 s handoff; /proc-not-pidstat;
  tree-not-single-PID). No existing `test_results_t4.md` at that path.

**Success Definition**:
- (a) Both files read for T4: `test_idle_and_gpu.sh` RUN 1 T4 block (L473-525) + `cpu_tree_seconds()`
  (L176-211) + the IDLE_SECS/CPU_LIMIT_PCT constants (L147-148); `test_daemon.py` blocklist-guard tests
  (L667, L1532) + the file header's CUDA-free declaration (L1-10). Findings recorded with exact line
  numbers + LIVE-source citations (textproc.py clean() step 3; config.toml [filter] L62-67; daemon.py
  on_final early-return on clean→None).
- (b) The coverage matrix (a)(b)(c) is COMPLETE; each row has a verdict (COVERED-shell-only /
  COVERED-shell+unit-logic / etc.) + the exact script/test lines + the mitigation that makes it pass.
- (c) The work-item's mocked pytest is **RUN** (double-timeout, AGENTS.md discipline) and its output is
  captured verbatim into the report — with a "T4-relevant vs collateral-matches" annotation of which
  `-k`-matched tests actually exercise T4 vs idle/auto-stop/cpu-fallback neighbors.
- (d) The Acceptance #5 mapping is explicit: which test/artifact proves each clause of #5 ("survives
  ≥2 min silence" = IDLE_SECS=120 + kill -0; "no hallucinated output" = no-finals double-signal; "trivial
  CPU" = avg_pct < 25%).
- (e) The split is stated: the full 120 s end-to-end is in the SHELL SCRIPT (real CUDA); the mocked
  tests prove ONLY the blocklist-guard logic. P1.M5.T5.S1 (acceptance cross-check) reads this to credit
  #5 correctly — it must NOT claim the mocked pytest alone proves T4.
- (f) Scope respected: ONLY T4 (no-finals / CPU% / no-crash). T6 (VRAM lifecycle) is owned by the
  parallel item P1.M5.T3.S2 — CITED, NOT re-audited. NO source/test/script file is edited. The shell
  script is NOT run (it loads CUDA ~5-8 min; static read only — consistent with P1.M5.T3.S2's no-run).

## User Persona

**Target User**: Internal — the plan orchestrator + downstream leaves:
1. **P1.M5.T5.S1** (acceptance-criteria cross-check) consumes this as the **evidence artifact for
   Acceptance #5** ("survives ≥2 min silence, no hallucination, trivial CPU"). It must credit the
   SHELL SCRIPT as the authoritative T4 proof (the only real 120 s end-to-end) and the mocked pytest
   as the blocklist-guard unit supplement — NOT the other way around. This report gives it the exact
   line citations + the pytest output to cite.
2. **P1.M5.T3.S2** (the parallel item auditing T6 GPU lifecycle in the SAME shell script) — its PRP
   lists T4 as OUT-OF-SCOPE ("→ P1.M5.T4.*"). This item HONORS that boundary (audits T4 only; cites
   P1.M5.T3.S2 for the VRAM slice). The two read overlapping RUN-1 sections but audit DIFFERENT signals
   (T6 = nvidia-smi VRAM presence; T4 = capture-pane/CPU/alive) — no conflict.
3. **Operators/reviewers** read `test_results_t4.md` to decide whether T4 is proven (it is) and what
   the low CPU % actually measures (the auto_stop 30 s handoff + amortized cold load), so they don't
   misread a future CPU regression.

**Use Case**: The compliance round (006) converted the unit audits into "tests pass" (P1.M5.T1.*) +
audited the offline T1 (P1.M5.T2.S1) and the E2E/GPU shell scripts (P1.M5.T3.S1/S2). THIS item closes
the test-suite loop on T4 — the idle-stability clause that is the DIRECT evidence for Acceptance #5
(the §8 top-3 risk: Whisper silence-hallucination "thank you."). The audit answers: (1) is the 120 s
silence + no-finals + CPU<25% + no-crash actually asserted somewhere? (YES — shell script RUN 1);
(2) does the mocked unit suite add anything? (YES — the blocklist-guard logic proof, fast); (3) what is
the mitigation, and does the test assert the result or the mechanism? (two-layer: VAD + blocklist;
asserts the RESULT via no-finals); (4) does the mocked pytest pass RIGHT NOW? (run it + record).

**Pain Points Addressed**: (1) Acceptance #5 is the no-hallucination clause — without a precise
"which test proves it" map, the cross-check (P1.M5.T5.S1) could over- or under-credit. This report pins
the evidence (shell = end-to-end; unit = guard logic) with line numbers. (2) The mocked pytest's `-k
'cpu'` filter matches UNRELATED device-fallback tests — without annotation, that match could be
misread as "T4-cpu is unit-tested." This report disambiguates. (3) The CPU<25% measurement includes
the cold-load spike (amortized over 120 s+) + the auto_stop 30 s handoff — recording WHY the number is
low prevents a future "CPU regressed!" false alarm when really auto_stop just didn't fire.

## Why

- **T4 is the direct evidence for Acceptance #5, the no-hallucination clause (§8 top-3 risk).** The
  compliance round audited the SOURCE (textproc blocklist → `architecture/gap_textproc.md`; daemon
  loop → `gap_daemon_loop.md`); THIS item audits the TESTS that prove that source actually stops
  Whisper's silence-hallucination end-to-end. Without confirming WHERE the 120 s assertion lives and
  that the mocked guard test passes, the "Acceptance #5 ✓" claim is unsupported.
- **The evidence lives in TWO places with DIFFERENT scope — the report must state the split.** The
  full real-CUDA 120 s + CPU% + no-crash trio is ONLY in the shell script; the mocked pytest proves
  ONLY the blocklist logic. P1.M5.T5.S1 needs this split to credit #5 correctly (a mocked-only proof
  would be insufficient for "survives 2 min with trivial CPU"). Recording it now prevents a
  downstream miscredit.
- **The mocked pytest is RUN, not just read — it confirms the guard logic passes TODAY.** The shell
  script's T4 block is read statically (it loads CUDA ~5-8 min; the parallel T6 audit also doesn't run
  it). But the mocked blocklist test (`test_on_final_rejects_hallucination`) is fast + CUDA-free, so
  running it gives a LIVE green check on the guard. This is the one piece of LIVE evidence this item
  adds beyond the static reads.
- **It disambiguates the `-k 'cpu'` and `-k 'silence'` collateral matches.** The filter catches device-
  fallback config tests (`test_cfg_to_kwargs_cpu_fallback*`) and the lite silence-duration test, which
  are NOT T4. Without annotation, a reviewer could think "T4 CPU is unit-tested." The report separates
  T4-relevant from collateral so the coverage picture is honest.
- **The findings are already in place** (research this round). So this item is low-risk: re-verify the
  (a)(b)(c) matrix against the live files, run the mocked pytest, write the report. The value is the
  evidence artifact + the live pytest green + the honest split — not heroic debugging.

## What

Three phases, in order: **(1) static read of both test files + mitigation source**, **(2) RUN the
mocked pytest (double-timeout) + capture output**, **(3) write `test_results_t4.md`** (the coverage
matrix + mitigation chain + pytest output + Acceptance #5 map + the split + correct-design notes).
The shell script is NOT executed (CUDA-heavy; static read only). NO source/test/script is edited.

### Success Criteria

- [ ] `test_idle_and_gpu.sh` T4 slice read: RUN 1 T4 block (L473-525), `cpu_tree_seconds()` (L176-211),
      `IDLE_SECS=120`/`CPU_LIMIT_PCT=25` (L147-148), the comment block (L1-130) documenting the blocklist
      + VAD mitigations. Line numbers CONFIRMED against the live file (may have drifted).
- [ ] `test_daemon.py` read: the CUDA-free header (L1-10), `_make_daemon()` (L618), `_FakeRecorder`
      (L28), and the two blocklist-guard tests (L667, L1532). Confirm the `-k` filter's T4-relevant vs
      collateral matches.
- [ ] Mitigation source read: `textproc.py clean()` (step 3 blocklist), `config.toml [filter]` (L62-67,
      incl. the VT-006 "you" removal note), `daemon.py on_final` (the clean→None early-return path).
- [ ] Coverage matrix (a)(b)(c) COMPLETE: each row = sub-check → shell-script line(s) → mocked-test
      line(s) → verdict (COVERED-shell-only / COVERED-shell+unit-logic). No row left to inference.
- [ ] Mocked pytest **RUN** under double-timeout: `timeout 300 .venv/bin/python -m pytest
      tests/test_daemon.py -q -k 'idle or hallucin or silence or cpu'` with bash-tool `timeout` ≥ 360.
      Output captured verbatim. Tests annotated T4-relevant vs collateral. All selected tests PASS.
- [ ] Acceptance #5 mapping explicit: "survives ≥2 min silence" = IDLE_SECS=120 + kill -0 (L147/511);
      "no hallucinated output" = no-finals double-signal (L500-509) backed by VAD+blocklist; "trivial
      CPU" = avg_pct < CPU_LIMIT_PCT=25 (L519-521).
- [ ] The SPLIT stated: full 120 s end-to-end = SHELL SCRIPT (real CUDA, authoritative); mocked tests =
      blocklist-guard LOGIC only (supplement, fast). P1.M5.T5.S1 must NOT credit the mocked pytest
      alone for #5.
- [ ] Correct-design notes recorded: CPU window amortizes cold-load spike; auto_stop 30 s handoff
      (config.py:65 → low steady-state CPU); /proc-not-pidstat (G-CPU-SAMPLING); tree-not-single-PID
      (G-CPU-TREE); kill -0 crash signal; VT-006 "you" blocklist removal.
- [ ] `test_results_t4.md` written to `plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md`, self-contained,
      with a clear VERDICT ("T4 FULLY COVERED: (a)(b)(c) asserted end-to-end in test_idle_and_gpu.sh
      RUN 1 (real CUDA); mocked pytest proves the blocklist-guard logic (PASSED); the two-layer
      mitigation = VAD gating + blocklist").
- [ ] Scope respected: ONLY T4 audited; T6 (VRAM) cited to P1.M5.T3.S2 (NOT re-audited); NO
      source/test/script edited; shell script NOT run (static read only).

## All Needed Context

### Context Completeness Check

_Pass._ The implementing agent gets: the full (a)(b)(c) coverage matrix pre-verified with exact line
numbers + LIVE-source citations, the CUDA-free confirmation for the mocked pytest (header + _FakeRecorder)
with the exact command + double-timeout discipline, the mitigation chain (VAD + blocklist) with the
VT-006 "you" nuance, the correct-design notes (cold-load amortization, auto_stop handoff, /proc-not-
pidstat), the Acceptance #5 mapping, the verbatim `test_results_t4.md` scaffold, the hard constraints
(run ONLY the mocked pytest, NOT the shell script; REPORT item, no edits), and the scope boundary with
the parallel T6 item. No inference required.

### Documentation & References

```yaml
# MUST READ — the two test homes of T4 (the audit subjects).
- file: tests/test_idle_and_gpu.sh
  why: "RUN 1 (default 1800s idle-unload threshold) holds the AUTHORITATIVE T4 assertions (the only
        place the real 120 s + CPU % + no-crash trio is asserted end-to-end against real CUDA + ambient
        mic). Lines: IDLE_SECS=120 (L147), CPU_LIMIT_PCT=25 (L148); cpu_tree_seconds() (L176-211 —
        /proc utime+stime over the PROCESS TREE ÷ CLK_TCK, NOT divided by nproc; pidstat NOT installed
        → G-CPU-SAMPLING); the T4 block L473-525 — cpu0 at L474 (before start L476), typed_before/
        last_final_before at L493-494, sleep IDLE_SECS at L495, cpu1 at L496, then (a) no-finals
        double-signal L500-509 (capture-pane UNCHANGED AND state.json last_final UNCHANGED), (b) no-
        crash kill -0 L511-516, (c) CPU avg_pct<25 L517-525. The comment block L1-130 documents the
        blocklist+VAD mitigations + the G-CPU-SAMPLING/G-CPU-TREE/G-CAPTURE/G-IDLE-NO-TYPING invariants."
  critical: "NOTE the T4 block is INTERLEAVED with T6(b) (VRAM-present asserted at L482-492 INSIDE the
             T4 CPU window, after start). That's T6's concern (owned by P1.M5.T3.S2), NOT T4's. CITE
             P1.M5.T3.S2 for the VRAM slice; do NOT re-audit it. ALSO NOTE cpu0 is captured BEFORE
             start → the CPU window INCLUDES the ~1-3s cold cuDNN load, AMORTIZED over 120 s+ → the
             average is sound (correct design, not a gap). ALSO: do NOT RUN this script (CUDA ~5-8 min);
             read it STATICALLY, consistent with P1.M5.T3.S2."

- file: tests/test_daemon.py
  why: "The mocked unit suite. Header L1-10 declares 'NO real RealtimeSTT / NO model load / NO CUDA /
        NO real feedback.py dependency' — CONFIRMS the work-item's pytest command is FAST (seconds).
        _make_daemon() (L618) wires _FakeRecorder (L28) + stub Feedback/Backend (L28-56). The T4-
        relevant tests (blocklist guard): test_on_final_rejects_hallucination (L667 — feeds 'thank
        you.' → be.typed==[] + fb.finals==[]) + test_on_final_rejected_hallucination_emits_no_latency_
        line (L1532). The -k filter ALSO catches idle/auto-stop/idle-unload neighbors (L767/818/
        3340-3414) + UNRELATED test_cfg_to_kwargs_cpu_fallback* (matched by 'cpu' but = device
        resolution, NOT T4 runtime CPU) + test_cfg_to_kwargs_lite_uses_shorter_silence_duration (L216,
        matched by 'silence', lite not T4)."
  critical: "CUDA-free CONFIRMED by the header — but AGENTS.md discipline is non-negotiable: run the
             pytest under DOUBLE-timeout (inner `timeout 300` + bash-tool `timeout` ≥ 360) regardless,
             and WATCH the output. If it unexpectedly loads CUDA (it shouldn't), Ctrl-C + run the
             AGENTS.md Cleanup block. The '-k cpu' match is a COLLATERAL false-friend (device tests) —
             the report MUST annotate it so 'T4 CPU is unit-tested' isn't misread. 'idle' matches
             idle-UNLOAD (T6(d)) tests too — annotate those as T6-adjacent, not T4."

# MUST READ — the mitigation source (why T4(a) 'no finals' passes).
- file: voice_typing/textproc.py
  why: "clean() step 3 (the blocklist hallucination guard): exact, case-insensitive, trailing-
        punctuation-stripped match. 'thank you.', 'bye.', 'BYE!' all normalize to match the 'bye.'
        entry. clean() returns None → on_final early-returns (no type, no record) → state.json
        last_final UNCHANGED → T4(a) passes. The docstring explicitly names T4: 'THE BLOCKLIST is the
        primary defense against Whisper's silence hallucination … VAD gating + this filter + PRD test
        T4 assert it together.'"
  critical: "clean() is PURE PYTHON, GPU-free, deterministic — that's WHY it has fast unit tests
             (test_textproc.py, owned by P1.M2.T2.S1) AND why the daemon-level guard is mockable.
             T4(a) asserts the END RESULT (no finals typed), which passes whether VAD suppressed the
             final OR the blocklist rejected it — both = guard worked."

- file: config.toml
  why: "[filter] block (L59-67): min_chars=2 (L61); blocklist (L62-67) = 'thank you.', 'thanks for
        watching.', 'bye.', 'thank you for watching'. The NOTE at L67 (VT-006): the bare 'you' entry
        was REMOVED — it is a common word users want to type, not a hallucination. This is the data
        the blocklist guard consumes."
  critical: "VT-006 'you' removal is a documented tradeoff (recall vs precision) — record it in the
             report so reviewers understand the blocklist is intentionally NARROW (exact-match only),
             not substring. 'yourself' is NEVER blocked even though 'you' sounds like it should."

- file: voice_typing/daemon.py
  why: "on_final: `txt = textproc.clean(text, cfg.filter); if txt is None: return` (the clean→None
        early-return — the path test_on_final_rejects_hallucination exercises). Also the VAD-stop
        tracking (_last_speech_monotonic) + auto_stop watchdog (auto_stop_idle_seconds default 30.0)
        that disarms ~30s into T4's 120s window → the low steady-state CPU (the 'handoff')."
  critical: "The auto_stop 30s handoff (config.py:65) is WHY T4(c) CPU is trivially low: ~30s of armed
             VAD inference + ~90s disarmed (near-zero). Record this so a future 'CPU regressed' alarm
             is correctly attributed (auto_stop firing is the lever, not a CPU-path change)."

# MUST READ — AGENTS.md (the hard rules; the timeout rule binds the mocked pytest run directly).
- file: AGENTS.md
  why: "Rule 1 (two timeouts on EVERY non-trivial command) + the test_daemon.py hang-vectors row
        ('Several suites (test_feed_audio.py, test_daemon.py, test_recorder_host.py) load real CUDA
        models … timeout 600 uv run pytest <file> -q … Run a single file or -k expr'). The test_idle_
        and_gpu.sh row ('~5-8 min … give the bash tool a timeout of 900 … do NOT run unless explicitly
        required')."
  critical: "EVEN THOUGH test_daemon.py's header says CUDA-free, AGENTS.md lists it as a hang risk — so
             the double-timeout discipline is MANDATORY for the mocked pytest run (inner `timeout 300` +
             bash-tool `timeout` ≥ 360). Do NOT run test_idle_and_gpu.sh (it is CUDA-heavy + out of this
             item's scope — static read only). If the pytest unexpectedly hangs/loads CUDA, Ctrl-C + the
             AGENTS.md Cleanup block (timeout 30 voicectl quit; systemctl --user stop; pkill)."

# MUST READ — the merged PRD (the spec T4 encodes; the oracle for each verdict).
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: "§6 T4 (Idle stability — '120 s silence … no finals typed, no crash, CPU <25% of one core
        (pidstat or /proc)') = the spec being audited; §8 (Known risks — Whisper silence-hallucination
        'thank you.' is a top-3 risk, mitigated by blocklist + VAD) = WHY T4 exists; §7 #5 ('Daemon
        survives ≥2 min of silence with no hallucinated output and trivial CPU use') = the acceptance
        clause this audit provides evidence for. When judging 'is T4 covered,' the PRD wording is the
        source of truth (esp. the 'pidstat OR /proc' latitude + 'of ONE core')."

# MUST READ — the parallel item's PRP (P1.M5.T3.S2, the T6 GPU-lifecycle audit of the SAME script).
- file: plan/006_862ee9d6ef41/P1M5T3S2/PRP.md
  why: "That PRP audits T6 (nvidia-smi VRAM idle/armed/disarmed/unload) in test_idle_and_gpu.sh and
        EXPLICITLY lists T4 as OUT-OF-SCOPE ('→ P1.M5.T4.*'). This item HONORS that boundary: audit T4
        only; CITE P1.M5.T3.S2 for the VRAM slice (T6(b) at L482-492 is interleaved inside the T4 CPU
        window but is T6's signal, not T4's). Read it to (a) align the scope boundary + (b) reuse its
        G-CPU-SAMPLING/G-CPU-TREE/G-TIMEOUTS/G-NOSOURCE invariant names (they apply to T4's CPU
        sampling too)."
  critical: "Do NOT re-audit T6 here. The two reports are complementary: P1.M5.T3.S2 = VRAM lifecycle
             (Acceptance #9); THIS = idle stability (Acceptance #5). Both read RUN 1 statically; neither
             runs the script. The one LIVE action this item adds is the mocked pytest (P1.M5.T3.S2 runs
             nothing)."

# Cross-ref — the source-side audits (this is the TEST-SIDE audit; cite, don't re-derive).
- file: plan/006_862ee9d6ef41/architecture/gap_textproc.md    # blocklist guard (source side)
- file: plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md  # on_final clean→None early-return + auto_stop (source side)
- file: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md    # idle watchdogs (source side)
  why: "These already audited the SOURCE. This item audits the TESTS that prove that source stops
        Whisper's hallucination. Cite them (e.g. 'per gap_textproc.md, clean() step 3 is the blocklist
        guard') rather than re-deriving. Don't duplicate their findings into test_results_t4.md beyond
        one-line citations."

# External — the /proc CPU-sampling semantics (validates the 'correct' verdict on T4(c)).
- url: https://man7.org/linux/man-pages/man5/proc.5.html
  why: "/proc/<pid>/stat field 14 (utime) + field 15 (stime) in clock ticks; /proc/<pid>/task/<pid>/
        children lists direct children (recursive walk for the tree). Confirms cpu_tree_seconds()'s
        /proc-based tree-sum is the zero-dep correct path (pidstat/sysstat NOT installed) and that the
        split-after-last-')' parse (comm may contain spaces/parens) is required. CLK_TCK via
        os.sysconf(SC_CLK_TCK) = 100 on this machine."
```

### Current Codebase tree (relevant slice — state at P1.M5.T4.S1)

```bash
tests/
├── test_idle_and_gpu.sh         (779 lines) ← IN SCOPE: RUN 1 T4 block L473-525 (READ ONLY; do NOT run)
│                                   + cpu_tree_seconds() L176-211; IDLE_SECS=120/CPU_LIMIT_PCT=25 L147-148.
│                                   (T6 VRAM slices L482-492 etc. owned by P1.M5.T3.S2 — CITE, don't re-audit)
├── test_daemon.py               (CUDA-free per header L1-10) ← IN SCOPE: blocklist-guard tests L667/L1532
│                                   + RUN the work-item's -k pytest (fast, mocked); _make_daemon L618
│                                   (_FakeRecorder L28). -k also catches idle/auto-stop/idle-unload +
│                                   cpu-fallback/silence COLLATERAL matches — annotate in report.
├── test_textproc.py             OUT — blocklist unit tests (owned by P1.M2.T2.S1; cite, don't re-run)
└── (other tests)                          OUT — P1.M5.T1.* (config/ctl/feedback/socket/systemd/typing)
voice_typing/
├── textproc.py                  # clean() step 3 = blocklist guard (the mitigation; cite)
├── config.py                    # L65 auto_stop_idle_seconds=30.0 (the 30s handoff → low CPU); blocklist cfg
├── daemon.py                    # on_final clean→None early-return; VAD-stop tracking; auto_stop watchdog
└── config.toml                  # [filter] L59-67: blocklist (thank you./bye./etc.) + VT-006 'you' removal
plan/006_862ee9d6ef41/
├── P1M5T4S1/test_results_t4.md                # ← OUTPUT (NEW; this item creates it)
├── P1M5T4S1/research/t4_coverage_research.md  # ← this PRP's research (already written; feed into the report)
├── P1M5T3S2/PRP.md                            # parallel T6 audit PRP (cite for scope boundary + G-* invariants)
├── architecture/gap_{textproc,daemon_loop,lifecycle}.md  # source-side audits (cite, don't re-derive)
└── prd_snapshot.md                            # §6 T4 + §8 (hallucination risk) + §7 #5
```

### Desired Codebase tree with files to be added/modified

```bash
plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md   # NEW — the coverage-assessment report (SOLE deliverable)
# (NO source/test/script files edited. REPORT item — audit only; run ONLY the mocked pytest, NOT the shell script.)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — RUN ONLY THE MOCKED PYTEST, NOT THE SHELL SCRIPT. The work-item step 3 says to run:
#     `timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or hallucin or silence or cpu'`
#   This is FAST + CUDA-free (test_daemon.py header L1-10: 'NO real RealtimeSTT / NO model load / NO CUDA';
#   _FakeRecorder L28). Do NOT run tests/test_idle_and_gpu.sh — it loads CUDA models for ~5-8 min (2 cold
#   inits + 120 s armed idle + idle-unload waits), AGENTS.md + the parallel T6 audit (P1.M5.T3.S2) both
#   say "do NOT run unless explicitly required." The shell script's T4 block is READ STATICALLY. If you
#   accidentally started the shell script, Ctrl-C IMMEDIATELY (its EXIT trap stops the daemon + kills
#   tmux + rm temp; it does NOT swap the audio source, so nothing to restore) + run the AGENTS.md Cleanup.

# CRITICAL #2 — DOUBLE-TIMEOUT on the mocked pytest, even though it's CUDA-free. AGENTS.md Rule 1 is
#   non-negotiable + the hang-vectors table lists test_daemon.py as a risk (some suites load CUDA).
#   Wrap: inner `timeout 300 .venv/bin/python -m pytest ...` + bash-tool `timeout` ≥ 360. WATCH the
#   output: if it unexpectedly loads CUDA (it shouldn't per the header), Ctrl-C + the AGENTS.md
#   Cleanup block. Treat exit 124 as 'wedged/loaded-CUDA,' NOT as 'retry.'

# CRITICAL #3 — the `-k 'cpu'` filter is a COLLATERAL FALSE-FRIEND. It matches test_cfg_to_kwargs_cpu_
#   fallback* (device-resolution CONFIG tests, NOT T4 runtime CPU %) + test_construct_force_cpu_*.
#   Similarly `-k 'idle'` catches idle-UNLOAD tests (T6(d), not T4) + auto-stop; `-k 'silence'` catches
#   the lite silence-duration test (lite mode, not T4). The ONLY -k-matched test that exercises T4's
#   hallucination guard is test_on_final_rejects_hallucination (+ its latency-line sibling). The report
#   MUST annotate the selected tests 'T4-relevant vs collateral' so a reviewer doesn't misread 'T4 CPU
#   is unit-tested' (it is NOT — CPU% is shell-script-only).

# CRITICAL #4 — the SPLIT is the report's load-bearing claim. The full 120 s + CPU% + no-crash trio
#   lives ONLY in the shell script (real CUDA + ambient mic). The mocked pytest proves ONLY the
#   blocklist-guard LOGIC (feed 'thank you.' → typed==[]). P1.M5.T5.S1 (acceptance cross-check) reads
#   this report to credit Acceptance #5 — it must credit the SHELL SCRIPT as authoritative + the mocked
#   pytest as the logic supplement, NOT the reverse. State this split explicitly in the report's verdict.

# CRITICAL #5 — T4(a) 'no finals' is a two-layer mitigation, asserted by RESULT not mechanism. Layer 1 =
#   VAD gating (RealtimeSTT silero/webrtc — pure silence usually produces NO final callback). Layer 2 =
#   blocklist (textproc.clean step 3 — drops 'thank you.'/'bye.' etc.). The shell test's double-signal
#   (capture-pane UNCHANGED AND state.json last_final UNCHANGED) passes if EITHER layer worked. That's
#   CORRECT (the goal is no hallucinated text typed, however achieved). Do NOT claim the test proves VAD
#   specifically OR the blocklist specifically — it proves the COMBINED result. The mocked unit test
#   (test_on_final_rejects_hallucination) is the one that isolates the BLOCKLIST layer.

# CRITICAL #6 — VT-006: bare 'you' was REMOVED from the blocklist (config.toml L67). It is a common word
#   users want to type, not a hallucination. The blocklist is intentionally NARROW (exact normalized
#   match, NOT substring) — 'yourself' is never blocked. Record this so reviewers understand the
#   recall-vs-precision tradeoff + don't 'fix' the blocklist by re-adding 'you.'

# CRITICAL #7 — the CPU<25% measurement INCLUDES the cold-load spike (cpu0 captured BEFORE voicectl
#   start at L474). The ~1-3s cuDNN/cuBLAS load is AMORTIZED over the 120 s+ window → the average is
#   sound. PLUS the auto_stop 30s handoff (config.py:65 default 30.0) disarms the mic ~30s in → steady-
#   state VAD-inference CPU drops to near-zero for the remaining ~90s. This is WHY the original passing
#   run measured ~2.5%. Record as CORRECT DESIGN, not a gap — so a future 'CPU regressed!' alarm is
#   correctly attributed (auto_stop firing is the lever, not a CPU-path change).

# CRITICAL #8 — /proc, NOT pidstat. pidstat/sysstat is NOT installed on this machine → cpu_tree_seconds()
#   uses /proc/<pid>/stat fields 14/15 (utime+stime) summed over the PROCESS TREE (recursive /proc/<pid>/
#   task/<pid>/children walk) ÷ CLK_TCK (=100). PRD §6 T4 says 'pidstat OR /proc sampling' → /proc
#   satisfies it. Tree-not-single-PID (G-CPU-TREE): the CUDA workers + SafePipe spawn children; a single-
#   PID read would UNDERCOUNT. NOT divided by nproc (it's % of ONE core per the PRD).

# CRITICAL #9 — this is a REPORT item. It does NOT fix any test or source. The ONLY edit is to
#   plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md (CREATE). Do NOT touch tests/test_idle_and_gpu.sh,
#   tests/test_daemon.py, any voice_typing/*.py, config.toml, PRD.md, tasks.json, prd_snapshot.md,
#   .gitignore. The one LIVE action is running the mocked pytest (read-only w.r.t. the repo).

# CRITICAL #10 — scope boundary. Audit ONLY T4 (no-finals / CPU% / no-crash). T6 (nvidia-smi VRAM
#   lifecycle) is owned by the parallel P1.M5.T3.S2 — CITE its PRP + report, do NOT re-audit the VRAM
#   assertions (T6(b) at L482-492 is interleaved inside the T4 CPU window but is T6's signal). The
#   idle-auto-stop + idle-UNLOAD mocked tests (caught by -k idle) are T6(d)-adjacent / lifecycle, not
#   T4 — note their presence + that they're covered by sibling items, but don't deep-audit them.
```

## Implementation Blueprint

### Data models and structure

N/A — no code models. The deliverable is one Markdown coverage-assessment report. The "data" is the
(a)(b)(c) coverage matrix + the mitigation chain + the captured mocked-pytest output + the Acceptance
#5 mapping + the correct-design notes.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: READ both test homes of T4 + the mitigation source (NO shell-script run; STATIC only).
  - READ tests/test_idle_and_gpu.sh RUN 1 T4 slice: L147 (IDLE_SECS=120), L148 (CPU_LIMIT_PCT=25),
    L176-211 (cpu_tree_seconds — /proc tree-sum ÷ CLK_TCK), L473-525 (the T4 block: cpu0 L474 → start
    L476 → T6(b) VRAM L482-492 [T6's, CITE P1.M5.T3.S2] → typed_before/last_final_before L493-494 →
    sleep IDLE_SECS L495 → cpu1 L496 → (a) no-finals double-signal L500-509 → (b) kill -0 L511-516 →
    (c) avg_pct<25 L517-525). Read the comment block L1-130 for the blocklist+VAD + G-* invariants.
  - READ tests/test_daemon.py: header L1-10 (CUDA-free declaration), _FakeRecorder L28, _make_daemon L618,
    test_on_final_rejects_hallucination L667, test_on_final_rejected_hallucination_emits_no_latency_line
    L1532. CONFIRM the line numbers (may have drifted). Identify which -k-matched tests are T4-relevant
    vs collateral (idle/auto-stop/idle-unload/cpu-fallback/silence).
  - READ the mitigation source: textproc.py clean() step 3 (blocklist); config.toml [filter] L59-67
    (blocklist + VT-006 'you' removal); daemon.py on_final (clean→None early-return) + the auto_stop
    watchdog (the 30s handoff → low CPU).
  - CROSS-CHECK the 'correct' verdicts: PRD §6 T4 wording ('pidstat OR /proc'; 'of ONE core');
    AGENTS.md (test_daemon.py hang-risk row → double-timeout; test_idle_and_gpu.sh ~5-8min → don't run).
  - DO NOT run test_idle_and_gpu.sh. DO NOT load CUDA. (If `timeout 15 .venv/bin/voicectl status` is
    needed to confirm a daemon ISN'T running before the pytest, it's fine — wrapped, per AGENTS.md.)
  - GO to Task 2.

Task 2: RUN the work-item's mocked pytest (double-timeout) + CAPTURE output.
  - COMMAND (verbatim from work-item step 3, AGENTS.md-wrapped):
      timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or hallucin or silence or cpu'
    Run it via the bash tool with `timeout` ≥ 360 (belt-and-suspenders over the inner 300).
  - EXPECT: FAST (seconds), CUDA-free (header L1-10). All selected tests PASS. Capture the FULL output
    (the `-q` summary line + any failures). If a test FAILS, record it verbatim (it's still evidence —
    a real finding, not a blocker for the REPORT; note it as a finding for a downstream remediation).
  - WATCH for an unexpected CUDA load (shouldn't happen per header): if output shows torch/cuDNN/cuBLAS
    init OR it runs > ~60s, Ctrl-C + the AGENTS.md Cleanup block, then re-run (the header promises it's
    CUDA-free; a load would indicate a collection-time import regression — a finding, not expected).
  - ANNOTATE the selected-test list 'T4-relevant' (test_on_final_rejects_hallucination + the latency
    sibling) vs 'collateral' (idle/auto-stop/idle-unload = T6(d)-adjacent; cpu-fallback = device config;
    silence = lite). This annotation goes into the report.
  - GO to Task 3.

Task 3: WRITE plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md (the SOLE deliverable).
  - USE the verbatim scaffold in "Task 3 SOURCE" below. Fill the LIVE-confirmed line numbers + the
    captured pytest output + the Acceptance #5 mapping.
  - STRUCTURE: (1) Verdict; (2) the (a)(b)(c) coverage matrix; (3) the two-layer mitigation chain;
    (4) the mocked-pytest result (verbatim output + T4-relevant vs collateral annotation); (5) Acceptance
    #5 mapping; (6) the SPLIT (shell = authoritative 120 s end-to-end; mocked = blocklist-guard logic);
    (7) correct-design notes; (8) scope (T4 only; T6 → P1.M5.T3.S2).
  - VERDICT line: "T4 FULLY COVERED: (a)(b)(c) asserted end-to-end in test_idle_and_gpu.sh RUN 1 (real
    CUDA, ambient mic); the mocked pytest proves the blocklist-guard LOGIC (PASSED, fast, CUDA-free);
    the two-layer mitigation = VAD gating + textproc blocklist; the shell script is the AUTHORITATIVE
    proof for Acceptance #5."
  - DO NOT edit any test, any source, config.toml, PRD.md, tasks.json, prd_snapshot.md, .gitignore.
    REPORT item only.

Task 4: (NONE) — no source/test/script changes. This is a static audit + one mocked-pytest run + a
  documentation deliverable. Verify the report is written + self-contained, then done.
```

#### Task 3 SOURCE — `test_results_t4.md` verbatim scaffold (pre-fill the static parts; confirm line numbers LIVE; paste the captured pytest output)

```markdown
# T4 Coverage Assessment — P1.M5.T4.S1 (PRD §6 T4 / Acceptance #5)

**Date:** <YYYY-MM-DD>
**Method:** STATIC read of `tests/test_idle_and_gpu.sh` + `tests/test_daemon.py` + mitigation source
(`textproc.py`, `config.toml`, `daemon.py`); PLUS a LIVE run of the work-item's mocked pytest
(`tests/test_daemon.py -k 'idle or hallucin or silence or cpu'`, CUDA-free, double-timeout). The shell
script is NOT run (CUDA ~5-8 min; static read only — consistent with the parallel T6 audit P1.M5.T3.S2).
**Verdict:** **T4 FULLY COVERED.** All three sub-checks ((a) no-finals, (b) CPU<25%, (c) no-crash) are
asserted end-to-end in `test_idle_and_gpu.sh` RUN 1 (real CUDA + ambient mic) — the AUTHORITATIVE proof.
The mocked pytest proves the **blocklist-guard LOGIC** (PASSED, fast, CUDA-free) — a logic supplement,
NOT a substitute for the 120 s end-to-end. Two-layer mitigation = VAD gating + textproc blocklist.

## 1. T4 sub-check coverage matrix

| sub-check | `test_idle_and_gpu.sh` RUN 1 (real CUDA) | `test_daemon.py` (mocked, CUDA-free) | verdict |
|---|---|---|---|
| (a) no hallucinated finals | ✅ L<NNN>-<NNN>: `IDLE_SECS=120` (L<NNN>); capture-pane UNCHANGED (`typed_before==typed_after`) AND state.json `last_final` UNCHANGED (`jq -r .last_final`) — **double-signal** across the 120 s window | ✅ logic-only: `test_on_final_rejects_hallucination` (L<NNN> — 'thank you.'→`be.typed==[]`); `test_on_final_rejected_hallucination_emits_no_latency_line` (L<NNN>) | **COVERED** (shell=end-to-end; unit=guard logic) |
| (b) CPU < 25 % of ONE core | ✅ L<NNN>-<NNN> + `cpu_tree_seconds()` L<NNN>-<NNN>: `/proc/<pid>/stat` utime+stime (fields 14/15) over the PROCESS TREE ÷ CLK_TCK; `avg_pct=(cpu1-cpu0)/elapsed*100` vs `CPU_LIMIT_PCT=25` (L<NNN>); NOT ÷ nproc; pidstat NOT installed (G-CPU-SAMPLING) | ❌ none (needs a live daemon) | **COVERED (shell only)** |
| (c) no crash | ✅ L<NNN>-<NNN>: `kill -0 "$DAEMON_PID"` after the 120 s window | ❌ none (needs a live daemon) | **COVERED (shell only)** |

## 2. The two-layer mitigation (why (a) passes)

1. **VAD gating** (RealtimeSTT silero/webrtc, §4.4): the recorder only finalizes on detected speech
   onset — pure silence usually produces NO final callback at all.
2. **blocklist** (`textproc.clean()` step 3, §4.7; `config.toml [filter]` L<NNN>-<NNN>): exact,
   case-insensitive, trailing-punctuation-stripped match drops "thank you.", "thanks for watching.",
   "bye.", "thank you for watching". **VT-006:** bare "you" was REMOVED (a word users type, not a
   hallucination); the blocklist is exact-match (not substring) → "yourself" is never blocked.

The shell test's double-signal (capture-pane UNCHANGED AND `last_final` UNCHANGED) asserts the **RESULT**
(no hallucinated text typed), which passes if EITHER layer worked. The mocked unit test isolates the
BLOCKLIST layer (feed "thank you." → typed==[]).

## 3. Mocked-pytest result (work-item step 3 — LIVE)

**Command** (AGENTS.md double-timeout):
```
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or hallucin or silence or cpu'
```
**Result:** <paste verbatim — the -q summary line(s) + pass/fail counts. Confirm CUDA-free (no
torch/cuDNN/cuBLAS in output; ran in seconds).>

**Selected tests — T4-relevant vs collateral:**
- ✅ T4-relevant (blocklist guard): `test_on_final_rejects_hallucination` (L<NNN>);
  `test_on_final_rejected_hallucination_emits_no_latency_line` (L<NNN>).
- ➖ collateral (idle/auto-stop — lifecycle, not T4's no-finals): `test_auto_stop_disarms_when_idle_
  beyond_threshold` (L<NNN>); `test_idle_watchdog_actually_disarms_in_background` (L<NNN>);
  `test_idle_unload_*` (L<NNN>-<NNN> — T6(d)-adjacent, owned by P1.M5.T3.S2).
- ➖ collateral (-k 'cpu' false-friend — device-resolution CONFIG tests, NOT T4 runtime CPU %):
  `test_cfg_to_kwargs_cpu_fallback*` (L<NNN>, ...); `test_construct_force_cpu_*` (L<NNN>, ...).
- ➖ collateral (-k 'silence' — lite mode, not T4): `test_cfg_to_kwargs_lite_uses_shorter_silence_
  duration` (L<NNN>).

## 4. Acceptance #5 mapping

Acceptance #5: "Daemon survives ≥2 min of silence with no hallucinated output and trivial CPU use."
| clause | evidence | artifact |
|---|---|---|
| "survives ≥2 min silence" | `IDLE_SECS=120` + `kill -0` after the window | test_idle_and_gpu.sh RUN 1 L<NNN>/L<NNN> |
| "no hallucinated output" | no-finals double-signal (capture-pane + last_final UNCHANGED), backed by VAD+blocklist | test_idle_and_gpu.sh L<NNN>-<NNN> + mocked guard L<NNN> |
| "trivial CPU" | `avg_pct < CPU_LIMIT_PCT=25` (of ONE core, tree-summed) | test_idle_and_gpu.sh L<NNN>-<NNN> |

## 5. The SPLIT (load-bearing — for P1.M5.T5.S1)

- **Shell script (test_idle_and_gpu.sh RUN 1) = AUTHORITATIVE.** The only place the real 120 s + CPU% +
  no-crash trio is asserted end-to-end against real CUDA + ambient mic. Acceptance #5 is proven HERE.
- **Mocked pytest (test_daemon.py) = blocklist-guard LOGIC supplement.** Fast, CUDA-free; proves the
  guard rejects hallucinated text at the daemon level. It does NOT, and cannot, prove "120 s / CPU% /
  no-crash" (those need a live daemon). P1.M5.T5.S1 must credit #5 against the SHELL SCRIPT, with the
  mocked pytest as corroboration of the guard logic — NOT the reverse.

## 6. Correct-design notes (NOT gaps)

1. **CPU window amortizes the cold-load spike.** `cpu0` is captured BEFORE `voicectl start` (L<NNN>) →
   the ~1-3s cuDNN/cuBLAS load is included but amortized over 120 s+ → average is sound.
2. **auto_stop 30s handoff.** `auto_stop_idle_seconds` default = 30.0 (config.py:65) disarms the mic
   ~30s into the window → steady-state VAD-inference CPU drops to near-zero for ~90s. This is WHY CPU
   is trivially low (~2.5% on the original passing run). A future 'CPU regressed' alarm should check
   auto_stop firing first.
3. **/proc, not pidstat (G-CPU-SAMPLING).** pidstat/sysstat NOT installed → /proc tree-sum is the
   zero-dep path; PRD §6 T4's 'pidstat OR /proc' latitude is satisfied.
4. **Tree, not single PID (G-CPU-TREE).** CUDA workers + SafePipe spawn children; single-PID read would
   undercount. Recursive /proc/<pid>/task/<pid>/children walk.
5. **kill -0 crash signal.** Succeeds iff the PID exists; a crash (segfault/OOM/assertion) reaps it →
   [FAIL]. Correct + sufficient.

## 7. Scope

- **IN scope (this item):** T4 (a)(b)(c) coverage across both test homes + the mocked-pytest run +
  Acceptance #5 mapping.
- **OUT of scope (cited, not re-audited):** T6 GPU lifecycle (nvidia-smi VRAM idle/armed/disarmed/
  unload) → **P1.M5.T3.S2**; the idle-UNLOAD mocked tests (T6(d)-adjacent) → P1.M5.T3.S2 / P1.M2.T2.S3;
  the blocklist unit tests (test_textproc.py) → P1.M2.T2.S1.
```

### Implementation Patterns & Key Details

```bash
# The ONE live command (work-item step 3, AGENTS.md double-timeout). Run via the bash tool with
# `timeout` >= 360; the inner `timeout 300` self-terminates on wedge (exit 124 = wedged/loaded-CUDA).
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or hallucin or silence or cpu'

# If you need to confirm no daemon is running BEFORE the pytest (so the mocked tests don't see a real
# control socket — they shouldn't, but belt-and-suspenders), wrap it per AGENTS.md Rule 1:
timeout 15 .venv/bin/voicectl status 2>/dev/null || true   # exit 2 / non-zero = no daemon = fine
```

### Integration Points

```yaml
DELIVERABLE:
  - create: "plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md"
  - pattern: "Self-contained coverage-assessment report (the verbatim scaffold in Task 3 SOURCE)."
  - consume_by: "P1.M5.T5.S1 (acceptance cross-check) reads this as the evidence artifact for
                 Acceptance #5; P1.M5.T3.S2 (parallel T6 audit) — cite for scope boundary."

RUN (the one live action):
  - command: "timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or hallucin or silence or cpu'"
  - bash_tool_timeout: ">= 360 (AGENTS.md belt-and-suspenders over the inner 300)"
  - expected: "FAST, CUDA-free; all selected tests PASS; capture verbatim + annotate T4-relevant vs collateral"

DO NOT RUN:
  - command: "tests/test_idle_and_gpu.sh"
  - reason: "CUDA ~5-8 min (2 cold inits + 120s armed idle + idle-unload waits); AGENTS.md + parallel
             T6 audit both say 'do NOT run unless explicitly required.' STATIC read only."

EDITS (NONE — REPORT item):
  - forbidden: "tests/*, voice_typing/*, config.toml, PRD.md, tasks.json, prd_snapshot.md, .gitignore"
  - only_write: "plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md (CREATE)"
```

## Validation Loop

### Level 1: Syntax & Style (N/A — no code; Markdown report)

```bash
# The deliverable is a Markdown report — no ruff/mypy. Just verify it's written + self-contained.
ls -la plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md
# Sanity: the verdict line + the 8 sections are present.
grep -c '^## ' plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md   # expect >= 7
grep -q 'FULLY COVERED' plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md && echo OK
```

### Level 2: The mocked pytest (the ONE live validation — work-item step 3)

```bash
# AGENTS.md double-timeout. CUDA-free per test_daemon.py header L1-10; runs in seconds.
# bash-tool `timeout` >= 360 (belt-and-suspenders over the inner 300).
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'idle or hallucin or silence or cpu'
# Expected: all selected tests PASS (exit 0), no torch/cuDNN/cuBLAS in output, runs in seconds.
# If exit 124 (timed out) OR CUDA load appears: Ctrl-C + AGENTS.md Cleanup block; that's a FINDING
# (header promises CUDA-free), not a retry loop.
```

### Level 3: Static cross-check (no run — confirms the matrix against LIVE files)

```bash
# Confirm the T4 block + cpu helper + constants exist where the report claims (line numbers may drift).
grep -n 'IDLE_SECS=120\|CPU_LIMIT_PCT=25' tests/test_idle_and_gpu.sh
grep -n 'cpu_tree_seconds()' tests/test_idle_and_gpu.sh
grep -n 'kill -0 "$DAEMON_PID"' tests/test_idle_and_gpu.sh
grep -n 'last_final_before\|last_final_after' tests/test_idle_and_gpu.sh
grep -n 'test_on_final_rejects_hallucination\|NO real RealtimeSTT' tests/test_daemon.py
grep -n 'blocklist' config.toml
# Expected: every grep hits >= 1 line; the report's line numbers match (re-confirm if drifted).
```

### Level 4: Domain-specific validation (the mitigation cross-check)

```bash
# Confirm the blocklist guard is the documented hallucination defense (textproc docstring names T4).
grep -n 'hallucination\|T4\|blocklist' voice_typing/textproc.py | head
# Confirm VT-006 'you' removal is documented.
grep -n 'you' config.toml
# Expected: textproc docstring names T4 + the blocklist as the primary defense; config.toml NOTE
# explains the 'you' removal.
```

## Final Validation Checklist

### Technical Validation

- [ ] Level 2 mocked pytest RUN (double-timeout) — all selected tests PASS, CUDA-free, output captured.
- [ ] Level 3 static cross-check — every claimed line number greps ≥ 1 hit in the LIVE file.
- [ ] Level 4 mitigation cross-check — textproc docstring names T4 + blocklist; config.toml VT-006 note.
- [ ] `test_results_t4.md` written to `plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md` (NEW).

### Feature Validation

- [ ] Coverage matrix (a)(b)(c) COMPLETE with verdicts + exact line numbers + LIVE-source citations.
- [ ] The SPLIT stated: shell script = authoritative 120 s end-to-end; mocked pytest = blocklist-guard logic.
- [ ] Acceptance #5 mapping explicit (3 clauses → evidence → artifact).
- [ ] Mitigation chain documented (VAD + blocklist) with the VT-006 'you' nuance.
- [ ] Correct-design notes recorded (cold-load amortization, auto_stop 30s handoff, /proc-not-pidstat,
      tree-not-single-PID, kill-0 crash signal).
- [ ] `-k` collateral matches annotated (idle/idle-unload/cpu-fallback/silence) so 'T4 CPU is unit-
      tested' isn't misread.

### Code Quality Validation

- [ ] Report is self-contained (a reader needs no other file to understand the T4 coverage verdict).
- [ ] Line numbers LIVE-confirmed (re-checked against the actual files, not copied from this PRP blindly).
- [ ] Citations to source-side gap docs (gap_textproc/gap_daemon_loop/gap_lifecycle) are one-liners, not
      duplicated findings.
- [ ] Scope respected: T6 cited to P1.M5.T3.S2, NOT re-audited.

### Documentation & Deployment

- [ ] The report's verdict line is unambiguous ("T4 FULLY COVERED …").
- [ ] The one live action (mocked pytest) is reproducible from the report's command.
- [ ] No source/test/script/config/PRD/tasks file modified (REPORT item).

---

## Anti-Patterns to Avoid

- ❌ Don't RUN `tests/test_idle_and_gpu.sh` — it loads CUDA for ~5-8 min. STATIC read only (consistent
  with the parallel T6 audit). The ONE live action is the mocked pytest.
- ❌ Don't skip the double-timeout on the mocked pytest because "the header says CUDA-free." AGENTS.md
  Rule 1 is non-negotiable + lists test_daemon.py as a hang risk. Inner `timeout 300` + bash-tool `timeout` ≥ 360.
- ❌ Don't claim the mocked pytest proves T4's 120 s / CPU% / no-crash — it proves ONLY the blocklist
  guard. The shell script is authoritative for the end-to-end trio. State the SPLIT.
- ❌ Don't misread the `-k 'cpu'` matches as T4-CPU tests — they're device-resolution config tests
  (collateral). Annotate T4-relevant vs collateral in the report.
- ❌ Don't claim T4(a) proves VAD specifically OR the blocklist specifically — it proves the COMBINED
  result (no finals typed). The mocked unit test is what isolates the blocklist layer.
- ❌ Don't re-audit T6 (nvidia-smi VRAM) — that's P1.M5.T3.S2. CITE it; don't duplicate.
- ❌ Don't edit any source/test/script/config/PRD/tasks file — this is a REPORT item. The ONLY write is
  `plan/006_862ee9d6ef41/P1M5T4S1/test_results_t4.md`.
- ❌ Don't "fix" the blocklist by re-adding 'you' — VT-006 removed it deliberately (a word users type).

---

## Confidence Score

**9/10** for one-pass implementation success. The coverage matrix + the CUDA-free confirmation + the
exact pytest command + the verbatim report scaffold are all pre-verified against the LIVE files. The
one residual risk: line-number drift between this PRP's citations and the live files at implementation
time — Task 1 explicitly says to CONFIRM line numbers, and Level 3 cross-checks them. The mocked pytest
is fast + deterministic (CUDA-free). No ambiguity in scope (T4 only; T6 → P1.M5.T3.S2) or deliverable
(one report, exact path).