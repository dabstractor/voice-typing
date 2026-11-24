# PRP — P1.M1.T1.S3: Pin default-to-fake duck wiring and ordered subprocess isolation

## Goal

**Feature Goal**: Lock BUG-001's fix with the regression pins the contract names: (1) **one dedicated default-config constructor-to-`_FakeDucker` actuation regression** in `tests/test_ducking.py` that patches ONLY the ducker-factory lookup and verifies engage/release actuation with zero busctl/wpctl attempts; (2) **media-transport tripwires** in `tests/test_typing_backends.py`'s recorder so a leaked media call fails loudly instead of being filtered out of assertions; (3) the **pinned ordering invocation** — `test_key_listener.py::test_zero_keyboard_warning_fires_once_at_first_arm` before `tests/test_typing_backends.py` in ONE bounded run — established as the canonical clean-ordering evidence (already verified green post-S1). Existing fake lifecycle, backend, and crash-heal coverage is retained with bounded completion before mocks unwind. All runs under the two-timeout rule. **Production code and shipped defaults untouched.**

**Deliverable**: Two files edited, additively: `tests/test_ducking.py` (+1 test: the default-to-fake wiring actuation regression, placed after `test_ducking_default_factory_builds_by_mode`) and `tests/test_typing_backends.py` (+fixture-level busctl/wpctl tripwire + explicit zero-media assertions in the two BUG-001 victim tests). Plus the pinned ordering invocation (a validation gate, not a new file) with its evidence cited for downstream tasks P1.M1.T3.S1 and P1.M2.T3.S2.

**Success Definition**:
- (a) The new ducking test: a DEFAULT `VoiceTypingConfig()` (duck_mode='mpris', unmutated) constructs through the REAL factory-lookup path (patched to return the fake — no `ducker=` injection), `d._ducker is fake`, `start()/stop()` → `fake.calls == ["engage", "release"]`, `ducked_states == [True, False]`, zero subprocess attempts, zero `vt-ducking`/`vt-duck-heal` threads after the cycle — all completing synchronously inside the test.
- (b) The typing-backends recorder: any `subprocess.run` call whose argv[0] is `busctl`/`wpctl` raises AssertionError at invocation; the two victims (`test_wtype_invokes_exact_argv`, `test_wtype_passes_check_true`) additionally assert zero media argvs in the ledger. Existing assertions byte-identical.
- (c) The pinned ordering invocation passes green (3/3 for determinism), under inner `timeout 300` + harness timeout.
- (d) All existing ducking lifecycle/backend/crash-heal/shutdown tests + the shipped-default pin (`test_config.py` → `mpris`) stay green and unmodified.
- (e) `voice_typing/`, `tests/conftest.py`, `tests/test_config.py`, and S2's migration files untouched.

## User Persona

**Target User**: The operator (whose live Brave/MPRIS endpoints must never be paused by a unit suite — PRD §4.2sexies R.7) and the downstream subtasks: **P1.M1.T3.S1** (needs clean-ordering evidence to classify `test_daemon.py` as a CPU suite in the G1 baseline) and **P1.M2.T3.S2** (needs evidence that unit suites no longer touch the live media bus for the README sync).

**Use Case**: A future change regresses the hermetic wiring (e.g. re-wires a default-config construction path, or reintroduces a leaked `vt-ducking` worker). The tripwire fails loudly at the leaked call; the victim tests fail on the polluted ledger; the pinned ordering invocation fails on the exact deterministic repro; the wiring test fails if the default-config→factory path stops actuating engage/release.

**Pain Points Addressed**: BUG-001's failure mode was ORDER-DEPENDENT and SILENT — the leaked worker's busctl kwargs corrupted later recorders intermittently, and the live side effect paused media with no resume. S3 converts every one of those failure modes into a synchronous, loud, deterministic assertion.

## Why

