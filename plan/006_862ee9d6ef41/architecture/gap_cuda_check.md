# Gap Report — P1.M1.T4.S1: cuda_check Probe & CPU Fallback vs PRD §4.4

**Date:** 2025-01 (audit re-verified against the live tree)
**Scope:** Audit `voice_typing/cuda_check.py` (the CUDA probe + `CUDA_DEFAULTS`/`CPU_FALLBACK` +
`resolve_device_and_models`) **and** its daemon consumption points (`_resolve_device_config`,
`cfg_to_kwargs`, `_log_resolved_device`, `status_snapshot`, `_resolved_device`,
`_unprobed_device_config`, the `force_cpu` retry) against **PRD §4.4** (the CUDA-probe / CPU-fallback
contract). Subtask **P1.M1.T4.S1** of verification round `006_862ee9d6ef41`.
**Audited artifacts (all read-only):**
- `voice_typing/cuda_check.py` — the probe (`_cuda_device_count`, `is_cuda_available`) + the two
  module dicts (`CUDA_DEFAULTS`, `CPU_FALLBACK`) + the single resolution site
  (`resolve_device_and_models`) + the `_main()` CLI smoke.
- `voice_typing/daemon.py` (read for the **5 cuda_check consumption points ONLY** — not the main
  loop / recorder-host lifecycle, which is P1.M2.T1/T2 scope): `_resolve_device_config` (L141),
  `cfg_to_kwargs` (L158), `_log_resolved_device` (L919), `status_snapshot` (L1548),
  `_resolved_device` (L1582), `_unprobed_device_config` (L1604), and the `force_cpu` retry path
  (L289-311).
- `tests/test_daemon.py` — the `cfg_to_kwargs` path suite (the contract's run target; cuda_check is
  covered indirectly via the `_cuda_resolve` monkeypatch helper @81).

**Bottom line:** ✅ All 7 PRD §4.4 contract points are **compliant** (each with file:line evidence
below). The live machine probe confirms `ctranslate2.get_cuda_device_count() == 1` / `VERDICT=cuda-ok`,
and the `cfg_to_kwargs` path suite is **7 passed** (0 failed). The architectural nuance — **VT-001:
the daemon process never probes CUDA** (the recorder-host child owns the resolution) — is recorded
as the deliberate design it is, **not** a defect. **No source files were modified.** The only new
artifact is this report.

---

## 1. Method

Each of PRD §4.4's contract points ((a) probe via `ctranslate2.get_cuda_device_count()`; (b) CPU
fallback = `device=cpu, compute_type=int8, realtime_model_type=tiny.en, model=small.en`; (c) the
probe returns a dict with device+compute_type+downgraded models; (d) lite-mode CPU substitute =
`tiny.en`; (e) the daemon consumes cuda_check output at startup; (f) the daemon logs the resolved
device; (g) the daemon surfaces the device in `status`) was mapped to **specific `cuda_check.py` /
`daemon.py` file:line** via `grep -nE`. The probe gate was then verified **empirically** (the live
`ctranslate2.get_cuda_device_count()` probe + the `cuda_check` CLI smoke, §3) **and** via the
hermetic unit suite (`tests/test_daemon.py` `cfg_to_kwargs` path tests, §4 —
`resolve_device_and_models` is monkeypatched, so the CPU-fallback branch is exercised deterministically
even on a CUDA machine).

### Commands run (re-verification)

```bash
# (a)-(c): cuda_check.py — the probe + the two configs + the resolution site
grep -nE 'get_cuda_device_count|def is_cuda_available' voice_typing/cuda_check.py
grep -nE 'CPU_FALLBACK\s*:|"device":\s*"cpu"|"compute_type":\s*"int8"|"final_model":\s*"small.en"|"realtime_model":\s*"tiny.en"' voice_typing/cuda_check.py
grep -nE 'def resolve_device_and_models|return dict\(defaults\)|return dict\(CPU_FALLBACK\)' voice_typing/cuda_check.py
# (d)-(g): daemon.py — the 5 consumption points
grep -nE 'lite_model = "tiny.en" if resolved\["device"\] == "cpu"' voice_typing/daemon.py
grep -nE 'def _resolve_device_config|return cuda_check.resolve_device_and_models|def cfg_to_kwargs' voice_typing/daemon.py
grep -nE 'def _log_resolved_device|voice-typing device resolved' voice_typing/daemon.py
grep -nE 'def status_snapshot|def _resolved_device' voice_typing/daemon.py
# (h): the LIVE machine probe + the contract's verification gate
timeout 60 .venv/bin/python -c "import ctranslate2; print('cuda_device_count =', ctranslate2.get_cuda_device_count())"
timeout 60 .venv/bin/python -m voice_typing.cuda_check
.venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs and (cuda or cpu or lite or fixed)"
```

