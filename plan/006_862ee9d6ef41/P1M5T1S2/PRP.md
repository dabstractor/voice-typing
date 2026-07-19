# PRP — P1.M5.T1.S2: daemon + recorder_host unit tests (mocked CUDA) — green-gate + results doc

## Goal

**Feature Goal**: Execute the **2 mocked-CUDA unit-test files** (`tests/test_daemon.py` = **193 tests** +
`tests/test_recorder_host.py` = **26 tests** = **219 tests combined**) that pin the daemon lifecycle and
the recorder-host IPC logic **without loading real CUDA models**, confirm they are **GREEN**, diagnose +
fix any failure (source OR test, classified by root cause) and re-run until green, then emit a results
document. This is the **mocked-CUDA half of P1.M5.T1** (the acceptance gate); the pure-Python half
(`test_config/textproc/typing_backends/feedback/voicectl/control_socket/status_sh/systemd` = 196 tests)
is the PREVIOUS leaf **P1.M5.T1.S1** (running in parallel) and is explicitly OUT of scope here.

**Verified baseline (LIVE this PRP's research): the suite is already GREEN** —
`219 passed in 4.80s`, exit 0, run with the exact contract command. Per-file `--collect-only` counts:
`test_daemon.py` = 193 (0.02s), `test_recorder_host.py` = 26 (0.01s), combined = 219 (0.02s). The
sub-second collection + 4.8 s wall time confirm every file is genuinely CUDA-free — both
`voice_typing/daemon.py` (lazy `from RealtimeSTT import AudioToTextRecorder` at line 341) and
`voice_typing/recorder_host.py` (lazy by design, line 54) keep CUDA OUT of module scope, and the tests
inject fakes for every external surface so those lazy paths are never triggered. Per the work-item
contract: these tests are the **primary coverage for acceptance criteria #2, #4, #5, #6, #9, #10**.

> **Count note:** the work-item contract said "191" tests for `test_daemon.py` and "~217" combined; the
> LIVE counts are **193 / 26 / 219** (the S1 PRP already recorded 193 for `test_daemon.py`). The
> discrepancy is immaterial — record the LIVE count at execution, never copy this PRP's number verbatim.

**Deliverable** (1 artifact — CREATE; **NO source/test edit unless a test actually fails**):
- `plan/006_862ee9d6ef41/P1M5T1S2/test_results_daemon.md` — a results doc recording the exact command
  run, per-file + total pass counts + timing, the GREEN verdict, and (if any fix was applied) a per-fix
  table. This mirrors the S1 sibling's `test_results_unit.md` format (the house precedent) under the
  contract's specified filename. No existing `test_results_daemon.md` — this PRP defines it.

**Success Definition**:
- (a) The 2-file suite passes: `219 passed` (±0), exit 0, re-verified LIVE at execution time.
- (b) If any test failed on first run, the failure was diagnosed (root-cause class A–E identified), the
  correct locus fixed (source / test / fixture), and the suite re-run green — with NO fix that weakens a
  guard, contorts source to match an over-eager test assertion, or papers over a thread race with a bare
  `sleep`.
- (c) `test_results_daemon.md` exists at the work-item path, is self-contained, and records: the exact
  command (with both AGENTS.md timeouts), per-file counts, total + timing, verdict, and any fixes.
- (d) Scope respected: the 9 pure-Python files (S1) and `test_feed_audio.py` (P1.M5.T2, real CUDA) were
  NOT added to this run.
- (e) No regression: the run touched ONLY the 2 in-scope files; no other test file was edited unless a
  shared source module (`daemon.py` / `recorder_host.py`) was the genuine root cause of a failure.

## User Persona

**Target User**: Internal — the plan orchestrator + downstream leaves:
1. **P1.M5.T5.S1** (acceptance-criteria cross-check) consumes this item's GREEN verdict as the primary
   evidence for **Acceptance #2** (drain, ≥3 s pause loses zero words), **#4** (only finalized text typed;
   nothing when toggled off), **#5** (idle silence / no hallucination), **#6** (voicectl cmds + systemd +
   boots un-armed AND un-loaded ~0 VRAM + auto-restart), **#9** (idle-unload ~0 VRAM, bounded teardown,
   no 90 s hang), and **#10** (lite mode). These are the acceptance criteria the contract explicitly
   names this item as covering.
2. **P1.M5.T2.\*** (T1 offline pipeline / `test_feed_audio.py` with REAL CUDA models) runs after; it
   relies on the daemon + recorder_host LOGIC this item confirmed green, so a real-model failure there is
   cleanly attributable to the CUDA/RealtimeSTT integration rather than to lifecycle logic this item
   would have caught.
3. **Operators/reviewers** read `test_results_daemon.md` as the signed-off evidence that the daemon core
   + the recorder-host subprocess IPC are sound before the real-model + E2E gates.