- **BUG-001 (Major) is fixed by S1+S2 but unpinned**: S1's fixture + S2's migration remove the vectors, but nothing pins (i) the production wiring itself (default cfg → factory → ducker → engage/release actuation), (ii) the recorder's intolerance of media calls, or (iii) the exact reported ordering repro. Without S3, a future refactor can silently reintroduce the leak and only the intermittent full-suite failures would tell.
- **The wiring gap is real**: `_make_ducking_daemon` (:320) injects via the `ducker=` ctor seam — it SKIPS `_build_default_ducker`, so no existing test proves the DEFAULT-config factory path actuates. `test_ducking_default_factory_builds_by_mode` (:454) builds real stacks but never dispatches (construction is pure — safe, but not an actuation proof). S3's test is the only one covering default-config constructor-to-actuation with a fake.
- **Tripwires > filtering**: the recorder's job is to prove the wtype call happened with the right kwargs. If a leaked call lands in the ledger, the RIGHT fix is isolation (S1/S2) — but the DETECTION should be a hard failure naming the media transport, never a filter that tolerates it.
- **The ordering pin is the cheapest end-to-end proof**: it reproduces the pollution window exactly (arming test's worker lifetime overlapping the recorder tests) in ~1 second, and is the evidence P1.M1.T3.S1 cites for a complete side-effect-free baseline.

## What

Additive-only edits to two test files, plus a validation-only ordering gate. No production code, no shipped-default changes, no conftest changes, no autouse, no global subprocess patch.

### Success Criteria

- [ ] `tests/test_ducking.py` gains ONE new test (after :491) that: builds DEFAULT `VoiceTypingConfig()`; monkeypatches `voice_typing.daemon._build_default_ducker` to return a `_FakeDucker`; monkeypatches `subprocess.run` with a recording tripwire; constructs WITHOUT `ducker=`; asserts `d._ducker is fake`, engage/release actuation, ducked state mirroring, zero tripwire attempts, zero duck threads — all synchronously in-test.
- [ ] All pre-existing tests in `test_ducking.py` (lifecycle :343-441, off-mode :442, factory-by-mode :454, backend :97-234, crash-heal :565-657, shutdown-flush :660-698) byte-identical and green.
- [ ] `tests/test_typing_backends.py`: the `recorder` fixture's fake `subprocess.run` raises on `argv[0] in {"busctl","wpctl"}`; the two victim tests assert zero media argvs; existing assertions unchanged.
- [ ] Pinned ordering invocation green 3/3: `timeout 300 .venv/bin/python -m pytest tests/test_key_listener.py::test_zero_keyboard_warning_fires_once_at_first_arm tests/test_typing_backends.py -q`.
- [ ] `timeout 300 .venv/bin/python -m pytest tests/test_ducking.py tests/test_config.py tests/test_typing_backends.py tests/test_key_listener.py -q` → all green (default pins + touched pure suites).
- [ ] `git diff --name-only` == exactly `{tests/test_ducking.py, tests/test_typing_backends.py}`.

## All Needed Context

### Context Completeness Check

_Pass._ The landed S1 fixture is read in full (88 lines); S2's PRP is read as the contract (disjoint edit set — its exclusions name test_ducking.py; typing_backends is S2 "GATE ONLY"); every existing double/test in test_ducking.py is enumerated with line numbers; the victim tests' exact assertions are quoted; the canonical ordering invocation is VERIFIED GREEN this session (39 passed in 1.04s); the mpris default pin location is verified (test_config.py:277-279); the baseline suite counts are verified (100 passed). The reference implementation below is copy-ready.

### Verified Current State (re-verified this session)

- **S1 landed** (commit 74252cd): `tests/conftest.py` = the opt-in `hermetic_daemon_media` fixture — `hermetic(cfg)` (duck off + private state), fail-closed `_build_default_ducker` patch, `read_ducked_flag` fake, `hermetic.read_calls`. Deliberately NO global subprocess patch ("a real media command must never 'prove' failure"). S2 (in flight, CONTRACT) adds `hermetic_cfg` + lazy imports and migrates 6 files — none of them test_ducking.py or test_typing_backends.py.
- **The reported-order test is S1-migrated**: `tests/test_key_listener.py:459-461` — `test_zero_keyboard_warning_fires_once_at_first_arm(monkeypatch, caplog, hermetic_daemon_media)`; `_wire_daemon(hermetic_daemon_media())`. Verified green with typing_backends after it: **39 passed**.
- **`_FakeDucker`** (tests/test_ducking.py:280-306): thread-safe `calls` ledger + `engages`/`releases` properties. **`_DuckingFakeFeedback`** (:309): `ducked_states` list. **`_make_ducking_daemon(cfg=None, *, duck=True)`** (:320): injects `ducker=fake` via the ctor seam. **`_ok_probe`/`_StubRecorder`/`_CtlFakeBackend`/`_DaemonFakeFeedback`**: the file's standard doubles (imported from test_daemon.py per the file's existing imports — check the file's import block at edit time).
- **Victim tests**: `test_wtype_invokes_exact_argv` (:89, `assert recorder.argvs == [("wtype","-d","12","--","hello world")]`) and `test_wtype_passes_check_true` (:94, `assert recorder.calls[0][1].get("check") is True`). **`class _Recorder`** (:44) + **`recorder` fixture** (:77) — file-local; monkeypatches `subprocess.run` for the whole test.
- **Shipped default pin**: `tests/test_config.py:277-279` — `assert a.duck_mode == "mpris" and a.duck_volume_pct == 15`. UNTOUCHED by S3; must stay green.
- **Baselines this session**: ordering pin 39 passed / 1.04s; `test_ducking.py + test_config.py` → 100 passed / 0.08s.

### Documentation & References

```yaml
# THE LANDED SEAM (S1 — input; commit 74252cd)
- file: tests/conftest.py
  why: The hermetic_daemon_media fixture S3 consumes for gates (S1's pin test_hermetic_media_
        fixture_blocks_unguarded_factory at test_key_listener.py:513). NOT edited by S3.
  critical: "Its design explicitly forbids a global subprocess patch / PATH shim — S3's tripwires
            are FILE-LOCAL recorders, never global. Do not 'improve' the fixture here."

# THE PARALLEL SIBLING (S2 — CONTRACT, in flight)
- file: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M1T1S2/PRP.md
  why: S2 migrates 6 constructor files via hermetic_cfg; its exclusions NAME test_ducking.py and
        leave test_typing_backends.py as gate-only → zero file collision with S3. Its L2 gates
        run ordering probes too; S3's pin is the canonical named pair.
  critical: "Assume S2 lands exactly as specified. S3's full-file ordering variant
            (test_key_listener.py + test_typing_backends.py) may be red on the OTHER arming
            tests until S2 lands — gate it AFTER S2, or report as 'pending S2'."

# THE FILE UNDER EDIT #1
- file: tests/test_ducking.py
  why: 698 lines. _FakeBackend :31; backend tests :97-234; _FakeDucker :280; _DuckingFakeFeedback
        :309; _make_ducking_daemon :320 (ducker= seam — SKIPS the factory); lifecycle :343-441;
        off-mode :442; factory-by-mode :454 (real builds, construction-pure, never dispatched);
        heal :565-657; _FlushRecordingDucker + shutdown :660-698.
  pattern: "Each lifecycle test completes its cycle in-test (d.start(); ...; d.stop() cleanup) —
            bounded before mocks unwind. Mirror that style in the new test."
  gotcha: "The new test must NOT use _make_ducking_daemon (ducker= skips the factory) and must NOT
           mutate cfg to duck_mode='off' — the DEFAULT 'mpris' path through the factory lookup is
           the thing under test. Construction of REAL AsyncDucker stacks without dispatch is safe
           (worker spawns lazily) — that's why :454 stays as-is."

# THE FILE UNDER EDIT #2
- file: tests/test_typing_backends.py
  why: _Recorder :44 + recorder fixture :77 (file-local, monkeypatches subprocess.run whole-test);
        victims :89 (exact argv) and :94 (check=True — the assertion the leaked busctl kwargs
        {'timeout':1.0,'check':False,...} corrupted).
  pattern: "Pure-Python; every subprocess call mocked. argv[0] is only ever wtype/ydotool/tmux
            tooling here — a busctl/wpctl argv is BY DEFINITION a leak."
  gotcha: "Keep the tripwire additive: existing assertions byte-identical; the fixture still
           records every call. A leaked worker SWALLOWS in-thread exceptions (failure
           discipline) — that's why the test-level zero-media assertion (not just the tripwire)
           is required."

# THE REPORTED REPRO (the ordering pin)
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/prd_snapshot.md
  why: BUG-001's Steps to Reproduce names the EXACT invocation (deterministic 3/3) and the
        victim failure signature (recorder.calls[0] kwargs = the leaked busctl call's).
  critical: "Use the invocation VERBATIM (single-test node + file). Pytest preserves CLI order —
            that ordering IS the reproduction of the pollution window."

# THE SHIPPED-DEFAULT PIN (must stay green, untouched)
- file: tests/test_config.py
  why: :277-279 pins duck_mode == 'mpris' + duck_volume_pct == 15 (P1.M2.T4's flip is INTENTIONAL
        production behavior). S3 changes NO defaults anywhere.

# THE SYSTEM CONTEXT (constructor inventory + S3's mandate)
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/system_context.md
  why: § BUG-001: 'Keep fake lifecycle/backend regressions and one dedicated default
        constructor-to-_FakeDucker wiring check. Keep tests/test_config.py's real default pin.
        A per-test safeguard can import daemon at fixture invocation... Repeat key-listener →
        typing-backend subprocess recorder order under safeguards; no old live-bus reproduction.'
  section: "§ BUG-001 (the two-media-paths section) is the load-bearing mandate."

# THIS SUBTASK'S RESEARCH NOTE
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M1T1S3/research/duck_wiring_and_ordering_findings.md
  why: §2.1 the new-test design + placement; §2.2 the tripwire design; §2.3 the ordering pin
        (VERIFIED green 39 passed this session); §3 baselines; §6 anti-patterns.
```

### Current Codebase tree (relevant slice)

```bash
tests/
├── conftest.py                  # S1's hermetic_daemon_media (S2 amends)     ← NOT EDITED by S3
├── test_ducking.py              # 698 lines; _FakeDucker :280; factory :454  ← EDIT (+1 test after :491)
├── test_typing_backends.py      # _Recorder :44; victims :89/:94             ← EDIT (tripwire + 2 asserts)
├── test_key_listener.py         # S1-migrated; the ordering pin's first node ← GATE ONLY
├── test_config.py               # mpris default pin :277                     ← GATE ONLY (untouched)
└── (S2's 6 migration files — NOT EDITED by S3)
voice_typing/                                                                 ← READ-ONLY
```

### Desired Codebase tree with files to be changed

```bash
tests/test_ducking.py            # MODIFY: +1 test — default-config→factory→_FakeDucker actuation
tests/test_typing_backends.py    # MODIFY: recorder tripwire (busctl/wpctl raise) + zero-media asserts in :89/:94
# NOTHING ELSE. conftest.py, test_config.py, S2's files, voice_typing/ untouched.
# The ordering pin is a VALIDATION GATE (documented command), not a file.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — THE NEW DUCKING TEST MUST USE THE DEFAULT CONFIG AND THE FACTORY LOOKUP, NOT THE
# ducker= SEAM. _make_ducking_daemon (:320) injects ducker=fake — that SKIPS _build_default_ducker,
# so it proves nothing about the default-config wiring. And do NOT mutate cfg.audio.duck_mode to
# 'off' — the 'mpris' DEFAULT path through the factory is the contract's exact phrase
# ("default-config constructor-to-_FakeDucker"). Patch ONLY:
#   monkeypatch.setattr(daemon, "_build_default_ducker", lambda cfg: fake, raising=True)

# CRITICAL #2 — THE TRIPWIRE MUST BE FILE-LOCAL, NEVER GLOBAL. S1's conftest design note: "a real
# media command must never 'prove' failure" — no global subprocess.run patch, no PATH/busctl shim.
# S3's tripwire lives INSIDE test_typing_backends.py's recorder fixture (file-local scope) and
# INSIDE the new ducking test (monkeypatch, function-scoped). Nothing in conftest.py.

# CRITICAL #3 — THE TRIPWIRE ALONE IS NOT THE GUARD. A leaked vt-ducking worker SWALLOWS in-thread
# exceptions (the AsyncDucker failure discipline logs-and-continues), so a tripwire raise inside the
# worker may not fail the test. The TEST-LEVEL zero-media assertion (scan recorder.argvs for
# busctl/wpctl) is the actual guard; the tripwire adds loud in-log visibility. Ship BOTH.

# CRITICAL #4 — BOUNDED COMPLETION BEFORE MOCKS UNWIND. Every dispatch in the new test must
# complete synchronously in-test: with _FakeDucker injected, engage/release are recorded at the
# seam under self._lock (synchronous); d.stop() finishes the release BEFORE the test returns, so
# the fake ledger and thread assertions are read while the monkeypatches are still active. Never
# sleep-and-hope; never assert after teardown.

# CRITICAL #5 — REAL STACKS ARE CONSTRUCTION-PURE. _build_default_ducker(mpris/volume cfg) builds
# AsyncDucker(AudioDucker(MprisBusctlBackend/WpctlVolumeBackend)) WITHOUT any subprocess — the
# 'vt-ducking' worker spawns lazily on first dispatch. That's why test_ducking_default_factory_
# builds_by_mode (:454) is safe as-is and must be RETAINED unchanged. Do not add dispatch to it.

# CRITICAL #6 — DO NOT TOUCH THE SHIPPED DEFAULT. test_config.py:277-279 pins duck_mode=='mpris'
# (P1.M2.T4's intentional flip). S3's tests prove the default path is FAKE-SWAPPABLE, not that the
# default is off. Any 'fix' that flips the default or the pin is a scope violation.

# GOTCHA #7 — THE FULL-FILE ORDERING VARIANT MAY DEPEND ON S2. The single-test pin (the reported
# repro) is S1-migrated and VERIFIED GREEN NOW. The full-file variant (whole test_key_listener.py
# before test_typing_backends.py) exercises OTHER arming tests that S2 migrates — gate it after S2
# lands (parallel contract), or report 'pending S2' explicitly. Never mark xfail to paper over it.

# GOTCHA #8 — TWO TIMEOUTS EVERYWHERE (AGENTS.md Rule 1): inner GNU `timeout 300` on every pytest
# invocation + the bash tool's own timeout above it. .venv/bin/python -m pytest. Never foreground
# the daemon; never arm live; never run test_feed_audio.py or CUDA/model suites (test_daemon.py is
# S2's gate, not S3's).

# GOTCHA #9 — IMPORTS FOR THE NEW DUCKING TEST: mirror the file's existing import block (daemon,
# VoiceTypingConfig, the test_daemon doubles _StubRecorder/_CtlFakeBackend/_ok_probe/
# _DaemonFakeFeedback are already in scope there — verify at edit time; add `import subprocess`
# and `import threading` only if not already imported).
```

## Implementation Blueprint

### Data models and structure

None new — the test reuses `_FakeDucker` (calls ledger), `_DuckingFakeFeedback` (ducked_states), `_StubRecorder`/`_CtlFakeBackend`/`_ok_probe`, and `VoiceTypingConfig` as-is.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PRECHECK — S1 landed + baselines green.
  - RUN: git log --oneline -2   # expect 74252cd (or later, if S2 landed)
  - RUN (the canonical ordering pin, already verified green):
        timeout 300 .venv/bin/python -m pytest \
          tests/test_key_listener.py::test_zero_keyboard_warning_fires_once_at_first_arm \
          tests/test_typing_backends.py -q        # expect ~39 passed
  - RUN: timeout 300 .venv/bin/python -m pytest tests/test_ducking.py tests/test_config.py -q
    # expect 100 passed (incl. the mpris default pin)

Task 1: ADD the default-to-fake wiring actuation regression to tests/test_ducking.py.
  - PLACE: immediately after test_ducking_default_factory_builds_by_mode (ends ~:491), before the
    P1.M2.T3.S2 crash-safety section banner.
  - CODE (copy-ready; adapt imports per the file's existing block):
        def test_ducking_default_wiring_actuates_engage_release_fake_only(monkeypatch):
            """P1.M1.T1.S3 (BUG-001): the DEFAULT config (duck_mode='mpris', unmutated) wires a
            ducker through the REAL factory lookup — patched to return a _FakeDucker — and
            arm/stop actuate engage/release with ZERO media-transport attempts.

            Distinct from _make_ducking_daemon (ducker= ctor seam SKIPS the factory) and from
            test_ducking_default_factory_builds_by_mode (real stacks, never dispatched): this is
            the one default-config constructor-to-_FakeDucker ACTUATION regression. The
            subprocess tripwire proves the negative (no busctl/wpctl can run); the thread check
            proves no 'vt-ducking'/'vt-duck-heal' worker exists. Bounded: the fake records at
            the seams synchronously, so the whole cycle completes before mocks unwind.
            """
            fake = _FakeDucker()
            media_attempts: list[tuple] = []

            def _tripwire_run(argv, *args, **kwargs):
                media_attempts.append(tuple(str(a) for a in argv))
                raise AssertionError(
                    f"media transport invoked under fake-only wiring: {tuple(argv)[:4]}"
                )

            monkeypatch.setattr(subprocess, "run", _tripwire_run)
            monkeypatch.setattr(
                daemon, "_build_default_ducker", lambda cfg: fake, raising=True
            )
            cfg = VoiceTypingConfig()  # DEFAULT — duck_mode='mpris' (the shipped pin)
            d = daemon.VoiceTypingDaemon(
                cfg, _DuckingFakeFeedback(), recorder=_StubRecorder(),
                backend=_CtlFakeBackend(), mic_prober=_ok_probe,
                # NO ducker= — the factory lookup is the path under test
            )
            assert d._ducker is fake  # ctor wired the factory's (faked) result
            fb = d._feedback if hasattr(d, "_feedback") else None  # adapt to the real attr
            d.start()
            d.stop()
            assert fake.calls == ["engage", "release"]
            assert media_attempts == []  # zero busctl/wpctl — the tripwire never fired
            assert not any(
                t.name in ("vt-ducking", "vt-duck-heal") for t in threading.enumerate()
            )
            # ducked-state mirroring (adapt fb accessor to the daemon's real surface; if the
            # feedback double is reachable, also assert its ducked_states == [True, False])
  - CONSTRAINTS: see Critical #1 (default cfg, factory-only patch, no ducker=), #4 (synchronous
    completion), #9 (imports). Capture the feedback double BEFORE construction if the ctor does
    not expose it (mirror how the lifecycle tests reach `fb` — they build fb first and pass it).

Task 2: STRENGTHEN tests/test_typing_backends.py — the recorder tripwire + victim assertions.
  - (a) In the `recorder` fixture's fake subprocess.run (inside _Recorder or the fixture
    wrapper, :44-88): BEFORE recording, raise on media transports:
        _MEDIA_TRANSPORTS = ("busctl", "wpctl")  # module constant near _Recorder
        # inside the fake run():
        if argv and str(argv[0]) in _MEDIA_TRANSPORTS:
            raise AssertionError(
                f"media transport {argv[0]!r} invoked in a typing-backend test (BUG-001 leak)"
            )
    Keep recording behavior otherwise byte-identical.
  - (b) In test_wtype_invokes_exact_argv (:89) and test_wtype_passes_check_true (:94), ADD one
    line each (existing assertions unchanged):
        assert not any(a[0] in ("busctl", "wpctl") for a in recorder.argvs)  # zero media leaks
  - WHY both layers: Critical #3 — the tripwire's raise can be swallowed inside a leaked worker
    thread; the test-level ledger scan is the deterministic guard. The tripwire gives the loud
    in-log naming.

