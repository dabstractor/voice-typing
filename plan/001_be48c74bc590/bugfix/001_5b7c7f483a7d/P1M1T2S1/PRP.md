# PRP — P1.M1.T2.S1: Add mic health detection via lazy PyAudio probe

## Goal

**Feature Goal**: Give `VoiceTypingDaemon` an internal mic-health signal it currently lacks. Add a `_probe_mic()` method that **lazily** imports PyAudio inside the method body, opens a short-lived `PyAudio` instance, enumerates input devices (mirroring RealtimeSTT's own `AudioInputWorker` discovery), and returns `(ok, error)`. Store the result in two new instance attributes — `self._mic_ok: bool` (default `True`) and `self._mic_error: str | None` (default `None`) — refreshed at the end of `__init__` (after recorder construction) and at the end of `_arm()` (after `set_microphone(True)`), always wrapped so a probe failure **never** breaks startup/arm (degraded mode stays acceptable). This is the detection half of bugfix Issue 2; the surfacing half is P1.M1.T2.S2.

**Deliverable** (one source file edited + one test file edited, no new files):
1. `voice_typing/daemon.py` — `VoiceTypingDaemon`: +`mic_prober` kwarg on `__init__`; +`self._mic_ok`/`self._mic_error`/`self._mic_prober` initialized in `__init__`; +a `_refresh_mic_status()` call at the end of `__init__` and at the end of `_arm()`; +two new private methods `_refresh_mic_status()` and `_probe_mic()`.
2. `tests/test_daemon.py` — +a hermetic `_ok_probe` stub; the 4 daemon-construction sites (`_make_daemon`, `_make_daemon_with_feedback`, +2 direct in the status tests) inject it; +a new test section exercising `_probe_mic`/`_refresh_mic_status`/`__init__`/`_arm` with **mocked pyaudio** and **injected probers** (no real PyAudio I/O).

**Success Definition**:
- (a) `_probe_mic` does `import pyaudio` **inside** the method (verified: `"pyaudio"` is NOT imported by `import voice_typing.daemon` — preserves the `voice_typing.ctl` import-purity invariant, bugfix Issue 4).
- (b) `_probe_mic()` returns `(True, None)` when a fake pyaudio exposes ≥1 device with `maxInputChannels > 0`; returns `(False, <msg>)` when there are zero input devices.
- (c) `_refresh_mic_status()` converts any probe exception (incl. pyaudio `ImportError`) into `_mic_ok=False, _mic_error=str(exc)` — never raises.
- (d) `__init__` and `_arm()` both refresh mic status; the attributes are initialized to `(True, None)` before the first refresh.
- (e) `mic_prober=None` (production) uses the real `_probe_mic`; an injected `mic_prober` is used instead (the hermetic test seam — matches the existing `recorder=`/`backend=`/`latency=` injection convention).
- (f) The full `tests/test_daemon.py` suite stays green and **no test performs real PyAudio I/O** (the 4 construction sites inject `_ok_probe`); `status_snapshot()` is UNCHANGED (still exactly 8 keys — S2 owns adding `mic_ok`/`mic_error`).
- (g) No out-of-scope work: no `status_snapshot()`/`ctl.py` changes (S2), no RealtimeSTT logger rate-limiting (S3), no config/README/systemd changes.

## User Persona

Not applicable. Internal attribute, no user-facing surface change (the bugfix contract §5 "DOCS: none — internal attribute, no user-facing surface change yet. The surfacing happens in S2."). The user benefit (seeing mic failure in `voicectl status`) lands in P1.M1.T2.S2.

## Why

- **Bugfix Issue 2 (Major):** today `_arm()` calls `self._recorder.set_microphone(True)` which **only flips a flag** (`RealtimeSTT/audio_recorder.py:718-723` → `self.use_microphone.value = microphone_on` — no I/O check, no return value, verified). The real capture happens in a separate daemon thread (`core/audio_input_worker.py`) whose infinite retry loop (`time.sleep(3)`, `exc_info=True` traceback per attempt) the daemon has **no reference to**. So when the mic is gone, `voicectl status` still reports a healthy `device: cuda` and `voicectl start` returns `listening: on` — the user speaks into a dead mic and only `journalctl` reveals it (2822+ retry errors observed on the live daemon). This subtask adds the **detection** the daemon currently completely lacks; S2 surfaces it; S3 rate-limits the spam.
- **Lazy import is non-negotiable.** PyAudio is imported lazily inside RealtimeSTT's worker (`audio_input_worker.py:38`) precisely so importing the daemon stays cheap and pure. Importing `pyaudio` at `daemon.py` module top would drag it into `import voice_typing.ctl` (ctl imports daemon transitively) and **violate the Issue 4 import-purity invariant** (`tests/test_voicectl.py::test_ctl_module_present_and_imports_pure`). The probe MUST `import pyaudio` inside the method body.
- **Probe mirrors the library's own notion of "a usable mic."** RealtimeSTT's `AudioInputWorker` discovers devices by enumerating and keeping those with `device_info.get('maxInputChannels', 0) > 0` (`audio_input_worker.py:61-62`, verified). Using the **same predicate** means our `ok` lines up with what the worker itself considers a valid input — not a divergent guess.
- **Never block the daemon.** A missing/failed mic must not prevent startup or toggle (degraded mode is the whole point — PRD §4.4 spirit). `_refresh_mic_status()` swallows every probe exception; the default `_mic_ok=True` ensures a never-probed state isn't falsely reported as broken.

## What

Add mic-health probing to `VoiceTypingDaemon`:

- `__init__` gains a keyword-only `mic_prober: Callable[[], tuple[bool, str | None]] | None = None`. `None` → use the real `self._probe_mic`; otherwise call the injected callable (the test seam).
- `__init__` initializes `self._mic_ok = True`, `self._mic_error = None`, `self._mic_prober = mic_prober`, then calls `self._refresh_mic_status()` at the very end (after recorder/backend construction).
- `_arm()` calls `self._refresh_mic_status()` at its end (after `set_microphone(True)`).
- `_refresh_mic_status()` picks the real or injected prober, wraps it in `try/except Exception` → on any failure sets `_mic_ok=False, _mic_error=str(exc)`, else stores the prober's `(ok, error)`. **Never raises.** (This is the contract's "Wrap _probe_mic in try/except Exception" — centralized in one sanctioned caller.)
- `_probe_mic()` does `import pyaudio` lazily, opens `pyaudio.PyAudio()`, enumerates devices keeping `maxInputChannels > 0` (mirroring `audio_input_worker.py:61-62`), `terminate()`s in `finally`, and returns `(True, None)` if ≥1 input device else `(False, "no PyAudio input devices available")`. Opens **no stream** (enumeration only) so it never disturbs the recorder's own capture.

