# S3 Research Findings — Pin default-to-fake duck wiring and ordered subprocess isolation

## 0. Task restatement (one line)

Add the regression pins that lock BUG-001's fix: (1) ONE dedicated default-config
constructor-to-`_FakeDucker` actuation regression in `tests/test_ducking.py` (patch only the
factory lookup; verify engage/release; zero busctl/wpctl attempts); (2) media-transport
tripwires in `tests/test_typing_backends.py`'s recorder so leaked calls fail loudly instead of
being filtered; (3) the pinned ordering invocation (key-listener arming test BEFORE
typing_backends in ONE bounded run) as the canonical evidence gate — all run under the
two-timeout rule. Production code and shipped defaults untouched.

## 1. Inputs (S1 landed; S2 in flight — the contract chain)

- **S1 (Complete, commit 74252cd)** created `tests/conftest.py` (88 lines, read in full):
  the opt-in `hermetic_daemon_media` fixture — `hermetic(cfg)` helper (duck_mode="off" +
  private tmp state), fail-closed `_build_default_ducker` patch (raises AssertionError),
  `read_ducked_flag` recording fake, `hermetic.read_calls` for assertions. Deliberately NO
  global subprocess patch ("a real media command must never 'prove' failure"). S1 migrated the
  key-listener arming tests; its structural pin is
  `tests/test_key_listener.py::test_hermetic_media_fixture_blocks_unguarded_factory` (:513).
- **S2 (in flight; CONTRACT)** migrates ordinary constructors across 6 files via conftest's
  `hermetic_cfg` (lazy daemon imports inside the fixture). Its exclusions explicitly INCLUDE
  `test_ducking.py` and `test_typing_backends.py` is "GATE ONLY" → **no file collision with S3**.
- **The shipped default stays `mpris`** — pinned by `tests/test_config.py:277-279`
  (`test_duck_mode_...`: `a.duck_mode == "mpris" and a.duck_volume_pct == 15`). S3 must keep
  this pin green and untouched (production media behavior/defaults unchanged).

## 2. The surfaces S3 touches (verified with line numbers)

### 2.1 tests/test_ducking.py (698 lines) — ADD the default-to-fake wiring regression