Task 3: RUN THE ORDERING PIN + all gates (Validation Loop). Record the pinned invocation's
  output (test count + duration) — it is the clean-ordering evidence for P1.M1.T3.S1 (G1
  baseline classification) and P1.M2.T3.S2 (README sync). No git commit unless the orchestrator
  directs. If asked:
  "P1.M1.T1.S3: pin default-to-fake duck wiring + ordered subprocess isolation (BUG-001)".

Task 4: (Conditional) IF S2 has landed by implementation time: also gate the full-file variant
  (timeout 300 .venv/bin/python -m pytest tests/test_key_listener.py tests/test_typing_backends.py
  -q → green). If S2 has NOT landed: skip it and note 'pending S2' in the wrap-up (Gotcha #7) —
  never xfail, never reorder, never run the old live-bus reproduction.
```

### Implementation Patterns & Key Details

```python
# The two-layer leak detection pattern (the core of S3):
#   LAYER 1 (tripwire, loud + immediate): the recorder's fake subprocess.run refuses media argv.
#   LAYER 2 (ledger scan, deterministic): the victim tests assert zero busctl/wpctl argvs.
# Rationale: a leaked vt-ducking worker swallows in-thread exceptions (failure discipline),
# so layer 1 alone may not fail a test — but layer 2 always does, and layer 1 names the culprit.

# The default-to-fake wiring pattern (distinct from both existing approaches):
#   _make_ducking_daemon(duck=True)   → ducker=fake via ctor seam   (SKIPS the factory)
#   factory-builds-by-mode test       → REAL stacks, never dispatched (no actuation proof)
#   S3's new test                     → DEFAULT cfg + factory LOOKUP patched to return the fake
#                                       → proves ctor wiring + engage/release actuation + zero
#                                         media attempts, all synchronously in-test.
# The monkeypatch target is the module attribute the daemon looks up at call time:
#   monkeypatch.setattr(daemon, "_build_default_ducker", lambda cfg: fake, raising=True)
```

### Integration Points

```yaml
DOWNSTREAM CONSUMERS:
  - P1.M1.T3.S1 (classify test_daemon.py as a CPU suite in G1): cites S3's pinned ordering
    invocation + tripwires as the clean-ordering/side-effect-free evidence for its baseline
    addendum.
  - P1.M2.T3.S2 (README sync): cites S3's evidence that unit suites no longer touch the live
    media bus.
SIBLINGS:
  - S1 (landed): owns conftest's fixture; S3 consumes (gates only) and never edits it.
  - S2 (in flight, CONTRACT): owns the 6 migration files; disjoint from S3's edit set. The
    full-file ordering variant gates after S2 lands.
PRESERVED SURFACES:
  - voice_typing/ (production), tests/conftest.py, tests/test_config.py (the mpris shipped
    default pin), S2's migration files, the pre-existing ducking lifecycle/backend/heal tests.
```

## Validation Loop

> AGENTS.md two-timeout rule on EVERY pytest (inner `timeout 300`, bash-tool timeout above it). `.venv/bin/python -m pytest`. Never foreground the daemon; never arm live; never run test_feed_audio.py or CUDA/model suites.

### Level 1: The edits landed (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- the new ducking test exists, uses the factory patch, not the ducker= seam ---"
grep -n "def test_ducking_default_wiring_actuates_engage_release_fake_only" tests/test_ducking.py
sed -n "$(grep -n 'def test_ducking_default_wiring_actuates_engage_release_fake_only' tests/test_ducking.py | cut -d: -f1),+40p" tests/test_ducking.py | grep -E "_build_default_ducker|VoiceTypingConfig\(\)|ducker=|media_attempts|vt-ducking"
# expect: the factory setattr present; VoiceTypingConfig() unmutated; NO ducker= kwarg in the ctor call
echo "--- the typing-backends tripwire + assertions ---"
grep -n "_MEDIA_TRANSPORTS\|busctl" tests/test_typing_backends.py | head -6
grep -c "busctl" tests/test_typing_backends.py   # expect >= 3 (constant + tripwire + 2 asserts)
echo "--- existing tests untouched ---"
git diff tests/test_ducking.py | grep -c "^-[^-]"   # expect 0 removed lines (purely additive)
git diff tests/test_typing_backends.py | grep "^-[^-]" | grep -v "recorder.argvs ==" | head -3  # only the re-indented fixture line may differ
echo "--- scope ---"
git diff --name-only   # expect exactly the two files
```

### Level 2: The new tests + all touched pure suites green

```bash
cd /home/dustin/projects/voice-typing
echo "--- the new wiring test ---"
timeout 300 .venv/bin/python -m pytest tests/test_ducking.py -q -k "default_wiring_actuates" 2>&1 | tail -2
echo "--- full ducking + the default pin + typing_backends + key_listener ---"
timeout 300 .venv/bin/python -m pytest tests/test_ducking.py tests/test_config.py tests/test_typing_backends.py tests/test_key_listener.py -q 2>&1 | tail -2
# expect: 1 passed for the -k; all green for the battery (100+ ducking/config baseline + the rest)
```

### Level 3: THE ORDERING PIN (the canonical BUG-001 repro, now green) — 3x for determinism

```bash
cd /home/dustin/projects/voice-typing
for i in 1 2 3; do
  echo "--- ordering pin run $i/3 (arming test BEFORE typing_backends, one bounded invocation) ---"
  timeout 300 .venv/bin/python -m pytest \
    tests/test_key_listener.py::test_zero_keyboard_warning_fires_once_at_first_arm \
    tests/test_typing_backends.py -q 2>&1 | tail -1
done
# expect: 3x green (~39 passed each run — record the exact count+duration as the evidence for
# P1.M1.T3.S1 / P1.M2.T3.S2). If ANY run fails with busctl-shaped kwargs in a wtype assertion,
# the hermetic wiring regressed — investigate the constructor path, do NOT filter the calls.
echo "--- (if S2 landed) the full-file variant ---"
timeout 300 .venv/bin/python -m pytest tests/test_key_listener.py tests/test_typing_backends.py -q 2>&1 | tail -1
```

### Level 4: The tripwires actually trip (mutation spot-check, then restore)

```bash
cd /home/dustin/projects/voice-typing
echo "--- 4a: the ledger guard fires on a simulated media call ---"
timeout 120 .venv/bin/python - <<'PY'
import sys
sys.path.insert(0, "tests")
# Simulate the polluted-ledger failure mode the victims guard against:
argvs = [("busctl", "--user", "call", "org.freedesktop.DBus"), ("wtype", "-d", "12", "--", "hi")]
assert any(a[0] in ("busctl", "wpctl") for a in argvs), "guard would miss a media call"
print("L4a PASS: the zero-media assertion detects a polluted ledger")
PY
echo "--- 4b: scope + exclusions ---"
git diff --name-only | grep -vE 'tests/(test_ducking|test_typing_backends)\.py' | grep -E '\.py$|\.toml$' && echo "L4b FAIL: out of scope" || echo "L4b PASS: only the two intended files"
git diff --quiet voice_typing/ tests/conftest.py tests/test_config.py && echo "L4c PASS: production/conftest/config-pin untouched" || echo "L4c FAIL"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: new ducking test present (factory patch, no ducker=, unmutated default cfg); typing-backends tripwire + 2 zero-media asserts; purely additive diffs; scope = the two files.
- [ ] L2: the new test green; ducking + config + typing_backends + key_listener battery green.
- [ ] L3: the ordering pin green 3/3 (record count+duration as downstream evidence); full-file variant green if S2 landed (else noted pending).
- [ ] L4: the ledger guard demonstrably detects a simulated media call; production/conftest/config-pin untouched.

### Feature Validation
- [ ] Default-config (mpris) constructor wires through the real factory lookup (patched to the fake) and actuates engage/release; ducked state mirrors; zero subprocess attempts; zero duck threads.
- [ ] Existing fake lifecycle, backend, crash-heal, and shutdown-flush coverage retained byte-identical and green.
- [ ] The recorder trips on busctl/wpctl argv; the two victims assert zero media argvs (no filtering).
- [ ] The shipped mpris default pin green and untouched.

### Code Quality Validation
- [ ] The new test's style mirrors the file's lifecycle tests (in-test start/stop cycle, asserts while mocks are live).
- [ ] Tripwires are file-local (no global patch — S1's design constraint honored).
- [ ] Zero-media assertions are additive; existing assertions byte-identical.

### Scope Boundary Validation
- [ ] `voice_typing/`, `tests/conftest.py`, `tests/test_config.py`, S2's six migration files untouched.
- [ ] No autouse, no global subprocess patch, no PATH shim, no xfail/reordering, no live-bus reproduction.
- [ ] Two timeouts on every pytest; no daemon foregrounded; no CUDA/model suites run.

### Documentation & Deployment
- [ ] The pinned ordering invocation + its green evidence recorded in the wrap-up for P1.M1.T3.S1 and P1.M2.T3.S2 to cite.
- [ ] New tests carry docstrings naming BUG-001 / P1.M1.T1.S3 and the distinction from the existing doubles.

---

## Anti-Patterns to Avoid

- ❌ **Don't use the `ducker=` ctor seam or mutate the cfg to `off` in the new wiring test** — `_make_ducking_daemon` already covers the seam; the contract's phrase is "default-config constructor-to-_FakeDucker" via the factory lookup (Critical #1).
- ❌ **Don't add a global subprocess patch or PATH/busctl shim** — S1's conftest design explicitly forbids it ("a real media command must never 'prove' failure"); tripwires are file-local (Critical #2).
- ❌ **Don't rely on the tripwire alone** — a leaked worker swallows in-thread raises; the test-level ledger scan is the deterministic guard; ship both layers (Critical #3).
- ❌ Don't assert after teardown or sleep-and-hope — the fake records synchronously; read the ledger while mocks are live (Critical #4).
- ❌ Don't add dispatch to `test_ducking_default_factory_builds_by_mode` — its real stacks are construction-pure; retaining it unchanged is required (Critical #5).
- ❌ Don't touch the shipped `mpris` default or its pin in test_config.py (Critical #6).
- ❌ Don't xfail/reorder/filter to "fix" the ordering pin — it must pass on real isolation; if the full-file variant is red pre-S2, report "pending S2" (Gotcha #7).
- ❌ Don't edit conftest.py, S2's migration files, or run forbidden suites; two timeouts everywhere (Gotchas #8-#9).
- ❌ Don't reproduce the old live-bus proof (constructing a default daemon without safeguards and watching busctl fire) — the system context explicitly forbids it; the fail-closed fixture raise and the tripwires are the sanctioned proofs.

---

## Confidence Score

**9/10** for one-pass success. Every input is read in full (S1's landed conftest; the 698-line test_ducking.py with all doubles/tests enumerated by line; the victim tests' exact assertions; S2's PRP as the parallel contract with a provably disjoint edit set); the canonical ordering invocation is VERIFIED GREEN this session (39 passed / 1.04s — so the pin's expected outcome is known, not assumed); the baselines are verified (100 passed ducking+config); and the reference implementations for both edits are copy-ready with their failure modes explained (the swallowed-in-thread tripwire → two-layer guard). The −1: the new ducking test's daemon-surface details (how the test reaches the feedback double for the `ducked_states` assertion, and the exact ctor kwargs the file's doubles expect) must be adapted to the file's live conventions at edit time — the blueprint pins the pattern and placement but names two attribute accesses to verify in-file.