All commands are re-runnable from this section; no daemon / socket / audio / display was needed
(the audit reads source, runs monkeypatched tests, and runs the `cuda_check` CLI smoke once — it
imports ctranslate2 + queries the driver; no model load).

---

## 2. Per-Point Compliance Table (PRD §4.4 / contract vs code)

> PRD §4.4 (the authority): *"If CUDA init fails entirely, daemon MUST log clearly and fall back to
> `device=cpu, compute_type=int8` with `realtime_model_type=tiny.en`, model `small.en` — degraded but
> functional — and say so in `status`."*

| # | PRD §4.4 / contract requirement | code actual (file:line — re-verified live) | Match |
|---|----------------------------------|---------------------------------------------|-------|
| (a) | CUDA probe via `ctranslate2.get_cuda_device_count()` | `cuda_check._cuda_device_count()` wraps the import + the call in `try/except`, returns `count==0` on **ANY** failure (cuda_check.py:62-81); `is_cuda_available()` returns `_cuda_device_count()[0] >= 1` (cuda_check.py:105-109) | ✅ |
| (b) | CPU fallback = `device=cpu, compute_type=int8, realtime=tiny.en, model=small.en` | `CPU_FALLBACK` module dict (cuda_check.py:53-58): `{"device":"cpu","compute_type":"int8","final_model":"small.en","realtime_model":"tiny.en"}` | ✅ **EXACT** match |
| (c) | probe returns a dict with `device + compute_type + (downgraded) model names` | `resolve_device_and_models()` (cuda_check.py:114-132): cuda path `return dict(defaults)` (:130); CPU path `return dict(CPU_FALLBACK)` (:131). Always a **fresh dict** the caller may mutate. | ✅ |
| (d) | lite-mode CPU substitute = `tiny.en` | daemon.py `cfg_to_kwargs` lite branch (daemon.py:188-191): `lite_model = "tiny.en" if resolved["device"] == "cpu" else cfg.asr.lite_model`; sets **both** `final_model` + `realtime_model` to it (:192-193). Pinned by `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en`. | ✅ |
| (e) | daemon `_resolve_device_config` / `cfg_to_kwargs` consume cuda_check output | daemon.py:141 `_resolve_device_config(cfg)` builds `defaults` from cfg (compute_type **derived** @151) → `return cuda_check.resolve_device_and_models(defaults)` (daemon.py:155); daemon.py:158 `cfg_to_kwargs(cfg, *, resolved=None, lite=False)` consumes the resolved dict | ✅ |
| (f) | daemon logs the resolved device at startup ("log clearly and fall back") | daemon.py:919 `_log_resolved_device()` → `logger.info("voice-typing device resolved: device=%s compute_type=%s final_model=%s realtime_model=%s", ...)` (daemon.py:932-938); defensive `except` logs "(resolution failed; see cuda_check logs)" (:940) | ✅ |
| (g) | daemon "says so in status" | daemon.py:1548 `status_snapshot()` returns `device/compute_type/final_model/realtime_model` from `self._resolved_device()` (daemon.py:1559 `dev = self._resolved_device()`, mapped at :1569-1572) | ✅ |
| (h) | machine: `ctranslate2.get_cuda_device_count() >= 1` (RTX 3080 Ti) | **LIVE** (§3): `cuda_device_count = 1`, version 4.8.1, `VERDICT=cuda-ok`; resolved CUDA config = `device=cuda, compute_type=float16, final_model=distil-large-v3, realtime_model=small.en` | ✅ |

> `daemon.py` line numbers are `grep -n`-verified against the **live** tree. `_resolve_device_config`
> (L141) and `cfg_to_kwargs` (L158) match the PRP's embedded references exactly;
> `_log_resolved_device` is at **L919** (research note said ~L918), `status_snapshot` at **L1548**
> (research said ~L1558), `_resolved_device` at **L1582** (research said ~L1597),
> `_unprobed_device_config` at **L1604** (research said ~L1604), and the `force_cpu` retry at
> **L289-311** (research said ~L302-311). These small deltas reflect a live re-verification against
> the current tree; the report cites the **verified** line numbers.

---

## 3. Live Machine Probe (RTX 3080 Ti, driver 610.43.02, CUDA UMD 13.3)

