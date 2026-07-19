# PRP — P1.M2.T3.S3: Verify T7 Lite Test Coverage (single model, ≥70% accuracy, snappier latency)

## Goal

**Feature Goal**: Produce the authoritative **T7 lite test-COVERAGE audit** as a new **section
APPENDED to `plan/006_862ee9d6ef41/architecture/gap_lite.md`**, verifying that **PRD §6 T7** (lite
mode) is fully covered by the existing test suite across `tests/test_feed_audio.py` (the offline
pipeline) + `tests/test_daemon.py` (the lite socket protocol) + the adjacent wire/CLI surfaces
(`test_control_socket.py`, `test_voicectl.py`, `test_status_sh.py`, `test_config.py`). This is a
**test-coverage verification** subtask of compliance round `006_862ee9d6ef41`: the deliverable is the
report section; **new tests are written ONLY if a real coverage gap is found — NONE is expected. This
PRP's author has already performed the audit and T7 coverage is COMPREHENSIVE (every clause has a
covering test with file:line evidence).**

> **VERIFIED VERDICT (this PRP's research): T7 coverage is ✅ COMPREHENSIVE — no gaps; no new tests.**
> The contract run target `pytest tests/ -q -k 'lite'` collects **26 tests / 398 deselected**
> (collect-only, re-ran live, fast/safe). Per-file: `test_daemon.py`=15 (4 kwargs + 11 mode-switch/
> socket-behavior), `test_config.py`=4 (lite config fields), `test_feed_audio.py`=2
> (`test_lite_feed_audio_utt_simple` + `test_lite_latency_lower_than_normal`, GPU-gated → skip w/o
> CUDA), `test_control_socket.py`=1, `test_voicectl.py`=1, `test_status_sh.py`=1 (the ⚡ prefix),
> `test_recorder_host.py`=0 (non-defect — S1 §4(ii)), `test_typing_backends.py`=1 (false-positive —
> "lite**ral**", NOT a lite test). Every T7 clause is covered: **(a) one model resident** →
> `test_lite_feed_audio_utt_simple@test_feed_audio.py:667` asserts `use_main_model_for_realtime is
> True` (integration) + 3 kwargs unit tests; **(b) finals ≥70% fuzzy** → `test_lite_feed_audio_
> utt_simple@test_feed_audio.py:676` asserts `_token_overlap >= 0.70`; **(c) shorter silence +
> lower latency** → `test_cfg_to_kwargs_lite_uses_shorter_silence_duration@test_daemon.py:216` (0.5
> vs 0.6) + `test_lite_latency_lower_than_normal@test_feed_audio.py:679` (`lite <= normal*1.25`
> band); **socket** → `test_toggle_lite_while_armed_in_lite_disarms@3708`, `test_toggle_while_
> armed_in_lite_switches_to_normal@3753` (`len(spawns)==2` = ONE reload), `test_status_snapshot_
> reports_mode@2918`, `test_dispatch_status_response_carries_mode@test_control_socket.py:143`.

**Deliverable** (ONE report SECTION appended to `gap_lite.md`; NO source edits, NO test edits unless a
real gap surfaces — none is expected): `plan/006_862ee9d6ef41/architecture/gap_lite.md` gains a new
**`## Gap Report — P1.M2.T3.S3: T7 Lite Test Coverage vs PRD §6`** section (an `## ` H2 sibling).
Format mirrors the `gap_lifecycle.md` per-subtask section pattern (P1.M2.T2.S1–S4 each appended a §N)
and S1's section already in `gap_lite.md`: title + date + scope + audited artifacts (test file:line) +
bottom-line verdict + §1 Method (collect-only + grep + run commands) + §2 per-clause coverage table
(T7 clause | covering test file:line | verdict) + §3 test inventory by file + §4 non-defect nuances +
conclusion tying the verdict to PRD §6 T7 + acceptance #10's testability. **This PRP's author has
already performed the audit** (full clause→test map in the research note) — the implementing agent
re-verifies, re-runs the contract target, and transcribes the section.

> **FILE-OWNERSHIP NOTE (parallel with S1 + S2).** S1 (P1.M2.T3.S1) CREATED `gap_lite.md` as a
> standalone H1 file. S2 (P1.M2.T3.S2) APPENDS its `## Gap Report — P1.M2.T3.S2: ...` H2 section.
> **S3 (this task) APPENDS its `## Gap Report — P1.M2.T3.S3: ...` H2 section** below whatever is
> there (S1's H1 content, and S2's section if S2 ran first). Because S1/S2/S3 are produced in the
> same compliance round, S3's implementation must be **robust to ordering**: APPEND only — never
> overwrite S1's or S2's content (read-modify-write preserving everything above, or `>>`). If
> `gap_lite.md` somehow does not yet exist, create it with a minimal H1 `# Gap Reports — Lite Mode
> (PRD §4.2ter)` header followed by the S3 section (see Task 6 + CRITICAL #5).

**Success Definition**:
- (a) `gap_lite.md` contains a section titled `## Gap Report — P1.M2.T3.S3: T7 Lite Test Coverage vs
  PRD §6` with the sub-parts (scope/artifacts, bottom line, §1 method, §2 coverage table, §3 inventory,
  §4 nuances, conclusion).
- (b) The recorded findings match the live re-verification: every T7 clause (feed_audio a/b/c + socket
  4 bullets) has a covering test with `tests/*.py` file:line.
- (c) `timeout 600 .venv/bin/python -m pytest tests/ -q -k 'lite'` is run + the result recorded. The
  collect-only baseline is **26 collected, 398 deselected** (re-ran live). The RUN result: **~24 passed,
  2 skipped** without CUDA (the 2 feed_audio tests skip "G-CPU") OR **26 passed** with CUDA (slow —
  loads real models; minutes). Record whichever the box shows.
- (d) **No `tests/*` or `voice_typing/*` files are modified** (because no gap exists — T7 coverage is
  comprehensive per audit). If — and only if — re-verification surfaces a REAL gap, write the missing
  test (TDD per SOW §3) and record it; otherwise record "none — comprehensive, no new tests."
- (e) `git status --short` shows ONLY `plan/006_862ee9d6ef41/architecture/gap_lite.md` (modified — S3's
  appended section; or new — if neither S1 nor S2 had created it) — no `voice_typing/*`, no `tests/*`,
  no `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore` change.

## User Persona

**Target User**: the maintainer (human or AI agent) who needs to trust that **PRD §6 T7** — the lite
mode's test plan — is actually backed by tests that assert the three load-bearing lite guarantees
((a) exactly ONE model resident, no distil-large-v3 worker; (b) finals ≥70% fuzzy over the clean→type
path; (c) the shorter silence gate + materially lower latency) AND the socket protocol
(toggle-lite arms with `mode:"lite"` in the response; toggle-lite again disarms; toggle reloads to
normal in one reload; status reports mode). Also the downstream **P1.M5.T5** acceptance-criteria
cross-check (maps acceptance #10's testability — "verified ~half the VRAM", "observably snappier",
"status and state.json report mode" — to these tests).

**Use Case**: A future change to lite construction, the mode-switch mechanic, or the socket response.
The T7 coverage map is the reference that proves the change keeps (or breaks) test coverage of the
one-model / accuracy / latency / socket-protocol contract — and tells the changer WHERE to add a test
if a new lite behavior is introduced.

**Pain Points Addressed**: Closes the "does a test actually ASSERT that lite loads one model (not just
construct it), that finals hit ≥70% on the real recorder, that the silence gate is shorter AND the
latency is lower, and that the socket surfaces mode on toggle-lite/disarm/reload/status?" question
with recorded, re-runnable evidence — not an assumption.

## Why

- **T7 is the lite acceptance gate.** PRD §6 T7 is the ONLY test clause that explicitly covers lite
  mode's three guarantees + its socket protocol. Without coverage, a regression (e.g. a RealtimeSTT
  upgrade silently loading TWO models; the silence gate not being shortened; the arm response dropping
  `mode`) would ship silently. This audit certifies each T7 clause has a pinning test (file:line).