Existing doubles/tests to RETAIN unchanged (the contract's "retain existing fake lifecycle,
backend and crash-heal coverage"):
- `_FakeBackend` (:31) — backend unit tests :97-234 (engage/release semantics, volume paths,
  failure discipline).
- `_FakeDucker` (:280-306) — thread-safe engage/release call ledger (`calls`, `engages`,
  `releases`). THE wiring double for S3.
- `_DuckingFakeFeedback` (:309) — `_DaemonFakeFeedback` + `set_ducked` recording
  (`ducked_states`).
- `_make_ducking_daemon(cfg=None, *, duck=True)` (:320) — injects `ducker=fake` through the
  CTOR seam (duck=False → no ducker). NOTE: this helper injects via `ducker=`, which SKIPS the
  factory — it does not prove the default-config factory path (that gap is exactly S3's test).
- Lifecycle tests :343-441 (engage-on-arm; release-on-stop/toggle-off/drain/idle-auto-stop/
  halt/quit/dead-host; no-release-on-cancel) — each completes its cycle IN-test (`d.start()`
  then `d.stop()` cleanup) → bounded before mocks unwind.
- `test_ducking_off_mode_no_ducker_zero_calls` (:442) + `test_ducking_default_factory_builds_
  by_mode` (:454 — builds REAL AsyncDucker stacks from `_build_default_ducker` for
  mpris/volume; CONSTRUCTION IS PURE, the `vt-ducking` worker spawns lazily on first dispatch,
  so constructing without dispatching never runs busctl — safe as-is, retained).
- Crash-heal `_HealBackend` tests :565-657 + `_FlushRecordingDucker` shutdown tests :660-698.

The NEW test (place right after `test_ducking_default_factory_builds_by_mode`, ~:491):
- Build a DEFAULT `VoiceTypingConfig()` (duck_mode='mpris' — the shipped default; do NOT
  mutate it to off).
- `monkeypatch.setattr(daemon, "_build_default_ducker", lambda cfg: fake, raising=True)` —
  patch ONLY the factory lookup, so the ctor's REAL wiring path (default cfg → factory call →
  assigned `self._ducker`) is exercised; the factory's RESULT is the fake.
- `monkeypatch.setattr(subprocess, "run", _tripwire)` where the tripwire records argv and
  raises AssertionError (belt-and-suspenders: with the fake injected no transport can run; the
  tripwire PROVES the negative — zero media attempts).
- Construct WITHOUT `ducker=` (unlike `_make_ducking_daemon`), with the standard fakes
  (`_DuckingFakeFeedback`, `_StubRecorder`, `_CtlFakeBackend`, `_ok_probe`).
- Assert: `d._ducker is fake`; `d.start(); d.stop()` → `fake.calls == ["engage", "release"]`;
  `fb.ducked_states == [True, False]`; tripwire attempts list `== []`; no
  `vt-ducking`/`vt-duck-heal` threads in `threading.enumerate()` after the cycle.
- Bounded completion: with the fake, dispatch is synchronous (the `_FakeDucker` docstring
  documents the lock discipline); the whole engage/release cycle completes before the test
  returns — nothing depends on post-teardown activity.

### 2.2 tests/test_typing_backends.py (481 lines) — STRENGTHEN the victims with tripwires

- `class _Recorder` (:44) + the `recorder` fixture (:77) — file-local (not conftest);
  monkeypatches `subprocess.run` for the whole test; records `(argv, kwargs)`.
- The two named BUG-001 victims: `test_wtype_invokes_exact_argv` (:89, asserts
  `recorder.argvs == [...]`) and `test_wtype_passes_check_true` (:94, asserts
  `recorder.calls[0][1].get("check") is True` — the exact assertion the leaked busctl kwargs
  corrupted).
- S3's strengthening (additive, no semantic change to existing assertions):
  (a) fixture-level tripwire — the recorder's fake `subprocess.run` raises AssertionError
  when `argv[0]` in `{"busctl", "wpctl"}` (media transports are never legitimate in this
  file: it tests wtype/ydotool/tmux only). A leaked vt-ducking worker's call now fails LOUDLY
  at invocation (visible in the log even if the worker swallows it).
  (b) explicit zero-media assertions in the two victim tests —
  `assert not any(a[0] in ("busctl", "wpctl") for a in recorder.argvs)` — a test-level
  guarantee independent of the tripwire's in-thread fate.
- This is "real wtype-recorder assertions rather than filtering leaked calls": the ledger is
  never filtered/skipped to find the wtype call; ANY media call is a hard failure.

### 2.3 The pinned ordering invocation (canonical evidence gate)

The BUG-001 deterministic repro (3/3 in the report):
```
timeout 300 .venv/bin/python -m pytest \
  tests/test_key_listener.py::test_zero_keyboard_warning_fires_once_at_first_arm \
  tests/test_typing_backends.py -q
```
- Pytest preserves CLI node order → the arming test runs BEFORE the typing-backends recorder
  tests, reproducing the pollution window exactly.
- **VERIFIED GREEN POST-S1 (this session): 39 passed in 1.04s.** The named test now requests
  `hermetic_daemon_media` (tests/test_key_listener.py:459-461) → no ducker, no worker, no
  busctl → the recorder ledger stays clean.
- The full-file variant (`tests/test_key_listener.py tests/test_typing_backends.py`) needs
  S2's remaining migrations for its OTHER arming tests — S3 runs it as a gate once S2 lands
  (parallel context: assume S2 lands exactly as specified).
- Determinism: the report showed 3/3; run the pin 3x in validation.
- The 8-file intermittent batch from the report is S2/P1.M1.T3.S1 territory (baseline
  classification); S3 pins only the reported deterministic pair.

## 3. Verified baseline (this session, two-timeout rule)

- Canonical ordering pin: **39 passed in 1.04s**.
- `tests/test_ducking.py tests/test_config.py -q`: **100 passed in 0.08s** (includes the
  `mpris` shipped-default pin at test_config.py:277-279 and all lifecycle/backend/heal tests).
- S1's fixture pin `test_hermetic_media_fixture_blocks_unguarded_factory` exists at
  tests/test_key_listener.py:513 (asserts the fail-closed factory raise + no duck threads +
  `hermetic.read_calls` consulted).

## 4. Scope boundaries

- `voice_typing/` READ-ONLY (production media behavior/defaults unchanged — the contract's
  DOCS: none).
- `tests/conftest.py` NOT edited (S1/S2 own it; S3 consumes the fixture as landed/S2-amended).
- `tests/test_config.py` NOT edited (the shipped `mpris` default pin stays untouched-green).
- S2's migration files NOT edited by S3 (no collision; S2's own gates cover them).
- No CUDA/model suites run; `test_feed_audio.py` never run; two timeouts on every pytest;
  never foreground the daemon; never arm live.
- S3's edit set: `tests/test_ducking.py` (one additive test) + `tests/test_typing_backends.py`
  (additive tripwire + two assertions).

## 5. Downstream consumers (why the evidence matters)

- **P1.M1.T3.S1** (classify test_daemon.py as CPU in G1): needs the hermetic suites +
  ordering evidence to record a complete, side-effect-free baseline; S3's pinned invocation is
  the named clean-ordering proof it cites.
- **P1.M2.T3.S2** (README sync): can state that unit suites no longer touch the live media
  bus, backed by S3's tripwires + ordering pin.

## 6. Anti-patterns

- ❌ Don't mutate the default cfg to duck_mode="off" in the new wiring test — the whole point
  is the DEFAULT ('mpris') path through the factory lookup.
- ❌ Don't inject via the `ducker=` ctor seam in the new test — that skips the factory (that's
  `_make_ducking_daemon`'s job, already covered).
- ❌ Don't filter/skip busctl-shaped calls in recorder assertions — tripwire + zero-media
  assertions instead.
- ❌ Don't add a global conftest subprocess patch or PATH shim (S1's design explicitly
  forbids: a real media command must never "prove" failure).
- ❌ Don't reorder suites or mark xfail to "fix" ordering — the pinned invocation must pass on
  real isolation.
- ❌ Don't touch test_config.py's mpris pin or any shipped default.
- ❌ Don't run the CUDA/forbidden suites; always two timeouts.