```
$ timeout 60 .venv/bin/python -c "import ctranslate2; print('cuda_device_count =', ctranslate2.get_cuda_device_count())"
cuda_device_count = 1
exit=0

$ timeout 60 .venv/bin/python -m voice_typing.cuda_check
ctranslate2_version=4.8.1
cuda_device_count=1
torch_cuda_available=True
VERDICT=cuda-ok
# 1 cuda device(s) visible to ctranslate2
# resolved: device=cuda compute_type=float16 final_model=distil-large-v3 realtime_model=small.en
exit=0 (0=cuda-ok, 1=cpu-fallback-required)
```

→ `count >= 1` (contract point (h) satisfied); the CUDA path resolves to the exact PRD §4.4
"starting values" (`device=cuda, compute_type=float16, final_model=distil-large-v3,
realtime_model=small.en`). **This machine HAS CUDA, so the live probe exercises the CUDA path
only.** The `CPU_FALLBACK` path (point (b)) is covered by the hermetic unit suite (§4), which
monkeypatches `resolve_device_and_models` onto a deterministic CPU path — that is precisely **why**
the tests mock the resolution function instead of probing the driver.

---

## 4. Test-Suite Result (the contract's run target)

```
$ .venv/bin/python -m pytest tests/test_daemon.py -q -k "cfg_to_kwargs and (cuda or cpu or lite or fixed)"
.......                                                                  [100%]
7 passed, 186 deselected in 0.03s
```

**7 passed, 0 failed, 0 errors** (matches the verified baseline). The suite is **hermetic** — the
`_cuda_resolve(monkeypatch, mapping)` helper (tests/test_daemon.py:81-99) monkeypatches
`daemon.cuda_check.resolve_device_and_models` onto a deterministic path, so **no real CUDA/driver
probe runs in the tests**. The load-bearing path tests:

| Test (tests/test_daemon.py) | line | Asserts (the contract point it pins) |
|---|---|---|
| `test_cfg_to_kwargs_cuda_path` | ~129 | cuda defaults → `device=cuda/float16/distil-large-v3/small.en` |
| `test_cfg_to_kwargs_cpu_fallback` | ~156 | `CPU_FALLBACK` → `device=cpu/int8/small.en/tiny.en` (point (b)) |
| `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en` | ~165 | lite + CPU → `tiny.en` for **both** models (point (d)) |
| `test_cfg_to_kwargs_lite_mode_uses_one_model` | ~138 | lite → single model, `use_main_model_for_realtime=True` |
| `test_cfg_to_kwargs_fixed_values` | ~234 | the §4.4 **FIXED** kwargs (silero_backend / post_speech / no_log_file / ...) |

**Coverage boundary (recorded so it is not over-trusted).** The `cfg_to_kwargs` suite pins
**behavior** (resolved dict → kwargs) but monkeypatches `resolve_device_and_models`, so it does **not**
exercise the real probe and does **not** explicitly map each assertion to "PRD §4.4 point (a)-(g)." A
future refactor could pass the suite yet drift from the PRD's exact `CPU_FALLBACK` values. **This
audit (S1) is the PRD-compliance check the unit suite cannot perform** — it is the human/agent
verification that closes that mapping gap. This boundary is the mirror of gap_config.md §7 (the drift
guard checks agreement, not spec compliance).

---

## 5. Architectural Note — VT-001: The Daemon Process Never Probes CUDA

**This is the single most important section of this report:** it records the deliberate invariant
that cuda_check's resolution runs in the **recorder-host child subprocess**, not the daemon process
itself — so that no future agent "fixes" status to probe CUDA directly (which would re-introduce a
CUDA context in the daemon process, the exact regression VT-001 exists to prevent).

**The invariant.** `daemon.VoiceTypingDaemon._resolved_device()` (daemon.py:1582-1602) **ONLY returns
`_resolved_device_cache`**; it **NEVER** calls `_resolve_device_config` or `cuda_check`. Its docstring
(daemon.py:1584-1595) states this explicitly: *"VT-001: the daemon process MUST NEVER probe CUDA ...
this method ONLY returns the cache; it NEVER calls _resolve_device_config / cuda_check."*

**Where the cache is seeded (all WITHOUT probing):**

