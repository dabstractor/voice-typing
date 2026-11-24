# PRP — P1.M1.T1.S2: Migrate ordinary daemon constructors and test consumers

## Goal

**Feature Goal**: Complete BUG-001's test-side fix (S1 landed the seam fixture; S2 does the sweep): make **every ordinary daemon constructor in the repo use isolated media and clean state** — no test can construct a default-config `VoiceTypingDaemon` that reaches the operator's live media bus (`busctl --user`) or reads/heals the operator's persisted duck flag — by migrating the constructor helpers and direct-ctor sites across the seven affected files, plus the two conftest adjustments the contract mandates (lazy daemon import; a plain shared `hermetic_cfg`).

**Deliverable**: ~8 files: `tests/conftest.py` (2 adjustments: lazy daemon imports + the additive `hermetic_cfg` function), `tests/test_daemon.py` (3 helpers + 16 direct ctors + 1 hermeticity pin), `tests/test_bulk_dispatch.py` (1 ctor), `tests/test_bulk_context_prompt.py` (ctor + the `_D` alias), `tests/test_context_prompt_refresh.py` (local `_make_daemon`), `tests/test_feed_audio.py` (1 ctor, **edit-only** — never run as CPU validation), and green-gate verification for the two importing consumers (`test_session_recovery.py`, `test_voicectl_session.py` — no edits expected).

**Success Definition**: (a) every `VoiceTypingDaemon(` construction in the migrated files goes through a hermetic cfg (`duck_mode="off"` + private/nonexistent-or-tmp state) or an injected fake; (b) conftest imports `voice_typing.daemon` only at fixture invocation (never at module import); (c) all migrated suites green under `timeout 300`; (d) the ordering-pollution probes (`<migrated arming file> + tests/test_typing_backends.py`) green; (e) the dedicated ducking tests (`test_ducking.py`) and the shipped-default pin (`test_config.py` → `mpris`) untouched and green; (f) `voice_typing/` untouched; (g) test_ime_manager/test_voicectl/test_control_socket not edited.

## User Persona

**Target User**: The operator (whose live Brave/MPRIS endpoints must never be paused by a unit suite — PRD R.7 "automation MUST NOT exercise the live desktop") and the downstream subtasks: **P1.M1.T1.S3** (ordered subprocess isolation needs hermetic files so only intended fake traffic is observable) and **P1.M1.T3.S1** (classifying `test_daemon.py` as a CPU suite requires it to be side-effect-free to run).

**Use Case**: Any future test constructs a daemon via `_make_daemon()`/`_make_lazy_daemon()`/the bulk/refresh helpers — or directly — and gets media-off + private state by DEFAULT; only the dedicated duck-wiring tests opt into `ducker=<fake>`.

**Pain Points Addressed**: order-dependent cross-file failures (leaked `vt-ducking` worker's `subprocess.run` landing in later recorders); the live side effect (suite pausing playing media, no resume); and the lingering construction-time vector (the boot-heal flag read against the operator's real state file).

## Why