**Use Case**: The compliance round (006) finished auditing every module (the `gap_*.md` reports). The
parallel S1 leaf converts the 9 pure-Python audits into "196 tests pass." THIS item converts the daemon +
recorder-host audits into "219 tests pass": the lazy-load lifecycle (§4.2bis), the graceful drain
(§4.2#2), the idle-unload + bounded teardown (§4.2bis), lite mode + mode-switch (§4.2ter), dead-child
recovery, the control-socket `status`, and the recorder-host IPC dispatch — all WITHOUT loading CUDA.

**Pain Points Addressed**: (1) The audits are static-read verdicts — this is the dynamic proof for the
two heaviest modules. (2) A silent drift between audit and execution (e.g. a daemon refactor changed the
`host_factory=` injection contract) would otherwise surface as a confusing failure in the minutes-long
real-model suite; this gate catches it in ~5 s. (3) Gives P1.M5.T2.\* a clean "daemon/recorder_host logic
is green" baseline so real-model failures isolate cleanly.

## Why

- **This is the fast, deterministic gate for the two heaviest modules, BEFORE the expensive real-model
  suites.** 219 mocked-CUDA tests in ~5 s vs. `test_feed_audio.py` / E2E / GPU-lifecycle that take
  minutes and need the GPU + a model load. Catching a lifecycle/IPC regression here costs seconds;
  catching it in `test_feed_audio.py` costs minutes + a model load.
- **It is the primary evidence for 6 of the 10 acceptance criteria** (#2, #4, #5, #6, #9, #10). The
  drain logic (AC#2), the listening gate (AC#4), the idle guards (AC#5), the un-loaded boot + lifecycle
  (AC#6), the idle-unload + bounded teardown (AC#9), and lite mode (AC#10) are ALL unit-tested here
  without CUDA, because the tests inject fakes for the recorder / host / backend / mic-prober and
  monkeypatch `cuda_check.resolve_device_and_models`.
- **It builds on the parallel S1 leaf's "dependencies green" baseline.** `daemon.py` + `recorder_host.py`
  depend on the pure-Python modules S1 covers (`config`/`textproc`/`typing_backends`/`feedback`/`ctl`/
  `socket`). With those confirmed green, a daemon/recorder_host test failure in THIS item is cleanly
  attributable to daemon/recorder_host logic — not to a downstream pure-Python dependency.
- **The suite is already green (verified).** So this item is low-risk: run, confirm, document. The value
  is the evidence artifact + the diagnosis playbook for the rare drift/flake case — not heroic debugging.

## What

Run the 2-file pytest command with AGENTS.md two-timeout discipline; confirm 219 passed; if any failure,
classify (§ failure taxonomy below) → fix the correct locus → re-run until green; write
`test_results_daemon.md`.

### Success Criteria

- [ ] `219 passed` (±0), exit 0, re-verified LIVE at execution (run BOTH timeouts: inner `timeout 300` +
      outer bash-tool `timeout` above 300, e.g. 320).
- [ ] Per-file counts recorded in `test_results_daemon.md` (`test_daemon.py` 193, `test_recorder_host.py`
      26 — re-measured LIVE at execution, not copied from this PRP).
- [ ] Any failure on first run was root-caused + fixed at the correct locus (source / test / fixture) —
      NOT silenced by weakening a guard, contorting source, or adding a bare `sleep`.
- [ ] The 9 pure-Python files (S1) / `test_feed_audio.py` (P1.M5.T2) NOT in this run (scope boundary).
- [ ] `test_results_daemon.md` written to the work-item path, self-contained (command + counts + timing +
      verdict + fixes-if-any).

## All Needed Context

### Context Completeness Check

_Pass._ The implementing agent gets: the exact run command (two-timeout form), the verified baseline
(219 passed / 4.80s / exit 0, LIVE this round), the per-file + per-area coverage map (test group → PRD
ref → acceptance criterion), the 5-class failure taxonomy with the fix-decision rule, the mocking /
injection contract (so a fixture-drift failure is diagnosable), the scope boundaries, and a verbatim
`test_results_daemon.md` scaffold. No inference required.

### Documentation & References

```yaml
# MUST READ — the verified baseline + the diagnosis playbook (THIS is the spec).
- file: plan/006_862ee9d6ef41/P1M5T1S2/research/daemon_recorder_host_run_verification.md
  why: "§1 the LIVE-verified green baseline (219 passed / 4.80s / exit 0) + exact --collect-only counts
        (daemon 193, recorder_host 26, combined 219). §2 WHY the tests stay fast (both modules keep CUDA
        out of module scope via lazy imports; tests inject fakes). §3 the mocking / injection contract
        the tests depend on (VoiceTypingDaemon(recorder=,recorder_host=,host_factory=,backend=,mic_prober=);
        _FakeHost mirrors RecorderHost's surface; _feed_event feeds canned IPC events). §4-5 the per-area
        coverage map (test group → PRD ref → acceptance criterion). §6 acceptance mapping (#2/#4/#5/#6/#9/#10).
        §7 the 5-class failure taxonomy (collection/import, logic-assertion, fixture/contract-drift,
        env/fixture, flaky/timing) with the fix-decision rule + _wait_for (never bare sleep). §8 AGENTS.md
        two-timeout + full-venv-path rules. §9 the output-doc format precedent."
  critical: "The suite is GREEN now; the diagnosis workflow only fires if a drift/flake appears at
             execution. There are NO drift-guard tests here (unlike S1) — Class C is fixture/contract
             drift (the daemon's injection API or _FakeHost's mirror of RecorderHost). These tests USE
             THREADS (idle watchdog, read_loop, concurrent shutdown) so Class E (timing) is more live
             here than in S1's pure-Python set — fix flake with _wait_for, never sleep."

# MUST READ — AGENTS.md (the repo's hard rules; this is a test-run item, the timeout rules bind directly).
- file: AGENTS.md
  why: "Rule 1 (two timeouts on every non-trivial command), the hang-vectors table (pytest = `timeout 600
        uv run pytest <file>`; this set is mocked-CUDA so the contract's 300 is ample but the discipline
        is identical), Rule 2 (never foreground the daemon — these tests don't need it; they're hermetic),
        Rule 3 (bound scratch files — /tmp is a RAM-backed tmpfs)."
  critical: "zsh aliases python/pytest — ALWAYS `.venv/bin/python -m pytest`. Inner `timeout 300` + outer
             bash-tool `timeout` > 300 (e.g. 320). Exit 124 = wedged (a thread/lock regression) → diagnose
             per-file under `timeout 60 -vv`, don't retry-blind. mypy is NOT installed; ruff is optional."

# MUST READ (cross-ref, cite-don't-re-audit) — the daemon/recorder_host audits that established each
# module is PRD-compliant. This item is the DYNAMIC proof of what they claimed statically. When a logic
# assertion fails, these reports state the PRD-intended behavior (the oracle for the fix-decision rule).
- file: plan/006_862ee9d6ef41/architecture/gap_daemon_loop.md      # daemon main loop + graceful drain (§4.2#1-2) — drain/on_final/run-loop tests
- file: plan/006_862ee9d6ef41/architecture/gap_lifecycle.md        # lazy load + recorder-host IPC + bounded teardown (§4.2bis) — lazy-load/idle-unload/single-flight/dead-child/killpg tests
- file: plan/006_862ee9d6ef41/architecture/gap_lite.md             # lite mode + mode-switch (§4.2ter) — toggle_lite/mode_switch tests
- file: plan/006_862ee9d6ef41/architecture/gap_recorder_kwargs.md  # cfg_to_kwargs + build_recorder (§4.4) — the kwargs/wiring tests
- file: plan/006_862ee9d6ef41/architecture/gap_socket.md           # control socket protocol (§4.2#3) — status_snapshot tests exercise status fields
- file: plan/006_862ee9d6ef41/architecture/gap_feedback.md         # feedback state/notify/throttle (§4.6) — _FakeFeedback mirrors this contract
  why: "Each maps a module/area to its PRD contract + the tests that pin it. If a daemon/recorder_host
        test fails, the matching gap_*.md tells you the PRD-intended behavior (source of truth for the
        fix-decision rule). gap_lifecycle.md is the largest (76KB) — it owns the recorder-host IPC +
        lazy-load + teardown surface that most of these tests exercise."

# MUST READ — the parallel S1 leaf's PRP (the CONTRACT this item consumes).
- file: plan/006_862ee9d6ef41/P1M5T1S1/PRP.md
  why: "S1 runs the 9 pure-Python files (196 tests) and emits test_results_unit.md. It confirms the
        pure-Python DEPENDENCIES (config/textproc/typing_backends/feedback/ctl/socket) of daemon.py +
        recorder_host.py are GREEN. This item ASSUMES that baseline: a daemon/recorder_host test failure
        here is attributable to daemon/recorder_host logic, not a downstream pure-Python dependency.
        S1 also defines the house format for the results doc (test_results_unit.md) — this item mirrors
        it under the contract's name test_results_daemon.md."
  critical: "S1 is running IN PARALLEL. Do NOT edit the 9 pure-Python files or S1's output. If a daemon
             test fails because a pure-Python DEPENDENCY regressed (e.g. config.py), that is S1's locus
             — coordinate rather than editing S1's files. The expected case: both leaves go green
             independently because the dependency set is already green."

# MUST READ — the merged PRD (the spec these logic tests encode; the oracle for fix-decisions).
- docfile: plan/006_862ee9d6ef41/prd_snapshot.md
  why: "§4.2#1-2 (daemon main loop + graceful drain — AC#2/#4/#5), §4.2bis (lazy load + recorder-host
        subprocess + bounded teardown + idle-unload — AC#6/#9), §4.2ter (lite mode + mode-switch — AC#10),
        §4.4 (recorder kwargs + CPU fallback — feeds AC#6), §4.5 (auto_stop_idle_seconds / idle guards),
        §4.6/§4.8 (feedback state + voicectl status fields — AC#6), §4.9 (systemd + signal handlers —
        AC#6 auto-restart), §7 acceptance #2/#4/#5/#6/#9/#10. When a logic assertion fails, the PRD value
        is the source of truth."

# MUST READ — the modules under test (read the parts the failing test exercises; don't re-read whole files).
- file: voice_typing/daemon.py        # 128KB — VoiceTypingDaemon, cfg_to_kwargs, build_recorder, _bounded_shutdown, _load_host, status_snapshot
  why: "The daemon core. Lazy-imports RealtimeSTT at line 341 (so `import voice_typing.daemon` is cheap /
        CUDA-free — that's WHY the suite runs in seconds). Internal injection API the tests pin:
        VoiceTypingDaemon(cfg, feedback, recorder=, recorder_host=, host_factory=, backend=, mic_prober=)."
- file: voice_typing/recorder_host.py # 42KB — RecorderHost: spawn/IPC queues/dispatch/read_loop/text/stop
  why: "The recorder-host child owner. Lazy by design (line 54: no RealtimeSTT/torch/ctranslate2 at module
        scope). IPC protocol: cmd_queue (arm/disarm/text/shutdown), abort_event (interrupts blocked text),
        event_queue (ready/error/final/partial/speech/vad/speech_end/gone). A dispatch test failing = the
        event→callback mapping here drifted from the test's _feed_event expectations."

# External — pytest invocation / exit semantics (the run mechanics).
- url: https://docs.pytest.org/en/stable/reference/exit-codes.html
  why: "pytest exit codes: 0 = no failures; 1 = tests failed; 2 = interrupted (Ctrl-C) OR a usage/collection
        error; 5 = no tests collected. `timeout`'s 124 = the process was killed by the inner timeout
        (wedged) — distinct from pytest's own exit codes."
  critical: "exit 124 (timeout) is NOT a pytest failure — it means the suite wedged (a thread/lock
             regression). Do NOT retry-blind; run the single suspected file under `timeout 60 -vv` to
             localize. These tests use threads (idle watchdog, read_loop, concurrent shutdown) so a hang
             is most likely a join/lock regression."
```

### Current Codebase tree (relevant slice — state at P1.M5.T1.S2)

```bash
tests/
├── test_daemon.py                 (193) ┐ IN SCOPE (this item): 219 mocked-CUDA tests, GREEN (4.80s)
├── test_recorder_host.py          ( 26) ┘   — daemon lifecycle + recorder-host IPC, NO real CUDA/models
├── test_config.py                 (34) ┐
├── test_config_repo_default.py    ( 3) │
├── test_textproc.py               (21) │
├── test_typing_backends.py        (27) ├── OUT — P1.M5.T1.S1 (parallel): 196 pure-Python tests (the deps-green baseline)
├── test_feedback.py               (38) │
├── test_voicectl.py               (32) │
├── test_control_socket.py         (21) │
├── test_status_sh.py              ( 5) │
├── test_systemd_unit.py           (15) ┘
└── test_feed_audio.py             ( 9)   OUT — P1.M5.T2 (PRD T1: real recorder + CUDA models, minutes)
# Modules under test (committed, present):
voice_typing/{daemon,recorder_host,config,textproc,typing_backends,feedback,ctl,cuda_check,prefetch}.py
plan/006_862ee9d6ef41/P1M5T1S2/test_results_daemon.md    # ← OUTPUT (NEW; this item creates it)
```

### Desired Codebase tree with files to be added/modified

```bash
plan/006_862ee9d6ef41/P1M5T1S2/test_results_daemon.md   # NEW — the results doc (the SOLE deliverable)
# (source/test files edited ONLY if a failure is genuinely root-caused to them — expected: none, suite is green)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (AGENTS.md) — TWO timeouts, no exceptions. Inner GNU `timeout 300` (the contract value) +
#   the bash tool's own `timeout` param set ABOVE 300 (e.g. 320). Exit 124 (timeout's kill) ≠ pytest's
#   exit codes; 124 means the suite WEDGED (a thread/lock regression — these tests use threads) → localize
#   with a single file under `timeout 60 -vv`, do NOT retry-blind. (research §7-8; AGENTS.md Rule 1.)

# CRITICAL #2 (AGENTS.md) — zsh aliases `python`/`pytest`. ALWAYS `.venv/bin/python -m pytest` (full
#   venv path). Bare `python`/`pytest` may resolve to a zsh shim/wrapper. mypy is NOT installed — do NOT
#   run it; ruff is optional (/home/dustin/.local/bin/ruff). py_compile + pytest are the gates.

# CRITICAL #3 — these tests are HERMETIC + MOCKED. They NEVER load CUDA, NEVER spawn a real child,
#   NEVER touch real PyAudio / XDG_RUNTIME_DIR / a real daemon. The fakes: _FakeFeedback /
#   _DaemonFakeFeedback, _FakeRecorder / _StrictFakeRecorder / _StubRecorder, _FakeBackend, _ok_probe,
#   _cuda_resolve (monkeypatches daemon.cuda_check.resolve_device_and_models), _FakeHost +
#   _fake_host_factory (lazy-load tests), _make_host + _feed_event (recorder_host dispatch). Do NOT start
#   the daemon / arm the mic to "help" them (AGENTS.md forbids foregrounding it anyway).

# CRITICAL #4 — WHY they stay fast (4.8 s, not minutes). BOTH modules keep CUDA out of module scope by
#   design: daemon.py:341 `from RealtimeSTT import AudioToTextRecorder  # lazy` (inside build_recorder);
#   recorder_host.py:54 `IMPORT PURITY: this module does NOT import RealtimeSTT/torch/ctranslate2 at
#   module scope`. The tests inject fakes so those lazy paths never fire. If the run suddenly takes
#   MINUTES, a test accidentally triggered the lazy import (constructed a real recorder) → that is a
#   FIXTURE bug, NOT a CUDA-setup issue. (research §2.)

# CRITICAL #5 — there are NO drift-guard tests here (unlike S1). The failure classes are:
#   A collection/import (source syntax/import bug OR a monkeypatch target like
#     daemon.cuda_check.resolve_device_and_models moved/renamed) → fix SOURCE or update the test's
#     monkeypatch attribute path.
#   B logic assertion → PRD is the oracle; the gap_*.md state the intent → fix SOURCE. If the assertion
#     over-specified an impl detail NOT pinned by the PRD → fix TEST.
#   C fixture/contract drift → the daemon's internal injection API (VoiceTypingDaemon(recorder=,
#     recorder_host=, host_factory=, backend=, mic_prober=)) OR _FakeHost's mirror of RecorderHost's
#     surface (spawn/is_alive/pid/set_microphone/abort/text/stop/device/mode) OR the recorder_host
#     event-kind set drifted from the real class → fix the TEST fixture, UNLESS the source change is a
#     genuine regression (then Class B → fix SOURCE).
#   D env/fixture (monkeypatch / capsys-vs-capfd / tmp_path) → fix TEST.
#   E flaky/timing (idle watchdog / read_loop / concurrent shutdown / drain-watchdog races) → these tests
#     use threads; a flake = a missing or too-tight _wait_for. Fix with the house _wait_for(predicate,
#     timeout) poll helper (test_daemon.py:515); NEVER add a bare sleep. (research §7.)

# CRITICAL #6 — the recorder_host IPC protocol. cmd_queue (arm/disarm/text/shutdown) + abort_event
#   (interrupts a child blocked in recorder.text()) + event_queue with kinds: ready/error/final/partial/
#   speech/vad/speech_end/gone. The dispatch tests feed CANNED events via _feed_event(host, kind, payload)
#   (puts on host._evt_q) and assert the event→callback mapping. A dispatch test failing = the mapping in
#   recorder_host._dispatch drifted from the test's expectations → check gap_lifecycle.md for the intended
#   mapping, then fix whichever side is wrong (research §3).

# CRITICAL #7 — scope boundary. Do NOT add the 9 pure-Python files (S1, parallel) or test_feed_audio.py
#   (P1.M5.T2, real CUDA models, minutes). Mixing them in changes the timeout budget (the real-model
#   suite takes minutes) + blurs S1/S2/T2 attribution. (research §8.)

# CRITICAL #8 — re-run a SINGLE failing file first. `timeout 60 .venv/bin/python -m pytest <file> -vv`
#   gives the full assertion diff fast; then re-run the full 2-file set to confirm no regression. Don't
#   iterate against the whole set. (test_daemon.py is 193 tests — a single-file -vv run is still <5 s.)

# CRITICAL #9 — the suite is GREEN now (verified this round: 219 passed / 4.80s / exit 0). The likely
#   outcome is "219 passed, no fixes applied." Do NOT invent fixes or refactor green code. Only touch
#   source/test if a run at execution time shows a real failure. (research §1.)

# CRITICAL #10 — _wait_for(predicate, timeout=2.0, interval=0.01) is the HOUSE poll helper, already
#   defined at test_daemon.py:515. It is the ONLY correct way to assert on async/threaded state (idle
#   watchdog disarm, read_loop drain, concurrent-stop teardown, drain-watchdog abort). A test that adds a
#   bare time.sleep() is a bug — replace it with _wait_for. (research §3, §7 Class E.)
```

## Implementation Blueprint

### Data models and structure

N/A — no code models. The deliverable is one Markdown results doc. The only "data" is the test outcome
(pass counts + timing + optional fix table).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: RUN the 2-file suite (AGENTS.md two-timeout discipline) — the gate.
  - RUN (from /home/dustin/projects/voice-typing):
      timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q
    (set the bash tool `timeout` to 320 — the outer backstop above the inner 300.)
  - EXPECT: `219 passed in ~5s`, exit 0. (Verified baseline this round: 219 passed / 4.80s / exit 0.)
  - IF exit 0 + 219 passed → go to Task 4 (write the results doc; "fixes: none").
  - IF exit 124 (timeout/wedged) → do NOT retry-blind; localize: run each file under
    `timeout 60 .venv/bin/python -m pytest <file> -q` to find the one that hangs (these tests use
    threads — a hang is a join/lock regression in idle watchdog / read_loop / concurrent shutdown);
    that file's fixture/thread is the regression → go to Task 2.
  - IF exit 1 (failures) or exit 2 (collection error) → go to Task 2 with the failing file(s).
  - DO NOT add the 9 pure-Python files (S1) or test_feed_audio.py (scope boundary, CRITICAL #7).

Task 2: (ONLY IF a failure) DIAGNOSE — classify the failure, decide the fix locus.
  - RE-PRODUCE the failure verbosely on the single file: `timeout 60 .venv/bin/python -m pytest <file> -vv`
  - CLASSIFY (research §7 taxonomy):
      Class A — collection/import ERROR  → SOURCE module has a syntax/import bug, OR a monkeypatch target
                                            (e.g. daemon.cuda_check.resolve_device_and_models) moved/renamed.
                                            Fix SOURCE, or update the test's monkeypatch attribute path.
      Class B — logic ASSERTION failure   → read the diff; the gap_*.md state the PRD intent. PRD-value
                                            assertion ⇒ fix SOURCE; over-specified impl-detail ⇒ fix TEST.
      Class C — FIXTURE/CONTRACT drift    → the daemon's injection API (host_factory=/mic_prober=/...) OR
                                            _FakeHost's mirror of RecorderHost's surface OR the recorder_host
                                            event-kind set drifted ⇒ fix the TEST fixture, UNLESS the source
                                            change is a genuine regression (then Class B ⇒ fix SOURCE).
      Class D — ENV/fixture (monkeypatch / capsys-vs-capfd / tmp_path / threading mismatch) ⇒ fix the TEST.
      Class E — FLAKY/timing (idle watchdog / read_loop / concurrent shutdown / drain watchdog) ⇒ add/loosen
                                            a _wait_for(predicate, timeout) poll (house pattern,
                                            test_daemon.py:515); NO bare sleep.
  - RECORD the class + the decided locus (for the results doc's fix table).
  - DO NOT: weaken a guard to make it pass; contort source to match an over-specified test; add a bare
    sleep; or fix a file outside daemon.py / recorder_host.py unless a shared source module is the genuine
    root (and if the root is a pure-Python dependency like config.py, that's the parallel S1 leaf's locus —
    coordinate, don't edit S1's files).

Task 3: (ONLY IF a failure) FIX + RE-RUN until green.
  - APPLY the fix at the locus chosen in Task 2.
  - RE-RUN the single file: `timeout 60 .venv/bin/python -m pytest <file> -vv` → must be green.
  - RE-RUN the FULL 2-file set (Task 1 command) → must be `219 passed`, exit 0 (confirm no regression).
  - IF a fix changes daemon.py / recorder_host.py (shared source), the full-set re-run is the regression
    check — it must stay 219 passed. (Also re-check it didn't break the parallel S1 set conceptually, but
    do NOT run S1's files — that's S1's gate.)
  - RECORD the fix in the results doc (file | change | class | test unblocked).

Task 4: WRITE plan/006_862ee9d6ef41/P1M5T1S2/test_results_daemon.md (the SOLE deliverable).
  - CREATE the file (NEW; no existing test_results_daemon.md). Use the verbatim scaffold in "Task 4 SOURCE".
  - CONTENT: exact command run (both timeouts), per-file counts, total + timing, verdict (GREEN), and the
    fixes table (empty / "none applied" if the suite was green on first run).
  - PLACEMENT: plan/006_862ee9d6ef41/P1M5T1S2/test_results_daemon.md (keeps the artifact with its work item).
  - DO NOT edit PRD.md / tasks.json / prd_snapshot.md / .gitignore. DO NOT touch source/tests if green.

Task 5: (NONE if green) — no source/test changes, no new tests. This is an execution + documentation item.
```

#### Task 4 SOURCE — `test_results_daemon.md` verbatim scaffold (pre-fill the LIVE counts; edit the timing/fixes at execution)

```markdown
# Test Results — P1.M5.T1.S2: daemon + recorder_host unit tests (mocked CUDA)

**Date:** <YYYY-MM-DD>
**Scope:** the 2 mocked-CUDA unit-test files (daemon lifecycle + recorder-host IPC). **Excludes** the 9
pure-Python files (P1.M5.T1.S1, parallel) and test_feed_audio.py (P1.M5.T2, real CUDA models).
**Verdict:** ✅ GREEN — 219 passed, 0 failed, 0 errors, 0 skipped.

## Command run (AGENTS.md two-timeout discipline)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q
# (bash-tool outer `timeout` set to 320 — the backstop above the inner 300.)
```

## Per-file results

| file | tests | result | module under test | PRD ref | acceptance |
|---|---|---|---|---|---|
| test_daemon.py | 193 | ✅ pass | voice_typing.daemon (lifecycle, lazy load, drain, idle-unload, lite, status) | §4.2/§4.2bis/§4.2ter/§4.4/§4.5/§4.6/§4.9 | #2,#4,#5,#6,#9,#10 |
| test_recorder_host.py | 26 | ✅ pass | voice_typing.recorder_host (IPC dispatch, queues, teardown, abort sentinel) | §4.2bis | #2,#6,#9 |
| **TOTAL** | **219** | **✅ all pass (~5s)** | | | |

## Acceptance-criteria evidence (this item is the primary unit-level coverage)

- **#2** (pause ≥3 s loses zero words, drain) — daemon drain tests + recorder_host abort-sentinel tests.
- **#4** (only finalized text typed; nothing when toggled off) — on_final gate tests.
- **#5** (idle silence, no hallucination) — idle-watchdog + hallucination-reject tests (unit guards;
  full 2-min silence = PRD T4 / P1.M5.T4).
- **#6** (voicectl cmds, systemd, boots un-armed + un-loaded ~0 VRAM, auto-restart) — lazy-boot +
  status + signal-handler + main-lifecycle + dead-child tests.
- **#9** (idle-unload ~0 VRAM, bounded teardown, no 90 s hang) — idle-unload + bounded-shutdown +
  single-flight + concurrent-stop tests.
- **#10** (lite mode) — toggle-lite + mode-switch + status-mode tests.

## Fixes applied

_None._ The suite was green on first run (219 passed in ~4.8s, exit 0). No source or test file was
modified. (If a failure had surfaced, record it here as: `file | change | root-cause class (A-E) |
test unblocked`.)

## Notes

- Wall time ~5s confirms both modules keep CUDA out of module scope (daemon.py lazy-imports RealtimeSTT
  at line 341; recorder_host.py is lazy by design at line 54) and the tests inject fakes — no model load.
- No drift-guard tests here (unlike S1); a failure would be a logic/fixture/threading regression, not a
  committed-file drift.
- Out of scope (other leaves): 9 pure-Python files → P1.M5.T1.S1 (parallel); test_feed_audio.py → P1.M5.T2.
```

### Implementation Patterns & Key Details

```python
# The fix-decision rule (when a logic assertion fails — Class B):
#   1. Does the assertion encode a PRD value (§4.2#1-2/§4.2bis/§4.2ter/§4.4/§4.5/§4.6/§4.8/§4.9)?
#        YES → the SOURCE (daemon.py / recorder_host.py) drifted from the PRD → fix SOURCE.
#              (the matching gap_*.md — gap_daemon_loop / gap_lifecycle / gap_lite / gap_recorder_kwargs
#               — states the intended behavior; that's the oracle.)
#        NO  → the test over-specified an implementation detail → fix the TEST.
#   2. For a FIXTURE/CONTRACT-DRIFT failure (Class C): is the daemon's injection API or _FakeHost's mirror
#      of RecorderHost out of sync with the real class because (a) the source genuinely changed behavior
#      (regression → Class B → fix SOURCE), or (b) the source legitimately evolved its internal API and
#      the test fixture just needs to follow (→ fix the TEST fixture)? gap_lifecycle.md is the oracle.
#   3. Never: silence a guard, contort source to an over-eager assertion, or add a bare sleep.

# The timeout-exit decision tree:
#   exit 0  + 219 passed → GREEN, write doc (fixes: none).
#   exit 1  (FAILURES)   → Task 2 (diagnose single file -vv) → Task 3 (fix + re-run full set).
#   exit 2  (COLLECTION) → a module won't import / a monkeypatch target is gone → Class A → fix SOURCE
#                           or the test's monkeypatch attribute path, re-run.
#   exit 124 (TIMEOUT)   → wedged → these tests use threads; localize per-file under `timeout 60 -vv` →
#                           Class E thread/join/lock regression → fix with _wait_for, not sleep; do NOT
#                           retry-blind.

# The _wait_for pattern (house helper, test_daemon.py:515) — for any async/threaded assertion:
#   _wait_for(lambda: d.is_listening(), timeout=2.0)      # idle watchdog disarm
#   _wait_for(lambda: host._evt_q.empty(), timeout=2.0)   # read_loop drained
#   _wait_for(lambda: rec.shutdowns == 1, timeout=2.0)    # concurrent-stop single teardown
# A bare time.sleep(N) in a threaded test is ALWAYS wrong — it's flaky AND slow. Use _wait_for.
```

### Integration Points

```yaml
CONSUMES (read-only):
  - tests/{test_daemon,test_recorder_host}.py                       # the 2 files (run)
  - voice_typing/{daemon,recorder_host,config,textproc,typing_backends,feedback,ctl,cuda_check}.py  # modules under test
  - plan/006_862ee9d6ef41/architecture/gap_{daemon_loop,lifecycle,lite,recorder_kwargs,socket,feedback}.md  # PRD-intent oracle
  - plan/006_862ee9d6ef41/prd_snapshot.md                           # §4.2/§4.2bis/§4.2ter/§4.4/§4.5/§4.6/§4.8/§4.9 + §7 AC#2/4/5/6/9/10
  - plan/006_862ee9d6ef41/P1M5T1S1/PRP.md                           # the parallel S1 leaf (deps-green baseline + results-doc format precedent)

PRODUCES (the SOLE output):
  - plan/006_862ee9d6ef41/P1M5T1S2/test_results_daemon.md           # NEW results doc (GREEN verdict + counts + fixes-if-any)

FEEDS (downstream consumers):
  - P1.M5.T5.S1 (acceptance cross-check)                            # consumes the GREEN verdict as primary evidence for AC#2/#4/#5/#6/#9/#10
  - P1.M5.T2.*  (T1 real-model feed_audio)                          # relies on "daemon/recorder_host logic green" to isolate real-model failures

PARALLEL-SAFE:
  - P1.M5.T1.S1 (pure-Python tests, in flight) = ZERO file overlap. It writes P1M5T1S1/test_results_unit.md
    + runs the 9 pure-Python files; this item runs test_daemon.py + test_recorder_host.py + writes
    test_results_daemon.md. No shared test file. The only shared surface is the SOURCE modules both depend
    on (config/textproc/typing_backends/feedback/ctl) — if a daemon test fails because one of THOSE
    regressed, that's S1's locus; coordinate rather than editing S1's files. Expected: both go green
    independently (the dependency set is already green).
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# The deliverable is a Markdown doc — validate structure, not code.
test -f plan/006_862ee9d6ef41/P1M5T1S2/test_results_daemon.md && echo "EXISTS"
grep -q 'P1.M5.T1.S2' plan/006_862ee9d6ef41/P1M5T1S2/test_results_daemon.md && echo "titled"
grep -qi 'GREEN'      plan/006_862ee9d6ef41/P1M5T1S2/test_results_daemon.md && echo "verdict present"
grep -q '219'         plan/006_862ee9d6ef41/P1M5T1S2/test_results_daemon.md && echo "total recorded"
# Expected: EXISTS; title + GREEN verdict + total 219 present. (No code to lint/type-check; mypy absent.)
```

### Level 2: Unit Tests (Component Validation) — THE gate

```bash
# Re-run the 2-file suite LIVE (two timeouts per AGENTS.md Rule 1):
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q
# (set the bash tool `timeout` to 320 — the outer backstop above the inner 300.)
# Expected: `219 passed in ~5s`, exit 0. Record the ACTUAL count + timing in test_results_daemon.md
# (do not copy this PRP's 4.80s verbatim — re-measure at execution).
```

### Level 3: Integration Testing (System Validation)

```bash
# Per-file isolation (sanity that no file is individually broken / slow):
timeout 120 .venv/bin/python -m pytest tests/test_daemon.py -q        2>&1 | tail -1   # expect "193 passed"
timeout  60 .venv/bin/python -m pytest tests/test_recorder_host.py -q 2>&1 | tail -1   # expect "26 passed"
# Expected: each exit 0, each <5s (test_daemon ~4.5s, recorder_host ~0.3s).
# (NO daemon / NO CUDA / NO mic / NO real child — these are mocked + hermetic. Do NOT start the daemon.)
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Import-purity spot-check (BOTH modules MUST stay CUDA-free at import — that's WHY the suite is fast):
.venv/bin/python -c "
import sys
import voice_typing.daemon, voice_typing.recorder_host
bad=[m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules]
print('CUDA-at-import leak:', bad or 'none')
assert not bad, 'a module imported CUDA at module scope — would slow/break this set (check daemon.py:341 / recorder_host.py:54 lazy imports)'
"
# Timing sanity (a CUDA/model load would take minutes; a clean run is seconds):
timeout 320 .venv/bin/python -m pytest tests/test_daemon.py tests/test_recorder_host.py -q 2>&1 | tail -1
#   expect "219 passed in <10s". If it takes MINUTES, a test triggered the lazy RealtimeSTT import →
#   fixture bug, NOT a CUDA-setup issue (CRITICAL #4). Localize per-file under `timeout 60 -vv`.
# Expected: no CUDA module imported at module scope; 219 passed in <10s.
```

## Final Validation Checklist

### Technical Validation

- [ ] `219 passed` (±0), exit 0, re-verified LIVE at execution (inner `timeout 300` + outer bash backstop 320).
- [ ] Per-file counts recorded (test_daemon.py 193, test_recorder_host.py 26 = 219).
- [ ] `test_results_daemon.md` exists at the work-item path; title + GREEN + total present.
- [ ] No CUDA import leaked into either module's module scope (Level 4 spot-check); run completes <10s.

### Feature Validation

- [ ] All success criteria from "What" section met.
- [ ] Any failure was root-caused (class A–E) + fixed at the correct locus (not silenced/contorted/slept).
- [ ] Scope respected: the 9 pure-Python files (S1) / test_feed_audio.py (P1.M5.T2) NOT in the run.
- [ ] If a fix changed daemon.py / recorder_host.py, the full 2-file set re-run green (no regression).

### Code Quality Validation

- [ ] `test_results_daemon.md` is self-contained (command + counts + timing + verdict + fixes).
- [ ] Re-measured timing recorded (not copied from this PRP's 4.80s).
- [ ] No green code refactored/invented; source/test touched ONLY on a real, root-caused failure.

### Documentation & Deployment

- [ ] Results doc placed at `plan/006_862ee9d6ef41/P1M5T1S2/test_results_daemon.md`.
- [ ] Feeds P1.M5.T5.S1 (Acceptance #2/#4/#5/#6/#9/#10 evidence) + P1.M5.T2.* (logic-green baseline).

---

## Anti-Patterns to Avoid

- ❌ Don't run with a single timeout or no timeout — AGENTS.md Rule 1 mandates inner `timeout` + outer
  bash-tool `timeout`; exit 124 (wedged) must be diagnosable, not swallowed.
- ❌ Don't use bare `python`/`pytest` (zsh aliases) — always `.venv/bin/python -m pytest`.
- ❌ Don't add the 9 pure-Python files (S1) or test_feed_audio.py (P1.M5.T2) — mixing them in blows the
  timeout budget (the real-model suite takes minutes) + blurs attribution.
- ❌ Don't add a bare `sleep` to fix a flaky threaded test (idle watchdog / read_loop / concurrent
  shutdown / drain watchdog) — use the `_wait_for(predicate, timeout)` house helper (test_daemon.py:515).
- ❌ Don't start the daemon / arm the mic / touch real XDG_RUNTIME_DIR / spawn a real child — these tests
  are hermetic (fakes injected; monkeypatched cuda_check; _make_host never spawns). AGENTS.md forbids
  foregrounding the daemon anyway.
- ❌ Don't assume a minutes-long run is a "CUDA setup problem" — both modules keep CUDA out of module
  scope; a slow run means a test triggered the lazy import (a FIXTURE bug), not a missing CUDA install.
- ❌ Don't contort source to match an over-specified test assertion — the PRD value is the oracle (read
  the gap_*.md); fix the test if it over-specified an impl detail.
- ❌ Don't edit the parallel S1 leaf's files (its 9 test files / its source locus / its test_results_unit.md)
  — if a daemon test fails because a pure-Python DEPENDENCY regressed, that's S1's locus; coordinate.
- ❌ Don't edit PRD.md / tasks.json / prd_snapshot.md / .gitignore.
- ❌ Don't copy this PRP's 4.80s timing or 219/193/26 counts into the results doc verbatim — re-measure
  LIVE at execution.
- ❌ Don't refactor or "improve" green code — this is an execution + documentation item; touch source/test
  ONLY on a real, root-caused failure.

---

## Confidence Score

**9/10** — one-pass success likelihood. The suite is ALREADY green (verified LIVE this round: 219 passed /
4.80s / exit 0 with the exact contract command), per-file counts match (daemon 193, recorder_host 26,
combined 219), collection is sub-second (0.02s) confirming both modules keep CUDA out of module scope,
and the deliverable is a single self-contained Markdown doc with a verbatim scaffold. The diagnosis/fix
playbook (CRITICAL #5 + Task 2 taxonomy) covers the rare drift/flake case at execution — including the
threading-specific Class E (_wait_for, not sleep) which is more live here than in S1's pure-Python set.
Residual -1: a drift could appear between this research and the implementing agent's run (e.g. a daemon
refactor changed the `host_factory=` injection contract, or a recorder_host event-kind was renamed), or
the parallel S1 leaf could touch a shared dependency — but the playbook resolves any such failure in one
classify→fix→re-run cycle, and gap_lifecycle.md / gap_daemon_loop.md pinpoint the intended behavior.