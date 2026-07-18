# Research — P1.M1.T4.S1: Audit cuda_check probe & CPU fallback vs PRD §4.4

> An audit/verification task (mirrors P1.M1.T3.S1's `gap_<module>.md` pattern). The deliverable is
> a gap report (`plan/006_862ee9d6ef41/architecture/gap_cuda_check.md`); the expected verdict is
> **COMPLIANT — no source change**. This PRP's author has performed the full audit (findings below);
> the implementing agent re-verifies the greps + pytest + the ctranslate2 probe, then transcribes.

## §0 — VERIFIED VERDICT: cuda_check.py + daemon consumption are PRD §4.4-COMPLIANT (no fix needed)

Every PRD §4.4 requirement + every contract point is satisfied, each with file:line evidence (§1),
the 7 path tests pass (§2), and the live machine probe confirms `ctranslate2.get_cuda_device_count()
== 1` (§3). The single documented divergence — `get_cuda_device_count()` probes the driver only, NOT
cuDNN — is an explicit, documented LIMITATION (cuda_check.py docstring), not a defect, and the
daemon has a construction-failure → CPU retry path to absorb it (§4-obs1).

## §1 — The audit points, mapped to PRD §4.4 + the contract (with file:line)

| # | PRD §4.4 / contract requirement | code actual (file:line) | result |
|---|----------------------------------|--------------------------|--------|
| (a) | Probe CUDA via `ctranslate2.get_cuda_device_count()` | `cuda_check._cuda_device_count()` (count==0 on ANY failure); `is_cuda_available()` returns `count >= 1` | ✅ |
| (b) | CUDA fail → `device="cpu", compute_type="int8", realtime_model_type="tiny.en", model="small.en"` | `CPU_FALLBACK = {device:cpu, compute_type:int8, final_model:small.en, realtime_model:tiny.en}` (cuda_check.py module-level dict) | ✅ EXACT match |
| (c) | Probe returns a dict with device + compute_type + (CPU) downgraded model names | `resolve_device_and_models()` returns `{device, compute_type, final_model, realtime_model}` (fresh dict) — CPU path returns `dict(CPU_FALLBACK)`, cuda path returns `dict(defaults)` | ✅ |
| (d) | Lite-mode CPU substitute is `tiny.en` | daemon.py `cfg_to_kwargs` lite branch ~L192: `lite_model = "tiny.en" if resolved["device"] == "cpu" else cfg.asr.lite_model`; sets BOTH final_model + realtime_model to it | ✅ (pinned by test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en) |
| (e) | daemon `_resolve_device_config` / `cfg_to_kwargs` consume cuda_check output | daemon.py:141 `_resolve_device_config(cfg)` → `cuda_check.resolve_device_and_models(defaults)`; daemon.py:158 `cfg_to_kwargs(cfg, resolved=None, lite=False)` consumes the resolved dict | ✅ |
| (f) | daemon logs the resolved device at startup ("log clearly and fall back") | daemon.py:918 `_log_resolved_device()` → `logger.info("voice-typing device resolved: device=%s compute_type=%s final_model=%s realtime_model=%s", ...)` | ✅ |
| (g) | daemon "says so in status" | daemon.py:1558 `status_snapshot()` returns `device/compute_type/final_model/realtime_model` from `_resolved_device()` (the cache) | ✅ |
| (h) | machine: ctranslate2 CUDA count ≥ 1 | LIVE PROBE (§3): `cuda_device_count = 1`, version 4.8.1, `VERDICT=cuda-ok` | ✅ |
| (i) | single resolution site (no bypass) | `resolve_device_and_models()` is the ONLY override; `_resolve_device_config` is its sole caller; drain uses fixed `_DRAIN_TIMEOUT_S=5.0`; idle auto-stop uses separate `auto_stop_idle_seconds` (system_context — lite-gate audit) | ✅ |

## §2 — Test coverage (the contract's verification gate)

- **No dedicated `tests/test_cuda_check.py`** — cuda_check is covered via `tests/test_daemon.py`'s
  `cfg_to_kwargs` suite, which monkeypatches `daemon.cuda_check.resolve_device_and_models` onto a
  deterministic path (the `_cuda_resolve(monkeypatch, mapping)` helper @81-99).
- **The load-bearing path tests** (file:line):
  - `test_cfg_to_kwargs_cuda_path` @129 (cuda defaults → device=cuda/float16/distil-large-v3/small.en)
  - `test_cfg_to_kwargs_cpu_fallback` @156 (CPU_FALLBACK → device=cpu/int8/small.en/tiny.en)
  - `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en` @165 (lite + CPU → tiny.en for BOTH models) ← point (d)
  - `test_cfg_to_kwargs_lite_mode_uses_one_model` @138 (lite → single model, use_main_model_for_realtime=True)
  - `test_cfg_to_kwargs_fixed_values` @234 (the §4.4 FIXED kwargs: silero_backend/post_speech/no_log_file/...)
- **RUN (this round):** `.venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs and (cuda or
  cpu or lite or fixed)"` → **7 passed, 186 deselected in 0.02s** (exit 0).
- **NOTE:** `cuda_check._main()` (the CLI smoke) is NOT unit-tested — it is a thin diagnostic printer.
  Its logic (`_cuda_device_count`/`is_cuda_available`/`resolve_device_and_models`) IS exercised via the
  cfg_to_kwargs suite (monkeypatched). The CLI is verified empirically by running the module directly
  (§3). This is a non-blocking observation (the CLI is operator-facing diagnostics, not a contract surface).

## §3 — The live machine probe (RTX 3080 Ti, driver 610.43.02, CUDA UMD 13.3)

```
$ timeout 60 .venv/bin/python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"
cuda_device_count = 1
version = 4.8.1
exit=0

$ timeout 60 .venv/bin/python -m voice_typing.cuda_check
ctranslate2_version=4.8.1
cuda_device_count=1
torch_cuda_available=True
VERDICT=cuda-ok
# 1 cuda device(s) visible to ctranslate2
# resolved: device=cuda compute_type=float16 final_model=distil-large-v3 realtime_model=small.en
exit=0
```

→ count ≥ 1 (contract satisfied); the CUDA path resolves to the PRD §4.4 "exact starting values"
(device=cuda, compute_type=float16, final_model=distil-large-v3, realtime_model=small.en). The
CPU_FALLBACK path is covered by the monkeypatched tests (§2) since this machine HAS CUDA (so the
live probe cannot exercise the fallback — that's why the tests mock `resolve_device_and_models`).

## §4 — config.py defaults (the inputs cuda_check receives)

`voice_typing/config.py:50-57` `AsrConfig`:
- `final_model: str = "distil-large-v3"` @52
- `realtime_model: str = "small.en"` @53
- `lite_model: str = "small.en"` @54 (PRD §4.2ter)
- `device: str = "cuda"` @57 ("cuda" | "cpu"; daemon may override via cuda_check at startup)
- `compute_type` is NOT a config field (cuda_check concern) — `_resolve_device_config` derives it:
  `"float16" if cfg.asr.device == "cuda" else "int8"` (daemon.py:151)
- VT-005 device validation @105-114: rejects anything other than "cuda"/"cpu".

These flow into `_resolve_device_config` as the `defaults` passed to
`cuda_check.resolve_device_and_models(defaults)`, which returns them verbatim on cuda-ok OR
overrides wholesale with CPU_FALLBACK on no-cuda.

## §5 — The architectural nuance: cuda_check resolution runs in the CHILD (VT-001)

This is the most important thing for the auditor to record correctly (it is NOT a defect — it is a
deliberate invariant):

- **The daemon PROCESS never probes CUDA.** `daemon.VoiceTypingDaemon._resolved_device()`
  (daemon.py:1597) ONLY returns `_resolved_device_cache`; it NEVER calls `_resolve_device_config`
  or `cuda_check`. This is invariant **VT-001** (the recorder-host subprocess architecture's core:
  keep the daemon process CUDA-context-free).
- **The cache is seeded in three places**, all WITHOUT probing:
  1. `__init__` → `_unprobed_device_config()` (daemon.py:1604): the config-derived device
     (compute_type derived from `cfg.asr.device`), used until the child reports.
  2. on every successful `_load_host()` → the CHILD's actual resolved device
     (`_child_resolved_device()` performs the real cuda_check resolution + seeds the cache on arm).
  3. on host death / idle-unload (VT-002) → reseeded to `_unprobed_device_config()`.
- **Where does `resolve_device_and_models` actually run?** In the **recorder-host child
  subprocess**, via `cfg_to_kwargs()` → `build_recorder()` (the child constructs the recorder). The
  daemon's `_resolve_device_config`/`cfg_to_kwargs` are the SHARED building blocks; the child calls
  them. `status_snapshot` then reports whatever the child last seeded into the cache.
- **Consequence for "say so in status":** before the first successful arm, `status_snapshot`
  reports the CONFIGURED intent (e.g. device=cuda), qualified by `models_loaded=False` /
  `phase=unloaded`. After arm, it reports the child's ACTUAL resolved device (cuda or cpu-fallback).
  This is correct + intentional — the daemon cannot know the child's verdict until the child arms.
- **Construction-failure CPU retry (bugfix Issue 3 / force_cpu):** if the child's WhisperModel
  construction fails (e.g. cuDNN missing despite cuda-ok), `main()` seeds
  `_resolved_device_cache` with `dict(cuda_check.CPU_FALLBACK)` and rebuilds — so `_log_resolved_device`
  then logs the ACTUAL cpu recorder (not the driver probe, which still sees the GPU). This closes the
  §4-obs1 cuDNN gap. daemon.py:302-311 is the force_cpu path.

## §6 — Non-blocking observations (record in the report; neither is a defect)

- **obs1 — the cuDNN limitation (documented).** `cuda_check.py` module docstring LIMITATION +
  `_cuda_device_count()` docstring: `get_cuda_device_count()` queries the CUDA **driver** only — it
  does NOT load cuDNN. A missing `libcudnn_ops.so.9` therefore still yields `VERDICT=cuda-ok`, and
  the failure surfaces later at `WhisperModel` construction in the daemon. The
  `launch_daemon.sh` LD_LIBRARY_PATH wrapper (P1.M4.T2) is what makes cuDNN findable; the daemon's
  force_cpu → CPU_FALLBACK retry (§5) absorbs a construction failure. This is BY DESIGN (probing
  cuDNN would require importing the heavy whisper stack), documented, and mitigated — NOT a defect.
- **obs2 — `is_cuda_available()` is the gate, not torch.** `_torch_cuda_available()` is a
  NICE-TO-HAVE diagnostic (only Silero VAD uses torch, and it runs fine on CPU); it does NOT gate
  the verdict. The MUST-HAVE gate is `ctranslate2` (the whisper inference engine). Documented in
  the module docstring. Non-blocking — record so a future reader doesn't "promote" torch to a gate.
- **obs3 — the CLI `_main()` is operator-facing, not unit-tested.** `python -m voice_typing.cuda_check`
  prints diagnostics + a greppable `VERDICT=` line (exit 0=cuda-ok / 1=cpu-fallback-required). It is
  verified empirically (§3), not by a unit test. Its logic is covered via the cfg_to_kwargs suite.
  Non-blocking — the CLI is diagnostics, not a contract surface.

## §7 — Scope discipline + parallel no-conflict

**IN scope (this audit):**
- `voice_typing/cuda_check.py` (the probe + CUDA_DEFAULTS/CPU_FALLBACK + resolve_device_and_models).
- daemon.py consumption: `_resolve_device_config` (141-156), `cfg_to_kwargs` (158-235, esp. lite CPU
  branch ~192), `_log_resolved_device` (918-940), `status_snapshot` + `_resolved_device` +
  `_unprobed_device_config` (1558-1620), force_cpu path (302-311).
- `tests/test_daemon.py` cfg_to_kwargs path tests (the contract's run target).
- The deliverable: `plan/006_862ee9d6ef41/architecture/gap_cuda_check.md` (mirror the
  gap_config.md/gap_textproc.md/gap_typing.md convention).

**OUT of scope (do NOT touch):**
- `launch_daemon.sh` LD_LIBRARY_PATH/cuDNN discovery → P1.M4.T2 (planned). The cuDNN finding (§6-obs1)
  is NOTED here for cross-reference but its remediation (if any) is that task's scope.
- config.py schema → P1.M1.T1 (complete). typing_backends → P1.M1.T3 (parallel). textproc → P1.M1.T2.
- The recorder-host subprocess lifecycle → P1.M2.T2 (planned). The VT-001 nuance (§5) is the
  recorder-host architecture's invariant; this audit RECORDS it, it does not change it.
- DOCS: none (internal module). CPU-only instructions are in README (Mode A — P1.M6.T1).
- Read-only: PRD.md, tasks.json, prd_snapshot.md, .gitignore.

**Parallel — P1.M1.T3.S1 (typing_backends audit, in flight):** DISJOINT files (cuda_check.py +
daemon.py consumption vs typing_backends.py). Both write a `gap_<module>.md` under `architecture/`
(cuda_check vs typing). No merge conflict.

## §8 — Validation tooling & machine gotchas

- **pytest ONLY.** This project has NO ruff/mypy. Validation = pytest + grep + the ctranslate2 probe.
  Do NOT invent ruff/mypy gates (the PRP template's ruff/mypy L1 lines are N/A).
- **Use full paths.** zsh aliases `python3`→`uv run`, `pip`→alias. Invoke `.venv/bin/python`
  explicitly. Never bare python/pytest/uv.
- **WRAP the ctranslate2 probe in a timeout.** It is a quick import + count (no model load, ~1s),
  but per repo AGENTS.md Rule 1 EVERY non-trivial command gets an inner `timeout` + the bash-tool
  `timeout`. Use `timeout 60 .venv/bin/python -c ...` (inner) and set the bash-tool `timeout` above it.
- **Do NOT run/restart the live daemon or voicectl.** This audit is read-only: read cuda_check.py +
  daemon.py, run the monkeypatched test suite (no CUDA/driver probe — tests mock resolve_device_and_models),
  and run the cuda_check CLI smoke once (it imports ctranslate2 + queries the driver — no model load,
  no daemon). No systemd, no socket.