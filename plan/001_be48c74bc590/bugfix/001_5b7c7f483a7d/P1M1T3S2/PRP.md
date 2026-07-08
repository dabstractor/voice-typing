# PRP — P1.M1.T3.S2: construction-failure → CPU retry in main()

## Goal

**Feature Goal**: In `main()`, wrap the `VoiceTypingDaemon` construction in its own try/except separate
from the `server.run()` block, and when construction fails AND the originally-resolved device was `cuda`,
retry **once** with `build_recorder(cfg, feedback, latency, force_cpu=True)` (the S1 capability, which
builds the exact PRD §4.4 CPU config and **skips the cuda_check driver probe entirely**), inject that
recorder via the existing `recorder=` kwarg, and continue to `server.start()` + `daemon.run()` so the
daemon runs in degraded CPU mode instead of `return 1` → systemd `Restart=on-failure` crash-loop. This
closes the second half of bugfix Issue 3 (the first half, the `force_cpu` capability, is P1.M1.T3.S1 —
**already landed**). PRD §4.4: "If CUDA init fails entirely, daemon MUST log clearly and fall back to
`device='cpu', compute_type='int8'` … — degraded but functional — and say so in `status`."

**Deliverable** (2 source edits + 1 doc edit + test changes; no new files):
1. `voice_typing/daemon.py` — restructure the construction inside `main()` (inner try/except → CPU retry
   via `build_recorder(force_cpu=True)` + `recorder=` injection + `_resolved_device_cache` seed); refactor
   `_log_resolved_device()` to read `self._resolved_device()` (the cache) so the startup log matches the
   actual device after a fallback. **No change** to `build_recorder`/`_construct`/`cfg_to_kwargs`,
   `cuda_check.py`, `_resolve_device_config`, or `VoiceTypingDaemon.__init__`.
2. `README.md` — "## CPU-only mode" (+3rd fallback way) and "### cuDNN load error" (auto-degrade note).
3. `tests/test_daemon.py` — MODIFY one existing test for hermeticity (assertion preserved) + ADD an
   additive test section (4 new tests for the retry + 1 for the `_log_resolved_device` cache read).

**Success Definition**:
- (a) When CUDA **construction** fails (driver probe said `cuda-ok` but cuDNN/cuBLAS load fails inside
  `AudioToTextRecorder.__init__`), `main()` retries once with `force_cpu=True`, the daemon runs in CPU
  mode, and `main()` returns `0` (systemd does NOT crash-loop).
- (b) `journalctl` shows the degradation clearly: a WARNING `CUDA recorder construction failed (...);
  falling back to CPU (device=cpu, compute_type=int8, models=small.en/tiny.en) — degraded but functional`
  followed by `daemon started in degraded CPU mode (construction-failure fallback)`.
- (c) After a successful CPU fallback, BOTH the startup log AND `voicectl status` report
  `device=cpu`/`compute_type=int8`/`small.en`/`tiny.en` (not the driver-probed `cuda`). PRD §4.4 "say so
  in status" satisfied for the construction-failure sub-case.
- (d) If the first attempt was NOT `cuda` (config already forces CPU, or probe failed) → NO retry → the
  original exception propagates → `return 1` (a CPU config has nothing to fall back to).
- (e) If the CPU retry ALSO fails (`build_recorder(force_cpu=True)` raises, or the re-constructed daemon
  raises) → propagates to the existing `except Exception` → `"fatal error during daemon lifecycle;
  exiting"` → `return 1`. `test_main_returns_one_on_daemon_construction_failure` still passes
  (semantics: both attempts fail → return 1).
- (f) All other `main()` lifecycle tests pass unmodified; all existing `tests/` tests pass.

## User Persona

**Target User**: the operator of the 24/7 systemd user service (`systemctl --user restart voice-typing`)
on a host whose NVIDIA driver reports a GPU but whose cuDNN/cuBLAS libs are not loadable at
`AudioToTextRecorder` construction (e.g. a stale `LD_LIBRARY_PATH` after `uv sync`, or nvidia wheels
absent).

**Use Case**: the daemon is restarted (boot, package upgrade, config edit). cuDNN fails to load. Instead
of crash-looping forever under `Restart=on-failure`, the daemon logs a clear degradation WARNING, falls
back to CPU, and keeps transcribing (slower but functional) so the user is never left without voice typing.

**Pain Points Addressed**: today this exact condition makes `systemctl --user status voice-typing` show an
endless restart loop and `journalctl` shows the construction traceback repeating — the product is down
hard. After this fix it degrades gracefully and the operator can read the WARNING + fix the lib path at
leisure, then restart to return to the GPU.

## Why

- **PRD §4.4 MUST is only half-met today.** `cuda_check.resolve_device_and_models()` probes the CUDA
  **driver** only (`ctranslate2.get_cuda_device_count()`); a missing `libcudnn_ops.so.9` still yields
  `cuda-ok`, so the failure surfaces later at recorder **construction**. The construction path in
  `main()` had no retry → `return 1` → systemd crash-loop. (daemon.py module docstring lines 25-29
  explicitly defer this to "a future task".)
- **systemd `Restart=on-failure` turns a recoverable degradation into a permanent outage.** The unit
  (`systemd/voice-typing.service`) has `Restart=on-failure, RestartSec=2`. Returning 1 on a GPU host with
  a broken cuDNN path loops forever. PRD §4.9 expects a 24/7 service.
- **S1 already built the capability; S2 is the wiring.** `build_recorder(cfg, feedback, latency,
  force_cpu=True)` exists (verified: `grep force_cpu voice_typing/daemon.py`; 6 S1 tests pass). It builds
  a CPU recorder from `cuda_check.CPU_FALLBACK` **without** re-probing the GPU. S2 is purely the
  main()-level try/except that decides when to call it, logs the degradation, and makes status reflect
  reality.