| Seed site (daemon.py file:line) | When | Value |
|---|---|---|
| `__init__` (daemon.py:573) | daemon construction | `_unprobed_device_config()` — config-derived (compute_type from `cfg.asr.device`) |
| `_load_host()` success (daemon.py:771) | every successful child arm | the CHILD's actual resolved device (`_child_resolved_device()` performs the real cuda_check resolution in the child) |
| host death / idle-unload (daemon.py:904, :1248) | VT-002 unload | reseeded to `_unprobed_device_config()` |

**Where does `resolve_device_and_models` actually run?** In the **recorder-host child subprocess**,
via `cfg_to_kwargs()` → `build_recorder()` (the child constructs the recorder). The daemon's
`_resolve_device_config` / `cfg_to_kwargs` are the **shared building blocks**; the child calls them.
`status_snapshot` then reports whatever the child last seeded into the cache.

**Consequence for "say so in status" (point (g)).** Before the first successful arm,
`status_snapshot` reports the **configured intent** (e.g. `device=cuda`), qualified by
`models_loaded=False` / `phase=unloaded`. After arm, it reports the child's **actual** resolved device
(cuda or cpu-fallback). **This is correct and intentional** — the daemon cannot know the child's
verdict until the child arms. Recording this so it is **not** mistaken for a defect: ❌ do **not**
report "the daemon doesn't probe CUDA at startup" or "status shows cuda before arm" as a gap.

**Construction-failure CPU retry (`force_cpu`).** If the child's `WhisperModel` construction fails
(e.g. cuDNN missing despite `cuda-ok`), the daemon's `_construct(..., force_cpu=True)` (daemon.py:289)
seeds `resolved = dict(cuda_check.CPU_FALLBACK)` (daemon.py:310) and rebuilds — so `_log_resolved_device`
then logs the **actual** cpu recorder (not the driver probe, which still sees the GPU). This closes
the cuDNN-limitation gap (§6-obs1). The `force_cpu` path passes `dict(cuda_check.CPU_FALLBACK)` as
`resolved` to `cfg_to_kwargs`, **skipping** `_resolve_device_config`/the driver probe entirely.

---

## 6. Mismatches / Drift / Non-Blocking Observations

**None — fully PRD §4.4-compliant.** All 7 contract points (a)-(g) pass with file:line evidence
(§2); the live probe confirms `count=1` (§3); the unit suite is 7 passed (§4); the VT-001 invariant
is correct-by-design (§5). **No source files were modified.**

The three non-blocking observations below are recorded so a future reader does **not** mistake them
for defects (or "fix" the probe to load cuDNN / promote torch to a gate):

### obs1 — The cuDNN limitation (DOCUMENTED + mitigated, NOT a defect)

`cuda_check.py` module docstring (LIMITATION, cuda_check.py:31-37) + `_cuda_device_count()` docstring
(cuda_check.py:67): `get_cuda_device_count()` queries the CUDA **driver** only — it does **NOT** load
cuDNN. A missing `libcudnn_ops.so.9` therefore still yields `VERDICT=cuda-ok`, and the failure
surfaces later at `WhisperModel` construction in the daemon. The `launch_daemon.sh` LD_LIBRARY_PATH
wrapper (P1.M4.T2) is what makes cuDNN findable; the daemon's `force_cpu → CPU_FALLBACK` retry (§5)
absorbs a construction failure. This is **by design** (probing cuDNN would require importing the
heavy whisper stack into the probe), **documented** in the module docstring, and **mitigated** by the
retry — **NOT a defect**. cuDNN discovery is `launch_daemon.sh` (P1.M4.T2) scope; cross-referenced
here only. `cuda_check` MUST NOT set `LD_LIBRARY_PATH` itself (ld.so reads it only at exec — module
docstring cuda_check.py:8-11).

### obs2 — `is_cuda_available()` is the gate, NOT torch (DOCUMENTED, NOT a defect)

`_torch_cuda_available()` (cuda_check.py:96-102) is a **nice-to-have** diagnostic probe (only Silero
VAD uses torch, and it runs fine on CPU); it does **NOT** gate the verdict. The MUST-HAVE gate is
`ctranslate2` (the whisper inference engine) — `is_cuda_available()` checks ctranslate2 **only**
(cuda_check.py:105-109). Documented in the module docstring (cuda_check.py:27-29). Non-blocking —
recorded so a future reader does not "promote" torch to a gate (which would mis-fallback on a
torch-only failure). The CLI prints `torch_cuda_available=` for diagnostics, but the `VERDICT=` line
derives from `is_cuda_available()` (ctranslate2) alone.

### obs3 — The CLI `_main()` is operator-facing, NOT unit-tested (DOCUMENTED, NOT a defect)