- **BUG-001 (Major) is only half-fixed**: S1 killed the seam for key-listener tests + proved the fixture; the other default-config arm sites (test_daemon, bulk_dispatch, bulk_context_prompt, context_prompt_refresh + their importers) still construct `duck_mode='mpris'` daemons whose `_arm()` dispatches real `busctl --user` (the PRD's deterministic 3/3 repro family), and whose construction reads the operator's real duck-flag state.
- **CFG-level isolation covers ALL arm paths at once**: `_build_default_ducker` runs only when `duck_mode != "off"` and `_duck_engage` no-ops when `_ducker is None` — so one cfg wrap covers `_arm()`, `start()`/`toggle()`, the run-loop lazy first-arm, and socket-driven arms, without chasing call sites (the contract's "audit all direct and indirect arm paths").
- **Why the helpers, not 150 test edits**: `_make_daemon` & co are plain helpers (no fixture access); wrapping their cfg hermeticizes ~100 call sites in 3 edits. The per-test `hermetic_daemon_media` fixture remains the fail-closed GUARD (S1's design; S3's ordered-isolation surface), not the bulk mechanism.
- **Safe to blanket-wrap test_daemon.py**: verified — NO test in test_daemon.py asserts ducking behavior (`grep "_duck|ducker"` → empty); dedicated ducking tests live in test_ducking.py and stay untouched.

## What

Two conftest adjustments (lazy daemon import + shared `hermetic_cfg`), helper + direct-ctor wraps across the target files, one hermeticity pin, edit-only feed_audio wrap. No production code, no shipped-default changes, no autouse, no global subprocess patch.

### Success Criteria

- [ ] conftest.py: `voice_typing.daemon`/`ducking_heal` imported INSIDE the fixture body; module level imports only dataclasses/pytest/`voice_typing.config`; new `hermetic_cfg(cfg=None, *, state_file=None)` present (duck off always; state_file param wins, else preserve a non-empty supplied state_file, else a nonexistent private default); the fixture's `hermetic()` delegates to it (behavior identical).
- [ ] test_daemon.py: `_make_daemon`/`_make_lazy_daemon` wrap `cfg = hermetic_cfg(cfg)`; `_make_daemon_with_feedback` wraps its cfg (tmp state preserved); all 16 direct-ctor sites wrapped; the new pin `test_make_daemon_helpers_are_media_hermetic` green.
- [ ] test_bulk_dispatch.py (:338 helper ctor), test_bulk_context_prompt.py (:410 + `_D` :702), test_context_prompt_refresh.py (local `_make_daemon` :162): cfg wrapped.
- [ ] test_feed_audio.py :573-576: cfg wrapped; validated by `--collect-only` only.
- [ ] test_session_recovery.py / test_voicectl_session.py: verified ctor-free (import-only consumers) and GREEN — no edits.
- [ ] All migrated suites + ordering probes + key_listener + ducking + config green; `voice_typing/`, test_ducking.py, test_config.py, test_ime_manager.py, test_voicectl.py, test_control_socket.py untouched.

## All Needed Context

### Context Completeness Check

_Pass._ S1's landed fixture is read in full; every constructor site is enumerated with line numbers and feedback type; the exclusion set is verified (0 ctors); the no-ducking-assertions fact in test_daemon.py is verified; the eager-import violation in the landed conftest is identified with the mandated fix.

### Documentation & References

```yaml
# THE LANDED SEAM CONTRACT (S1 — this task's INPUT; committed 74252cd)
- file: tests/conftest.py
  why: The hermetic_daemon_media fixture (hermetic() helper + fail-closed _build_default_ducker
        patch + read_ducked_flag fake). S2 (a) makes its daemon/ducking_heal imports LAZY (inside
        the fixture body — the contract's "do not eagerly import daemon in conftest"; the landed
        version imports them at module top), (b) adds the plain hermetic_cfg() and delegates.
  critical: "Keep the fixture OPT-IN (no autouse) and its fail-closed/guard semantics byte-identical
            — only the import placement and the additive function change."
- file: tests/test_key_listener.py
  why: The S1 migration precedent — call style `_wire_daemon(hermetic_daemon_media())` (the fixture
        object called → hermetic cfg passed positionally). S2 mirrors: pass hermetic_cfg(...) into
        helpers' cfg param.
- file: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/system_context.md
  why: The constructor inventory (§ lines 9-12): the helpers/direct-ctor hotspots, the _D alias, the
        importing consumers, the feed_audio model-backed ctor, the exclusions (voicectl fake server,
        ime_manager import purity, g5 lab already-off), and "import daemon at fixture invocation,
        not at collection".
  critical: "test_ime_manager.py must NOT gain daemon imports; test_voicectl/test_control_socket use
            duck-typed servers (0 ctors) — leave them alone."

# THE PRODUCTION SEAM (READ-ONLY)
- file: voice_typing/daemon.py
  why: ctor :799 (`ducker=` param) + :1021-1023 (factory only when duck_mode != 'off') + :810
        (read_ducked_flag at construction) + :1804 (_arm → _duck_engage, no-op when _ducker None).
        These four lines are WHY cfg-level isolation covers every arm path.
  gotcha: "DO NOT edit voice_typing/ in S2 — the whole fix works through cfg + existing seams."

# THE MIGRATION TARGETS (each site's line + feedback type verified)
- file: tests/test_daemon.py
  why: _make_daemon :682 (84 no-cfg + 11 cfg calls; _DaemonFakeFeedback); _make_daemon_with_feedback
        :1932 (REAL Feedback, tmp_path state — wrap, state preserved); _make_lazy_daemon :3337;
        16 direct ctors (:689, :1287, :1949, :2069, :2122, :2147, :2186, :2910, :2923, :2954, :3344,
        :4104, :4146, :4192, :4238, :4289). 235 tests, pure CPU. NO ducking assertions (verified).
  pattern: "Add `from conftest import hermetic_cfg` (sibling-import precedent: `import test_daemon
            as td` works — tests/ is on sys.path). Wrap at each site; fake-feedback sites take the
            nonexistent-default state path; real-Feedback sites keep tmp state via preservation."
  gotcha: "149 arm-ish calls exist — do NOT chase them; the cfg wrap covers them all."
- file: tests/test_bulk_dispatch.py
  why: 1 ctor :338 inside a helper taking cfg (builds _FakeBundle/_FakeTarget). Wrap the helper's cfg.
- file: tests/test_bulk_context_prompt.py
  why: ctor :410 AND the local alias `from voice_typing.daemon import VoiceTypingDaemon as _D` (:690)
        used at :702 — wrap BOTH (the alias is easy to miss; the contract names it).
- file: tests/test_context_prompt_refresh.py
  why: local `_make_daemon` :158-170 (ctor :162; 13 in-file calls) with _FakeFeedback. Wrap its cfg.
- file: tests/test_feed_audio.py
  why: :573-576 `cfg = VoiceTypingConfig()` → ctor with _StubFeedback/_NoopBackend + REAL recorder +
        real run-thread (the model-backed path). Wrap cfg. EDIT-ONLY validation: --collect-only +
        py_compile (real-model suite; AGENTS.md forbids treating it as a CPU slice).
- file: tests/test_session_recovery.py
  why: 0 direct ctors — `import test_bulk_dispatch as tbd` (:45) + `import test_daemon as td` (:46).
        Covered by the helper wraps. Gate by running green; no edit expected.
- file: tests/test_voicectl_session.py
  why: 0 direct ctors — `import test_daemon as td` (:34, _make_lazy_daemon). Covered. Gate green.

# THE DOUBLES/EXCLUSIONS
- file: tests/test_ducking.py
  why: _FakeDucker (:280) + the dedicated duck-lifecycle tests — the INTENTIONAL real-path
        exception. UNTOUCHED by S2 (S3 pins default→fake wiring there).
- file: tests/test_config.py
  why: pins the SHIPPED default duck_mode == "mpris" — the config surface must stay default-on in
        production; only test configs go off. UNTOUCHED.

# THIS SUBTASK'S RESEARCH NOTE (the full inventory table)
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/P1M1T1S2/research/migration_inventory_findings.md
  why: §1 S1's landed contract + THE EAGER-IMPORT VIOLATION; §2 the per-file inventory table
       (counts, lines, feedback types, exclusions); §3 the design (hermetic_cfg semantics, why
       helpers-not-fixtures, the pin); §4 validation facts; §5 downstream.
  section: "§2 (the table — work from it) and §3 (the design) are load-bearing."
```

### Current Codebase tree (relevant slice)

```bash
tests/
├── conftest.py                      # S1's fixture (LANDED)               ← EDIT (2 adjustments)
├── test_daemon.py                   # 3 helpers + 16 direct ctors + pin   ← EDIT
├── test_bulk_dispatch.py            # ctor :338 in a helper               ← EDIT
├── test_bulk_context_prompt.py      # ctor :410 + _D :690/:702            ← EDIT
├── test_context_prompt_refresh.py   # local _make_daemon :162             ← EDIT
├── test_feed_audio.py               # ctor :576 (model-backed)            ← EDIT (collect-only validation)
├── test_session_recovery.py         # imports td/tbd (0 ctors)            ← GATE ONLY
├── test_voicectl_session.py         # imports td (0 ctors)                ← GATE ONLY
├── test_key_listener.py             # S1-migrated (reference)             ← GATE ONLY
├── test_typing_backends.py          # the pollution victim (probes)       ← GATE ONLY
└── (test_ducking/test_config/test_ime_manager/test_voicectl/test_control_socket — UNTOUCHED)
voice_typing/                                                                  ← READ-ONLY
```

### Desired Codebase tree with files to be changed

```bash
tests/conftest.py                   # MODIFY: lazy daemon imports (inside fixture) + additive hermetic_cfg(); fixture delegates
tests/test_daemon.py                # MODIFY: 3 helper wraps + 16 ctor wraps + 1 hermeticity pin
tests/test_bulk_dispatch.py         # MODIFY: 1 helper wrap
tests/test_bulk_context_prompt.py   # MODIFY: 2 wraps (ctor + _D)
tests/test_context_prompt_refresh.py# MODIFY: 1 helper wrap
tests/test_feed_audio.py            # MODIFY: 1 cfg wrap (collect-only validation)
# NOTHING ELSE. session_recovery/voicectl_session expected edit-free; voice_typing/ untouched.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — NO PRODUCTION CODE CHANGES. Everything works through cfg (duck_mode/state_file)
# and the EXISTING ducker= seam. Editing voice_typing/ in S2 is a scope violation.

# CRITICAL #2 — LAZY DAEMON IMPORT IN CONFTEST (the contract mandate). The landed S1 conftest
# imports voice_typing.daemon at MODULE level — move `import voice_typing.daemon as daemon_mod`
# and `import voice_typing.ducking_heal as ducking_heal_mod` INSIDE the fixture body. Module
# level keeps only dataclasses/pytest/voice_typing.config (pure). Failure to do this is the
# single most likely contract miss.

# CRITICAL #3 — hermetic_cfg SEMANTICS (state_file precedence): explicit state_file param WINS;
# else a NON-EMPTY supplied cfg.feedback.state_file is PRESERVED (real-Feedback tmp sites keep
# their writable private state); else the nonexistent private default (missing file ⇒ the
# boot-heal read swallows to False; fake-feedback sites never write state anyway). duck_mode
# is ALWAYS "off". Never mutate the argument (dataclasses.replace, top + audio + feedback).

# CRITICAL #4 — DON'T CHASE ARM CALLS. ~149 arm-ish calls exist across the files; the cfg wrap
# at the constructor covers every direct and indirect arm path (factory gated on duck_mode;
# _duck_engage no-ops on _ducker None). The "audit" is: enumerate every VoiceTypingDaemon(
# construction and confirm each is wrapped — grep the inventory lines.

# CRITICAL #5 — THE _D ALIAS IS A CONSTRUCTOR TOO. test_bulk_context_prompt.py:690 imports
# VoiceTypingDaemon as _D locally (used :702) — wrapping only the :410 ctor misses it. The
# contract names _D explicitly.

# CRITICAL #6 — feed_audio IS EDIT-ONLY. Wrap the cfg; validate with --collect-only +
# py_compile. NEVER run test_feed_audio.py as a CPU slice (real model loads; AGENTS.md).

# CRITICAL #7 — DON'T TOUCH THE EXCLUSIONS. test_ducking.py (intentional real-path duck tests),
# test_config.py (shipped default pin = mpris), test_ime_manager.py (import purity — adding a
# daemon import there breaks its own coverage), test_voicectl.py/test_control_socket.py
# (duck-typed servers, 0 ctors).

# GOTCHA #8 — THE FIXTURE STAYS OPT-IN + FAIL-CLOSED. S2's bulk mechanism is the cfg wrap, NOT
# autouse and NOT a global subprocess.run patch (a real media command must never "prove"
# failure; S3 owns ordered subprocess isolation).

# GOTCHA #9 — IMPORT STYLE: `from conftest import hermetic_cfg` in test modules (tests/ is on
# sys.path — the `import test_daemon as td` precedent). conftest's hermetic_cfg imports only
# voice_typing.config, so this adds NO daemon import to any test module that lacks one.

# GOTCHA #10 — TWO TIMEOUTS on every pytest (inner timeout 300 + bash-tool above); .venv/bin/
# python -m pytest; never foreground the daemon; never arm live; test_daemon.py is pure CPU
# (mocked CUDA via _cuda_resolve) and safe to run — 235 tests.
```

## Implementation Blueprint

### Data models and structure

None new — `hermetic_cfg` composes the existing `VoiceTypingConfig` dataclasses via `replace`.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PRECHECK — S1 landed + baseline green.
  - RUN: git log --oneline -1 (expect 74252cd or later); test -f tests/conftest.py
  - RUN (confirm the S1 baseline): timeout 300 .venv/bin/python -m pytest
        tests/test_key_listener.py::test_zero_keyboard_warning_fires_once_at_first_arm
        tests/test_typing_backends.py -q   → all passed.
  - READ tests/conftest.py + the S1-migrated sites in test_key_listener.py (the call style to mirror).

Task 1: EDIT tests/conftest.py — the two adjustments.
  - (a) Move the daemon_mod/ducking_heal_mod imports INSIDE hermetic_daemon_media (Critical #2).
  - (b) ADD the module-level plain function (config-only imports):
        def hermetic_cfg(cfg=None, *, state_file=None) -> VoiceTypingConfig:
            """Test-owned hermetic config for ORDINARY daemon construction (BUG-001 / P1.M1.T1.S2).

            duck_mode is ALWAYS 'off'; feedback.state_file: the state_file param wins, else a
            non-empty supplied state_file is PRESERVED (real-Feedback tmp sites stay writable),
            else a nonexistent private default (the boot-heal read swallows missing → False).
            Returns a NEW config (replace; never mutates). Plain function so constructor HELPERS
            (no fixture access) share ONE discipline with the hermetic_daemon_media fixture.
            """
  - (c) Refactor the fixture's hermetic() to delegate: hermetic_cfg(cfg, state_file=str(state_path))
        — behavior identical (explicit state_file wins).
  - CONSTRAINTS: opt-in unchanged; fail-closed patch + read fake byte-identical; no subprocess patch.

Task 2: EDIT tests/test_daemon.py — the helpers + direct ctors + the pin.
  - Add `from conftest import hermetic_cfg` near the test-module imports (after the existing
    voice_typing imports; note it in the module docstring's hermeticity line if one exists).
  - _make_daemon (:682): `cfg = cfg or VoiceTypingConfig()` → `cfg = hermetic_cfg(cfg)`.
  - _make_daemon_with_feedback (:1932): wrap its cfg (built with FeedbackConfig(state_file=
    str(tmp_path / "state.json"))) with hermetic_cfg — the non-empty tmp state is preserved.
  - _make_lazy_daemon (:3337): `cfg = cfg or VoiceTypingConfig()` → `cfg = hermetic_cfg(cfg)`.
  - The 16 direct-ctor sites (list in the research note §2 / the file refs): read each context;
    wrap its cfg with hermetic_cfg(...) right before construction (fake-feedback sites take the
    default; any real-Feedback site's tmp state is preserved by construction).
  - ADD the pin (place near _make_daemon's tests):
        def test_make_daemon_helpers_are_media_hermetic():
            """P1.M1.T1.S2: the ordinary constructor helpers build media-hermetic daemons —
            _ducker None, duck off, state private; arm/disarm spawns no duck threads (BUG-001)."""
            d, _fb, _rec, _be = _make_daemon()
            dl, _fbl = _make_lazy_daemon()
            for d_ in (d, dl):
                assert d_._ducker is None
                assert d_._cfg.audio.duck_mode == "off"     # adapt to the real cfg attr name
                sf = d_._cfg.feedback.state_file
                assert sf and "/run/user/" not in sf          # private, not the OS runtime dir
                d_.start() if hasattr(d_, "start") else d_._arm()
                d_.stop() if hasattr(d_, "stop") else d_._disarm()
            import threading
            assert not any(t.name.startswith(("vt-ducking", "vt-duck-heal")) for t in threading.enumerate())
    (adapt attribute names to the daemon's real cfg storage; mirror _make_daemon's arm style —
     many existing tests call d.start()/d.stop(); keep it minimal.)

Task 3: EDIT the three small-file helpers + _D.
  - test_bulk_dispatch.py (:338): in the enclosing helper, `cfg = hermetic_cfg(cfg)` before the
    ctor (import hermetic_cfg from conftest).
  - test_bulk_context_prompt.py (:410 ctor AND the `_D` use :702 — Critical #5): wrap both cfgs.
  - test_context_prompt_refresh.py (local _make_daemon :158-170): wrap its cfg.

Task 4: EDIT tests/test_feed_audio.py (edit-only).
  - :573: `cfg = VoiceTypingConfig()` → follow with `cfg = hermetic_cfg(cfg)` (or wrap inline at
    :576). Import via `from conftest import hermetic_cfg` — NOTE: this file already imports
    daemon (real-model suite), so no import-purity concern.
  - VALIDATE: timeout 60 .venv/bin/python -m pytest tests/test_feed_audio.py --collect-only -q
    AND .venv/bin/python -c "import py_compile; py_compile.compile('tests/test_feed_audio.py',
    doraise=True)". DO NOT RUN the suite (Critical #6).

Task 5: VERIFY the importing consumers need no edit + run all gates (Validation Loop).
  - grep -c "VoiceTypingDaemon(" tests/test_session_recovery.py tests/test_voicectl_session.py
    → both 0 (they consume td/tbd helpers → covered by the wraps).
  - Run the L2 gate batteries.

Task 6: WRAP UP. No git commit unless the orchestrator directs. If asked:
  "P1.M1.T1.S2: migrate ordinary daemon constructors to hermetic media/state (BUG-001 sweep)".
```

### Implementation Patterns & Key Details

```python
# The migration is ONE pattern applied ~22 times: wrap the cfg before construction.
#   cfg = hermetic_cfg(cfg)            # helpers (covers ~100 call sites in 3 edits)
#   d = VoiceTypingDaemon(hermetic_cfg(cfg), ...)   # direct ctors (incl. _D)
# Why it covers every arm path: daemon ctor :1021-1023 builds a ducker ONLY when duck_mode !=
# 'off'; _duck_engage no-ops when _ducker is None; the construction-time boot-heal read resolves
# cfg.feedback.resolved_state_file() — private/nonexistent ⇒ isolated (swallow → False).
# The per-test fixture stays the fail-closed GUARD (and S3's isolation surface): under it, an
# UNWRAPPED default-config construction raises synchronously at the factory lookup.
# State precedence in hermetic_cfg is the one subtlety: explicit param > supplied non-empty >
# nonexistent default — real-Feedback tests keep writing their tmp state; fake-feedback tests
# never write state at all.
```

### Integration Points

```yaml
DOWNSTREAM CONSUMERS (NOT S2):
  - P1.M1.T1.S3 (default→fake duck wiring + ordered subprocess isolation): needs S2's hermetic
    files so its ordered recorder tests observe ONLY intended fake traffic; its wiring pin uses
    ducker=_FakeDucker (the sanctioned escape) in test_ducking.py.
  - P1.M1.T3.S1 (classify test_daemon.py as a CPU suite in G1 + fold its legacy reds into the
    classification): needs running test_daemon.py to be side-effect-free — S2's migration is the
    precondition.
  - P1.M3 (bulk work): the bulk dispatch/context-prompt suites are now hermetic by default.
SIBLING (S1): landed; S2 preserves its fixture semantics (only import placement + delegation change).
PRESERVED SURFACES: shipped config defaults (mpris) in voice_typing/config.py + config.toml
  (pinned by test_config.py); test_ducking.py's real-path duck tests; test_ime_manager import purity.
```

## Validation Loop

> AGENTS.md two-timeout rule on every pytest (inner `timeout 300`, bash-tool above). `.venv/bin/python -m pytest`. Never foreground the daemon; never arm live; never run test_feed_audio as a CPU slice.

### Level 1: The wraps landed (static)

```bash
cd /home/dustin/projects/voice-typing
echo "--- conftest: lazy daemon import + hermetic_cfg ---"
! grep -n "^import voice_typing.daemon\|^import voice_typing.ducking_heal" tests/conftest.py && echo "L1a PASS: no module-level daemon import"
grep -q "def hermetic_cfg" tests/conftest.py && echo "L1b PASS: hermetic_cfg defined"
grep -n "import voice_typing.daemon" tests/conftest.py | head -2   # expect it INSIDE the fixture (indented)
echo "--- every ctor site wrapped (count hermetic_cfg uses per file) ---"
for f in test_daemon test_bulk_dispatch test_bulk_context_prompt test_context_prompt_refresh test_feed_audio; do
  echo "$f: hermetic_cfg uses = $(grep -c hermetic_cfg tests/$f.py)"
done
echo "--- the _D alias site wrapped ---"
grep -n "_D(" tests/test_bulk_context_prompt.py | head -3
echo "--- exclusions untouched ---"
git diff --name-only | grep -E 'test_ducking|test_config\.py|test_ime_manager|test_voicectl\.py|test_control_socket' && echo "L1 FAIL" || echo "L1c PASS: exclusions untouched"
git diff voice_typing/ | grep -q . && echo "L1 FAIL: production touched" || echo "L1d PASS"
```

### Level 2: All migrated suites + consumers + ordering probes green

```bash
cd /home/dustin/projects/voice-typing
echo "--- the heavy target (235 CPU tests) ---"
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q 2>&1 | tail -3
echo "--- the migrated small files ---"
timeout 300 .venv/bin/python -m pytest tests/test_bulk_dispatch.py tests/test_bulk_context_prompt.py tests/test_context_prompt_refresh.py -q 2>&1 | tail -3
echo "--- the importing consumers (no edits expected) ---"
timeout 300 .venv/bin/python -m pytest tests/test_session_recovery.py tests/test_voicectl_session.py -q 2>&1 | tail -3
echo "--- S1's file still green + the dedicated ducking/default suites untouched-green ---"
timeout 300 .venv/bin/python -m pytest tests/test_key_listener.py tests/test_ducking.py tests/test_config.py -q 2>&1 | tail -3
echo "--- ORDERING PROBES (the pollution mechanism): migrated arming file + typing_backends ---"
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "arm" --co -q >/dev/null 2>&1 # (pick one arming test below)
timeout 300 .venv/bin/python -m pytest "tests/test_daemon.py::test_start_arms" tests/test_typing_backends.py -q 2>&1 | tail -2
timeout 300 .venv/bin/python -m pytest tests/test_bulk_dispatch.py tests/test_typing_backends.py -q 2>&1 | tail -2
# Expected: ALL green. (Substitute a real arming test name from `pytest --co -k arm`.) If any
# typing_backends wtype-recorder test fails with busctl-shaped kwargs, a constructor was missed —
# re-audit the inventory.
```

### Level 3: Structural hermeticity (the pin + a live-shaped proof)

```bash
cd /home/dustin/projects/voice-typing
echo "--- the S2 pin ---"
timeout 300 .venv/bin/python -m pytest tests/test_daemon.py -q -k "media_hermetic" 2>&1 | tail -2
echo "--- no duck threads leak across the full test_daemon run (one-off, in-process) ---"
.venv/bin/python - <<'PY'
import sys, threading
sys.path.insert(0, "tests")
import pytest
rc = pytest.main(["-q", "tests/test_daemon.py", "-x", "-k", "arm"])
import time; time.sleep(0.5)
leaked = [t.name for t in threading.enumerate() if t.name.startswith(("vt-ducking", "vt-duck-heal"))]
assert not leaked, f"leaked duck threads: {leaked}"
print("L3 PASS: no vt-ducking/vt-duck-heal threads after arming tests")
PY
echo "--- the fixture's fail-closed guard still works post-refactor (S1's pin) ---"
timeout 300 .venv/bin/python -m pytest tests/test_key_listener.py -q -k "hermetic_media_fixture" 2>&1 | tail -2
```

### Level 4: Scope + feed_audio edit-only validation

```bash
cd /home/dustin/projects/voice-typing
echo "--- feed_audio: collect + compile only (NEVER run) ---"
timeout 60 .venv/bin/python -m pytest tests/test_feed_audio.py --collect-only -q 2>&1 | tail -2
.venv/bin/python -c "import py_compile; py_compile.compile('tests/test_feed_audio.py', doraise=True); print('L4a PASS: feed_audio compiles')"
echo "--- only the intended files changed ---"
git diff --name-only | grep -vE 'tests/(conftest|test_daemon|test_bulk_dispatch|test_bulk_context_prompt|test_context_prompt_refresh|test_feed_audio)\.py' | grep -E '\.py$|\.toml$|\.md$' && echo "L4 FAIL" || echo "L4b PASS: scope clean"
echo "--- consumers verified edit-free ---"
git diff --name-only | grep -E 'test_session_recovery|test_voicectl_session' && echo "L4 CHECK: consumer edited (only acceptable if a ctor was found)" || echo "L4c PASS: consumers untouched (as expected)"
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: conftest lazy daemon import + hermetic_cfg present; every ctor site wrapped (incl. `_D`); exclusions + `voice_typing/` untouched.
- [ ] L2: test_daemon (235), bulk_dispatch, bulk_context_prompt, context_prompt_refresh, session_recovery, voicectl_session, key_listener, ducking, config all green; ordering probes green.
- [ ] L3: the hermeticity pin green; no vt-ducking/vt-duck-heal threads leak; S1's fail-closed pin still green post-refactor.
- [ ] L4: feed_audio compiles + collects (never run); scope = the 6 intended files; consumers edit-free.

### Feature Validation
- [ ] Every ordinary daemon construction in the repo goes through hermetic cfg or an injected fake; no default-config constructor remains in the migrated files.
- [ ] The construction-time boot-heal read is isolated (private/nonexistent state) for all migrated sites; real-Feedback sites keep their writable tmp state.
- [ ] Dedicated ducking tests + shipped `mpris` default preserved and green.

### Code Quality Validation
- [ ] One wrap pattern everywhere (hermetic_cfg); the fixture delegates rather than duplicating the replace logic.
- [ ] The pin asserts behavior (no ducker, no threads), not just cfg fields.

### Scope Boundary Validation
- [ ] `voice_typing/`, test_ducking.py, test_config.py, test_ime_manager.py, test_voicectl.py, test_control_socket.py untouched.
- [ ] S3's deliverables (wiring pin + ordered subprocess isolation) not pre-written.
- [ ] No autouse, no global subprocess patch, no live arming; two-timeout discipline throughout.

### Documentation & Deployment
- [ ] Local fixture/helper comments accurate (the conftest docstring's S2 note updated if it claims "key-listener only").

---

## Anti-Patterns to Avoid

- ❌ Don't leave the conftest's daemon import at module level — the contract explicitly forbids eager import; move it inside the fixture (Critical #2, the most likely miss).
- ❌ Don't chase the ~149 arm call sites — wrap the cfg at the constructors; that covers every direct/indirect arm path (Critical #4).
- ❌ Don't miss the `_D` alias (test_bulk_context_prompt.py:690/:702) — it is a second constructor (Critical #5).
- ❌ Don't override a real-Feedback site's writable tmp state with the nonexistent default — the state_file precedence (param > non-empty > default) exists precisely to preserve those (Critical #3).
- ❌ Don't mutate the supplied cfg or a production default — `dataclasses.replace` all the way down.
- ❌ Don't make the fixture autouse, patch `subprocess.run` globally, or "fix" ordering by reordering suites — cfg-level isolation + the fail-closed guard are the design.
- ❌ Don't run test_feed_audio.py (edit + collect-only) or the CUDA/forbidden suites; don't foreground the daemon (AGENTS.md).
- ❌ Don't touch test_ime_manager.py (import purity), test_voicectl.py/test_control_socket.py (duck-typed servers), test_ducking.py (intentional real-path), test_config.py (shipped default pin).
- ❌ Don't pre-write S3's wiring pin or ordered-isolation tests — S2's pin is helper-hermeticity only.

---

## Confidence Score

**9/10** for one-pass success. The input contract (S1's landed fixture) is read in full and committed; every constructor site is enumerated with verified line numbers, feedback types, and call-site counts; the exclusion set is verified ctor-free; the two subtle hazards (the eager daemon import in the landed conftest; the `_D` alias) are both identified with their fixes; and the no-ducking-assertions fact makes the blanket wrap provably safe in test_daemon.py. The −1: the 16 direct-ctor sites in test_daemon.py each need a context read (some may use real Feedback or unusual cfg construction — the state-preservation rule handles them, but it's 16 judgment points), plus the pin's attribute names (`_cfg` storage, arm style) must be adapted to the daemon's real surface.