- **Scope discipline.** S1 = the `force_cpu` knob on the build path. S2 = the construction-layer retry in
  main() + status/logging surfacing + docs. S2 does NOT touch the build path, `cuda_check.py`, or
  `_resolve_device_config` (S1's negative constraints carry over).

## What

**User-visible behavior**: a cuDNN/cuBLAS load failure at daemon startup no longer crash-loops the
systemd unit. The daemon logs a clear WARNING, runs on CPU (`device=cpu`, `compute_type=int8`,
`small.en`/`tiny.en`), and `voicectl status` reports `device: cpu (int8)`. If the CPU path also fails,
the daemon exits 1 as before (genuine fatal error).

**Technical requirements**:
- `main()`'s `VoiceTypingDaemon` construction gets its OWN try/except (inner), nested inside the existing
  broad try/except (outer → "fatal error" → return 1).
- On an inner-construction `Exception`, consult `_resolve_device_config(cfg)["device"]`. If `== "cuda"`,
  retry with `build_recorder(..., force_cpu=True)` + `recorder=` injection + cache seed + logs. Otherwise
  re-raise (propagates to outer → return 1).
- `_log_resolved_device()` reads the cached `self._resolved_device()` so the startup log agrees with
  `status_snapshot()` after a fallback.
- README documents the automatic fallback.

### Success Criteria

- [ ] `main()` constructs the daemon via `VoiceTypingDaemon(cfg, feedback, latency=latency)` (shared
  `LatencyLog`).
- [ ] On construction `Exception` with `_resolve_device_config(cfg)["device"] == "cuda"`: `main()` logs
  the WARNING (verbatim message, values from `cuda_check.CPU_FALLBACK`), calls
  `build_recorder(cfg, feedback, latency, force_cpu=True)`, re-constructs
  `VoiceTypingDaemon(cfg, feedback, latency=latency, recorder=cpu_recorder)`, sets
  `daemon._resolved_device_cache = dict(cuda_check.CPU_FALLBACK)`, logs
  `"daemon started in degraded CPU mode (construction-failure fallback)"`, and proceeds to
  `server.start()` + `daemon.run()` → returns 0.
- [ ] On construction `Exception` with resolved device `!= "cuda"`: re-raise (no retry) → return 1.
- [ ] If the CPU retry raises: propagates to the outer `except Exception` → "fatal error" → return 1.
- [ ] `_log_resolved_device()` calls `self._resolved_device()` (the cache), not `_resolve_device_config`
  directly.
- [ ] After a CPU fallback, `status_snapshot()` reports `device=cpu`/`int8`/`small.en`/`tiny.en` and the
  startup log line says `device=cpu`.
- [ ] `test_main_returns_one_on_daemon_construction_failure` passes (assertion `main() == 1` unchanged;
  hermeticity monkeypatches added).
- [ ] All other existing `tests/` tests pass unmodified.
- [ ] `build_recorder`/`_construct`/`cfg_to_kwargs`, `cuda_check.py`, `_resolve_device_config`,
  `VoiceTypingDaemon.__init__` are unchanged (S1's negative constraints).

## All Needed Context

### Context Completeness Check

_Pass._ A developer who has never seen this repo can implement S2 from this PRP + the referenced
research note. Both source edits are given as verbatim old→new text against the current (post-S1) file;
the design rationale (why `recorder=` injection, why the latency must be shared, why the cache must be
seeded, why `_log_resolved_device` must read the cache) is documented in the research note; the test plan
mirrors the existing `_patch_main_lifecycle`/`BoomDaemon`/`_MainFakeDaemon` idioms already proven in the
suite. No real CUDA/RealtimeSTT/model-load is needed for any gate (the retry path is tested with
monkeypatched `build_recorder` returning a `_StubRecorder`).

### Documentation & References

```yaml
# MUST READ — the verified design: construction site, device-reporting chain, latency invariant,
# the test-hermeticity problem, the option-2 decision, README sites, tooling.
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M1T3S2/research/main_retry_design_and_test_plan.md
  why: "§0 confirms S1 is LANDED (build_recorder force_cpu exists + 6 tests pass). §1 is the verbatim
        construction block in main(). §2 is the device-reporting chain (why _resolved_device_cache must
        be seeded + _log_resolved_device refactored). §3 is the latency-sharing invariant. §4 is the
        BoomDaemon hermeticity problem + the _RaiseOnceDaemon pattern for the success-fallback test.
        §5 is the option-2 decision. §6 the README sites. §7 tooling."
  section: "§2 (cache seed) and §4 (test hermeticity) are load-bearing."

# MUST READ — the consumer contract (S1's Integration Points) + the exact target config
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/P1M1T3S1/PRP.md
  why: "Integration Points → DOWNSTREAM CONSUMER (P1.M1.T3.S2) gives the SANCTIONED call:
        rec = build_recorder(cfg, feedback, latency, force_cpu=True)
        daemon = VoiceTypingDaemon(cfg, feedback, recorder=rec, ...)
        and states: 'T3.S2 also owns ... surfacing device=\"cpu\" in status ... T3.S2 may need to make
        the daemon's self-reported device reflect the actual built recorder.' This PRP implements exactly
        that (recorder= injection + _resolved_device_cache seed)."
  critical: "S1 Gotcha #7: 'DO NOT add force_cpu to VoiceTypingDaemon.__init__ ... inject via the EXISTING
             recorder= kwarg.' S2 honours this — NO __init__ change."

# THE AUTHORITATIVE TARGET CONFIG (the values force_cpu produces + the cache seed source)
- file: voice_typing/cuda_check.py
  why: "CPU_FALLBACK = {device:'cpu', compute_type:'int8', final_model:'small.en', realtime_model:'tiny.en'}.
        S2 seeds daemon._resolved_device_cache = dict(cuda_check.CPU_FALLBACK) and logs its values. Do NOT
        hardcode {'device':'cpu',...} (drift risk); reference the constant (already module-top imported
        in daemon.py as `from voice_typing import cuda_check`)."
  critical: "dict(...) gives a fresh copy so the module constant can't be mutated. The keys exactly match
             what _resolved_device()/status_snapshot() read."

# THE EDIT SITES — main() construction block + _log_resolved_device (verbatim text in Tasks 1-2)
- file: voice_typing/daemon.py
  why: "main() construction block @~1119-1124 (the `from voice_typing.feedback import Feedback` ...
        daemon = VoiceTypingDaemon(cfg, Feedback(cfg.feedback)) ... server = ControlServer(...) lines).
        _log_resolved_device @~467-486 (the `resolved = _resolve_device_config(self._cfg)` line). These
        are the ONLY daemon.py edits."
  pattern: "main() initialises daemon=None/server=None/restore=None BEFORE the try; the finally block is
            NULL-SAFE (if daemon is not None: daemon.shutdown()). The inner try must keep `daemon` None on
            total failure so the finally skips shutdown. _log_resolved_device is wrapped in try/except
            (defensive); _resolved_device() never raises."
  gotcha: "`build_recorder`, `_resolve_device_config`, `cuda_check`, `LatencyLog`, `logger` are all
           module globals — monkeypatchable via monkeypatch.setattr(daemon, '...') in tests, exactly like
           the existing tests patch daemon.VoiceTypingDaemon."

# THE TEST FILE — the seams to mirror + the ONE existing test to update for hermeticity
- file: tests/test_daemon.py
  why: "_patch_main_lifecycle(monkeypatch, daemon_cls=...) @~895 patches VoiceTypingConfig/VoiceTypingDaemon/
        ControlServer/install_shutdown_signal_handlers/feedback.Feedback/basicConfig (NOT _resolve_device_config
        or build_recorder). test_main_returns_one_on_daemon_construction_failure @~979 uses BoomDaemon (raises
        in __init__). _MainFakeDaemon.__init__(cfg, fb, **kw) absorbs latency=/recorder= kwargs. _StubRecorder
        @~471 is the fake recorder. The main()-test section banner is @~870 (P1.M4.T3.S1)."
  pattern: "ADD a new banner section at the END of the file (additive). MODIFY the one BoomDaemon test in
            place (add 2 hermeticity monkeypatches; keep the == 1 assertion). For the success-fallback test
            use a stateful _RaiseOnceDaemon (raise on 1st construction, succeed on 2nd) + a build_recorder
            capture that records force_cpu and returns _StubRecorder. NO real CUDA/RealtimeSTT/model-load."
  critical: "On a GPU host the un-modified BoomDaemon test would call the REAL build_recorder(force_cpu=True)
             (loads CPU models) because _resolve_device_config is un-patched → returns cuda. The update is a
             HERMETICITY fix (deterministic 'both attempts fail'), NOT a contract change."

# THE CONTRACT (this item) — authoritative scope + the test that must still pass
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/tasks.json
  why: "P1.M1.T3.S2 LOGIC (a)-(e) + OUTPUT + DOCS. (a) wrap construction in its own try/except; (b) on
        Exception check _resolve_device_config(cfg) for cuda + log the WARNING; (c) retry with force_cpu=True
        (option 2: build_recorder + recorder= injection); (d) CPU retry fail → existing fatal+return 1
        (preserve test_main_returns_one_on_daemon_construction_failure); (e) success → log + continue. DOCS
        Mode A = README CPU-only/Troubleshooting."

# THE DEFECT (Issue 3) — the bug this fixes
- docfile: plan/001_be48c74bc590/bugfix/001_5b7c7f483a7d/prd_snapshot.md
  why: "§2 Issue 3 (Major): 'In main() (or build_recorder()), wrap recorder construction in a try/except;
        on failure with a resolved device==\"cuda\", re-resolve with cuda_check.CPU_FALLBACK, reconstruct,
        log the degradation clearly, and continue.' S1 added the capability; S2 adds the main() retry."

# THE README SECTIONS TO EDIT (Mode A)
- file: README.md
  why: "'## CPU-only mode' @~146 (currently 'There are two ways' — add a 3rd construction-failure way) and
        '### cuDNN load error (`libcudnn_ops.so.9`)' @~166 under Troubleshooting (add auto-degrade note).
        These are the user-facing doc for the new behavior."
```

### Current Codebase tree (relevant slice — S1 LANDED; S2 edits marked)

```bash
/home/dustin/projects/voice-typing/
├── voice_typing/
│   ├── daemon.py        # main() construction @~1119  ← EDIT (Task 1: inner try/except + CPU retry + cache seed)
│   │                    # _log_resolved_device @~467   ← EDIT (Task 2: read self._resolved_device() cache)
│   │                    # build_recorder/_construct/cfg_to_kwargs @134-287 — UNCHANGED (S1 landed; S2 consumes).
│   │                    # _resolve_device_config @117, VoiceTypingDaemon.__init__ @393 — UNCHANGED.
│   └── cuda_check.py    # CPU_FALLBACK — UNCHANGED (S2 reads it; does not modify).
├── README.md            # '## CPU-only mode' @146 + '### cuDNN load error' @166  ← EDIT (Task 3, Mode A docs)
└── tests/
    └── test_daemon.py   # test_main_returns_one_on_daemon_construction_failure @~979  ← MODIFY (hermeticity)
                         # + new additive banner section at END                      ← EDIT (Task 4: 5 tests)
# No new files. No cuda_check.py / config.py / ctl.py / systemd / launch_daemon.sh changes.
```

### Desired Codebase tree with files to be changed

```bash
voice_typing/daemon.py   # EDIT main() construction block (inner try/except → force_cpu retry + recorder=
#                        # injection + _resolved_device_cache seed + 2 log lines); EDIT _log_resolved_device
#                        # (read cache). NO other function touched. No new imports (cuda_check already
#                        # module-top; LatencyLog already defined in-module).
README.md                # EDIT '## CPU-only mode' (add 3rd way) + '### cuDNN load error' (add auto-degrade note).
tests/test_daemon.py     # MODIFY test_main_returns_one_on_daemon_construction_failure (add 2 hermeticity
#                        # monkeypatches; keep == 1 assertion); ADD one banner section (5 tests: success
#                        # fallback, skip-when-not-cuda, cpu-build-fails, _log_resolved_device cache read,
#                        # WARNING/degraded log presence).
# No new files.
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — DO NOT add force_cpu to VoiceTypingDaemon.__init__. S1 Gotcha #7 + Integration Points
# mandate the recorder= injection: main() calls build_recorder(cfg, feedback, latency, force_cpu=True)
# and passes the result via the EXISTING recorder= keyword-only kwarg. __init__ stays byte-identical.
# (research §5; S1 PRP.)

# CRITICAL #2 — SHARE ONE LatencyLog across both attempts. The recorder's on_vad_stop/partial callbacks
# are wired (via build_recorder→_build_callbacks) to the LatencyLog, and on_final.finalize_utterance reads
# the SAME object. main() must create latency = LatencyLog() ONCE and pass latency=latency to BOTH
# build_recorder (retry) and VoiceTypingDaemon (both attempts). __init__ sets self._latency = latency when
# given (and uses the injected recorder as-is, NOT calling build_recorder). (research §3.)

# CRITICAL #3 — THE CACHE SEED IS HOW STATUS REFLECTS THE FALLBACK. _resolved_device() (read by
# status_snapshot) caches via self._resolved_device_cache (getattr/setattr — documented extension point,
# "no __init__ edit"). After a CPU retry, main() sets daemon._resolved_device_cache = dict(cuda_check.
# CPU_FALLBACK) so status reports device=cpu. Without this, status would re-probe the driver (sees the
# GPU) and LIE (report cuda while the recorder is on cpu) — violating PRD §4.4 "say so in status". The
# cache keys {device,compute_type,final_model,realtime_model} exactly match CPU_FALLBACK. (research §2.)

# CRITICAL #4 — _log_resolved_device MUST ALSO READ THE CACHE, else journalctl contradicts itself.
# Currently it calls _resolve_device_config(self._cfg) DIRECTLY (re-probes the driver → logs cuda after a
# CPU fallback, contradicting the WARNING). Refactor: call self._resolved_device() (the cache) instead.
# On the normal cuda path the cache is lazily populated on first call → same log as today. The existing
# test_run_logs_resolved_device_at_startup still passes (cache populated via monkeypatched cuda_check).
# (research §2.)

# CRITICAL #5 — THE RETRY MUST FIRE ONLY WHEN THE FIRST ATTEMPT WAS CUDA. If _resolve_device_config(cfg)
# ["device"] != "cuda" (config forces cpu, or the probe itself failed) there is nothing to fall back to →
# re-raise → return 1. Use .get("device") (defensive) and compare == "cuda". (item LOGIC (b).)

# CRITICAL #6 — THE BoomDaemon TEST MUST BE MADE HERMETIC. On a GPU host _resolve_device_config is
# un-patched → returns cuda → the retry branch calls the REAL build_recorder(force_cpu=True) → imports
# RealtimeSTT + loads CPU Whisper models (seconds, spawns workers). The existing
# test_main_returns_one_on_daemon_construction_failure must monkeypatch _resolve_device_config (→cuda)
# AND build_recorder (→fake _StubRecorder, no model load) so it deterministically exercises "both attempts
# fail → return 1". The assert daemon.main() == 1 is PRESERVED. This is a hermeticity fix, not a contract
# change. (research §4.)

# CRITICAL #7 — KEEP `daemon` NONE ON TOTAL FAILURE. main() initialises daemon=None before the try; the
# finally does `if daemon is not None: daemon.shutdown()`. The inner try assigns `daemon = ...` only on
# success. If both attempts raise, daemon stays None → finally skips shutdown (correct: nothing was
# successfully built). If the retry builds cpu_recorder but the re-construction raises, cpu_recorder is
# leaked until process exit (return 1) — ACCEPTABLE (process exit reclaims it; the retry re-construction
# failing is near-impossible: __init__ just stores refs + probes the mic). Do NOT add cleanup for it.
# (research §1, §4.)

# CRITICAL #8 — LOG VALUES FROM cuda_check.CPU_FALLBACK, do NOT hardcode. The WARNING message must match
# PRD §4.4 (device=cpu, compute_type=int8, models=small.en/tiny.en) — interpolate from
# cuda_check.CPU_FALLBACK so it can't drift: fb["device"], fb["compute_type"], fb["final_model"],
# fb["realtime_model"]. (cuda_check.py CPU_FALLBACK.)

# CRITICAL #9 — DO NOT MODIFY build_recorder/_construct/cfg_to_kwargs/cuda_check.py/_resolve_device_config.
# S1 landed those; S2 CONSUMES them. The only daemon.py edits are main()'s construction block and
# _log_resolved_device. (S1 negative constraints carry over; research §8.)

# GOTCHA #10 — FULL PATHS in every bash command. This machine aliases python3→uv run, pip→alias, tmux→zsh
# plugin. Invoke .venv/bin/python and .venv/bin/python -m pytest explicitly. Never bare python/pytest/uv.

# GOTCHA #11 — THIS PROJECT USES pytest, NOT ruff/mypy. pyproject.toml has NO [tool.ruff]/[tool.mypy] —
# only [dependency-groups] dev=["pytest>=9.1.1"]. Do NOT invent ruff/mypy validation commands. Validation
# = py_compile + pytest. (research §7.)

# GOTCHA #12 — `from __future__ import annotations` is at daemon.py's top; `LatencyLog` / `cuda_check` /
# `build_recorder` / `_resolve_device_config` / `logger` are all already in scope inside main(). No new
# imports are needed for the edits.
```

## Implementation Blueprint

### Data models and structure

No config/schema/pydantic changes. No new types. The only "data" change is seeding an existing internal
cache attribute (`daemon._resolved_device_cache`) with an existing constant (`dict(cuda_check.CPU_FALLBACK)`).
The resolved-dict shape `{device, compute_type, final_model, realtime_model}` is unchanged.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: EDIT voice_typing/daemon.py — main(): wrap construction in its own try/except + CPU retry
  - FIND main() construction block (@~1119-1124). Current:
        from voice_typing.feedback import Feedback

        daemon = VoiceTypingDaemon(cfg, Feedback(cfg.feedback))
        # quit path: ControlServer._dispatch("quit") -> request_shutdown() (blocks until text()
        #   returns) -> on_quit=daemon.shutdown() -> recorder.shutdown() (release VRAM).
        server = ControlServer(daemon, on_quit=daemon.shutdown)
  - EDIT (oldText → newText):
      OLD:
        from voice_typing.feedback import Feedback

        daemon = VoiceTypingDaemon(cfg, Feedback(cfg.feedback))
        # quit path: ControlServer._dispatch("quit") -> request_shutdown() (blocks until text()
        #   returns) -> on_quit=daemon.shutdown() -> recorder.shutdown() (release VRAM).
        server = ControlServer(daemon, on_quit=daemon.shutdown)
      NEW:
        from voice_typing.feedback import Feedback

        feedback = Feedback(cfg.feedback)
        # One LatencyLog shared by the recorder callbacks (on_vad_stop/partial, wired in build_recorder)
        # and the daemon's on_final.finalize_utterance. Created here (not left to __init__) so the
        # construction-failure CPU retry below can build a forced-CPU recorder wired to this SAME
        # collector before re-constructing the daemon. (bugfix Issue 3 / P1.M1.T3.S2.)
        latency = LatencyLog()

        # bugfix Issue 3 / P1.M1.T3.S2 (PRD §4.4): the cuda_check driver probe can say "cuda-ok" while
        # cuDNN/cuBLAS then fails to load INSIDE AudioToTextRecorder.__init__ (e.g. a missing
        # libcudnn_ops.so.9). Without a retry that is `return 1` -> systemd Restart=on-failure crash-loop.
        # So: if construction fails AND the originally-resolved device was cuda, retry ONCE on the PRD
        # §4.4 CPU config via build_recorder(force_cpu=True) (which SKIPS the cuda_check probe entirely
        # — S1) and inject the recorder through the existing recorder= kwarg (no __init__ change). Any
        # failure here (probe raises, CPU build raises, re-construction raises) propagates to the outer
        # `except Exception` -> "fatal error" -> return 1, preserving total-failure semantics.
        try:
            daemon = VoiceTypingDaemon(cfg, feedback, latency=latency)
        except Exception as exc:
            if _resolve_device_config(cfg).get("device") != "cuda":
                raise  # first attempt was already CPU (or the probe failed) — nothing to fall back to
            cpu_fb = cuda_check.CPU_FALLBACK
            logger.warning(
                "CUDA recorder construction failed (%s); falling back to CPU "
                "(device=%s, compute_type=%s, models=%s/%s) — degraded but functional",
                exc, cpu_fb["device"], cpu_fb["compute_type"],
                cpu_fb["final_model"], cpu_fb["realtime_model"],
            )
            cpu_recorder = build_recorder(cfg, feedback, latency, force_cpu=True)
            daemon = VoiceTypingDaemon(cfg, feedback, latency=latency, recorder=cpu_recorder)
            # Make the daemon's self-reported device reflect the ACTUAL cpu recorder, not the driver
            # probe (which still sees the GPU). _resolved_device() (read by status_snapshot) caches via
            # this attribute; seeding it here means voicectl status reports device=cpu after the
            # fallback (PRD §4.4 "say so in status"). _log_resolved_device (refactored in Task 2) also
            # reads this cache, so the startup log agrees.
            daemon._resolved_device_cache = dict(cuda_check.CPU_FALLBACK)
            logger.info("daemon started in degraded CPU mode (construction-failure fallback)")
        # quit path: ControlServer._dispatch("quit") -> request_shutdown() (blocks until text()
        #   returns) -> on_quit=daemon.shutdown() -> recorder.shutdown() (release VRAM).
        server = ControlServer(daemon, on_quit=daemon.shutdown)
  - WHY: inner try/except isolates construction from the server/run block (item LOGIC (a)); the cuda
    guard (LOGIC (b)) ensures a CPU config isn't pointlessly re-tried; build_recorder(force_cpu=True) +
    recorder= injection is the S1-sanctioned retry (LOGIC (c), option 2); the cache seed + Task 2 make
    status + the startup log reflect cpu (LOGIC/OUTPUT); any failure re-raises into the outer except
    (LOGIC (d)); on success we fall through to server/run (LOGIC (e)). The shared `latency` keeps the
    recorder callbacks and finalize_utterance on one collector (CRITICAL #2).
  - DO NOT: add force_cpu to VoiceTypingDaemon.__init__; hardcode the CPU values (use cuda_check.
    CPU_FALLBACK); call build_recorder WITHOUT force_cpu=True on the retry; forget the cache seed
    (status would lie); set the cache on the non-fallback path.

Task 2: EDIT voice_typing/daemon.py — _log_resolved_device: read the cache so the startup log agrees
  - FIND _log_resolved_device (@~467). Current body:
        def _log_resolved_device(self) -> None:
            """Log the resolved device/models once at startup (CUDA residency proof; PRD acceptance T6).

            Wrapped in try/except so a probe failure (odd env / missing ctranslate2 in a degraded run)
            NEVER breaks the listen loop. Reuses S1's _resolve_device_config (the same resolution
            build_recorder applied), so the logged device matches the recorder's actual device.
            """
            try:
                resolved = _resolve_device_config(self._cfg)
                logger.info(
                    "voice-typing device resolved: device=%s compute_type=%s final_model=%s "
                    "realtime_model=%s",
                    resolved["device"],
                    resolved["compute_type"],
                    resolved["final_model"],
                    resolved["realtime_model"],
                )
            except Exception:
                logger.info("voice-typing device resolved: (resolution failed; see cuda_check logs)")
  - EDIT (two changes — the docstring + the one resolved= line):
      OLD:
            Wrapped in try/except so a probe failure (odd env / missing ctranslate2 in a degraded run)
            NEVER breaks the listen loop. Reuses S1's _resolve_device_config (the same resolution
            build_recorder applied), so the logged device matches the recorder's actual device.
            """
            try:
                resolved = _resolve_device_config(self._cfg)
      NEW:
            Reads self._resolved_device() — the SAME cached resolution status_snapshot() reports — so
            the startup log and voicectl status always agree. After a construction-failure CPU fallback
            (bugfix Issue 3 / P1.M1.T3.S2), main() seeds _resolved_device_cache with
            cuda_check.CPU_FALLBACK, so this logs the ACTUAL cpu recorder (not the driver probe, which
            still sees the GPU). _resolved_device() never raises (it degrades to 'unknown' on probe
            failure); the try/except is retained as a defensive guard.
            """
            try:
                resolved = self._resolved_device()
  - WHY: on the normal path the cache is lazily populated by the first _resolved_device() call (→
    cuda_check → cuda) → identical log to today (test_run_logs_resolved_device_at_startup still passes).
    After a CPU fallback the cache is cpu (seeded in Task 1) → the startup log says device=cpu, matching
    the WARNING + status (no journalctl contradiction; CRITICAL #4).
  - DO NOT: remove the try/except (keep it defensive); change the logger.info format string or field
    order; touch _resolved_device() itself.

Task 3: EDIT README.md — Mode A: document the automatic construction-failure → CPU fallback
  - FIND "## CPU-only mode" (@~146). Current opening:
        ## CPU-only mode

        There are two ways the daemon ends up on CPU.

        1. You force it. Set `[asr] device = "cpu"` in `config.toml` and restart. The daemon
           derives `compute_type="int8"`. If a GPU is present, it still uses your configured
           `final_model` and `realtime_model`, just on CPU with int8 quantization.
        2. Auto-fallback. When `ctranslate2` sees zero CUDA devices at startup, the daemon
           overrides to `device="cpu"`, `compute_type="int8"`, and the smaller models
           `small.en` (final) and `tiny.en` (realtime), regardless of config.
  - EDIT (oldText → newText):
      OLD:
        There are two ways the daemon ends up on CPU.

        1. You force it. Set `[asr] device = "cpu"` in `config.toml` and restart. The daemon
           derives `compute_type="int8"`. If a GPU is present, it still uses your configured
           `final_model` and `realtime_model`, just on CPU with int8 quantization.
        2. Auto-fallback. When `ctranslate2` sees zero CUDA devices at startup, the daemon
           overrides to `device="cpu"`, `compute_type="int8"`, and the smaller models
           `small.en` (final) and `tiny.en` (realtime), regardless of config.
      NEW:
        There are three ways the daemon ends up on CPU.

        1. You force it. Set `[asr] device = "cpu"` in `config.toml` and restart. The daemon
           derives `compute_type="int8"`. If a GPU is present, it still uses your configured
           `final_model` and `realtime_model`, just on CPU with int8 quantization.
        2. Auto-fallback. When `ctranslate2` sees zero CUDA devices at startup, the daemon
           overrides to `device="cpu"`, `compute_type="int8"`, and the smaller models
           `small.en` (final) and `tiny.en` (realtime), regardless of config.
        3. Construction-failure fallback. The check in #2 only asks whether `ctranslate2` can
           *see* a GPU; it does not load cuDNN. If a GPU is visible but CUDA/cuDNN init then fails
           while building the recorder (for example a missing `libcudnn_ops.so.9` after a stale
           `uv sync`), the daemon retries once on the same CPU config as #2 and keeps running
           instead of crash-looping. `journalctl --user -u voice-typing` shows
           `CUDA recorder construction failed (...); falling back to CPU ... — degraded but
           functional` then `daemon started in degraded CPU mode`, and `voicectl status` reports
           `device: cpu (int8)`. Fix the library path (see the cuDNN section under Troubleshooting)
           and restart to return to the GPU.
  - FIND "### cuDNN load error (`libcudnn_ops.so.9`)" closing lines (@~166-174). Current end of section:
           ldd /home/dustin/projects/voice-typing/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib/libcudnn.so.9
           systemctl --user restart voice-typing
        ```

        After any fix, restart with `systemctl --user restart voice-typing` so the wrapper
        recomputes the library paths.
  - EDIT (append a paragraph after "...recomputes the library paths."):
      OLD:
        After any fix, restart with `systemctl --user restart voice-typing` so the wrapper
        recomputes the library paths.
      NEW:
        After any fix, restart with `systemctl --user restart voice-typing` so the wrapper
        recomputes the library paths.

        If cuDNN still cannot be loaded at daemon startup, the daemon now degrades to CPU
        automatically instead of crash-looping under `Restart=on-failure`: the journal shows the
        `falling back to CPU ... degraded but functional` line and `voicectl status` reports
        `device: cpu (int8)`. Transcription keeps working (slower); fix the library path above and
        restart to get back on the GPU.
  - WHY: Mode A docs (item DOCS) — tell operators the daemon degrades gracefully so they do not
    mistake a CPU-fallback run for a healthy GPU run or for a dead unit. Aligns with PRD §4.4 "say so
    in status" + the existing "On CPU fallback, `device` shows `cpu (int8)`" line in the Logs section.
  - DO NOT: edit other README sections; change the existing numbered items 1/2 (only add #3); touch
    install.sh / systemd unit / config.toml.

Task 4: EDIT tests/test_daemon.py — MODIFY one test for hermeticity + ADD an additive section (5 tests)
  - PART A — MODIFY test_main_returns_one_on_daemon_construction_failure (@~979). Current:
        def test_main_returns_one_on_daemon_construction_failure(monkeypatch):
            class BoomDaemon:
                def __init__(self, *a, **k):
                    raise RuntimeError("recorder init failed")

                def run(self):
                    pass

                def shutdown(self):
                    pass

            _patch_main_lifecycle(monkeypatch, daemon_cls=BoomDaemon)
            assert daemon.main() == 1  # caught, logged, returns 1 (systemd Restart)
  - EDIT (oldText → newText):
      OLD:
            _patch_main_lifecycle(monkeypatch, daemon_cls=BoomDaemon)
            assert daemon.main() == 1  # caught, logged, returns 1 (systemd Restart)
      NEW:
            # bugfix P1.M1.T3.S2: main() now RETRIES on cuda. Without these hermeticity patches, a GPU
            # host would hit the REAL build_recorder(force_cpu=True) (loads CPU models) inside the retry.
            # Force the resolved device to cuda (so the retry branch is entered deterministically) and
            # stub build_recorder (so no RealtimeSTT/model load). BoomDaemon still raises on BOTH
            # constructions -> "both CUDA and CPU fail" -> return 1 (the assertion is unchanged).
            _patch_main_lifecycle(monkeypatch, daemon_cls=BoomDaemon)
            monkeypatch.setattr(
                daemon, "_resolve_device_config",
                lambda _cfg: dict(daemon.cuda_check.CUDA_DEFAULTS),
            )
            monkeypatch.setattr(daemon, "build_recorder", lambda *a, **k: _StubRecorder())
            assert daemon.main() == 1  # caught, logged, returns 1 (systemd Restart)
  - WHY: the assertion (main()==1) is PRESERVED; only hermeticity monkeypatches are added so the test
    deterministically exercises "both attempts fail → return 1" on any host (CRITICAL #6). _StubRecorder
    is already defined @~471 (the S2 daemon-test section); reuse it, do not redefine.
  - DO NOT: change the BoomDaemon class; change the `assert daemon.main() == 1` assertion; remove the
    existing comment.

  - PART B — ADD a new additive banner section at the END of the file (after the P1.M1.T2.S3
    mic-retry section, i.e. after test_rate_limit_filter_is_logger_level_chokepoint). Reuse existing
    `_StubRecorder`, `_patch_main_lifecycle`, `VoiceTypingConfig`, `daemon`, `logging`, `pytest` (all
    already imported/defined; do NOT redefine). Verbatim:
        # ===========================================================================
        # bugfix P1.M1.T3.S2 — construction-failure → CPU retry in main() (PRD §4.4)
        # (ADDITIVE: main() retries once with build_recorder(force_cpu=True) when the first attempt was
        #  cuda and construction failed. Uses _patch_main_lifecycle + a stateful _RaiseOnceDaemon + a
        #  build_recorder capture. ZERO real CUDA/RealtimeSTT/model-load — build_recorder is stubbed.)
        # ===========================================================================


        def _raise_once_daemon_factory():
            """A VoiceTypingDaemon stand-in that raises on the FIRST construction, succeeds on the SECOND.

            Captures the constructor kwargs of each attempt so the fallback test can assert the 2nd
            attempt got the injected recorder= and the shared latency=. State is per-factory (no
            class-level leakage across tests).
            """
            attempts = {"n": 0, "kwargs": []}

            class _RaiseOnceDaemon:
                def __init__(self, cfg, fb, **kw):
                    attempts["n"] += 1
                    attempts["kwargs"].append(dict(kw))
                    if attempts["n"] == 1:
                        raise RuntimeError("cuda recorder construction failed")
                    self.cfg, self.fb = cfg, fb
                    self.recorder = kw.get("recorder")
                    self.run_called = False
                    self.shutdown_calls = 0

                def run(self):
                    self.run_called = True

                def shutdown(self):
                    self.shutdown_calls += 1

            return _RaiseOnceDaemon, attempts


        def test_main_falls_back_to_cpu_on_cuda_construction_failure(monkeypatch, caplog):
            """cuda construction fails -> retry with force_cpu=True -> daemon runs (return 0)."""
            daemon_cls, attempts = _raise_once_daemon_factory()
            built = {"force_cpu": None, "n": 0}

            def fake_build_recorder(cfg, feedback, latency=None, force_cpu=False):
                built["force_cpu"] = force_cpu
                built["n"] += 1
                return _StubRecorder()

            _patch_main_lifecycle(monkeypatch, daemon_cls=daemon_cls)
            # _patch_main_lifecycle set VoiceTypingDaemon; re-assert our overrides (it does not touch
            # _resolve_device_config or build_recorder, so order is safe):
            monkeypatch.setattr(daemon, "_resolve_device_config",
                                lambda _cfg: dict(daemon.cuda_check.CUDA_DEFAULTS))
            monkeypatch.setattr(daemon, "build_recorder", fake_build_recorder)

            with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
                code = daemon.main()

            assert code == 0                                  # daemon ran in degraded CPU mode
            assert built["n"] == 1 and built["force_cpu"] is True   # retried exactly once, forced CPU
            assert attempts["n"] == 2                         # two VoiceTypingDaemon constructions
            # 2nd attempt got the injected recorder + the shared latency (NOT None):
            assert attempts["kwargs"][1].get("recorder") is not None
            assert attempts["kwargs"][1].get("latency") is attempts["kwargs"][0].get("latency")
            # the degradation was logged clearly (WARNING + the INFO degraded-mode line):
            msgs = [r.getMessage() for r in caplog.records]
            assert any("falling back to CPU" in m and "degraded but functional" in m for m in msgs), msgs
            assert any("degraded CPU mode" in m for m in msgs), msgs


        def test_main_skips_cpu_retry_when_resolved_device_not_cuda(monkeypatch):
            """A cpu (or failed) first attempt has nothing to fall back to -> no retry -> return 1."""
            built = {"n": 0}

            def fake_build_recorder(*a, **k):
                built["n"] += 1
                return _StubRecorder()

            class _AlwaysBoom:
                def __init__(self, *a, **k):
                    raise RuntimeError("construction failed")

                def run(self):
                    pass

                def shutdown(self):
                    pass

            _patch_main_lifecycle(monkeypatch, daemon_cls=_AlwaysBoom)
            monkeypatch.setattr(daemon, "_resolve_device_config",
                                lambda _cfg: dict(daemon.cuda_check.CPU_FALLBACK))  # resolved == cpu
            monkeypatch.setattr(daemon, "build_recorder", fake_build_recorder)

            assert daemon.main() == 1
            assert built["n"] == 0                            # NO retry (first attempt was not cuda)


        def test_main_returns_one_when_cpu_build_also_fails(monkeypatch):
            """cuda construction fails AND the CPU recorder build fails -> return 1 (total failure)."""

            def fake_build_recorder(*a, **k):
                raise RuntimeError("cpu recorder build also failed")

            daemon_cls, attempts = _raise_once_daemon_factory()
            _patch_main_lifecycle(monkeypatch, daemon_cls=daemon_cls)
            monkeypatch.setattr(daemon, "_resolve_device_config",
                                lambda _cfg: dict(daemon.cuda_check.CUDA_DEFAULTS))
            monkeypatch.setattr(daemon, "build_recorder", fake_build_recorder)

            assert daemon.main() == 1
            assert attempts["n"] == 1                         # only the (failed) cuda attempt ran
            # the cpu build raised inside the retry -> propagated to the outer "fatal error" -> return 1


        def test_log_resolved_device_reads_cache_after_cpu_fallback(caplog):
            """_log_resolved_device reports the SEEDED cpu cache, not a fresh driver probe (CRITICAL #4)."""
            d, *_ = _make_daemon()                            # _ok_probe; no cache set
            d._resolved_device_cache = dict(daemon.cuda_check.CPU_FALLBACK)  # simulate main()'s seed
            with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
                d._log_resolved_device()
            line = next(
                (m for m in (r.getMessage() for r in caplog.records) if "device resolved" in m), None
            )
            assert line is not None, "no device-resolved line"
            assert "device=cpu" in line and "compute_type=int8" in line
            assert "final_model=small.en" in line and "realtime_model=tiny.en" in line


        def test_main_fallback_warning_message_matches_prd_44(monkeypatch, caplog):
            """The WARNING names the exact PRD §4.4 CPU config (device/compute_type/models)."""
            daemon_cls, _attempts = _raise_once_daemon_factory()
            _patch_main_lifecycle(monkeypatch, daemon_cls=daemon_cls)
            monkeypatch.setattr(daemon, "_resolve_device_config",
                                lambda _cfg: dict(daemon.cuda_check.CUDA_DEFAULTS))
            monkeypatch.setattr(daemon, "build_recorder",
                                lambda *a, **k: _StubRecorder())
            with caplog.at_level(logging.INFO, logger="voice_typing.daemon"):
                daemon.main()
            warn = next((r for r in caplog.records if r.levelno == logging.WARNING
                         and "falling back to CPU" in r.getMessage()), None)
            assert warn is not None
            msg = warn.getMessage()
            assert "device=cpu" in msg and "compute_type=int8" in msg
            assert "models=small.en/tiny.en" in msg
  - WHY: PART A keeps the "both fail → return 1" contract hermetic; PART B proves the happy fallback
    (return 0, force_cpu=True, recorder= injected, shared latency, logs), the no-retry-when-cpu guard,
    the cpu-build-also-fails path, the _log_resolved_device cache read, and the exact WARNING message.
    All use _patch_main_lifecycle + monkeypatched _resolve_device_config/build_recorder — ZERO real
    CUDA/RealtimeSTT/model-load.
  - DO NOT: call the real build_recorder in any test; redefine _StubRecorder/_make_daemon/_patch_main_
    lifecycle (reuse); modify any existing test other than the BoomDaemon one in PART A.

Task 5: VALIDATE — run the Validation Loop L1-L4 below; fix until all green. No git commit unless the
  orchestrator directs it. If asked, message:
  "P1.M1.T3.S2: construction-failure → CPU retry in main() (force_cpu recorder injection + status cache)".
```

### Implementation Patterns & Key Details

```python
# PATTERN 1 — the construction-failure retry in main() (the core change). The inner try/except isolates
# construction; the cuda guard prevents a pointless CPU→CPU retry; build_recorder(force_cpu=True) skips
# cuda_check (S1); the recorder= injection needs no __init__ change; the cache seed makes status honest.
latency = LatencyLog()                          # shared by recorder callbacks + on_final
try:
    daemon = VoiceTypingDaemon(cfg, feedback, latency=latency)
except Exception as exc:
    if _resolve_device_config(cfg).get("device") != "cuda":
        raise                                   # nothing to fall back to
    cpu_fb = cuda_check.CPU_FALLBACK
    logger.warning("CUDA recorder construction failed (%s); falling back to CPU "
                   "(device=%s, compute_type=%s, models=%s/%s) — degraded but functional",
                   exc, cpu_fb["device"], cpu_fb["compute_type"],
                   cpu_fb["final_model"], cpu_fb["realtime_model"])
    cpu_recorder = build_recorder(cfg, feedback, latency, force_cpu=True)   # S1 capability; skips cuda_check
    daemon = VoiceTypingDaemon(cfg, feedback, latency=latency, recorder=cpu_recorder)
    daemon._resolved_device_cache = dict(cuda_check.CPU_FALLBACK)           # status + startup log say cpu
    logger.info("daemon started in degraded CPU mode (construction-failure fallback)")

# PATTERN 2 — _log_resolved_device reads the cache (so the startup log agrees with status after a fallback).
def _log_resolved_device(self):
    try:
        resolved = self._resolved_device()      # cached; reflects the ACTUAL recorder after a CPU fallback
        logger.info("voice-typing device resolved: device=%s ...", resolved["device"], ...)

# PATTERN 3 — the shared-latency invariant. main() owns the ONE LatencyLog; __init__ stores it
# (self._latency = latency) and uses the injected recorder as-is. The recorder's callbacks (wired by
# build_recorder→_build_callbacks) and on_final.finalize_utterance both touch the SAME collector.
```

### Integration Points

```yaml
UPSTREAM CONSUMED — P1.M1.T3.S1 (force_cpu capability; LANDED):
  - build_recorder(cfg, feedback, latency, force_cpu=True) builds an AudioToTextRecorder with
    device=cpu/int8/small.en/tiny.en WITHOUT calling _resolve_device_config/cuda_check. S2 calls this
    EXACTLY once, only inside the cuda-retry branch. No edit to build_recorder/_construct/cfg_to_kwargs.

DEVICE REPORTING — _resolved_device() / status_snapshot() (cached extension point):
  - _resolved_device() caches via self._resolved_device_cache (getattr/setattr). S2 seeds it with
    dict(cuda_check.CPU_FALLBACK) after a successful CPU retry so status_snapshot() reports device=cpu.
    _log_resolved_device (Task 2) reads the same cache so the startup log agrees. NO change to
    _resolved_device(), status_snapshot(), or VoiceTypingDaemon.__init__.

UNCHANGED (S1 negative constraints carry over):
  - _resolve_device_config @117, cuda_check.py, VoiceTypingDaemon.__init__ @393, build_recorder/
    _construct/cfg_to_kwargs @134-287, _build_callbacks, _filter_kwargs_to_signature, _FIXED_KWARGS.
  - config.toml / config.py / ctl.py / control-socket protocol / launch_daemon.sh / systemd unit.

DOCS — README.md (Mode A, this item):
  - "## CPU-only mode" (+3rd construction-failure way) + "### cuDNN load error" (auto-degrade note).
    P1.M3.T1.S1 (full-changeset README sync) is PLANNED/separate — these additive paragraphs do not
    conflict with it.

BUILD ARTIFACTS:
  - S2 creates NO new files, NO dist/, NO uv.lock/pyproject changes, NO .venv changes. It is a 2-edit
    source patch to daemon.py + a 2-edit README patch + test changes. `uv sync`/`uv build` are NOT run.
```

## Validation Loop

> Full paths in every command (zsh aliases shadow python3/pip on this machine). Run from the repo root
> `/home/dustin/projects/voice-typing`. This project uses pytest (NO ruff/mypy in pyproject — Gotcha #11);
> the gates below are the project's actual tooling. All gates are hermetic/unit: NO real CUDA, NO model
> load, NO real RealtimeSTT (build_recorder is stubbed in the new tests; _resolve_device_config is forced).

### Level 1: the two daemon.py edits are in place (static)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
echo "--- main() has the inner try/except + force_cpu retry + cache seed ---"
grep -n 'force_cpu=True' voice_typing/daemon.py           # EXPECT: exactly 1 (the main() retry call)
grep -n '_resolved_device_cache = dict(cuda_check.CPU_FALLBACK)' voice_typing/daemon.py  # EXPECT: 1 (main seed)
grep -n 'falling back to CPU' voice_typing/daemon.py      # EXPECT: 1 (the WARNING)
grep -n 'degraded CPU mode' voice_typing/daemon.py        # EXPECT: 1 (the success log)
echo "--- _log_resolved_device reads the cache (NOT _resolve_device_config directly) ---"
grep -n 'resolved = self._resolved_device()' voice_typing/daemon.py   # EXPECT: >=1 (inside _log_resolved_device)
echo "--- daemon.py compiles + imports cleanly ---"
"$PY" -m py_compile voice_typing/daemon.py && echo "L1 PASS: py_compile OK" || echo "L1 FAIL: syntax error"
"$PY" -c "import voice_typing.daemon as m; print('L1 PASS: import OK', callable(m.main))" || echo "L1 FAIL"
# Expected: the retry uses force_cpu=True exactly once; the cache is seeded; the WARNING + degraded log
# exist; _log_resolved_device reads self._resolved_device(); py_compile + import clean.
```

### Level 2: scope guards — S1's negative constraints hold (build path + cuda_check untouched)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
"$PY" - <<'PY'
import inspect, pathlib
from voice_typing import daemon, cuda_check
# build_recorder/_construct/cfg_to_kwargs still have S1's force_cpu/resolved (S2 does NOT change them):
assert "force_cpu" in inspect.signature(daemon.build_recorder).parameters
assert "force_cpu" in inspect.signature(daemon._construct).parameters
assert "resolved" in inspect.signature(daemon.cfg_to_kwargs).parameters
print("L2 PASS: S1 build-path surface intact (force_cpu/resolved present)")
# _resolve_device_config + cuda_check are UNCHANGED (no force_cpu added there by S2):
assert "force_cpu" not in inspect.signature(daemon._resolve_device_config).parameters
cc = pathlib.Path("voice_typing/cuda_check.py").read_text()
assert "force_cpu" not in cc, "scope violation: cuda_check.py modified"
assert cuda_check.CPU_FALLBACK == {"device":"cpu","compute_type":"int8",
                                   "final_model":"small.en","realtime_model":"tiny.en"}
print("L2 PASS: _resolve_device_config + cuda_check.py unchanged")
# VoiceTypingDaemon.__init__ still has NO force_cpu (S2 used recorder= injection, not a new param):
assert "force_cpu" not in inspect.signature(daemon.VoiceTypingDaemon.__init__).parameters
assert "recorder" in inspect.signature(daemon.VoiceTypingDaemon.__init__).parameters
print("L2 PASS: __init__ unchanged (no force_cpu); recorder= injection path used")
PY
# Expected: S1 surface intact; _resolve_device_config/cuda_check/__init__ untouched.
```

### Level 3: unit tests — the new section + the modified test + no regression

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
echo "--- the 5 new S2 tests + the modified BoomDaemon test ---"
"$PY" -m pytest tests/test_daemon.py -v \
  -k "construction_failure or cpu_retry or cpu_build or resolved_device_reads_cache or fallback_warning or falls_back_to_cpu or skips_cpu_retry" \
  -p no:cacheprovider 2>&1 | tail -20
echo "--- the FULL test_daemon.py suite (backward compat: every prior test still green) ---"
"$PY" -m pytest tests/test_daemon.py -v -p no:cacheprovider 2>&1 | tail -25
echo "--- the rest of the fast suite (cross-file regression) ---"
"$PY" -m pytest tests/ -p no:cacheprovider 2>&1 | tail -15
# Expected: all new S2 tests pass; the modified test_main_returns_one_on_daemon_construction_failure
# passes (== 1); every pre-existing test passes (no regression). If a pre-existing main() test fails,
# re-check that the normal path (first attempt succeeds) never enters the retry branch and never calls
# _resolve_device_config (it must not — _resolve_device_config is ONLY in the except branch).
```

### Level 4: behavior proof — the retry logic is correct (hermetic, no real CUDA)

```bash
cd /home/dustin/projects/voice-typing
PY=.venv/bin/python
# The AUTHORITATIVE behavior proof is the pytest suite (Task 4 PART B), which asserts the 4 outcomes
# hermetically (build_recorder + _resolve_device_config monkeypatched — ZERO real CUDA/RealtimeSTT):
#   (1) cuda fail -> force_cpu retry -> return 0 (test_main_falls_back_to_cpu_on_cuda_construction_failure)
#   (2) not-cuda first attempt -> no retry -> return 1  (test_main_skips_cpu_retry_when_resolved_device_not_cuda)
#   (3) cuda fail + cpu build fail -> return 1          (test_main_returns_one_when_cpu_build_also_fails)
#   (4) _log_resolved_device reports the seeded cpu cache (test_log_resolved_device_reads_cache_after_cpu_fallback)
#   (+) the WARNING names the exact PRD §4.4 config      (test_main_fallback_warning_message_matches_prd_44)
# This gate is a focused re-run of exactly those tests (they are the behavior contract):
"$PY" -m pytest tests/test_daemon.py -v -p no:cacheprovider \
  -k "falls_back_to_cpu or skips_cpu_retry or cpu_build_also or resolved_device_reads_cache or fallback_warning" \
  2>&1 | tail -15
# Expected: all 5 pass. If any fails, READ the assertion + fix the implementation (NOT the test — the
# tests are the spec). Common failure: forgot the cache seed (status/log report cuda) or the cuda guard
# (retries a cpu config) or the latency sharing (recorder callbacks on a different LatencyLog).
```

## Final Validation Checklist

### Technical Validation
- [ ] L1: main() has the inner try/except + `build_recorder(..., force_cpu=True)` + cache seed + WARNING
      + degraded log; `_log_resolved_device` reads `self._resolved_device()`; py_compile + import clean.
- [ ] L2: S1 build-path surface intact; `_resolve_device_config`/`cuda_check.py`/`__init__` untouched.
- [ ] L3: all 5 new S2 tests + the modified BoomDaemon test pass; full `tests/test_daemon.py` + `tests/`
      green (no regression).
- [ ] L4: the 5 behavior-contract tests pass (cuda-fail→return 0; not-cuda→return 1; cpu-build-fail→return 1; cache-driven startup log; exact WARNING message).

### Feature Validation
- [ ] CUDA construction failure (resolved device cuda) → retry with `force_cpu=True` → daemon runs →
      `main()` returns 0 (no systemd crash-loop).
- [ ] The WARNING logs the exact PRD §4.4 config (device=cpu, compute_type=int8, models=small.en/tiny.en)
      and "degraded but functional"; followed by "daemon started in degraded CPU mode".
- [ ] After a successful CPU fallback, `status_snapshot()` AND the startup log report device=cpu/int8/
      small.en/tiny.en (cache seeded + `_log_resolved_device` reads cache).
- [ ] Non-cuda first attempt → no retry → return 1.
- [ ] CPU retry also fails (build or re-construction raises) → "fatal error" → return 1.
- [ ] README "CPU-only mode" (3 ways) + "cuDNN load error" (auto-degrade note) document the behavior.

### Code Quality Validation
- [ ] `recorder=` injection used (NO `force_cpu` added to `VoiceTypingDaemon.__init__`).
- [ ] ONE shared `LatencyLog` across both attempts (callbacks + finalize_utterance on the same collector).
- [ ] CPU config sourced from `cuda_check.CPU_FALLBACK` (no hardcoded drift) for both the log + cache.
- [ ] The cache seed is the documented `_resolved_device_cache` extension point (no `__init__` edit).
- [ ] New tests are ADDITIVE (banner section); only the BoomDaemon test is modified (hermeticity only;
      assertion preserved); all reuse existing `_StubRecorder`/`_patch_main_lifecycle`/`_make_daemon`.

### Scope Boundary Validation
- [ ] No change to `build_recorder`/`_construct`/`cfg_to_kwargs`, `cuda_check.py`, `_resolve_device_config`,
      `VoiceTypingDaemon.__init__`, `_resolved_device()`, `status_snapshot()`, `_build_callbacks`,
      `_filter_kwargs_to_signature`, `_FIXED_KWARGS`.
- [ ] No `config.toml`/`config.py` field, no control-socket protocol change, no `ctl.py`/systemd/
      launch_daemon.sh change.
- [ ] README edits are Mode A (this item's behavior); no other doc files touched.

---

## Anti-Patterns to Avoid

- ❌ Don't add `force_cpu` to `VoiceTypingDaemon.__init__` — S1 mandates the `recorder=` injection.
- ❌ Don't forget the cache seed — without it `status_snapshot` lies (reports cuda while on cpu).
- ❌ Don't leave `_log_resolved_device` calling `_resolve_device_config` directly — journalctl would
  contradict the fallback WARNING (log cuda after "falling back to CPU").
- ❌ Don't create two `LatencyLog` instances — the recorder callbacks and `on_final` must share one.
- ❌ Don't retry when the first attempt wasn't cuda (a cpu config has nothing to fall back to).
- ❌ Don't call the real `build_recorder` in tests — stub it (it imports RealtimeSTT + loads models).
- ❌ Don't hardcode `{'device':'cpu',...}` — source it from `cuda_check.CPU_FALLBACK`.
- ❌ Don't modify the BoomDaemon test's `assert daemon.main() == 1` — only add hermeticity monkeypatches.
- ❌ Don't catch the inner exception too broadly such that the cpu-retry failure is swallowed — it MUST
  propagate to the outer `except Exception` → "fatal error" → return 1.