- **Complementary to S1/S2 (not duplicate).** S1 audited the lite CONSTRUCTION CODE (compliant); S2
  audited the mode-switch RELOAD CODE (compliant). S3 audits the TEST COVERAGE — a distinct angle:
  "regardless of whether the code is compliant, is there a TEST that would FAIL if it weren't?" The
  three audits together certify both the implementation AND its guard-rails.
- **No-invented-work discipline.** The audit finds coverage COMPREHENSIVE. The implementing agent must
  NOT invent gaps to justify writing tests (that bloats the suite + masks the real verdict). The 6
  non-defect nuances (§4 / CRITICAL #6) document the cases where the test deviates from the literal
  PRD wording but is a sound, documented engineering choice — so they are not mistaken for gaps.

## What

Re-verify T7 test coverage by (1) collecting the lite-test inventory (`pytest tests/ -q -k 'lite'
--collect-only` → record 26/398), (2) grepping the cited tests to confirm each exists + asserts what
the research note documents, (3) RUNNING the contract target (`pytest tests/ -q -k 'lite'`, wrapped in
`timeout 600`) and recording the result, and (4) APPENDING the `## Gap Report — P1.M2.T3.S3: ...`
section to `gap_lite.md`. The audit is expected to confirm comprehensive coverage (no gaps → no new
tests). The section's coverage table maps each T7 clause to its covering test (file:line) + verdict.

### Success Criteria

- [ ] `gap_lite.md` contains the `## Gap Report — P1.M2.T3.S3: T7 Lite Test Coverage vs PRD §6` section
  + the sub-parts.
- [ ] Coverage table covers: **(a)** one-model resident (`test_lite_feed_audio_utt_simple` integration
  + 3 kwargs unit tests); **(b)** finals ≥70% fuzzy (`test_lite_feed_audio_utt_simple`); **(c)** shorter
  silence (`test_cfg_to_kwargs_lite_uses_shorter_silence_duration`) + lower latency
  (`test_lite_latency_lower_than_normal`); **socket** toggle-lite-arms-mode-in-response
  (`test_start_lite_loads_lite_host_and_arms` + `test_dispatch_status_response_carries_mode`);
  toggle-lite-again-disarms (`test_toggle_lite_while_armed_in_lite_disarms`); toggle-reloads-normal-
  one-reload (`test_toggle_while_armed_in_lite_switches_to_normal` `len(spawns)==2`); status-reports-
  mode (`test_status_snapshot_reports_mode` + voicectl + status_sh ⚡).
- [ ] `timeout 600 .venv/bin/python -m pytest tests/ -q -k 'lite'` → recorded (collect-only
  `26/424, 398 deselected`; run count per the box's CUDA state).
- [ ] No `tests/*` or `voice_typing/*` files modified (`git status --short` == `gap_lite.md` only —
  modified/new). (If a real gap was found + a test written, that `tests/*` change is ALSO expected —
  record it in the section; otherwise none.)
- [ ] Conclusion ties the verdict to PRD §6 T7 + acceptance #10's testability; defers the live GPU
  VRAM/accuracy pass to `test_idle_and_gpu.sh` (P1.M5.T3) + the real-hardware smoke (T5, README).

## All Needed Context

### Context Completeness Check

_Pass._ The audit is **already performed** by this PRP's author (research note §0: the contract run
target collect-only baseline `26/424, 398 deselected` + per-file breakdown; §1: the full T7 clause→
covering-test map with file:line for feed_audio a/b/c + socket 4 bullets; §2: the 2 GPU-gated
integration tests read in full (what they assert, line-by-line); §3: the 15 `test_daemon.py` lite
tests indexed; §4: the 6 non-defect nuances). A developer new to this repo can re-verify from the
research note + the cited test lines + the grep/collect/run commands. The nuances (one-model proven
via flag not VRAM; path shared by fixture construction; latency uses a 25% band not strict `<`;
test_recorder_host.py has 0 lite tests; arm-response-mode is structurally guaranteed; the typing-
backends false-positive) are documented so they are not mistaken for gaps.

### Documentation & References

```yaml
# MUST READ — the pre-verified coverage audit (clause→test map + contract-target baseline + nuances).
- docfile: plan/006_862ee9d6ef41/P1M2T3S3/research/t7_coverage_audit.md
  why: "§0 ★ the contract run target COLLECT-ONLY baseline (26/424, 398 deselected) + per-file breakdown
        + run semantics (skip vs CUDA). §1 ★ the T7 clause→covering-test table (feed_audio a/b/c +
        socket 4 bullets, each with tests/*.py file:line + verdict). §2 the 2 GPU-gated integration
        tests read in full. §3 the 15 test_daemon.py lite tests indexed (kwargs 4 + mode-switch 11).
        §4 the 6 NON-DEFECT nuances (flag-not-VRAM; path-by-construction; latency-25%-band;
        test_recorder_host.py=0; arm-response-structural; typing-backends-false-positive). §5 the
        gap_lite.md section shape. §6 scope boundaries (disjoint from S1/S2). §7 the re-grep commands."
  section: "ALL load-bearing. §0 (the count), §1 (the clause→test table), §4 (the nuances)."

# MUST READ — the gap-report section format to mirror (per-subtask §N-append pattern).
- docfile: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md
  why: "The canonical pattern for MULTIPLE subtasks appending sections to ONE gap file: P1.M2.T2.S1-S4
        each appended a §N section (title + Date/Scope/Audited-artifacts(file:line) + 'Bottom line:'
        verdict + §1 Method + §2 per-property table + §3 test pass/fail count + §4 non-defect nuances
        + conclusion). gap_lite.md is the lite-mode area file (S1 created it; S2 + S3 append sections)."
  critical: "Mirror the SECTION format (## title), not a whole-file rewrite. S1's section is the H1
             content; S2's + S3's sections are ## H2 siblings BELOW it. APPEND only."

# MUST READ — the file S1 created + S2 appends to (S3 appends too). Read to confirm the current shape.
- docfile: plan/006_862ee9d6ef41/architecture/gap_lite.md
  why: "S1 (P1.M2.T3.S1) CREATED this file with H1 '# Gap Report — P1.M2.T3.S1: Lite Recorder
        Construction vs PRD §4.2ter' (the 4 kwargs clauses). S2 APPENDS its '## Gap Report —
        P1.M2.T3.S2: Mode-Switch Reload ...' H2 section. S3 (THIS task) APPENDS its '## Gap Report —
        P1.M2.T3.S3: T7 Lite Test Coverage ...' H2 section below whatever is there."
  critical: "Do NOT overwrite S1's or S2's sections. APPEND (read-modify-write PRESERVING all content
             above, or >>). If the file is somehow absent, create with a minimal H1 + the S3 section
             (CRITICAL #5). The whole file stays in git as ONE artifact accumulating lite-audit sections."

# MUST READ — the two contract INPUT files (T7 coverage lives here).
- file: tests/test_feed_audio.py
  why: "The OFFLINE pipeline + lite integration tests. lite_recorder fixture @L311 (builds
        cfg_to_kwargs(cfg, lite=True) — the REAL swap). test_lite_feed_audio_utt_simple @L653
        (T7(a): rec.use_main_model_for_realtime is True @L667; T7(b): _token_overlap >= 0.70 @L676).
        test_lite_latency_lower_than_normal @L679 (T7(c): lite_best <= normal_best*1.25 @L774, the
        25% band; best-of-3 min). _token_overlap helper @L142 (the fuzzy multiset matcher; PRD §6
        >=0.80 normal / >=0.70 lite). GPU-gated: pytest.skip if not cuda_check.is_cuda_available()."
  pattern: "session-scoped fixtures coexist (recorder + lite_recorder share the GPU); _run_utterance
            harness feeds WAV chunks in real-time pacing + collects finals via the shared on_final path."
  gotcha: "These 2 tests SKIP without CUDA (G-CPU) → the run shows '2 skipped'; with CUDA they LOAD
           REAL MODELS (small.en + distil-large-v3) → minutes, MUST wrap in timeout 600 (AGENTS.md)."

# MUST READ — the lite socket-behavior + kwargs unit tests (mocked-CUDA, ~0.04s).
- file: tests/test_daemon.py
  why: "15 lite tests (kwargs 4 + mode-switch/socket 11). kwargs: test_cfg_to_kwargs_lite_mode_uses_
        one_model@138, test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en@165,
        test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal@185,
        test_cfg_to_kwargs_lite_uses_shorter_silence_duration@216. socket: test_start_lite_loads_
        lite_host_and_arms@2863 (d._mode=='lite'+fb.modes==['lite']), test_mode_switch_normal_to_
        lite_reloads@2875, test_same_mode_arm_is_instant_no_reload@2892,
        test_toggle_lite_while_listening_in_lite_stops@2904 (disarm), test_status_snapshot_reports_
        mode@2918, test_mode_switch_stops_outgoing_host@2927 (outgoing stop_calls==1),
        test_start_lite_after_idle_unload_reloads_in_lite@2951, test_toggle_lite_while_idle_arms_in_
        lite@3696, test_toggle_lite_while_armed_in_lite_disarms@3708 (len(spawns)==1),
        test_toggle_lite_while_armed_in_normal_switches_to_lite@3719, test_toggle_while_armed_in_lite_
        switches_to_normal@3753 (len(spawns)==2 = ONE reload), test_toggle_lite_while_armed_in_normal_
        failed_reload_clears_listening@3790, test_toggle_while_armed_in_lite_failed_reload_clears_
        listening@~3803, test_toggle_lite_docstring_says_pressing_d_not_f@3851."
  critical: "The 'one reload' count is pinned by len(spawns)==2 in test_toggle_while_armed_in_lite_
             switches_to_normal@3753 + the reverse @3719; the disarm-no-reload by len(spawns)==1
             @3708. These are the T7 socket-clause pins."

# MUST READ — the wire-response-carries-mode proof (structural, for nuance §4.5).
- file: tests/test_control_socket.py
  why: "test_dispatch_status_response_carries_mode@143 — proves the {'ok':True,**status_snapshot()}
        spread surfaces mode on the wire (uses a _ModeDaemon subclass that emits mode:'lite'). This is
        the structural proof the ARM response carries mode (since _arm_response@daemon.py:1890 spreads
        the same status_snapshot that has 'mode'@1567)."
  pattern: "ControlServer._dispatch tested directly (no socket) with a _StubDaemon recording calls."

# MUST READ — the daemon arm-response + status_snapshot path (the wire-mode mechanism).
- file: voice_typing/daemon.py
  why: "_arm_response@1875-1890 ('return {\"ok\": True, **self._daemon.status_snapshot()}' @L1890 —
        the arm response spreads status_snapshot). status_snapshot@1565-1567 ('\"mode\": self._mode'
        @L1567 — PRD §4.2ter 'normal'|'lite'). _dispatch@1892-1939 routes toggle/start/start-lite/
        toggle-lite/stop/status/quit → _arm_response (arms) or {'ok':True,**status_snapshot()} (status)."
  gotcha: "The arm response carrying mode is PROVEN by composition: _arm_response spreads
           status_snapshot (has mode) + test_dispatch_status_response_carries_mode proves status's mode
           reaches the wire. A direct _dispatch('toggle-lite')['mode'] test would be redundant (nuance
           §4.5) — do NOT add it unless you want optional hardening."

# CONTEXT — the CLI + tmux surfaces of mode (status-reports-mode clause).
- file: tests/test_voicectl.py
  why: "test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode — voicectl accepts
        toggle-lite/start-lite + format_result renders 'mode:' (L78 shows format_result with
        mode:'lite'). One of the 4 'status reports mode' surfaces."
- file: tests/test_status_sh.py
  why: "test_status_sh_lite_mode_prefixes_bolt — the tmux status line prefixes lite with ⚡ (PRD §4.2ter
        'State / status'). Another status-reports-mode surface."

# CONTEXT — the config-field tests (lite_model / lite_post_speech_silence_duration).
- file: tests/test_config.py
  why: "4 tests match -k 'lite' via the lite_model / lite_post_speech_silence_duration config params.
        Confirms the lite config fields are validated by the AsrConfig known-keys loader (SOW input)."

# CONTEXT — the PRD spec being audited against.
- docfile: PRD.md   # §6 T7 (lite test plan) + §4.2ter (lite mode spec) + §7 #10 (acceptance)
  why: "§6 T7 — the 3 feed_audio asserts (a one-model resident; b finals ≥70% fuzzy; c shorter silence
        + materially lower latency) + the 4 socket bullets (toggle-lite arms mode:'lite'; toggle-lite
        again disarms; toggle reloads normal one-reload; status reports mode). §4.2ter — the lite spec
        the tests encode. §7 #10 — acceptance (verified ~half VRAM; observably snappier; status +
        state.json report mode). Map each to its covering test in the coverage table."

# CONTEXT — the sibling tasks (disjoint scope; S3 APPENDS to S1+S2's file).
- docfile: plan/006_862ee9d6ef41/P1M2T3S1/PRP.md
  why: "S1 = lite CONSTRUCTION CODE audit (the 4 kwargs clauses). CREATED gap_lite.md. S3 cites S1's
        kwargs tests (test_cfg_to_kwargs_lite_*) as the (a)/(c) UNIT coverage; S1 §4(ii) already
        recorded test_recorder_host.py=0 lite tests as a non-defect (S3 reuses that nuance §4.4)."
- docfile: plan/006_862ee9d6ef41/P1M2T3S2/PRP.md
  why: "S2 = mode-switch RELOAD CODE audit (the 6 clauses). APPENDS its H2 section to gap_lite.md. S3
        cites S2's mode-switch tests (test_mode_switch_*, test_toggle_while_armed_in_lite_*) as the
        socket-clause coverage. SAME FILE; disjoint ANGLE (S2=code compliant? S3=tests cover it?). If
        S2's section is already present when S3 runs, S3 appends BELOW it."
```

### Current Codebase tree (relevant slice — audit reads these; writes ONLY the gap_lite.md section)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py          # READ: _arm_response@1875-1890 (spreads status_snapshot), status_snapshot@1565
│   │                      #       ("mode":self._mode@1567), _dispatch@1892-1939
│   └── (config.py, recorder_host.py, ctl.py, feedback.py — READ-ONLY per S1/S2 if needed)
├── tests/
│   ├── test_feed_audio.py     # RUN: test_lite_feed_audio_utt_simple@653, test_lite_latency_lower_than_normal@679 (GPU-gated)
│   ├── test_daemon.py         # RUN: 15 lite tests (kwargs 4 @138-238 + mode-switch/socket 11 @2863-3851)
│   ├── test_control_socket.py # RUN: test_dispatch_status_response_carries_mode@143
│   ├── test_voicectl.py       # RUN: test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode
│   ├── test_status_sh.py      # RUN: test_status_sh_lite_mode_prefixes_bolt
│   ├── test_config.py         # RUN: 4 lite-config-field tests
│   ├── test_recorder_host.py  # (0 lite tests — nuance §4.4, NOT a gap)
│   └── test_typing_backends.py# (1 FALSE-POSITIVE — "lite**ral**", nuance §4.6, NOT a lite test)
└── plan/006_862ee9d6ef41/architecture/
    ├── gap_lifecycle.md   # READ: the per-subtask section format to mirror
    └── gap_lite.md        # APPEND (S3's H2 section) — S1 created it; S2 may have appended; append below all
```

### Desired Codebase tree (what this task produces)

```bash
plan/006_862ee9d6ef41/architecture/gap_lite.md   # S3's section APPENDED (or created w/ H1 + section if absent)
# No tests/* or voice_typing/* changes. git status --short == gap_lite.md (modified or new).
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 — FULL PATHS in every bash command (zsh aliases python3→uv run). Use .venv/bin/python,
#   NEVER bare python/pytest. Two timeouts on every non-trivial command (AGENTS.md Rule 1): inner
#   `timeout` + the bash-tool `timeout` param above it (outer backstop). The control socket has NO
#   read timeout — never run untimed voicectl.

# CRITICAL #2 — test_feed_audio.py's 2 lite tests are GPU-GATED. `if not cuda_check.is_cuda_available():
#   pytest.skip("T7 is a GPU integration test (G-CPU)")`. WITHOUT CUDA → 2 skipped (fast); WITH CUDA →
#   they LOAD REAL MODELS (session-scoped recorder + lite_recorder fixtures hold small.en +
#   distil-large-v3) → MINUTES. The collect-only count (26/424) is the safe baseline; the RUN wraps
#   in `timeout 600`. Default expectation on a non-GPU box: ~24 passed, 2 skipped.

# CRITICAL #3 — The latency test asserts a 25% TOLERANCE BAND (`lite_best <= normal_best * 1.25`), NOT
#   strict "materially lower" (`<`). This is a DOCUMENTED, sound choice (in-test comment L758-777): on
#   a fast GPU a 9-word utterance shows the small-model win swamped by VAD/realtime-stabilization/GPU-
#   scheduling noise, so strict `<` is flaky; the test's job is to catch a two-model regression (~1.5-
#   2x slower), which the 1.25x band catches loudly. The one-model invariant (test_lite_feed_audio_
#   utt_simple) is the PRIMARY proof. Do NOT flag this as a gap or "tighten" it to strict `<` — it
#   would make the test flaky without adding real coverage. (Nuance §4.3.)

# CRITICAL #4 — "ONE model resident / ~half VRAM" is proven via the use_main_model_for_realtime FLAG
#   + the kwargs dict, NOT via VRAM measurement or child-log grep. PRD T7(a) literally says "grep the
#   child log / check VRAM ≈ half of normal" but the test asserts the AUTHORITATIVE mechanism (the flag
#   early-returns out of RealtimeSTT's realtime-engine init, so the large model never constructs → ~half
#   VRAM is structurally guaranteed). VRAM varies by GPU/driver; log-grep is brittle; the flag is
#   strictly MORE reliable. The live VRAM diff is exercised by tests/test_idle_and_gpu.sh T7 (shell
#   suite, P1.M5.T3) — OUT of scope for this pytest coverage audit. Do NOT flag as a gap. (Nuance §4.1.)

# CRITICAL #5 — FILE-OWNERSHIP RACE with S1 + S2. S1 CREATED gap_lite.md; S2 APPENDS; S3 APPENDS.
#   S3's implementation must be robust to ordering:
#     • `ls plan/006_862ee9d6ef41/architecture/gap_lite.md` SUCCEEDS (S1 done — expected; S2 may or
#       may not have appended): APPEND the '## Gap Report — P1.M2.T3.S3: ...' section BELOW all
#       existing content (read-modify-write PRESERVING S1's H1 + S2's section if present; or >> to
#       append). Do NOT overwrite.
#     • If it FAILS (neither S1 nor S2 ran — unlikely): CREATE gap_lite.md with a minimal H1
#       '# Gap Reports — Lite Mode (PRD §4.2ter)' + the S3 section, so the work is not lost (S1/S2
#       sections reconciled later / by P1.M5.T5).
#   In ALL cases the deliverable is the SAME S3 section content; only the file-prelude differs.

# CRITICAL #6 — This is a RE-VERIFICATION of already-comprehensive coverage. Do NOT invent gaps to
#   look thorough: if every T7 clause has a covering test (it does) + the contract target passes (it
#   will — 24 passed/2 skipped or 26 passed), the verdict is ✅ COMPREHENSIVE and NO tests/* files
#   change. New tests are written ONLY if re-verification surfaces a REAL gap (record it + the test).
#   The 6 nuances (§4) are the cases where the test deviates from literal PRD wording but is sound.

# CRITICAL #7 — Do NOT re-audit the lite CONSTRUCTION code (S1) or the mode-switch RELOAD code (S2).
#   S3's angle is TEST COVERAGE — "which test covers T7 clause X?" — citing S1/S2's tests as coverage
#   evidence without re-deriving the code compliance. The live GPU VRAM/accuracy pass is test_idle_and_
#   gpu.sh T7 (P1.M5.T3); the real-hardware smoke is T5 (README, P1.M6.T1) — both OUT of scope.

# CRITICAL #8 — test_typing_backends.py::test_wtype_text_starting_with_dash_stays_literal is a FALSE
#   POSITIVE (matches -k lite via "lite**ral**"). It is NOT a lite-mode test (it tests wtype text
#   escaping). Reconcile the collect-only count (26) by noting this in §3 so the count is honest.
```

## Implementation Blueprint

### Data models and structure

None (audit only). The "data" is the T7 clause→covering-test table + the contract-target count +
the 6 nuances, transcribed into the `gap_lite.md` section.

### Implementation Tasks (ordered by dependencies — a re-verify + transcribe runbook)

```yaml
Task 1: COLLECT the lite-test inventory (the contract-target baseline)
  - CMD: timeout 120 .venv/bin/python -m pytest tests/ -q -k 'lite' --collect-only
  - EXPECTED: "26/424 tests collected (398 deselected) in 0.05s" (research §0). Record in §3.
  - PER-FILE (confirm): test_daemon.py=15, test_config.py=4, test_feed_audio.py=2, test_control_
    socket.py=1, test_voicectl.py=1, test_status_sh.py=1, test_recorder_host.py=0, test_typing_
    backends.py=1 (FALSE-POSITIVE — note in §3).

Task 2: RE-VERIFY the feed_audio T7 coverage (clauses a/b/c)
  - READ tests/test_feed_audio.py: lite_recorder fixture @L311 (cfg_to_kwargs(cfg, lite=True) @L324);
    test_lite_feed_audio_utt_simple @L653 (guard skip @L660; T7(a) use_main_model_for_realtime is True
    @L667; T7(b) _token_overlap(joined, SIMPLE_TEXT) >= 0.70 @L676); test_lite_latency_lower_than_
    normal @L679 (guard skip @L692; best-of-3 _final_latency_ms; T7(c) lite_best <= normal_best*1.25
    @L774). READ _token_overlap @L142 (the fuzzy matcher).
  - VERDICT: (a)+(b)+(c) covered. Record file:line in §2 rows.

Task 3: RE-VERIFY the kwargs-unit + silence-gate coverage (clauses a-unit / c-silence)
  - GREP tests/test_daemon.py: test_cfg_to_kwargs_lite_mode_uses_one_model @L138 (model==
    realtime_model_type=="small.en" + use_main_model_for_realtime True; normal distil-large-v3 + False);
    test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en @L165 (CPU tiny.en, one-model preserved);
    test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal @L185 (only 4 fields differ);
    test_cfg_to_kwargs_lite_uses_shorter_silence_duration @L216 (0.5 vs 0.6, tunable to 0.3).
  - VERDICT: one-model kwargs + silence-gate covered. Record file:line in §2 rows.

Task 4: RE-VERIFY the socket-behavior coverage (socket 4 bullets)
  - GREP tests/test_daemon.py: toggle-lite-arms-mode → test_start_lite_loads_lite_host_and_arms @L2863
    (d._mode=="lite" + d._host.mode=="lite" + fb.modes==["lite"]); toggle-lite-again-disarms →
    test_toggle_lite_while_armed_in_lite_disarms @L3708 (is_listening False, len(spawns)==1) +
    test_toggle_lite_while_listening_in_lite_stops @L2904; toggle-reloads-normal-one-reload →
    test_toggle_while_armed_in_lite_switches_to_normal @L3753 (len(spawns)==2, d._mode=="normal") +
    test_mode_switch_stops_outgoing_host @L2927 (outgoing stop_calls==1) + test_mode_switch_normal_
    to_lite_reloads @L2875 (reverse) + test_same_mode_arm_is_instant_no_reload @L2892 (same-mode no
    reload) + test_start_lite_after_idle_unload_reloads_in_lite @L2951; status-reports-mode →
    test_status_snapshot_reports_mode @L2918.
  - GREP tests/test_control_socket.py: test_dispatch_status_response_carries_mode @L143 (wire mode).
  - GREP tests/test_voicectl.py: test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode
    (CLI mode: rendering); tests/test_status_sh.py: test_status_sh_lite_mode_prefixes_bolt (⚡).
  - READ voice_typing/daemon.py: _arm_response @L1875-1890 (spreads status_snapshot @L1890);
    status_snapshot "mode":self._mode @L1567 — the structural proof the arm response carries mode.
  - VERDICT: all 4 socket bullets covered. Record file:line in §2 rows + note the arm-response-mode
    is structurally guaranteed (nuance §4.5).

Task 5: RUN the contract target + record the result
  - CMD: timeout 600 .venv/bin/python -m pytest tests/ -q -k 'lite'
  - EXPECTED (non-GPU box): ~24 passed, 2 skipped (the 2 feed_audio tests skip "G-CPU") in ~0.04s.
    (GPU box: 26 passed but SLOW — minutes; the 2 feed_audio tests load real models.) Record in §1
    + §3. On a real FAILURE: debug root cause (do NOT weaken an assertion); if a test is GENUINELY
    missing coverage for a T7 clause, that's the gap — write the test (TDD, Task X) + record it.

Task 6: APPEND the section to gap_lite.md (mirror gap_lifecycle.md's per-subtask section format)
  - CHECK: `ls plan/006_862ee9d6ef41/architecture/gap_lite.md` (CRITICAL #5):
    • EXISTS (S1 done; S2 may have appended): read-modify-write PRESERVING all existing content;
      APPEND the S3 H2 section below it.
    • ABSENT (S1/S2 not run — unlikely): CREATE with H1 '# Gap Reports — Lite Mode (PRD §4.2ter)' +
      the S3 H2 section.
  - SECTION TITLE: "## Gap Report — P1.M2.T3.S3: T7 Lite Test Coverage vs PRD §6"
  - Date + Scope (T7 feed_audio a/b/c + socket 4 bullets) + Audited artifacts (test file:line list).
  - "Bottom line:" ✅ COMPREHENSIVE (all T7 clauses covered) + the contract-target count (collect
    26/424, 398 deselected; run per CUDA state) + acceptance #10 testability.
  - §1 Method: the collect-only command + the grep commands (research §7) + the run command (Task 5).
  - §2 per-clause coverage table (research §1A + §1B): T7 clause | covering test (file:line) | ✅.
  - §3 test inventory by file (research §0 table + §3 index) + the false-positive note.
  - §4 non-defect nuances (research §4): (4.1) flag-not-VRAM; (4.2) path-by-construction; (4.3)
    latency-25%-band; (4.4) test_recorder_host.py=0; (4.5) arm-response-structural; (4.6) typing-
    backends-false-positive.
  - Conclusion: T7 coverage is comprehensive; certifies acceptance #10's testability; defers the
    live GPU VRAM/accuracy pass to test_idle_and_gpu.sh (P1.M5.T3) + the real-hardware smoke (T5,
    README, P1.M6.T1). No tests/* or voice_typing/* modified.

Task 7: SCOPE GUARD — verify no tests/* or voice_typing/* files changed
  - CMD: git status --short
  - EXPECTED: ONLY `plan/006_862ee9d6ef41/architecture/gap_lite.md` (modified — S3 appended; or new —
    if S1/S2 absent). No voice_typing/*, no tests/*, no PRD.md/tasks.json/prd_snapshot.md/.gitignore.
    (If a real gap was found + a test written in Task X, that tests/* change is ALSO expected —
    record it in the section; otherwise none.)
```

### Implementation Patterns & Key Details

```bash
# PATTERN — a re-verification test-coverage audit: collect, grep the cited tests, run, transcribe.

# 1. Collect the lite-test inventory (fast/safe — no model load):
timeout 120 .venv/bin/python -m pytest tests/ -q -k 'lite' --collect-only
#   → "26/424 tests collected (398 deselected) in 0.05s"

# 2. Re-locate every cited lite test (the greps the gap report's §1 will cite):
grep -nE 'def test_cfg_to_kwargs_lite|def test_start_lite|def test_mode_switch|def test_same_mode_arm|def test_toggle_lite|def test_toggle_while_armed_in_lite|def test_status_snapshot_reports_mode|def test_start_lite_after_idle' tests/test_daemon.py
grep -nE 'def lite_recorder|def test_lite_feed_audio|def test_lite_latency|use_main_model_for_realtime|_token_overlap|>= 0\.70|<= normal_best' tests/test_feed_audio.py
grep -nE 'def test_dispatch_status_response_carries_mode|"mode"|_dispatch' tests/test_control_socket.py
grep -nE 'def test_lite_commands|def test_status_sh_lite|mode.*lite' tests/test_voicectl.py tests/test_status_sh.py
grep -nE 'def _arm_response|def status_snapshot|"mode": self\._mode' voice_typing/daemon.py

# 3. RUN the contract target (record the count for §1/§3):
timeout 600 .venv/bin/python -m pytest tests/ -q -k 'lite'
#   → non-GPU: ~24 passed, 2 skipped in ~0.04s. (GPU: 26 passed, slow.)

# 4. Append the section to gap_lite.md (CRITICAL #5: append, never overwrite):
F=plan/006_862ee9d6ef41/architecture/gap_lite.md
if [ -f "$F" ]; then echo "exists → APPEND '## Gap Report — P1.M2.T3.S3: ...' below S1(+S2)"; \
else echo "absent → CREATE with H1 '# Gap Reports — Lite Mode (PRD §4.2ter)' + the S3 section"; fi
#   (read-modify-write PRESERVING all content above; do NOT overwrite.)

# 5. Scope guard:
git status --short   # → ONLY gap_lite.md (modified or new). No voice_typing/*, no tests/*, no PRD/tasks.json.
```

### Integration Points

```yaml
CONSUMED (read-only — verify, don't change):
  - tests/test_feed_audio.py: lite_recorder@311, test_lite_feed_audio_utt_simple@653, test_lite_latency_
    lower_than_normal@679, _token_overlap@142.
  - tests/test_daemon.py: the 15 lite tests (kwargs 4 @138-238 + mode-switch/socket 11 @2863-3851).
  - tests/test_control_socket.py: test_dispatch_status_response_carries_mode@143.
  - tests/test_voicectl.py: test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode.
  - tests/test_status_sh.py: test_status_sh_lite_mode_prefixes_bolt.
  - tests/test_config.py: the 4 lite-config-field tests.
  - voice_typing/daemon.py: _arm_response@1875-1890, status_snapshot@1565-1567 ("mode"@1567), _dispatch@1892.
PRODUCED (this task):
  - plan/006_862ee9d6ef41/architecture/gap_lite.md — S3's "## Gap Report — P1.M2.T3.S3: T7 Lite Test
    Coverage vs PRD §6" section APPENDED (or the file created with H1 + S3 section if absent).
DOWNSTREAM CONSUMERS:
  - P1.M5.T2.S1 / P1.M5.T2.S2 (T1/T3 test-coverage validation): references this audit's feed_audio +
    socket test inventory.
  - P1.M5.T5 (acceptance cross-check): maps acceptance #10's testability ("verified ~half VRAM";
    "observably snappier"; "status + state.json report mode") to this audit's covering tests.
DO NOT TOUCH:
  - tests/* (no gap exists), voice_typing/*, PRD.md, **/tasks.json, **/prd_snapshot.md, .gitignore,
    pyproject.toml, uv.lock. No new deps. Do NOT overwrite S1's or S2's sections (append only).
```

## Validation Loop

> Full paths in every command (CRITICAL #1). Two timeouts (inner `timeout` + bash-tool `timeout`),
> per AGENTS.md. The unit/socket/config/CLI tests are mocked-CUDA (~0.04s); the 2 feed_audio tests
> are GPU-gated (skip w/o CUDA, or minutes w/ CUDA).

### Level 1: Re-verify the T7 clause→test map against the live tests (read the cited lines)

```bash
cd /home/dustin/projects/voice-typing
grep -nE 'def test_cfg_to_kwargs_lite|def test_start_lite|def test_mode_switch|def test_same_mode_arm|def test_toggle_lite|def test_toggle_while_armed_in_lite|def test_status_snapshot_reports_mode|def test_start_lite_after_idle' tests/test_daemon.py
grep -nE 'def lite_recorder|def test_lite_feed_audio|def test_lite_latency|use_main_model_for_realtime|_token_overlap|>= 0\.70|<= normal_best' tests/test_feed_audio.py
grep -nE 'def test_dispatch_status_response_carries_mode|"mode"|_dispatch' tests/test_control_socket.py
grep -nE 'def test_lite_commands|def test_status_sh_lite|mode.*lite' tests/test_voicectl.py tests/test_status_sh.py
grep -nE 'def _arm_response|def status_snapshot|"mode": self\._mode' voice_typing/daemon.py
# Expected: each clause's covering test file:line from research §1 is present and reads as documented.
#   (a) test_lite_feed_audio_utt_simple@667 use_main_model_for_realtime is True + kwargs@138/165/185.
#   (b) test_lite_feed_audio_utt_simple@676 _token_overlap >= 0.70.
#   (c) test_cfg_to_kwargs_lite_uses_shorter_silence_duration@216 + test_lite_latency_lower_than_normal@774.
#   socket: test_start_lite_loads_lite_host_and_arms@2863, test_toggle_lite_while_armed_in_lite_disarms@3708,
#   test_toggle_while_armed_in_lite_switches_to_normal@3753 (len(spawns)==2), test_status_snapshot_reports_
#   mode@2918, test_dispatch_status_response_carries_mode@test_control_socket.py:143.
```

### Level 2: Collect + run the contract target (the coverage gate)

```bash
cd /home/dustin/projects/voice-typing
# collect-only (fast/safe — the baseline count):
timeout 120 .venv/bin/python -m pytest tests/ -q -k 'lite' --collect-only
# Expected: "26/424 tests collected (398 deselected) in 0.05s".

# RUN the contract target (record the count):
timeout 600 .venv/bin/python -m pytest tests/ -q -k 'lite'
# Expected (non-GPU): ~24 passed, 2 skipped in ~0.04s. (GPU: 26 passed, slow — minutes.)
# On a real FAILURE: debug root cause (do NOT weaken an assertion). If a T7 clause genuinely has NO
#   covering test, that's the gap — write the missing test (TDD) + record it in the section. (None expected.)
```

### Level 3: Transcribe the section + scope guard

```bash
cd /home/dustin/projects/voice-typing
F=plan/006_862ee9d6ef41/architecture/gap_lite.md
# CRITICAL #5 — robust to S1/S2 ordering:
if [ -f "$F" ]; then echo "EXISTS (S1 done; S2 maybe) → APPEND '## Gap Report — P1.M2.T3.S3: ...' below"; \
else echo "ABSENT (S1/S2 not run) → CREATE with H1 '# Gap Reports — Lite Mode (PRD §4.2ter)' + the S3 section"; fi
# (read-modify-write PRESERVING all content above if present; do NOT overwrite.)
git status --short
# Expected: ONLY gap_lite.md (modified — S3 appended; or new — if absent). No voice_typing/*, no tests/*,
#   no PRD.md/tasks.json/prd_snapshot.md/.gitignore change.
```

### Level 4: Report completeness check (the deliverable quality gate)

```bash
cd /home/dustin/projects/voice-typing
F=plan/006_862ee9d6ef41/architecture/gap_lite.md
grep -qE '## Gap Report — P1.M2.T3.S3: T7 Lite Test Coverage' "$F" && echo "S3 section title OK"
grep -qE 'COMPREHENSIVE|✅' "$F" && echo "verdict OK"
grep -qE '26/424|26 collected|398 deselected' "$F" && echo "collect baseline OK"
grep -qE 'test_lite_feed_audio_utt_simple|test_cfg_to_kwargs_lite|test_toggle_while_armed_in_lite|test_status_snapshot_reports_mode' "$F" && echo "covering-test evidence OK"
grep -qiE 'nuance|non-defect' "$F" && echo "nuances section OK"
grep -qE 'acceptance #10|T7' "$F" && echo "PRD §6 T7 + acceptance #10 tie-in OK"
# Expected: all 6 checks pass → the section has title + verdict + collect count + covering-test evidence +
#   nuances + the T7/acceptance #10 tie-in.
```

## Final Validation Checklist

### Technical Validation
- [ ] Level 1: every T7 clause's covering test file:line present in the live tests and reads as
      documented (research §1).
- [ ] Level 2: `pytest tests/ -q -k 'lite' --collect-only` → `26/424, 398 deselected`; `timeout 600
      .venv/bin/python -m pytest tests/ -q -k 'lite'` → recorded (24 passed/2 skipped OR 26 passed).
- [ ] Level 3: `gap_lite.md` section appended (or created with H1 + section if S1/S2 absent); `git
      status --short` == `gap_lite.md` only (modified or new).
- [ ] Level 4: section has title + ✅ verdict + collect count + covering-test evidence + nuances + T7 tie-in.

### Feature (Coverage-Audit) Validation
- [ ] (a) one-model resident coverage verified (`test_lite_feed_audio_utt_simple` integration + 3 kwargs unit).
- [ ] (b) finals ≥70% fuzzy coverage verified (`test_lite_feed_audio_utt_simple` `_token_overlap >= 0.70`).
- [ ] (c) shorter-silence + lower-latency coverage verified (`test_cfg_to_kwargs_lite_uses_shorter_
      silence_duration` + `test_lite_latency_lower_than_normal`).
- [ ] socket: toggle-lite-arms-mode / toggle-lite-disarms / toggle-reloads-normal-one-reload / status-
      reports-mode all verified (test_daemon.py @2863/3708/3753/2918 + test_control_socket.py:143 +
      voicectl + status_sh ⚡).
- [ ] Coverage table maps each T7 clause to covering test (file:line) vs ✅.

### Code Quality / Scope Validation
- [ ] No `tests/*` or `voice_typing/*` files modified (no gap exists → no new test; T7 coverage is
      comprehensive per audit).
- [ ] S3 section is an `## ` H2 appended to gap_lite.md (NOT a new file, NOT overwriting S1/S2).
- [ ] Section follows the gap-report format (mirror gap_lifecycle.md's per-subtask sections + S1's).

### Forbidden-Operations Compliance
- [ ] `tests/*` NOT modified. `voice_typing/*` NOT modified.
- [ ] `PRD.md`, `**/tasks.json`, `**/prd_snapshot.md`, `.gitignore` NOT modified.
- [ ] S1's and S2's sections in gap_lite.md NOT overwritten (append-only; create-with-H1 only if absent).
- [ ] No new deps; no `pyproject.toml`/`uv.lock` change.

---

## Anti-Patterns to Avoid

- ❌ Don't invent coverage gaps to look thorough — T7 coverage is COMPREHENSIVE (pre-verified). If every
  clause has a covering test (it does) + the contract target passes, the verdict is ✅ and NO `tests/*`
  files change. Record nuances, not phantom gaps.
- ❌ Don't flag the latency test's 25% band (`<= normal*1.25`) as a gap or "tighten" it to strict `<` —
  it is a documented, sound choice (GPU noise on a 9-word utterance makes strict `<` flaky; the test
  catches the real two-model regression ~1.5-2x slower; the one-model invariant is the primary proof)
  (CRITICAL #3 / nuance §4.3).
- ❌ Don't flag the one-model check using `use_main_model_for_realtime` (not VRAM/grep) as a gap — the
  flag is the authoritative mechanism (structurally guarantees ~half VRAM); the live VRAM diff is
  `test_idle_and_gpu.sh` T7's job (P1.M5.T3), out of scope for this pytest audit (CRITICAL #4 / §4.1).
- ❌ Don't flag `tests/test_recorder_host.py` having 0 lite tests as a gap — lite construction is unit-
  tested at the `cfg_to_kwargs` layer (test_daemon.py) + the child is a pass-through (S1 §4(ii) / §4.4).
- ❌ Don't flag the arm-response carrying mode as a gap — it's structurally guaranteed (`_arm_response`
  spreads `status_snapshot` which has `mode`) + proven by `test_dispatch_status_response_carries_mode`
  (CRITICAL #... / nuance §4.5). A direct `_dispatch("toggle-lite")["mode"]` test would be redundant.
- ❌ Don't overwrite S1's or S2's `gap_lite.md` content — APPEND the S3 H2 section below all existing
  content (or create with a minimal H1 + S3 section ONLY if the file is absent) (CRITICAL #5).
- ❌ Don't re-audit the lite construction CODE (S1) or the mode-switch reload CODE (S2) — S3's angle is
  TEST COVERAGE only; cite their tests as coverage evidence (CRITICAL #7).
- ❌ Don't use bare `python`/`pytest` (zsh aliases). Full paths: `.venv/bin/python`. Two timeouts
  (inner `timeout` + outer bash-tool `timeout`), per AGENTS.md.
- ❌ Don't count `test_wtype_text_starting_with_dash_stays_literal` as a lite test — it's a FALSE
  POSITIVE (matches "lite**ral**"); reconcile the 26-collected count honestly in §3 (CRITICAL #8).

---

## Confidence Score

**9.5/10** for one-pass success. This is a re-verification test-coverage audit with every fact
pre-verified against the live tree: the contract-target collect-only baseline (`26/424, 398 deselected`,
re-ran live) + per-file breakdown; the full T7 clause→covering-test map with exact `tests/*.py`
file:line for feed_audio a/b/c + socket 4 bullets (research §1); the 2 GPU-gated integration tests read
in full (what they assert, line-by-line — research §2); the 15 `test_daemon.py` lite tests indexed
(research §3); the structural proof the arm response carries mode (`_arm_response`@1890 spreads
`status_snapshot`@1567); the gap-report section format to mirror; and the 6 non-defect nuances
documented so they are not mistaken for gaps. The file-ownership race with S1/S2 is handled explicitly
(CRITICAL #5: append if exists, create-with-H1 if absent). Residual risk (−0.5): (i) a future code/test
shift between this PRP's research and implementation could move a line number or rename a test — the
implementer re-runs the greps + the collect/run, so the section always reflects the live tree; (ii) the
RUN count depends on the box's CUDA state (24 passed/2 skipped vs 26 passed) — the section records
whichever it observes, with the collect-only baseline as the stable anchor. (iii) If S2 has NOT yet
appended when S3 runs, S3 appends directly below S1's H1 (the content is preserved either way; ordering
is reconciled by P1.M5.T5).