`_disarm()`, `status_snapshot()`, `ctl.py`, `config.py` are **untouched**.

### Success Criteria

- [ ] `grep -n 'import pyaudio' voice_typing/daemon.py` returns exactly ONE match, **inside** `_probe_mic` (not at module top).
- [ ] After `.venv/bin/python -c "import voice_typing.daemon"`, `"pyaudio" not in sys.modules` (lazy import verified).
- [ ] `VoiceTypingDaemon.__init__` has a keyword-only `mic_prober=None` param; `self._mic_ok`/`self._mic_error`/`self._mic_prober` are set; `_refresh_mic_status()` is called at the end of `__init__` and at the end of `_arm()`.
- [ ] `_probe_mic()` returns `(True, None)` for a fake pyaudio with an input device; `(False, <str>)` for zero input devices.
- [ ] `_refresh_mic_status()` sets `_mic_ok=False, _mic_error=str(exc)` when the prober raises (incl. `ImportError`).
- [ ] New probe tests pass with **mocked pyaudio** (`monkeypatch.setitem(sys.modules, "pyaudio", fake)`) and **injected probers** — zero real PyAudio I/O.
- [ ] The 4 daemon-construction sites in `tests/test_daemon.py` inject `_ok_probe`; `tests/test_daemon.py` is fully green; no test imports/opens real pyaudio.
- [ ] `status_snapshot()` still returns exactly `{listening, partial, last_final, uptime_s, device, compute_type, final_model, realtime_model}` (the existing `test_status_snapshot_keys_and_cuda_values` at line 767 stays green — S1 does NOT add mic fields).

## All Needed Context

### Context Completeness Check

