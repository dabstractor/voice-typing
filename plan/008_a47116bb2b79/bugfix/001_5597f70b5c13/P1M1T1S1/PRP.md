# PRP — P1.M1.T1.S1: Establish a hermetic media fixture at the first-arm seam

## Goal

**Feature Goal**: Kill BUG-001's root cause at the SEAM: create the repo's first `tests/conftest.py` with an opt-in, function-scoped **`hermetic_daemon_media`** fixture that makes any daemon constructed under it structurally incapable of touching the operator's live desktop media bus — a test-owned config helper (`duck_mode='off'` + private state), a fail-closed guard on the daemon's ducker-factory lookup, and function-scoped isolation of the persisted duck-flag read — then migrate the key-listener arming tests that reproduce the bug.

**Deliverable**: Two files:
1. `tests/conftest.py` (NEW) — the `hermetic_daemon_media` fixture (helper callable + fail-closed factory patch + read-flag isolation; use and fake-heal exceptions documented in its docstring).
2. `tests/test_key_listener.py` (MODIFY) — `_wire_daemon`/arming callers migrated to the fixture (incl. the two deterministic repro tests and the one manual `duck_mode="off"` site).

**Success Definition**: (a) the PRD's deterministic cross-file repro (`test_zero_keyboard_warning_fires_once_at_first_arm` + `tests/test_typing_backends.py`) — currently 1 failed 3/3 runs — goes GREEN; (b) under the fixture, an ordinary arm/stop starts neither a `vt-ducking` worker nor a `vt-duck-heal` thread, even if operator state would say `ducked`; (c) unguarded factory use (default `duck_mode='mpris'`, no `ducker=`) fails SYNCHRONOUSLY with a clear error at daemon construction; (d) `tests/test_key_listener.py` fully green; (e) only the two files change.

## User Persona

**Target User**: Every test that constructs a `VoiceTypingDaemon` (S2 migrates the other seven files; S3 pins the dedicated duck-wiring test) — and the operator whose live Brave/MPRIS endpoints must never be paused by a unit suite (PRD R.7: "automation MUST NOT exercise the live desktop").

**Use Case**: A test arms a daemon to assert listener/lifecycle behavior; the fixture guarantees the arm cannot dispatch `busctl --user` at the live session or read/heal the operator's persisted duck flag.

**Pain Points Addressed**: (1) order-dependent cross-file failures (leaked `vt-ducking` worker's `subprocess.run` landing in later tests' recorders); (2) live side effect — the suite pausing the operator's playing media with no resume.

## Why

