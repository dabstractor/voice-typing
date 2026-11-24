# Research Note: migrating ordinary daemon constructors + test consumers (P1.M1.T1.S2)

**Status:** EMPIRICALLY VERIFIED against the live repo at HEAD `74252cd` (S1 LANDED and committed — conftest.py exists, test_key_listener.py migrated). All line numbers below verified this session.

## §1. S1's landed contract (the input)

- `tests/conftest.py` — the opt-in, function-scoped `hermetic_daemon_media` fixture returning a `hermetic(cfg=None) -> cfg` helper (dataclasses.replace: `audio.duck_mode="off"` + `feedback.state_file=<fixture tmp path>`), a fail-closed patch of `voice_typing.daemon._build_default_ducker` (raises AssertionError on unguarded use), and a recording fake for `voice_typing.ducking_heal.read_ducked_flag` (returns False; `hermetic.read_calls` exposed).
- `tests/test_key_listener.py` migrated — call style: `_wire_daemon(hermetic_daemon_media())` (the fixture object called → hermetic cfg passed positionally). The :492 manual `duck_mode="off"` site replaced.
- ⚠️ **THE LANDED CONFTEST EAGERLY IMPORTS daemon** (`import voice_typing.daemon as daemon_mod` at module top). The S2 contract mandates "do not eagerly import daemon in conftest" → **S2 must move the daemon + ducking_heal imports INSIDE the fixture body** (invocation-time). Keep `from voice_typing.config import VoiceTypingConfig` at module level (pure dataclasses).

## §2. The migration inventory (verified counts + contexts)

| File | Constructors | Feedback | Migration |
|---|---|---|---|
| tests/test_daemon.py | `_make_daemon` :682 (84 no-cfg + 11 explicit-cfg calls); `_make_daemon_with_feedback` :1932 (REAL Feedback, tmp_path state); `_make_lazy_daemon` :3337; **16 direct ctors** (:689 inside _make_daemon itself, :1287, :1949 inside with_feedback, :2069/:2122/:2147/:2186, :2910/:2923/:2954, :3344 inside lazy, :4104/:4146/:4192/:4238/:4289) | fake (`_DaemonFakeFeedback`) except with_feedback (real, private tmp) | wrap the 3 helpers' cfg + each direct ctor's cfg |
| tests/test_bulk_dispatch.py | 1 ctor :338 (inside a helper taking `cfg`, building `_FakeBundle`) | fake | wrap helper's cfg |
| tests/test_bulk_context_prompt.py | 1 ctor :410 + **the `_D` alias** :690 → `_D(...)` :702 | fake | wrap both |
| tests/test_context_prompt_refresh.py | local `_make_daemon` :158-170 (1 ctor :162; 13 helper calls in-file) | `_FakeFeedback` | wrap helper's cfg |
| tests/test_session_recovery.py | **0 direct ctors** — `import test_daemon as td` (:46) + `import test_bulk_dispatch as tbd` (:45) | — | covered by the td/tbd helper wraps; gate by running green |
| tests/test_voicectl_session.py | **0 direct ctors** — `import test_daemon as td` (:34; `_make_lazy_daemon`, `_fake_host_factory`) | — | covered; gate by running green |
| tests/test_feed_audio.py | 1 ctor :576 (`test_daemon_path_emits_latency_line_and_types_nothing` — real recorder + real run-thread, `_StubFeedback` fake feedback, `_NoopBackend`) | fake (`_StubFeedback`) | wrap cfg :573; **validate via --collect-only ONLY** (real-model suite — never run as CPU validation) |

**Excluded (verified 0 direct ctors / out of scope):** test_voicectl.py (fake server; imports daemon module but never constructs), test_control_socket.py (duck-typed servers), test_ime_manager.py (import-purity coverage — do NOT add daemon imports), test_ducking.py (dedicated intentional ducking tests + `_FakeDucker`), test_config.py (shipped `duck_mode=="mpris"` default pin), tests/g5_timing_lab.py (`build_cfg` already sets duck off privately).