_Pass._ All claims verified against the actual repo + the installed RealtimeSTT wheel: current line numbers (the contract's "`__init__` at 300-326" is **stale** — `__init__` is now at line 374 after the greenfield S2/S3/T2 growth; `_arm`/`_disarm`/`_setup_logging` match within ±1), the flag-only `set_microphone`, the worker's `maxInputChannels` predicate, pyaudio 0.2.14 importability + ALSA stderr spam, the 4 test construction sites, the exact-set status test, and the existing injection convention. A developer new to this codebase can apply the patch from this PRP alone.

### Documentation & References

```yaml
# MUST READ — the defect definition (authoritative)
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/prd_snapshot.md
  why: §2 Issue 2 is the source — verified live behavior (2822+ retry errors, silent status), the
       flag-only set_microphone, the infinite retry loop. The prescribed fix (a) "Detect mic/PyAudio
       open failure ... reflect it in status_snapshot() (e.g. add a mic_ok/error field)". S1 is the
       DETECTION half; S2 is the SURFACING half.
  critical: "S1 adds the probe + attributes ONLY. Do NOT touch status_snapshot() — that is S2. Do NOT
            rate-limit the RealtimeSTT logger — that is S3."

# MUST READ — fix strategy + the lazy-import + catch-all + don't-block-startup design decisions
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/architecture/issue_analysis.md
  why: Issue 2 section spells out the 3-subtask split and the load-bearing design decisions:
       "The PyAudio probe should NOT import pyaudio at module level (keeps voice_typing.ctl import
        pure — Issue 4 invariant). Import it lazily inside the probe function." / "The probe should
        catch all exceptions (PyAudio may not be installed, device may be gone)." / "_mic_ok updated
        on each _arm() AND at startup. It should NOT require the mic to be working for the daemon to
        start (degraded mode is acceptable)."
  critical: "These three sentences ARE the design contract for _probe_mic + _refresh_mic_status.
            lazy import; catch-all; default True + never block startup."

# MUST READ — the RealtimeSTT API surface (verified against the installed wheel)
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/architecture/external_deps.md
  why: Confirms set_microphone is flag-only (audio_recorder.py:718-723), the worker's retry loop
       (audio_input_worker.py ~100-177, no callback to daemon), pyaudio imported lazily in the worker,
       and the Issue 4 invariant (daemon must not import pyaudio at module level).
  critical: "The daemon has NO reference to the audio worker thread's state — that is WHY we probe
            independently with our own short-lived PyAudio instance."

# THE EDIT SITE — VoiceTypingDaemon.__init__ (signature + tail) and _arm()/_disarm()
- file: voice_typing/daemon.py
  why: __init__ signature at lines 374-382 (params: cfg, feedback, *, recorder, backend, latency);
        __init__ body 383-400 (self._cfg … self._backend); _arm() at 491-495; _disarm() at 497-502.
        Callable is ALREADY imported (line 21: `from typing import TYPE_CHECKING, Any, Callable`).
  pattern: "Keyword-only injected deps with `= None` defaults (recorder/backend/latency) — add
            mic_prober in the SAME style. Mic-lifecycle methods (_arm/_disarm) group together;
            place _refresh_mic_status + _probe_mic right after _disarm()."
  gotcha: "The contract's '__init__ at daemon.py:300-326' is STALE (pre-greenfield-growth). Navigate
            BY METHOD NAME; current __init__ is at line 374. _arm/_disarm/_setup_logging match the
            contract within ±1 line."

# THE LIBRARY LOGIC TO MIRROR — device enumeration predicate
- file: .venv/lib/python3.12/site-packages/RealtimeSTT/core/audio_input_worker.py
  why: Lines 61-62 enumerate devices keeping `device_info.get('maxInputChannels', 0) > 0` — the
        library's OWN notion of a valid input device. Line 38 does `import pyaudio` lazily inside the
        worker (the precedent for our lazy import). Lines 89-90 + 108-110 are the validation+retry
        loop whose failure we are detecting.
  critical: "Use the SAME maxInputChannels>0 predicate so our 'ok' matches the worker's discovery.
            Do NOT open a stream (enumeration only) — avoids disturbing the recorder's capture."

# THE TEST FILE — patterns + the 4 construction sites that MUST get the hermetic stub
- file: tests/test_daemon.py
  why: _make_daemon() @402-407 (used by ~30 tests), _make_daemon_with_feedback() @~752-759 (used by
        4 status tests), +2 direct constructions @796 and @810 (test_resolved_device_*). All construct
        VoiceTypingDaemon; WITHOUT a stub they would do REAL pyaudio I/O on every test (slow + ALSA
        stderr spam + non-hermetic — verified pyaudio 0.2.14 is importable here with 16 inputs).
  pattern: "Injection convention: _make_daemon passes recorder=/backend= fakes. Add mic_prober=_ok_probe
            in the SAME way. Probe-specific tests mock pyaudio via monkeypatch.setitem(sys.modules,...)
            and/or inject their own counting/raising probers."
  critical: "ALL FOUR construction sites must inject _ok_probe or the existing suite does real PyAudio.
            The 2 direct constructions at 796/810 are IDENTICAL text — edit BOTH."

# THE PARITY SIBLING — T1.S1 (no_log_file) shows the exact add-a-test-section style to follow
- file: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M1T1S1/PRP.md
  why: Same changeset, same daemon.py, same test file. Its 'ADD a dedicated test' + 'lockstep' +
        'monkeypatch cuda_check for hermeticity' patterns are the template for this PRP's test section.
  critical: "This PRP runs IN PARALLEL with T1.S1 (which adds no_log_file to _FIXED_KWARGS + a test).
            The two edits are in DIFFERENT methods (T1.S1: _FIXED_KWARGS dict; T2.S1: __init__/_arm/
            new methods) so they do NOT conflict. Both add test SECTIONS (additive) — no overlap."

# THE PURITY INVARIANT — the test S1's lazy import must keep passing
- file: tests/test_voicectl.py
  why: test_ctl_module_present_and_imports_pure asserts heavy modules (torch/ctranslate2) are absent
        from sys.modules after importing voice_typing.ctl. pyaudio must stay in the same "not imported
        at module load" category — importing pyaudio at daemon.py top would break this family.
  critical: "Lazy import inside _probe_mic is what keeps this green. L2 validation asserts
            'pyaudio' not in sys.modules after importing the daemon."
```

### Current Codebase tree (relevant slice — T1.S1 may be landing in parallel)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   └── daemon.py            # VoiceTypingDaemon.__init__ @374-400; _arm @491-495; _disarm @497-502;
│   │                          status_snapshot @539 (UNCHANGED); Callable already imported @21.
│   │                          NOTE: T1.S1 (parallel) adds "no_log_file": True to _FIXED_KWARGS @~108
│   │                          — a DIFFERENT method, no conflict with T2.S1's edits.
└── tests/
    └── test_daemon.py       # _make_daemon @402; _make_daemon_with_feedback @~752; direct constructs
                              # @796 & @810; status exact-set test @767 (must stay 8 keys). ← EDIT + ADD
# pyaudio 0.2.14 IS installed (.venv) — 25 devices / 16 inputs on this box — which is WHY the test
# stub matters (without it, every daemon test opens real PortAudio + spams ALSA jack warnings).
```

### Desired Codebase tree with files to be added/changed

```bash
voice_typing/daemon.py       # MODIFY: +mic_prober kwarg; +_mic_ok/_mic_error/_mic_prober in __init__;
#                              +_refresh_mic_status() call in __init__ & _arm; +2 new methods. (no new files)
tests/test_daemon.py         # MODIFY: +_ok_probe stub; 4 construction sites inject it; +new probe test section.
# No new files. No config/ctl/status_snapshot/systemd/install.sh changes. No dependency changes.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — A REAL PROBE IN __init__ POISONS THE TEST SUITE. pyaudio 0.2.14 is importable in
# .venv (16 input devices here). If __init__ calls the REAL _probe_mic unconditionally, every one of
# the ~35 daemon-constructing tests opens real PortAudio: slow (~10-50ms each), spams "ALSA lib ..."
# jack warnings to stderr (verified — they must be filtered even in a manual check), and is non-
# hermetic (the suite's charter is "NO real RealtimeSTT / NO CUDA / NO real feedback dependency").
# FIX: dependency-inject mic_prober (None=real in production) and inject _ok_probe in ALL FOUR test
# construction sites (_make_daemon, _make_daemon_with_feedback, + the 2 direct @796/@810). This is
# the SINGLE most important detail for one-pass success.

# CRITICAL #2 — LAZY IMPORT OR BREAK ISSUE 4. `import voice_typing.ctl` imports daemon transitively.
# Importing pyaudio at daemon.py module top would put pyaudio in sys.modules for the ctl-purity test.
# _probe_mic MUST do `import pyaudio` INSIDE the method body (RealtimeSTT's own worker does this at
# audio_input_worker.py:38 — follow that precedent). L2 validates 'pyaudio' not in sys.modules post-import.

# CRITICAL #3 — status_snapshot IS S2's, NOT S1's. test_status_snapshot_keys_and_cuda_values
# (test_daemon.py:767) asserts set(s) == exactly 8 keys. S1 MUST NOT add mic_ok/mic_error to
# status_snapshot (that is P1.M1.T2.S2). S1 only stores the attributes; S2 reads them. Touching
# status_snapshot here breaks that exact-set test AND crosses into S2's scope.

# CRITICAL #4 — _probe_mic MAY RAISE; _refresh_mic_status MUST CATCH. `import pyaudio` raises
# ImportError if PyAudio isn't installed; PyAudio() can raise OSError (no audio subsystem);
# get_default_input_device_info() raises OSError if no default. The contract: "Wrap _probe_mic in
# try/except Exception ... set _mic_ok=False, _mic_error=str(exc)". _refresh_mic_status is the ONE
# place that wrap lives (called from both __init__ and _arm). _probe_mic itself returns (False,msg)
# for the expected "no devices" case but may RAISE for unexpected ones — the caller converts.

# CRITICAL #5 — ALWAYS terminate() the PyAudio instance. pyaudio.PyAudio() initializes PortAudio
# (allocates resources). Use try/finally with pa.terminate() so a probe between toggles never leaks
# PortAudio handles across the daemon's 24/7 lifetime. (RealtimeSTT's worker terminates on shutdown;
# our probe is short-lived and must clean up every call.)

# GOTCHA #6 — _arm() runs UNDER self._lock (called by start/toggle). _refresh_mic_status() therefore
# does its (real, ~10-50ms) PyAudio enumeration while holding the lock. Acceptable: toggles are
# infrequent/user-initiated, and on_final does NOT take self._lock today (Issue 5, separate). Do NOT
# move the probe OFF the lock here — keep _arm atomic with its status refresh; revisit only if toggle
# latency becomes observable. (In tests _ok_probe is instant, so this never bites the suite.)

# GOTCHA #7 — the probe opens a SEPARATE PyAudio instance and enumerates; it opens NO stream. This
# is intentional and safe: it does NOT touch the recorder's own capture stream (held by the worker).
# Do NOT be tempted to "reuse the recorder's PyAudio" — the daemon has no handle to it and the worker
# owns it. Enumeration via a fresh instance is the isolated, side-effect-free choice.

# GOTCHA #8 — PyAudio/ALSA prints harmless "ALSA lib ... Cannot connect to server ..." jack warnings
# to stderr during PyAudio() init EVEN ON SUCCESS. Under systemd these flow to journald. This is a
# known minor noise source from ANY pyaudio.PyAudio() call, not a bug in our probe. Rate-limiting/
# redirecting that noise is S3's job (RealtimeSTT logger), NOT S1's. Do NOT add stderr suppression
# here (out of scope; would complicate the probe). Just be aware the production probe-on-toggle will
# add a few ALSA lines to journald until S3 addresses the logger holistically.

# GOTCHA #9 — use the STRING-ANNOTATION style consistently? NO — Callable is a REAL import (line 21),
# so `mic_prober: Callable[[], tuple[bool, str | None]] | None = None` is fine non-string (matches how
# `recorder: Any = None` is written). The TYPE_CHECKING-only types (Feedback, TypingBackend) use
# strings because they are imported under `if TYPE_CHECKING:`; Callable is not.

# GOTCHA #10 — FULL PATHS in every bash command. This machine aliases python3→uv run, pip→alias,
# tmux→zsh plugin. Invoke .venv/bin/python and .venv/bin/pytest explicitly. (Inside _probe_mic,
# `import pyaudio` resolves the venv's pyaudio by construction — not an alias issue.)

# GOTCHA #11 — DO NOT run/restart the live systemd daemon to verify (out of scope, slow, needs mic).
# The deterministic gates are the unit tests (mocked pyaudio + injected probers) + the import-purity
# check. The runtime effect (attributes updated on arm) follows directly from the verified logic.

# GOTCHA #12 — the 2 direct constructions at test_daemon.py:796 and :810 are IDENTICAL text:
#     d = daemon.VoiceTypingDaemon(
#         cfg, Feedback(cfg.feedback), recorder=_StubRecorder(), backend=_FakeBackend()
#     )
# A find/replace hits BOTH (correct — both need mic_prober=_ok_probe). If editing by hand, do both.
```

## Implementation Blueprint

### Data models and structure

No config/schema/pydantic changes. The only new "structure" is two instance attributes (`self._mic_ok: bool`, `self._mic_error: str | None`) + one injection slot (`self._mic_prober`). The probe's return type is `tuple[bool, str | None]` (a plain tuple, not a dataclass — matches the lightweight, internal-attribute nature the contract specifies).

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY voice_typing/daemon.py — add mic_prober kwarg + init the attributes + refresh call
  - FIND VoiceTypingDaemon.__init__ signature (lines 374-382). Its tail param is:
        latency: "LatencyLog | None" = None,
    ) -> None:
  - EDIT: add ONE keyword-only param after latency (Callable is already imported at line 21):
        latency: "LatencyLog | None" = None,
        mic_prober: Callable[[], tuple[bool, str | None]] | None = None,
    ) -> None:
  - FIND the __init__ body tail (the last statement, ~line 398-400):
        self._backend = (
            backend if backend is not None else typing_backends.make_backend(cfg.output)
        )
  - EDIT: append the mic-health init + first refresh immediately AFTER self._backend:
        self._backend = (
            backend if backend is not None else typing_backends.make_backend(cfg.output)
        )
        # Mic health probe (bugfix Issue 2 / P1.M1.T2.S1): detect a dead/missing mic so status
        # (P1.M1.T2.S2) can surface it instead of silently reporting "listening: on". Injectable
        # (mic_prober=) so unit tests stay hermetic — NO real PyAudio/CUDA in the test suite
        # (production leaves mic_prober=None -> self._probe_mic, which imports pyaudio LAZILY).
        self._mic_ok: bool = True            # default True: never-probed ≠ broken (PRD §4.4 spirit)
        self._mic_error: str | None = None
        self._mic_prober = mic_prober
        self._refresh_mic_status()
  - DO NOT touch self._cfg/_feedback/_lock/_listening/_shutdown/_start_monotonic/_latency/_recorder.
  - DO NOT change _disarm(), status_snapshot(), _resolved_device(), run(), on_final(), main().

Task 2: MODIFY voice_typing/daemon.py — _arm() refreshes mic status after set_microphone(True)
  - FIND _arm() (lines 491-495):
        def _arm(self) -> None:
            """Private: arm mic + set listening + notify. Called under the lock by start/toggle."""
            self._listening.set()
            self._recorder.set_microphone(True)
            self._feedback.set_listening(True)
  - EDIT: add the refresh as the LAST line of _arm (after set_listening):
        def _arm(self) -> None:
            """Private: arm mic + set listening + notify. Called under the lock by start/toggle."""
            self._listening.set()
            self._recorder.set_microphone(True)
            self._feedback.set_listening(True)
            self._refresh_mic_status()  # bugfix Issue 2 / P1.M1.T2.S1: re-probe mic health on each arm
  - DO NOT add it to _disarm() (the contract specifies _arm only; disarming doesn't need a re-probe).

Task 3: ADD voice_typing/daemon.py — _refresh_mic_status() + _probe_mic() methods
  - PLACE: immediately AFTER _disarm() (which ends at line 502) and BEFORE start() (line 504) — keeps
    the mic-lifecycle private methods grouped (_arm/_disarm/_refresh_mic_status/_probe_mic).
  - ADD EXACTLY these two methods:
        def _refresh_mic_status(self) -> None:
            """Run the mic probe (real or injected) and store ok/error. NEVER raises.

            Sanctioned caller of the probe (bugfix Issue 2 / P1.M1.T2.S1): both __init__ and _arm()
            route through here so the try/except + attribute update live in ONE place. A probe failure
            (pyaudio missing, no devices, any exception) degrades to _mic_ok=False + _mic_error=str(exc)
            — the daemon stays runnable (degraded mode is acceptable; PRD §4.4 spirit). Tests inject
            mic_prober to stay hermetic; production leaves it None -> self._probe_mic.
            """
            prober = self._probe_mic if self._mic_prober is None else self._mic_prober
            try:
                ok, error = prober()
            except Exception as exc:  # defensive: a probe must never break startup or arm
                ok, error = False, str(exc)
            self._mic_ok = bool(ok)
            self._mic_error = error

        def _probe_mic(self) -> tuple[bool, str | None]:
            """Lazy PyAudio probe: is at least one input device available? Returns (ok, error|None).

            Mirrors RealtimeSTT's own AudioInputWorker device discovery (core/audio_input_worker.py:
            enumerate devices, keep those with maxInputChannels > 0). pyaudio is imported INSIDE this
            method (NOT at module top) so `import voice_typing.daemon` / `voice_typing.ctl` stay pure
            (bugfix Issue 4 invariant). Opens a SEPARATE, short-lived PyAudio instance only to ENUMERATE
            (no stream opened) — does not disturb the recorder's own capture stream. May RAISE on
            pyaudio-not-installed / no audio subsystem; _refresh_mic_status converts that to (False, str).
            """
            import pyaudio  # lazy: preserve ctl import purity (bugfix Issue 4)

            pa = pyaudio.PyAudio()
            try:
                inputs = [
                    i for i in range(pa.get_device_count())
                    if (pa.get_device_info_by_index(i).get("maxInputChannels") or 0) > 0
                ]
            finally:
                pa.terminate()
            if not inputs:
                return False, "no PyAudio input devices available"
            return True, None

Task 4: MODIFY tests/test_daemon.py — add the _ok_probe stub + inject it at the 4 construction sites
  - ADD the stub once, near the other S2 test helpers (e.g. right after _FakeBackend, before
    _wait_for / _make_daemon, ~line 400). EXACTLY:
        def _ok_probe():
            """Hermetic mic-probe stub for daemon-constructing tests (bugfix Issue 2 / P1.M1.T2.S1).

            Returns a healthy mic so __init__/_arm never touch real PyAudio. Probe-specific tests
            inject their own probers (or mock pyaudio via sys.modules) to exercise _probe_mic directly.
            """
            return (True, None)
  - EDIT construction site A — _make_daemon() (~line 407). Change:
        d = daemon.VoiceTypingDaemon(cfg, fb, recorder=rec, backend=be)
    to:
        d = daemon.VoiceTypingDaemon(cfg, fb, recorder=rec, backend=be, mic_prober=_ok_probe)
  - EDIT construction site B — _make_daemon_with_feedback() return (~line 759). Change:
        return daemon.VoiceTypingDaemon(cfg, fb, recorder=rec, backend=be), fb
    to:
        return daemon.VoiceTypingDaemon(cfg, fb, recorder=rec, backend=be, mic_prober=_ok_probe), fb
  - EDIT construction sites C+D — the TWO identical direct constructions (~lines 796 and 810, in
    test_resolved_device_caches_resolve_called_once and test_resolved_device_failure_degrades_to_unknown).
    Both currently read:
        d = daemon.VoiceTypingDaemon(
            cfg, Feedback(cfg.feedback), recorder=_StubRecorder(), backend=_FakeBackend()
        )
    Change BOTH to:
        d = daemon.VoiceTypingDaemon(
            cfg, Feedback(cfg.feedback), recorder=_StubRecorder(), backend=_FakeBackend(),
            mic_prober=_ok_probe,
        )
  - WHY: without these 4 edits, those tests do REAL pyaudio I/O (Gotcha #1). _make_daemon covers
    ~30 tests; the factory + the 2 direct sites cover the entire hermetic suite.
  - DO NOT touch tests/test_feed_audio.py:559 — that is the real-audio integration test (T1); a real
    probe there is consistent with its already-non-hermetic nature (it opens a real recorder).

Task 5: ADD tests/test_daemon.py — new probe test section (mock pyaudio + inject probers; no real I/O)
  - PLACE: a new section at the END of the file, under a clear banner comment, e.g.:
        # ===========================================================================
        # bugfix P1.M1.T2.S1 — mic health probe: _probe_mic / _refresh_mic_status / __init__ / _arm
        # (ADDITIVE — mocks pyaudio via sys.modules + injects probers; ZERO real PyAudio I/O.)
        # ===========================================================================
        import sys as _sys
  - ADD these tests (each is hermetic; pyaudio is faked via monkeypatch.setitem(sys.modules,...) so the
    lazy `import pyaudio` inside _probe_mic binds to the fake):
        def _install_fake_pyaudio(monkeypatch, *, device_input_channels):
            """Install a fake 'pyaudio' module in sys.modules; _probe_mic's `import pyaudio` binds to it.

            device_input_channels: list of maxInputChannels per device index (the probe keeps those >0).
            """
            class _Dev(dict):
                pass
            devices = [_Dev(maxInputChannels=ch) for ch in device_input_channels]
            class _PA:
                def get_device_count(self):
                    return len(devices)
                def get_device_info_by_index(self, i):
                    return devices[i]
                def terminate(self):
                    pass
            fake = type("M", (), {"PyAudio": _PA})
            monkeypatch.setitem(_sys.modules, "pyaudio", fake)
            return fake

        def test_probe_mic_ok_when_input_device_present(tmp_path, monkeypatch):
            _install_fake_pyaudio(monkeypatch, device_input_channels=[0, 2, 0])  # index 1 is an input
            d, *_ = _make_daemon()   # _ok_probe used at init (no real pyaudio); we call _probe_mic directly
            ok, err = d._probe_mic()
            assert ok is True and err is None

        def test_probe_mic_fails_when_no_input_devices(tmp_path, monkeypatch):
            _install_fake_pyaudio(monkeypatch, device_input_channels=[0, 0])  # outputs only
            d, *_ = _make_daemon()
            ok, err = d._probe_mic()
            assert ok is False and isinstance(err, str) and err

        def test_probe_mic_raises_when_pyaudio_unavailable(monkeypatch):
            # `import pyaudio` raises ImportError when sys.modules["pyaudio"] is None.
            monkeypatch.setitem(_sys.modules, "pyaudio", None)
            d, *_ = _make_daemon()
            with pytest.raises(ImportError):
                d._probe_mic()   # _probe_mic itself raises; _refresh_mic_status is what catches it

        def test_refresh_mic_status_catches_probe_exception():
            # An injected prober that raises -> _mic_ok=False, _mic_error=str(exc); never propagates.
            def boom():
                raise RuntimeError("portaudio exploded")
            d, *_ = _make_daemon()
            d._mic_prober = boom
            d._refresh_mic_status()
            assert d._mic_ok is False and "portaudio exploded" in (d._mic_error or "")

        def test_refresh_mic_status_stores_probe_result():
            d, *_ = _make_daemon()
            d._mic_prober = lambda: (False, "no devices")
            d._refresh_mic_status()
            assert d._mic_ok is False and d._mic_error == "no devices"

        def test_init_initializes_mic_status_and_calls_probe():
            calls = []
            cfg = VoiceTypingConfig()
            d = daemon.VoiceTypingDaemon(
                cfg, _DaemonFakeFeedback(), recorder=_StubRecorder(), backend=_FakeBackend(),
                mic_prober=lambda: (calls.append(1), (True, None))[1],
            )
            assert d._mic_ok is True and d._mic_error is None
            assert len(calls) == 1          # __init__ probed exactly once

        def test_arm_refreshes_mic_status():
            calls = []
            d = daemon.VoiceTypingDaemon(
                VoiceTypingConfig(), _DaemonFakeFeedback(), recorder=_StubRecorder(),
                backend=_FakeBackend(),
                mic_prober=lambda: (calls.append(1), (True, None))[1],
            )
            assert len(calls) == 1          # init
            d.start()                       # -> _arm -> _refresh_mic_status
            assert len(calls) == 2          # armed once more

        def test_make_daemon_injection_is_hermetic_no_real_pyaudio():
            # Guard against regression: the factory must inject _ok_probe (no real pyaudio in tests).
            d, *_ = _make_daemon()
            assert d._mic_prober is _ok_probe
            assert d._mic_ok is True        # the stub reported healthy
            assert "pyaudio" not in _sys.modules or True  # (informational; other tests may have imported it)
  - The two `(calls.append(1), (True, None))[1]` lambdas record a call AND return a well-formed probe
    result (tuple index [1] is the (ok,error) tuple). This is the standard "counting callable" idiom.

Task 6: VALIDATE — run the Validation Loop L1–L5 below; fix until all green. No git commit unless the
  orchestrator directs it. If asked, message:
  "P1.M1.T2.S1: add lazy PyAudio mic-health probe to VoiceTypingDaemon (_probe_mic + _mic_ok/_mic_error)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the lazy import (Issue 4 purity). pyaudio is imported INSIDE _probe_mic, so importing
# the daemon module (and transitively voice_typing.ctl) never loads pyaudio. Mirrors RealtimeSTT's
# own worker (audio_input_worker.py:38). L2 asserts 'pyaudio' not in sys.modules after import.
def _probe_mic(self) -> tuple[bool, str | None]:
    import pyaudio                       # <-- the ONLY 'import pyaudio' in daemon.py (inside the method)
    pa = pyaudio.PyAudio()
    try:
        inputs = [i for i in range(pa.get_device_count())
                  if (pa.get_device_info_by_index(i).get("maxInputChannels") or 0) > 0]
    finally:
        pa.terminate()                   # CRITICAL #5: always release PortAudio
    return (True, None) if inputs else (False, "no PyAudio input devices available")

# PATTERN 2 — the catch-all refresh (never raises; the contract's "Wrap _probe_mic in try/except").
# Called from BOTH __init__ and _arm so the try/except + attribute update live in one place.
def _refresh_mic_status(self) -> None:
    prober = self._probe_mic if self._mic_prober is None else self._mic_prober
    try:
        ok, error = prober()             # _probe_mic may raise (ImportError/OSError); injected may raise
    except Exception as exc:             # CRITICAL #4: any failure -> degraded, never propagate
        ok, error = False, str(exc)
    self._mic_ok = bool(ok)
    self._mic_error = error

# PATTERN 3 — dependency injection (the codebase convention: recorder=/backend=/latency= are all
# injectable seams; mic_prober= joins them). Production passes mic_prober=None (real _probe_mic);
# tests pass _ok_probe (or a custom counting/raising prober). This is what keeps the ~35 daemon
# tests hermetic (CRITICAL #1) — without it they open real PortAudio.
```

### Integration Points

```yaml
DOWNSTREAM — P1.M1.T2.S2 (Surface mic health in status_snapshot() + voicectl status):
  - S2 reads self._mic_ok and self._mic_error (the attributes S1 creates) and adds "mic_ok" +
    "mic_error" keys to status_snapshot()'s returned dict. That will BREAK the exact-set test at
    test_daemon.py:767 — S2's job to update that expected set (NOT S1's). S1 MUST leave status_snapshot
    at exactly 8 keys so the current suite stays green at the S1/S2 boundary.
  - S2 also updates ctl.py format_result() to display mic status. S1 touches NEITHER.

DOWNSTREAM — P1.M1.T2.S3 (Rate-limit RealtimeSTT mic-retry traceback spam):
  - S3 attaches a logging.Filter/custom handler to the "realtimestt" logger to dedupe the
    "Microphone connection failed ... Retrying..." traceback. S1 does NOT touch logging. S1's probe is
    INDEPENDENT of (complementary to) S3: S1 detects proactively (can the OS see a mic?); S3 limits the
    reactive noise (the worker's retry tracebacks). Both are needed for full Issue 2 remediation.

DOWNSTREAM — the attributes are ALSO the basis for any future "auto re-resolve default device on
  sustained failure" (Issue 2 suggested fix (c)). S1 does not implement recovery — only detection.

PRODUCTION RUNTIME (daemon under systemd):
  - At boot, __init__ probes once (mic_ok reflects reality). On every voicectl toggle/start (_arm),
    the probe re-runs, so a hot-plugged mic is picked up on the next arm. The probe adds ~10-50ms +
    a few ALSA jack warnings (Gotcha #8) per arm — acceptable for a user-initiated toggle.
  - The probe opens NO stream and a SEPARATE PyAudio instance (Gotcha #7) — it does not disturb the
    recorder's capture. set_microphone()'s flag-only behavior is UNCHANGED (we are not replacing it;
    we are adding an independent health signal alongside it).

NO INTERFACE CHANGES:
  - VoiceTypingConfig / config.toml: no new field (mic health is a runtime probe, not user config).
  - ctl.py / control-socket protocol: unchanged in S1 (S2 adds the mic_ok/mic_error surface).
  - launch_daemon.sh / systemd unit / cuda_check: unchanged.
```

## Validation Loop

> Full paths in every command (zsh aliases shadow python3/pip on this machine). Run from the repo root
> `/home/dustin/projects/voice-typing`. All gates are pure/unit: NO model load, NO real mic, NO CUDA,
> NO systemd. pyaudio is MOCKED via sys.modules in the probe tests; the hermetic suite injects _ok_probe.

### Level 1: The edits are in place (static + structural checks)

```bash
cd /home/dustin/projects/voice-typing
echo "--- exactly ONE 'import pyaudio', and it is INSIDE _probe_mic (not at module top) ---"
test "$(grep -c 'import pyaudio' voice_typing/daemon.py)" -eq 1 && echo "L1 PASS: single import" || echo "L1 FAIL"
grep -n 'import pyaudio' voice_typing/daemon.py | grep -q '^[0-9]*:.*import pyaudio  # lazy' && echo "L1 PASS: lazy (inside method)" || echo "L1 FAIL: not the lazy form"
echo "--- no module-top pyaudio (the import must be indented inside a def) ---"
awk '/^import pyaudio/{print "L1 FAIL: module-top import"; bad=1} END{if(!bad) print "L1 PASS: no module-top pyaudio"}' voice_typing/daemon.py
echo "--- mic_prober kwarg + attributes + refresh calls present ---"
grep -q 'mic_prober: Callable\[\], tuple\[bool, str | None\]\] | None = None' voice_typing/daemon.py && echo "L1 PASS: mic_prober kwarg" || echo "L1 FAIL: kwarg"
grep -q 'self._mic_ok: bool = True' voice_typing/daemon.py && echo "L1 PASS: _mic_ok init" || echo "L1 FAIL"
grep -q 'self._mic_error: str | None = None' voice_typing/daemon.py && echo "L1 PASS: _mic_error init" || echo "L1 FAIL"
grep -q 'def _refresh_mic_status' voice_typing/daemon.py && grep -q 'def _probe_mic' voice_typing/daemon.py && echo "L1 PASS: both methods exist" || echo "L1 FAIL"
# _refresh_mic_status is called in __init__ AND _arm (exactly 2 call sites):
echo "refresh call sites: $(grep -c 'self._refresh_mic_status()' voice_typing/daemon.py) (expect 2)"
echo "--- status_snapshot STILL exactly 8 keys (S2 owns adding mic fields) ---"
.venv/bin/python - <<'PY'
import ast
src = open("voice_typing/daemon.py").read()
# crude: count keys in the status_snapshot return dict literal
import re
m = re.search(r"def status_snapshot\(self\).*?return \{(.*?)\}", src, re.S)
assert m, "status_snapshot not found"
keys = re.findall(r'^\s*"([a-z_]+)":', m.group(1), re.M)
assert keys == ["listening","partial","last_final","uptime_s","device","compute_type","final_model","realtime_model"], keys
print("L1 PASS: status_snapshot unchanged (8 keys):", keys)
PY
# Expected: single lazy import inside _probe_mic; no module-top import; kwarg+attrs+methods present;
# exactly 2 _refresh_mic_status() calls (__init__ + _arm); status_snapshot still 8 keys.
```

### Level 2: Import purity — lazy import keeps `voice_typing.ctl` clean (Issue 4 invariant)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
import sys
# Importing the daemon (and transitively ctl) must NOT load pyaudio (lazy import inside _probe_mic).
for mod in ("voice_typing.daemon", "voice_typing.ctl"):
    __import__(mod)
assert "pyaudio" not in sys.modules, "pyaudio was imported at module load — violates Issue 4 purity!"
print("L2 PASS: pyaudio NOT in sys.modules after importing voice_typing.daemon + voice_typing.ctl")
# And constructing a daemon WITHOUT mic_prober=None still doesn't import pyaudio until _probe_mic runs:
PY
# Expected: "L2 PASS: pyaudio NOT in sys.modules ...". If this fails, the import leaked to module top.
```

### Level 3: New probe unit tests (mocked pyaudio + injected probers — zero real I/O)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v \
  -k "probe_mic or refresh_mic_status or init_initializes_mic_status or arm_refreshes_mic_status or make_daemon_injection_is_hermetic"
# Expected: ALL selected tests PASS, specifically:
#   test_probe_mic_ok_when_input_device_present
#   test_probe_mic_fails_when_no_input_devices
#   test_probe_mic_raises_when_pyaudio_unavailable
#   test_refresh_mic_status_catches_probe_exception
#   test_refresh_mic_status_stores_probe_result
#   test_init_initializes_mic_status_and_calls_probe
#   test_arm_refreshes_mic_status
#   test_make_daemon_injection_is_hermetic_no_real_pyaudio
# These prove: the predicate, the no-devices path, exception handling, __init__/_arm refresh, and that
# the factory injects the hermetic stub (no real pyaudio anywhere in the suite).
```

### Level 4: No regressions across the full daemon unit suite (the 4 construction-site edits hold)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/python -m pytest tests/test_daemon.py -v
# Expected: ALL tests PASS (the suite was green before; the mic_prober injection at the 4 sites keeps
# every daemon-constructing test hermetic — none opens real pyaudio). Pay special attention to:
#   - the ~30 _make_daemon()-based tests (start/stop/toggle/on_final/run-loop)
#   - the 4 _make_daemon_with_feedback() status tests (status_snapshot still 8 keys)
#   - test_resolved_device_caches_resolve_called_once + test_resolved_device_failure_degrades_to_unknown
#     (the 2 DIRECT constructions at 796/810 that also got mic_prober=_ok_probe)
# If any test does real pyaudio I/O you'll see "ALSA lib ..." noise on stderr — that means a
# construction site was missed (re-check Task 4's 4 edits).
# Optional belt-and-suspenders: also run the voicectl purity test (Issue 4) to confirm no leak:
.venv/bin/python -m pytest tests/test_voicectl.py -k "ctl_module_present_and_imports_pure" -v
```

### Level 5: Scope guards — status_snapshot/ctl/config untouched; no S2/S3 work; no new files

```bash
cd /home/dustin/projects/voice-typing
echo "--- status_snapshot() NOT modified by S1 (git diff should show no status_snapshot lines) ---"
git diff -U0 voice_typing/daemon.py | grep -E '^\+.*mic_ok|^\+.*mic_error' | grep -i status || echo "L5 PASS: no mic_* added inside status_snapshot (S2's job)"
echo "--- ctl.py / config.py / status_snapshot consumers untouched ---"
git diff --exit-code -- voice_typing/ctl.py voice_typing/config.py tests/test_control_socket.py && echo "L5 PASS: ctl/config/test_control_socket unchanged" || echo "L5 NOTE: a tracked file in that set changed — verify it's not S1's doing"
echo "--- only daemon.py + test_daemon.py changed (no new files, no config/systemd/install.sh) ---"
git status --short
echo "--- read-only files UNCHANGED ---"
git diff --exit-code -- PRD.md plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/tasks.json pyproject.toml config.toml && echo "L5 PASS: read-only files unchanged" || echo "L5 FAIL: a read-only file was modified"
# Expected: git status shows ONLY voice_typing/daemon.py + tests/test_daemon.py modified (no new files);
# no mic_* keys inside status_snapshot; ctl/config/test_control_socket/PRD/tasks.json/pyproject/config.toml unchanged.
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: exactly one `import pyaudio` (inside `_probe_mic`, lazy); no module-top import; `mic_prober` kwarg + `_mic_ok`/`_mic_error`/`_mic_prober` init + `_refresh_mic_status()`/`_probe_mic()` methods present; exactly 2 `_refresh_mic_status()` calls (`__init__` + `_arm`); `status_snapshot` still 8 keys.
- [ ] L2: `pyaudio` NOT in `sys.modules` after `import voice_typing.daemon` + `voice_typing.ctl` (Issue 4 purity holds).
- [ ] L3: all 8 new probe tests PASS (predicate, no-devices, exception, __init__/_arm refresh, hermetic injection).
- [ ] L4: full `tests/test_daemon.py` green; `test_ctl_module_present_and_imports_pure` still green.
- [ ] L5: only `daemon.py` + `test_daemon.py` changed; no mic_* in status_snapshot; read-only files unchanged.

### Feature Validation
- [ ] `_probe_mic()` returns `(True, None)` with an input device; `(False, <str>)` with none.
- [ ] `_refresh_mic_status()` converts any probe exception (incl. `ImportError`) to `_mic_ok=False, _mic_error=str(exc)` — never raises.
- [ ] `__init__` initializes `(True, None)` then refreshes; `_arm()` refreshes again after `set_microphone(True)`.
- [ ] `mic_prober=None` (production) → real `_probe_mic`; injected → the injected callable (hermetic seam).
- [ ] The probe mirrors RealtimeSTT's `maxInputChannels > 0` predicate; opens no stream; always `terminate()`s.

### Code Quality Validation
- [ ] New methods have docstrings citing bugfix Issue 2 / P1.M1.T2.S1 + the lazy-import rationale (Issue 4).
- [ ] `mic_prober` follows the existing `recorder=`/`backend=`/`latency=` keyword-only injection convention.
- [ ] `_probe_mic` placed adjacent to `_arm`/`_disarm` (mic-lifecycle grouping); inline comment on the `_arm` refresh line.
- [ ] No bare `python`/`pip`/`pytest` in commands (all `.venv/bin/...`).
- [ ] Test additions are ADDITIVE (new section); existing tests unchanged except the 4 targeted `mic_prober=_ok_probe` injections.

### Scope Boundary Validation
- [ ] `status_snapshot()` UNCHANGED (S2 owns `mic_ok`/`mic_error` surfacing); `ctl.py` UNCHANGED.
- [ ] No RealtimeSTT-logger rate-limiting (S3); no config/README/systemd/install.sh/launch_daemon.sh changes.
- [ ] `tests/test_feed_audio.py` left unchanged (its real-audio nature is consistent with a real probe).
- [ ] No conflict with parallel T1.S1 (different methods: T1.S1 edits `_FIXED_KWARGS`; T2.S1 edits `__init__`/`_arm` + adds methods).
- [ ] No new dependencies; no new files.

---

## Anti-Patterns to Avoid

- ❌ Don't `import pyaudio` at `daemon.py` module top — it leaks into `import voice_typing.ctl` and breaks the Issue 4 purity test. Import it **inside** `_probe_mic` (Gotcha #2; mirrors the library's own worker at `audio_input_worker.py:38`).
- ❌ Don't call the real `_probe_mic` from `__init__` without the `mic_prober` injection seam — the ~35 daemon tests would all open real PortAudio (slow, ALSA spam, non-hermetic). Inject `mic_prober` and stub it in the 4 test construction sites (Gotcha #1, CRITICAL #1).
- ❌ Don't forget any of the 4 construction sites (`_make_daemon`, `_make_daemon_with_feedback`, + the 2 identical direct constructions at test_daemon.py:796/810) — a missed site means real pyaudio I/O in those tests (Gotcha #1/#12).
- ❌ Don't add `mic_ok`/`mic_error` to `status_snapshot()` — that's S2 and breaks the exact-set test at line 767 (CRITICAL #3). S1 only STORES the attributes.
- ❌ Don't let `_probe_mic`/`_refresh_mic_status` raise out of `__init__`/`_arm` — any probe failure must degrade to `_mic_ok=False`, never block startup/arm (CRITICAL #4; PRD §4.4 spirit).
- ❌ Don't forget `pa.terminate()` in a `finally` — a leaked PortAudio handle per probe (called on every toggle) compounds over a 24/7 daemon (CRITICAL #5).
- ❌ Don't open a stream in the probe or try to reuse the recorder's PyAudio — enumerate via a fresh, short-lived instance (Gotcha #7); the daemon has no handle to the worker's PyAudio.
- ❌ Don't add the refresh to `_disarm()` — the contract specifies `__init__` + `_arm()` only; disarming needs no re-probe.
- ❌ Don't conflate S1 (detection) with S2 (surfacing) or S3 (rate-limiting) — S1 is the probe + attributes ONLY.
- ❌ Don't rate-limit/suppress the ALSA stderr noise here — that's S3's logger work; S1's probe is allowed to emit a few ALSA lines (Gotcha #8).
- ❌ Don't run/restart the live systemd daemon as "verification" — the deterministic gates are the unit tests (mocked pyaudio) + the import-purity check (Gotcha #11).
- ❌ Don't modify `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`, `pyproject.toml`, or `config.toml` (READ-ONLY / owned by others).

---

## Confidence Score

**9/10** for one-pass implementation success. The change is small and self-contained (one new kwarg, two new methods, two call-site additions, four targeted test injections, one new additive test section), and every load-bearing claim is **verified against the actual repo + installed wheel**: the current line numbers (with the contract's stale `__init__:300-326` corrected to 374), the flag-only `set_microphone` (audio_recorder.py:718), the worker's `maxInputChannels>0` predicate (audio_input_worker.py:61-62) and its lazy pyaudio import (line 38), pyaudio 0.2.14 importability + ALSA-spam-on-init (the reason the test stub is mandatory), `Callable` already imported, the 4 exact test construction sites, the status_snapshot exact-set test (line 767, which S1 must not touch), and the `mic_prober=` injection matching the existing `recorder=`/`backend=`/`latency=` convention. The non-overlap with the parallel T1.S1 edit (different methods) is confirmed. The −1 residual risk is the **four-site test injection**: if the implementer misses one of the 4 construction sites, those specific tests would do real pyaudio I/O — on this machine they would still *pass* (a mic is present) but be slow/noisy/non-hermetic, and on a headless/CI host they could fail. The PRP mitigates this as CRITICAL #1 + Gotcha #12, supplies a guard test (`test_make_daemon_injection_is_hermetic_no_real_pyaudio` asserts `d._mic_prober is _ok_probe`), and L4 explicitly watches for ALSA stderr noise as the tell. No real mic/CUDA/systemd is touched by any gate.