- **BUG-001 (Major, verified live)**: after the `duck_mode` default flipped to `"mpris"`, daemon-constructing tests that call `_arm()` build a REAL `AsyncDucker(AudioDucker(MprisBusctlBackend))` (daemon.py:1022-1023) and dispatch `_duck_engage()` (daemon.py:1804) → leaked `vt-ducking` worker runs `/usr/bin/busctl --user` against `/run/user/1000/bus` (verified hitting the operator's real Brave MPRIS endpoint). Constructor's boot heal is a second vector: `ducking_heal.read_ducked_flag(cfg)` (daemon.py:810) can independently spawn a `vt-duck-heal` thread (:1029-1037).
- **Fix at the seam, not per-test**: the PRD's own recommendation — "default cfg.audio.duck_mode='off' in shared fixtures (or inject a fake through the existing `ducker=` seam)". A conftest fixture is reusable by S2/S3 without duplicating logic per file.
- **Fail-closed beats fail-open**: masking with a global `subprocess.run` patch is FORBIDDEN (it hides real regressions and recreates recorder pollution ambiguity). The synchronous raise at the factory is the proof — no real media command may ever "prove failure".

## What

Opt-in fixture (NOT autouse): requesting tests get (1) a `hermetic(cfg) -> cfg` helper returning a TEST-OWNED config with `audio.duck_mode="off"` and `feedback.state_file` pointed at a private tmp path (unrelated fields preserved; the supplied config never mutated); (2) `voice_typing.daemon._build_default_ducker` monkeypatched to raise (unguarded factory use fails at construction); (3) `voice_typing.ducking_heal.read_ducked_flag` monkeypatched to an isolated recording fake (invocation-time, not collection-time). Migrate `_wire_daemon`/arming callers in `tests/test_key_listener.py`.

### Success Criteria

- [ ] `tests/conftest.py` exists with the opt-in, function-scoped `hermetic_daemon_media` fixture; docstring documents use + intentional fake-heal exceptions; NOT autouse; no global `subprocess.run` patch.
- [ ] The helper preserves unrelated fields, never mutates its argument or any production default; returns a fresh config (dataclasses `replace`, mirroring the blocklist not-shared discipline).
- [ ] `monkeypatch`ed `_build_default_ducker` raises `AssertionError` naming the fix (inject `ducker=` or use the helper).
- [ ] `read_ducked_flag` fake isolated at fixture invocation (records calls; never consults the real resolved state path).
- [ ] The two arming tests (:459 `test_zero_keyboard_warning_fires_once_at_first_arm`, :477 `test_no_warning_when_keyboards_watched`) and `test_no_warning_before_listener_started` (:492, manual `duck_mode="off"`) migrated; the manual mutation + its noise comment removed.
- [ ] PRD repro pair GREEN; `tests/test_key_listener.py` green under `timeout 300`.

## All Needed Context

### Context Completeness Check

_Pass._ The daemon seam code, the heal vector, the deterministic repro, the `_FakeDucker` pattern, and the affected test sites are verified below with line numbers; the one helper definition the implementer must read at edit time (`_wire_daemon`) is pinned by file + call-signature evidence.

### Verified Current State (re-verified this session)

**The seam (voice_typing/daemon.py):**
- `VoiceTypingDaemon.__init__(..., ducker: Any = None, ...)` (:799). At :1021-1023:
  ```python
  self._ducker: Any = ducker
  if self._ducker is None and cfg.audio.duck_mode != "off":
      self._ducker = _build_default_ducker(cfg)      # ← the factory lookup to guard
  ```
- `_build_default_ducker(cfg)` — module-level (:687). "CONSTRUCTION IS PURE" (no subprocess/thread; the `vt-ducking` worker spawns lazily on first dispatch) — so guarding the factory is enough to make construction+arm hermetic.
- Boot-heal vector: `self._startup_ducked = ducking_heal.read_ducked_flag(cfg)` (:810, module imported as `import voice_typing.ducking_heal as ducking_heal` :187 → attribute lookup at call time, so monkeypatching the module attribute works); if truthy → `vt-duck-heal` thread (:1029-1037).
- `_arm()` → `self._duck_engage()` (:1804); `_duck_engage` (:1681) no-ops when `self._ducker` is None.
- `ducking_heal.read_ducked_flag(cfg)` (ducking_heal.py:50) gates on `cfg.feedback.resolved_state_file()`; swallow-all (missing file → `False`) — pointing `feedback.state_file` at a private nonexistent tmp path also isolates it by config alone; the monkeypatch fake adds invocation-time recording.

**The test seam (tests/test_key_listener.py):**
- `_wire_daemon(cfg=None)` — constructs a daemon with fake recorder/backend/mic (the file's hermetic pattern); called as `_wire_daemon()` and `_wire_daemon(cfg)` (:502, :509). READ its definition before editing (~:380-430).
- Affected sites: `test_zero_keyboard_warning_fires_once_at_first_arm` (:459 — `d._arm()` twice), `test_no_warning_when_keyboards_watched` (:477 — `d._arm()`), `test_no_warning_before_listener_started` (:492-509 — manually sets `cfg.audio.duck_mode = "off"` with a comment acknowledging the busctl noise; the fixture supersedes this).

**The deterministic repro (PRD Steps to Reproduce, 3/3):**
```bash
timeout 300 .venv/bin/pytest tests/test_key_listener.py::test_zero_keyboard_warning_fires_once_at_first_arm tests/test_typing_backends.py -q
# TODAY: 1 failed — test_wtype_passes_check_true (recorder.calls[0] kwargs are the leaked
# busctl call's {'timeout': 1.0, 'check': False, ...} instead of wtype's check=True).
```

**Existing doubles to reuse:** `_FakeDucker` (tests/test_ducking.py:280-305 — engage/release + engage/release counters) is the S3 wiring-test double (NOT needed in S1's migrated tests; their assertions are listener-focused). **No `tests/conftest.py` exists** (verified).

### Documentation & References

```yaml
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/architecture/system_context.md
  why: § BUG-001 — the two live vectors (_build_default_ducker inert-until-_arm; the EARLIER
       read_ducked_flag boot heal that fires independently of arming) + affected test inventory.
- docfile: plan/008_a47116bb2b79/bugfix/001_5597f70b5c13/prd_snapshot.md
  why: h3.0 Issue 1 (the live busctl proof, the repro, the affected files list) + h2.5 first
        recommendation (shared-fixture / ducker= seam approach this PRP implements).
- file: voice_typing/daemon.py
  why: The exact seam to guard (:799 ctor param, :1014-1037 ctor body, :1804 _arm dispatch, :687
        factory, :810 read). READ-ONLY — S1 changes NO production code.
  gotcha: "The factory is only called when ducker is None AND duck_mode != 'off' — the fail-closed
           patch therefore fires exactly on the unguarded case; the helper's duck_mode='off' path
           and explicit ducker= are the sanctioned escapes."
- file: voice_typing/ducking_heal.py
  why: read_ducked_flag (:50) + heal (:84) — the independent boot-heal vector; resolved_state_file
        is the single path source (private state_file ⇒ config-level isolation too).
- file: tests/test_ducking.py
  why: _FakeDucker (:280) documents the duck seam contract (engage/release) for the docstring's
        "intentional fake-heal exceptions" note and S3's wiring pin.
- file: tests/test_key_listener.py
  why: _wire_daemon (the fake recorder/backend/mic seam) + the three sites to migrate (:459/:477/:492).
```

### Current Codebase tree (relevant slice)

```bash
tests/
├── (conftest.py does NOT exist)     # ← CREATE (the fixture)
├── test_key_listener.py             # _wire_daemon + arming sites :459/:477/:492  ← EDIT
├── test_ducking.py                  # _FakeDucker :280 (reference only)
└── test_typing_backends.py          # the repro's downstream victim (READ-ONLY gate)
voice_typing/
├── daemon.py                        # the seam (:799/:1014-1037/:1804/:687/:810)  ← READ-ONLY
└── ducking_heal.py                  # read_ducked_flag :50                        ← READ-ONLY
```

### Desired Codebase tree with files to be changed

```bash
tests/conftest.py          # NEW — hermetic_daemon_media fixture (opt-in, function-scoped)
tests/test_key_listener.py # MODIFY — _wire_daemon + the three arming sites migrated
# NOTHING ELSE. S2 migrates the other seven files; S3 pins the dedicated wiring test; daemon.py untouched.
```

### Known Gotchas of our Codebase & Library Quirks

```python
# CRITICAL #1 — NO PRODUCTION CODE CHANGES. The fixture works entirely through the EXISTING
# seams (ducker= param, cfg.audio.duck_mode, cfg.feedback.state_file, module attributes).
# Editing daemon.py/ducking_heal.py in S1 is a scope violation.

# CRITICAL #2 — OPT-IN, NOT AUTOUSE. hermetic_daemon_media is requested explicitly. Autouse
# would change semantics for suites S2 hasn't migrated (and mask the fail-closed raise as
# collection errors). S2/S3 opt in file-by-file.

# CRITICAL #3 — NEVER GLOBALLY PATCH subprocess.run. The old pollution WAS stray subprocess.run
# traffic; a global patch would hide future real leaks. The synchronous factory raise is the
# only sanctioned proof of failure. Likewise do not patch PATH or the busctl binary.

# CRITICAL #4 — THE HELPER MUST NOT MUTATE. Return a NEW config (dataclasses.replace on the
# top level + the audio and feedback sub-configs — mirror FilterConfig.blocklist's
# default_factory not-shared discipline). A supplied cfg is copied, never edited in place;
# a default VoiceTypingConfig() is never mutated (the :492 test's manual
# cfg.audio.duck_mode = "off" is exactly the pattern to eliminate).

# CRITICAL #5 — ISOLATION AT INVOCATION, NOT COLLECTION. Use the fixture's monkeypatch (function
# scope) for read_ducked_flag — module-level import-time patching would leak across tests and
# defeat the point. monkeypatch (not a bare assignment) guarantees teardown.

# CRITICAL #6 — THE FACTORY PATCH MUST TARGET voice_typing.daemon._build_default_ducker (the
# module attribute the ctor looks up at :1023), not a rebound copy. Same for
# voice_typing.ducking_heal.read_ducked_flag (daemon calls it as ducking_heal.read_ducked_flag —
# module-attribute lookup, :187 import style makes the patch effective).

# GOTCHA #7 — THE 106s/real-model suites are NOT in play here; but keep the AGENTS.md
# two-timeout rule on every pytest run (inner timeout 300 + bash-tool timeout above it).

# GOTCHA #8 — _wire_daemon(cfg=None) is a plain helper, not a fixture: the migrated arming
# tests must REQUEST hermetic_daemon_media and pass the hermetic cfg through (or _wire_daemon
# gains an optional hermetic= parameter defaulting to identity). Keep its fake
# recorder/backend/mic wiring untouched.

# GOTCHA #9 — THE :492 TEST'S CAPLOG ASSERTION. test_no_warning_before_listener_started asserts
# NO WARNING at all — under the helper (duck_mode='off') no ducker exists so no ducking noise:
# the assertion strengthens naturally. Remove the now-obsolete manual-off + comment.
```

## Implementation Blueprint

### Data models and structure

None new — the fixture composes existing dataclasses (`VoiceTypingConfig.audio.duck_mode`, `.feedback.state_file`) via `dataclasses.replace`.

### Implementation Tasks (ordered)

```yaml
Task 0: CONFIRM THE RED (the PRD repro, before any change):
  - RUN: timeout 300 .venv/bin/pytest tests/test_key_listener.py::test_zero_keyboard_warning_fires_once_at_first_arm tests/test_typing_backends.py -q
  - EXPECT: 1 failed (test_wtype_passes_check_true; the leaked busctl kwargs). If green, STOP —
    the tree moved; re-verify anchors before proceeding.

Task 1: CREATE tests/conftest.py — the hermetic_daemon_media fixture.
  - STRUCTURE (adapt to the repo's docstring style):
        import dataclasses
        import pytest
        import voice_typing.daemon as daemon_mod
        import voice_typing.ducking_heal as ducking_heal_mod
        from voice_typing.config import VoiceTypingConfig

        @pytest.fixture
        def hermetic_daemon_media(monkeypatch, tmp_path):
            """Opt-in hermeticity for daemon-constructing tests (BUG-001 / P1.M1.T1.S1).

            USE: request this fixture in any test that constructs a VoiceTypingDaemon and arms it;
            build the daemon's config with the returned helper. Guarantees, for the duration of
            ONE test: (1) no real ducker can be built — voice_typing.daemon._build_default_ducker
            raises, so the ONLY sanctioned escapes are the ducker= injection seam (a fake, cf.
            _FakeDucker in tests/test_ducking.py:280 — the intentional exception for the dedicated
            duck-wiring tests) or duck_mode='off' via this helper; (2) the persisted duck-flag read
            (ducking_heal.read_ducked_flag) is an isolated recording fake — no vt-duck-heal thread
            can start even if the operator's real state would say ducked; (3) the helper's config
            points feedback.state_file at a private nonexistent tmp path (config-level isolation
            belt-and-suspenders). NO global subprocess.run patch: a real media command can never
            'prove' failure — the factory raise is synchronous. NOT autouse: S2 migrates suites
            file-by-file.
            """
            state_path = tmp_path / "state.json"

            def hermetic(cfg: VoiceTypingConfig | None = None) -> VoiceTypingConfig:
                base = cfg if cfg is not None else VoiceTypingConfig()
                return dataclasses.replace(
                    base,
                    audio=dataclasses.replace(base.audio, duck_mode="off"),
                    feedback=dataclasses.replace(base.feedback, state_file=str(state_path)),
                )

            calls: list = []

            def _fake_read_ducked_flag(cfg):
                calls.append(cfg)
                return False  # isolated: never consults cfg.feedback.resolved_state_file()

            monkeypatch.setattr(
                ducking_heal_mod, "read_ducked_flag", _fake_read_ducked_flag,
                raising=True,
            )

            def _fail_closed_factory(cfg):
                raise AssertionError(
                    "hermetic_daemon_media: unguarded _build_default_ducker use — a real ducker "
                    "would dispatch busctl --user at the live session (BUG-001). Inject a fake "
                    "via ducker= (the dedicated duck-wiring tests) or build cfg with this "
                    "fixture's hermetic() helper (duck_mode='off')."
                )

            monkeypatch.setattr(daemon_mod, "_build_default_ducker", _fail_closed_factory,
                                raising=True)
            hermetic.read_calls = calls  # tests may assert the read was consulted/isolated
            return hermetic
  - CONSTRAINTS: opt-in (no autouse); function-scoped monkeypatch/tmp_path only; the helper
    never mutates its argument; preserve every unrelated field (replace, not reconstruct).

Task 2: EDIT tests/test_key_listener.py — migrate the arming seam.
  - READ _wire_daemon's definition first. Give it the hermetic path: EITHER it gains an optional
    `hermetic=None` parameter (identity when None) applied to its cfg before construction, OR the
    migrated tests pass `_wire_daemon(hermetic(...))` explicitly — pick the smaller diff.
  - test_zero_keyboard_warning_fires_once_at_first_arm (:459) and
    test_no_warning_when_keyboards_watched (:477): add the `hermetic_daemon_media` fixture
    parameter; construct via the helper. Their listener assertions are unchanged.
  - test_no_warning_before_listener_started (:492): replace the manual
    `cfg = VoiceTypingConfig(); cfg.audio.duck_mode = "off"` + noise comment with the helper
    (fixture-parameter + `cfg = hermetic()`); the no-WARNING assertion now covers the ducking
    path too.
  - DO NOT touch non-arming tests (they construct but never _arm(); S2 sweeps them wholesale).

Task 3: ADD one hermeticity pin INSIDE test_key_listener.py (small, same seam):
        def test_hermetic_media_fixture_blocks_unguarded_factory(hermetic_daemon_media):
            hermetic = hermetic_daemon_media
            # (a) unguarded default-mpris construction fails SYNCHRONOUSLY at the factory lookup
            with pytest.raises(AssertionError, match="_build_default_ducker"):
                _wire_daemon(VoiceTypingConfig())       # default duck_mode='mpris', no ducker=
            # (b) the helper's config constructs+arms cleanly: no ducker, no heal thread
            d, _fb = _wire_daemon(hermetic())
            d._arm(); d._disarm()
            assert d._ducker is None
            assert not any(t.name == "vt-duck-heal" for t in threading.enumerate())
            assert hermetic_daemon_media.read_calls     # the flag read WAS isolated+consulted
  (adapt to _wire_daemon's real signature; import threading/pytest as the file already does).

Task 4: VERIFY (gates below). No git commit unless the orchestrator directs. If asked:
  "P1.M1.T1.S1: hermetic_daemon_media fixture (conftest) + key-listener arming migration (BUG-001 seam)".
```

### Implementation Patterns & Key Details

```python
# The fixture's correctness rests on THREE structural guarantees, all through existing seams:
#  (1) FACTORY FAIL-CLOSED: daemon.py:1022-1023 calls _build_default_ducker ONLY when
#      (ducker is None AND duck_mode != "off"). Patching the module attribute to raise makes
#      the unguarded case fail AT CONSTRUCTION — before any thread/subprocess can spawn
#      (the factory itself is construction-pure; the worker spawns on first dispatch).
#  (2) READ ISOLATION: daemon.py:810 calls ducking_heal.read_ducked_flag(cfg) via module
#      attribute (:187 import style) — the recording fake (returns False) means
#      self._startup_ducked is always False under the fixture -> no vt-duck-heal thread (:1029).
#  (3) CONFIG ISOLATION: feedback.state_file -> private tmp path means even the un-patched
#      resolved_state_file() resolution (heal's single path source) cannot see operator state.
# Escapes by design: ducker=<fake> (S3's dedicated wiring tests — the docstring's intentional
# exception) and hermetic()'s duck_mode='off' (the ordinary case). Everything else raises.
```

### Integration Points

```yaml
DOWNSTREAM CONSUMERS (NOT S1):
  - P1.M1.T1.S2: migrates the other default-config arm sites (test_bulk_dispatch, test_daemon,
    test_voicectl, test_session_recovery, test_context_prompt_refresh, test_bulk_context_prompt,
    test_ime_manager) onto the SAME fixture — no fixture changes needed (opt-in design).
  - P1.M1.T1.S3: pins default→fake duck wiring + ordered subprocess isolation using ducker=
    with a _FakeDucker (tests/test_ducking.py:280 pattern) — the docstring's sanctioned escape.
PRODUCTION CODE: unchanged. The seams consumed (ducker= param :799, cfg.audio.duck_mode,
cfg.feedback.state_file, module attributes) are exactly the ones the PRD's h2.5 names.
TEST POLLUTION SURFACE: the repro's victim (tests/test_typing_backends.py) needs NO edit —
the leak's SOURCE is eliminated, which is the point (vs. ordering the suites around it).
```

## Validation Loop

> AGENTS.md two-timeout rule on every pytest (inner `timeout 300`, bash-tool timeout above). `.venv/bin/python -m pytest` (repo idiom). No daemon foregrounded; no live arming; no CUDA suites.

### Level 0: RED confirmation (run BEFORE any change)

```bash
cd /home/dustin/projects/voice-typing
timeout 300 .venv/bin/python -m pytest tests/test_key_listener.py::test_zero_keyboard_warning_fires_once_at_first_arm tests/test_typing_backends.py -q 2>&1 | tail -4
# Expected TODAY: 1 failed (test_wtype_passes_check_true — leaked busctl kwargs). This is the bug.
```

### Level 1: The fixture landed correctly (static)

```bash
cd /home/dustin/projects/voice-typing
test -f tests/conftest.py && echo "L1a PASS: conftest exists"
grep -q "def hermetic_daemon_media" tests/conftest.py && echo "L1b PASS: fixture defined"
grep -qE "^@pytest.fixture" tests/conftest.py && ! grep -q "autouse" tests/conftest.py && echo "L1c PASS: opt-in (no autouse)"
grep -q "_build_default_ducker" tests/conftest.py && grep -q "read_ducked_flag" tests/conftest.py && echo "L1d PASS: both guards present"
! grep -qE "subprocess\.run" tests/conftest.py && echo "L1e PASS: no subprocess patch"
grep -c "dataclasses.replace" tests/conftest.py   # expect >=3 (top + audio + feedback)
```

### Level 2: The repro is GREEN + the file is green (the S1 gate)

```bash
cd /home/dustin/projects/voice-typing
echo "--- the PRD repro pair (was 1 failed 3/3) ---"
timeout 300 .venv/bin/python -m pytest tests/test_key_listener.py::test_zero_keyboard_warning_fires_once_at_first_arm tests/test_typing_backends.py -q 2>&1 | tail -3
# Expected: all passed.
echo "--- full key-listener suite (incl. the migrated sites + the new pin) ---"
timeout 300 .venv/bin/python -m pytest tests/test_key_listener.py -q 2>&1 | tail -3
# Expected: all passed.
echo "--- the 8-file batch that was intermittently (2/5) polluted ---"
timeout 300 .venv/bin/python -m pytest tests/test_control_socket.py tests/test_key_listener.py tests/test_typing_backends.py tests/test_textproc.py -q 2>&1 | tail -3
# Expected: all passed (the source leak is gone; ordering can no longer matter).
```

### Level 3: Hermeticity is structural (one-off proof, no live bus)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
# Simulate the fixture by hand (no pytest): unguarded factory raises; hermetic cfg arms clean.
import dataclasses, threading
import voice_typing.daemon as dm
import voice_typing.ducking_heal as dh
from voice_typing.config import VoiceTypingConfig
orig_f, orig_r = dm._build_default_ducker, dh.read_ducked_flag
def boom(cfg): raise AssertionError("unguarded _build_default_ducker")
dm._build_default_ducker = boom
dh.read_ducked_flag = lambda cfg: False
try:
    # (a) default cfg (duck_mode='mpris') + no ducker= -> synchronous raise
    try:
        # minimal ctor context: use the same kwargs the key-listener fakes provide — if the
        # ctor needs more, adapt from tests/test_key_listener.py:_wire_daemon
        raise SystemExit(0)  # placeholder: primary proof lives in the pytest pin (Task 3)
    except AssertionError:
        pass
    cfg = VoiceTypingConfig()
    h = dataclasses.replace(cfg, audio=dataclasses.replace(cfg.audio, duck_mode="off"),
                            feedback=dataclasses.replace(cfg.feedback, state_file="/nonexistent/x.json"))
    assert h.audio.duck_mode == "off" and h is not cfg and cfg.audio.duck_mode == "mpris"
    print("L3 PASS: helper contract (new object, arg untouched, off + private state)")
finally:
    dm._build_default_ducker, dh.read_ducked_flag = orig_f, orig_r
PY
# The full behavioral proof (unguarded ctor raises; arm/disarm spawns no vt-ducking/vt-duck-heal)
# is the Task 3 pytest pin — run it explicitly:
timeout 300 .venv/bin/python -m pytest tests/test_key_listener.py -q -k hermetic_media_fixture 2>&1 | tail -2
```

### Level 4: Scope

```bash
cd /home/dustin/projects/voice-typing
git status --short | grep -vE 'plan/'
git diff --name-only | grep -vE 'tests/conftest\.py|tests/test_key_listener\.py' | grep -E '\.py$|\.toml$' && echo "L4 FAIL: out of scope" || echo "L4 PASS: only conftest.py + test_key_listener.py"
git diff voice_typing/ | grep -q . && echo "L4 FAIL: production code touched" || echo "L4 PASS: voice_typing/ untouched"
```

## Final Validation Checklist

### Technical Validation
- [ ] L0: repro pair RED before the change (the leaked-busctl failure reproduced).
- [ ] L1: conftest exists; fixture opt-in; both guards present; no subprocess patch; replace-based helper.
- [ ] L2: repro pair GREEN; full `test_key_listener.py` green; the multi-file batch green.
- [ ] L3: helper contract proven (new object, argument untouched, `off` + private state); the Task-3 pin passes (unguarded ctor raises; no `vt-ducking`/`vt-duck-heal` threads after arm/disarm).
- [ ] L4: only `tests/conftest.py` + `tests/test_key_listener.py` changed; `voice_typing/` untouched.

### Feature Validation
- [ ] Ordinary arm/stop under the fixture starts neither `vt-ducking` nor `vt-duck-heal`, even if operator state would say ducked.
- [ ] Unguarded factory use fails synchronously with the fix-naming error.
- [ ] The :492 manual `duck_mode="off"` mutation + noise comment eliminated (helper supersedes).
- [ ] Fixture docstring documents use + the intentional `ducker=` fake exception (S3).

### Code Quality Validation
- [ ] Function-scoped monkeypatch/tmp_path only (no import-time, no module-level state).
- [ ] `_wire_daemon`'s fake recorder/backend/mic wiring untouched; minimal diff at the three sites.

### Scope Boundary Validation
- [ ] No production code, no config, no README/ACCEPTANCE changes.
- [ ] S2's files (bulk_dispatch/daemon/voicectl/session_recovery/context_prompt/bulk_context_prompt/ime_manager) NOT pre-migrated; S3's wiring pin NOT pre-written.

---

## Anti-Patterns to Avoid

- ❌ Don't touch `voice_typing/` — the fixture works entirely through the existing `ducker=`/config/module-attribute seams; production edits are a scope violation.
- ❌ Don't make the fixture autouse or patch `subprocess.run` globally — opt-in per file (S2's migration), and the synchronous raise is the only failure proof.
- ❌ Don't mutate the supplied config or a production default in the helper — `dataclasses.replace` all the way down (audio + feedback sub-configs), mirroring the blocklist not-shared discipline.
- ❌ Don't isolate the duck-flag read at collection/import time — monkeypatch inside the fixture (function scope = invocation time), per the contract.
- ❌ Don't patch a rebound copy of the factory or the read — target `voice_typing.daemon._build_default_ducker` and `voice_typing.ducking_heal.read_ducked_flag` module attributes (the call sites look them up at call time).
- ❌ Don't migrate S2's seven files or write S3's wiring pin — only `_wire_daemon` + the three key-listener sites (+ the one hermeticity pin).
- ❌ Don't skip L0 — if the repro is already green the tree moved; re-verify before editing.
- ❌ Don't run the live daemon, arm anything for real, or skip the two-timeout rule on pytest.

---

## Confidence Score

**9.5/10** for one-pass success. Both live vectors are pinned to verified lines (the :1022-1023 factory lookup + :1804 engage; the :810 read + :1029 heal thread), the module-attribute patch points are confirmed effective by the `ducking_heal` import style (:187), the deterministic 3/3 repro doubles as the RED→GREEN oracle, and the escapes (`ducker=` fake, helper `off`) are exactly the PRD's prescribed seams. The −0.5 covers `_wire_daemon`'s exact definition (pinned by call-signature evidence; read before editing) and standard tree-drift on the cited line numbers.