**Arm-path coverage:** isolation at the CFG level covers EVERY arm path — direct `_arm()`, `start()`/`toggle()`, the run-loop lazy first-arm (`_load_host` → `_arm`), socket-driven arms — because `_build_default_ducker` is only called when `duck_mode != "off"` (daemon ctor :1021-1023) and `_duck_engage` no-ops when `self._ducker is None`. Construction-time isolation = the boot-heal read (`ducking_heal.read_ducked_flag`, daemon :810) which resolves `cfg.feedback.resolved_state_file()` — a private/nonexistent path isolates it. **No test in test_daemon.py asserts ducking behavior** (grep `_duck|ducker` in test_daemon.py → EMPTY) — so blanket-wrapping every cfg there cannot break an assertion.

## §3. The design: cfg-level hermeticity by default at the helpers + lazy-import conftest

**conftest.py (minimal S2 adjustments):**
1. **Lazy daemon imports** (the contract mandate): move `import voice_typing.daemon as daemon_mod` + `import voice_typing.ducking_heal as ducking_heal_mod` into the fixture body. Module level keeps only `dataclasses`, `pytest`, `VoiceTypingConfig`.
2. **Add a plain module-level `hermetic_cfg(cfg=None, *, state_file=None) -> VoiceTypingConfig`** (config-only — importable by test modules WITHOUT pulling daemon): `duck_mode="off"` always; `feedback.state_file = state_file` if given, ELSE preserved when the supplied cfg's is non-empty (real-Feedback sites keep their tmp paths), ELSE a nonexistent private default (`tempfile.gettempdir()/vt-hermetic-<pid>-state.json` — missing file ⇒ `read_ducked_flag` swallows to False; fake-feedback sites never write state anyway). The fixture's `hermetic()` delegates to it with `state_file=str(state_path)` — identical behavior, one replace discipline.

**Why a plain function, not the fixture, for the helpers:** `_make_daemon` & co are plain helpers called by ~100 tests; they cannot request fixtures. Wrapping their cfg makes all 84+11+4 call sites hermetic in 3 edits; the per-test fixture stays the fail-closed GUARD (and S3's ordered-isolation surface), not the bulk mechanism. Sibling-import precedent: `import test_daemon as td` works (tests/ on sys.path) ⇒ `from conftest import hermetic_cfg` works.

**test_daemon.py:** `from conftest import hermetic_cfg`; `_make_daemon`: `cfg = cfg or VoiceTypingConfig()` → `cfg = hermetic_cfg(cfg)`; `_make_daemon_with_feedback`: wrap its `VoiceTypingConfig(feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")))` (non-empty state preserved by hermetic_cfg); `_make_lazy_daemon`: `cfg = hermetic_cfg(cfg)`; each of the 16 direct-ctor sites: wrap its cfg (fake-feedback sites take the default nonexistent path; any real-Feedback site keeps its tmp state via preservation).

**One new pin (S2-appropriate, distinct from S3's):** `test_make_daemon_helpers_are_media_hermetic` — `_make_daemon()`/`_make_lazy_daemon()` return daemons with `_ducker is None`, cfg duck off, state private (non-empty, not the OS runtime dir); arm/disarm spawns no `vt-ducking`/`vt-duck-heal` thread. (S3 owns the default→fake duck wiring pin + ordered subprocess isolation — do not duplicate.)

## §4. Validation facts

- The PRD repro pair (key_listener arming test + test_typing_backends.py) is GREEN post-S1 — rerun to confirm the baseline before S2 edits.
- `test_daemon.py` = **235 tests, pure CPU** (mocked CUDA via `_cuda_resolve`; PRD finding #4: it is NOT a real CUDA hang vector) — runs green under `timeout 300` (est. <90 s).
- Ordering probes (the pollution mechanism): `<migrated-file> + tests/test_typing_backends.py` — e.g. `pytest tests/test_daemon.py::<one arming test> tests/test_typing_backends.py -q`.
- test_feed_audio.py: **edit only** — `--collect-only` + `py_compile` (it loads real models; AGENTS.md forbids treating it as a CPU slice).
- Two-timeout rule everywhere; never foreground the daemon; never arm anything live.

## §5. Downstream

- **P1.M1.T1.S3** (default→fake duck wiring + ordered subprocess isolation): consumes S2's safe bounded CPU slices — its ordered-isolation tests need the migrated files to be hermetic so ONLY the intended fake traffic is observable.
- **P1.M1.T3.S1** (classify test_daemon.py as a CPU suite in G1): needs S2's migration done (running the file must be side-effect-free first).
- Shipped defaults preserved: `voice_typing/config.py` + `config.toml` still ship `mpris` (test_config.py pins it); only TEST configs go off.