`cuda_check._main()` (cuda_check.py:142-175) is a thin diagnostic printer: a greppable `VERDICT=`
line (cuda_check.py:164) + the resolved config + exit code (0=cuda-ok / 1=cpu-fallback-required). It
is **NOT** unit-tested — its logic (`_cuda_device_count` / `is_cuda_available` /
`resolve_device_and_models`) IS exercised via the `cfg_to_kwargs` suite (monkeypatched, §4). The CLI
is verified **empirically** (§3, the `python -m voice_typing.cuda_check` smoke). Non-blocking — the
CLI is operator-facing diagnostics, not a contract surface. A future test could be added but is not
required for §4.4 compliance.

---

## 7. Scope Discipline & Parallel No-Conflict

**IN scope (this audit):**
- `voice_typing/cuda_check.py` (the probe + `CUDA_DEFAULTS`/`CPU_FALLBACK` + `resolve_device_and_models`).
- `voice_typing/daemon.py` consumption points: `_resolve_device_config` (L141-155), `cfg_to_kwargs`
  (L158-235, esp. the lite CPU branch at L188-193), `_log_resolved_device` (L919-940),
  `status_snapshot` + `_resolved_device` + `_unprobed_device_config` (L1548-1620), and the
  `force_cpu` retry path (L289-311). daemon.py was **read** for these consumption points **only**.
- `tests/test_daemon.py` `cfg_to_kwargs` path suite (the contract's run target).
- The deliverable: this report (`plan/006_862ee9d6ef41/architecture/gap_cuda_check.md`).

**OUT of scope (do NOT touch):**
- `launch_daemon.sh` LD_LIBRARY_PATH/cuDNN discovery → **P1.M4.T2** (planned). The cuDNN finding
  (§6-obs1) is cross-referenced here but its remediation is that task's scope.
- `config.py` schema → **P1.M1.T1** (complete; see gap_config.md). `textproc` → P1.M1.T2 (complete;
  gap_textproc.md). `typing_backends` → **P1.M1.T3** (parallel; gap_typing.md).
- The recorder-host subprocess lifecycle → **P1.M2.T2** (planned). The VT-001 nuance (§5) is the
  recorder-host architecture's invariant; this audit RECORDS it, it does not change it.
- Read-only: `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`.

**Parallel — P1.M1.T3.S1 (typing_backends audit, in flight):** **DISJOINT files** (cuda_check.py +
daemon.py consumption vs typing_backends.py). Both write a `gap_<module>.md` under `architecture/`
(`gap_cuda_check.md` vs `gap_typing.md`). **No merge conflict.**

---

## 8. Conclusion

`cuda_check.py` + its daemon consumption are **PRD §4.4-compliant** on all 7 contract points (each
with file:line evidence in §2): the probe uses `ctranslate2.get_cuda_device_count()` (count==0 on any
failure); the `CPU_FALLBACK` dict matches the PRD's exact `device=cpu, compute_type=int8,
realtime_model=tiny.en, model=small.en`; `resolve_device_and_models()` returns a fresh dict; lite-mode
CPU substitutes `tiny.en`; the daemon consumes the output via `_resolve_device_config`/`cfg_to_kwargs`,
logs it at startup (`_log_resolved_device`), and surfaces it in `status` (`status_snapshot`). The live
machine probe confirms `cuda_device_count=1` / `VERDICT=cuda-ok` (RTX 3080 Ti); the `cfg_to_kwargs`
path suite is **7 passed**. The **VT-001** architectural invariant (the daemon process never probes
CUDA — the recorder-host child owns the resolution) is recorded as **correct-by-design**, and the
three non-blocking observations (cuDNN limitation; torch-is-diagnostics-not-gate; CLI not unit-tested)
are documented so they are not mistaken for defects.

**No code changes were required and none were made.** `voice_typing/cuda_check.py`,
`voice_typing/daemon.py`, and `tests/test_daemon.py` are **unchanged** — the audit confirms they are
already fully PRD §4.4-compliant. (This is the expected outcome: the contract's "fix any defect"
branch is **not** taken because no defect exists.) This closes **P1.M1.T4.S1**. Downstream
consumers — **P1.M2.T2** (recorder-host lifecycle, the child that owns the resolution),
**P1.M2.T4** (recorder kwargs audit), and **P1.M4.T2** (launch_daemon.sh cuDNN discovery) — can rely
on this report's findings: cuda_check's device/compute_type/models flow INTO the recorder kwargs is
correct, and the VT-001 invariant is recorded for the recorder-host audit.