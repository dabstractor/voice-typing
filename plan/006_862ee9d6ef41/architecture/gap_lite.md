# Gap Report — P1.M2.T3.S1: Lite Recorder Construction vs PRD §4.2ter

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit the **lite-mode recorder construction path** against **PRD §4.2ter + §4.4** on
the **4 item clauses (a)–(d)**. The audited call chain is:
`daemon.cfg_to_kwargs(lite=True)` → `build_recorder(lite=True)` ←
`recorder_host._worker_main(mode="lite")` ← `daemon._load_host("lite")`. The audited code regions
are: `daemon.cfg_to_kwargs` (L158-216 — the lite delta), `_construct` (L285-311),
`build_recorder` (L323-345), `_load_host` (L698-795 — mode param + mode→`RecorderHost(mode=)`
threading), `start_lite` (L1376) / `toggle_lite` (L1426 — both call `_load_host("lite")`);
`recorder_host._worker_main` (L421-510, esp. L456-498), `_child_resolved_device` (L680-715 — the
lite CPU-fallback STATUS path), `RecorderHost.mode` property (L168) + `spawn` (L181-228 — mode is
the 6th `_worker_main` arg); `config.py` `AsrConfig.lite_model` (L54) +
`lite_post_speech_silence_duration` (L59). Subtask **P1.M2.T3.S1** of compliance round
`006_862ee9d6ef41`.

**Audited artifacts (all read-only):**
- `voice_typing/daemon.py` — `_FIXED_KWARGS` (L98-119: `use_main_model_for_realtime=False` @L101 —
  the value the lite override flips to True); `cfg_to_kwargs` (L158-216: `lite` param @L159;
  lite branch @L184-192 sets `resolved["final_model"]=resolved["realtime_model"]=lite_model`
  with the CPU lite substitute `"tiny.en"` @L190; common kwargs block `"model"`/`"realtime_
  model_type"`/`"post_speech_silence_duration"` @L200-203; lite override @L206-213 sets
  `kwargs["use_main_model_for_realtime"]=True` @L209 + `kwargs["post_speech_silence_duration"]=
  cfg.asr.lite_post_speech_silence_duration` @L213); `_construct` (L285-311: `lite` param @L292;
  `cfg_to_kwargs(cfg, resolved=resolved, lite=lite)` @L311); `build_recorder` (L323-345: `lite`
  param @L323; threaded into `_construct(...,lite=lite)` @L344); `_load_host` (L698: `mode` param
  @L698; `RecorderHost(..., mode=mode)` @L751-757; `self._mode = mode` @L766);
  `start_lite` (L1376) / `toggle_lite` (L1426) (both call `_load_host("lite")`).
- `voice_typing/recorder_host.py` — `RecorderHost.__init__` (`self._mode = mode` @L125);
  `RecorderHost.mode` property (L168-170); `spawn` (L181-228: `ctx.Process(target=_worker_main,
  args=(self._cfg, self._cmd_q, self._evt_q, self._abort_event, self._force_cpu, self._mode))`
  @L194-196 — mode is the 6th arg); `_worker_main` (L421-510: `mode` param @L425;
  `lite = mode == "lite"` @L458; `build_recorder(..., lite=lite)` @L476; the force_cpu RETRY
  `build_recorder(..., force_cpu=True, ..., lite=lite)` @L481-494 PRESERVES lite across the retry;
  `_child_resolved_device(cfg, force_cpu, lite=lite)` @L498); `_child_resolved_device` (L680-715:
  `lite` param @L680; @L707-714 `if lite: lite_model = "tiny.en" if d["device"]=="cpu" else
  cfg.asr.lite_model; d["final_model"]=d["realtime_model"]=lite_model`).
- `voice_typing/config.py` — `AsrConfig.lite_model: str = "small.en"` @L54;
  `post_speech_silence_duration: float = 0.6` @L58; `lite_post_speech_silence_duration: float =
  0.5` @L59; both real config keys validated by the `AsrConfig` known-keys loader (L86-87).
- `tests/test_daemon.py` — the 4 lite kwargs tests (`test_cfg_to_kwargs_lite_mode_uses_one_model`
  @L138; `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en` @L165;
  `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal` @L185;
  `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` @L216).
- `tests/test_recorder_host.py` — ZERO lite tests (`grep -c -i lite` = 0); recorded as a non-defect
  nuance (§4.2), not a coverage gap.

**Bottom line:** ✅ **COMPLIANT** — all 4 clauses (a)–(d) pass (each with `daemon.py` /
`recorder_host.py` / `config.py` file:line evidence below). The lite-mode recorder builds with
EXACTLY ONE model (`cfg.asr.lite_model` = "small.en" on CUDA, "tiny.en" on CPU) for BOTH realtime
and final via `use_main_model_for_realtime=True` (the large `distil-large-v3` never constructs —
the §4.2ter + acceptance #10 one-model / ~half-VRAM guarantee); lite uses its own SNUGGER
`post_speech_silence_duration` (`lite_post_speech_silence_duration`, default 0.5 vs normal 0.6 —
the perceived-latency lever, since the silence gate, not the model, dominates end-to-end latency);
the mode is threaded end-to-end from `_load_host("lite")` through `RecorderHost(mode=)` into the
child's `lite = mode == "lite"` derivation; and the CPU lite substitute (`tiny.en`) is applied
consistently in BOTH the LOAD path (`cfg_to_kwargs`) and the STATUS path (`_child_resolved_device`)
so `voicectl status` reports what actually loaded. The contract's run target
`tests/test_recorder_host.py tests/test_daemon.py -q -k lite` is **15 passed, 204 deselected in
0.04s** (re-ran live during this audit; matches the verified baseline). Four **non-defect
nuances** are recorded (§4) so they are not mistaken for gaps. **No source or test files were
modified** — the lite construction is PRD §4.2ter / §4.4 / acceptance #10-compliant per this
re-verification; no defect surfaced. The only new artifact is this report.

---

## 1. Method

Each of the 4 clauses (a)–(d) was mapped to **specific `voice_typing/daemon.py` /
`voice_typing/recorder_host.py` / `voice_typing/config.py` file:line** via `grep -nE`, then
re-verified by reading `cfg_to_kwargs` (L158-216), `_construct` (L285-311), `build_recorder`
(L323-345), `_load_host` (L698-795), `start_lite` (L1376) / `toggle_lite` (L1426);
`recorder_host._worker_main` (L421-510), `_child_resolved_device` (L680-715), `RecorderHost.__init__`
(L120-168) + `spawn` (L181-228); and `config.py` `AsrConfig` (L54-59) against the **PRD §4.2ter
("Recorder construction (lite)")** + **§4.4 (lite note)** wording (the three one-model kwargs —
`model`/`realtime_model_type`=`lite_model` + `use_main_model_for_realtime=True`; the silence-gate
override `post_speech_silence_duration`=`lite_post_speech_silence_duration`; the CPU fallback to
`tiny.en`; and the mode being a spawn-time property threaded end-to-end). The full mode→lite call
chain was traced from `start_lite`/`toggle_lite` → `_load_host("lite")` → `RecorderHost(mode=)` →
`spawn` (`Process(target=_worker_main, args=(..., self._mode))`) → `_worker_main(mode=)` →
`lite = mode == "lite"` → `build_recorder(lite=lite)` → `_construct(lite=lite)` →
`cfg_to_kwargs(lite=True)`, confirming the chain is unbroken (research §1). The two-site
lite-CPU-fallback (`cfg_to_kwargs` LOAD path + `_child_resolved_device` STATUS path) was
cross-checked to confirm both sites discriminate on `device == "cpu"` and both map to `tiny.en`
(research §2). The contract's test target was then re-run live (§3). The 4 non-defect nuances (§4)
were confirmed against the code/docstring evidence (the `_worker_main` pass-through docstring
@L456-458; `test_recorder_host.py`'s zero-lite-test grep; the two-site duplication rationale; and
the "mode is a spawn-time property" docstring @L456-457).

### Commands run (re-verification)

```bash
# locate every lite construction site (kwargs builder, the chain, the CPU fallback, the config fields)
grep -nE 'def cfg_to_kwargs|def _construct|def build_recorder|def _load_host|def start_lite|def toggle_lite|lite|use_main_model_for_realtime|post_speech_silence_duration|self\._mode' voice_typing/daemon.py
grep -nE 'def _worker_main|def _child_resolved_device|lite = mode|lite=lite|tiny\.en|def mode|target=_worker_main|self\._mode' voice_typing/recorder_host.py
grep -nE 'lite_model|lite_post_speech_silence_duration|post_speech_silence_duration' voice_typing/config.py
# the contract's run target (re-ran live)
timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k lite
# confirm test_recorder_host.py contributes 0 lite tests (nuance §4.2)
grep -c -i lite tests/test_recorder_host.py
# scope guard — no source modified
git status --short
```

---

## 2. The 4 clauses — per-clause compliance table

| # | Clause (PRD §4.2ter / §4.4) | Code actual (`voice_typing/*.py`) | Verdict |
|---|---|---|---|
| (a) | **`_load_host("lite")` threads `lite=True` end-to-end into the recorder builder** — the mode→lite chain is unbroken: `_load_host("lite")` → `RecorderHost(mode="lite")` → `spawn` → `_worker_main(mode="lite")` → `lite = mode=="lite"` → `build_recorder(lite=lite)` → `cfg_to_kwargs(lite=True)` | `daemon.py`: `start_lite` @L1376 / `toggle_lite` @L1426 call `_load_host("lite")`; `_load_host(mode=…)` @L698 builds `RecorderHost(..., mode=mode)` @L751-757 (production branch w/ `is_listening`) + @L752-756 (test-fake branch) and publishes `self._mode = mode` @L766 on success. `recorder_host.py`: `RecorderHost.__init__` stores `self._mode = mode` @L125; `mode` property @L168-170; `spawn` @L194-196 `ctx.Process(target=_worker_main, args=(self._cfg, self._cmd_q, self._evt_q, self._abort_event, self._force_cpu, self._mode))` (mode = 6th arg); `_worker_main(..., mode=…)` @L421/425 derives `lite = mode == "lite"` @L458 and calls `build_recorder(cfg, relay_fb, relay_lat, on_speech=_child_on_speech, lite=lite)` @L476. `daemon.py`: `build_recorder(..., lite=…)` @L323/323 → `_construct(..., lite=lite)` @L285/292/344 → `cfg_to_kwargs(cfg, resolved=resolved, lite=lite)` @L311. The force_cpu RETRY in `_worker_main` @L481-494 re-calls `build_recorder(..., force_cpu=True, ..., lite=lite)` — `lite` is PRESERVED across the retry (it is a per-mode property, not a device property). | ✅ **COMPLIANT** |
| (b) | **Lite sets the ONE-model kwargs** — `model`=`lite_model`, `realtime_model_type`=`lite_model`, `use_main_model_for_realtime=True` (the large final model never constructs; verified against RealtimeSTT v1.0.2 `use_main_model_for_realtime=True` early-returns out of `_initialize_realtime_transcription_model`) | `daemon.py`: `cfg_to_kwargs` lite branch @L184-192 — `lite_model = "tiny.en" if resolved["device"]=="cpu" else cfg.asr.lite_model` @L190; `resolved["final_model"] = resolved["realtime_model"] = lite_model` @L191-192 (both = small.en on CUDA). Common kwargs block @L200-204 — `"model": resolved["final_model"]` @L201, `"realtime_model_type": resolved["realtime_model"]` @L202 (both small.en on CUDA / tiny.en on CPU). Lite override block @L206-209 — `kwargs["use_main_model_for_realtime"] = True` @L209 (overrides the `use_main_model_for_realtime=False` in `_FIXED_KWARGS` @L101). `config.py`: `AsrConfig.lite_model: str = "small.en"` @L54. | ✅ **COMPLIANT** |
| (c) | **`post_speech_silence_duration` overridden to the snugger lite threshold** — lite MUST use its own shorter `post_speech_silence_duration` (`lite_post_speech_silence_duration`, default 0.5 vs 0.6) to actually feel faster (the silence gate, not the model, is the perceived-latency bottleneck — §4.2ter latency-log finding) | `daemon.py`: common kwargs block `"post_speech_silence_duration": cfg.asr.post_speech_silence_duration` @L203 (the 0.6 normal value); lite override block @L206-213 — `kwargs["post_speech_silence_duration"] = cfg.asr.lite_post_speech_silence_duration` @L213 (overrides the common-block 0.6 with the lite 0.5). `config.py`: `post_speech_silence_duration: float = 0.6` @L58; `lite_post_speech_silence_duration: float = 0.5` @L59. | ✅ **COMPLIANT** |
| (d) | **CPU lite fallback = `tiny.en`, applied in BOTH the LOAD path and the STATUS path** — the degraded lite substitute is `tiny.en` (mirrors how normal CPU-fallback maps `small.en`→`tiny.en`); both the construction (what the recorder builds) and the status report (what `voicectl status` shows) must agree | **LOAD path** — `daemon.cfg_to_kwargs` @L190 `lite_model = "tiny.en" if resolved["device"]=="cpu" else cfg.asr.lite_model` (→ `resolved["final_model"]`/`["realtime_model"]` @L191-192 → the recorder's `model`/`realtime_model_type` kwargs @L201-202). **STATUS path** — `recorder_host._child_resolved_device` @L707-714 `if lite: lite_model = "tiny.en" if d["device"]=="cpu" else cfg.asr.lite_model; d["final_model"]=d["realtime_model"]=lite_model` (the dict the child sends back as its `'ready'` event, which seeds `daemon._resolved_device_cache` for `voicectl status`). Both discriminate on `device == "cpu"` (NOT a `force_cpu` flag — `cfg_to_kwargs` has none; the resolved device is the truth and also covers probe-failure / `cuda_check`→CPU). | ✅ **COMPLIANT** (two-site consistency — intentional duplication, see nuance §4.3) |

---

## 3. Test result — the contract's run target (the evidence)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k lite
# → 15 passed, 204 deselected in 0.04s
```

**Recorded count: 15 passed, 204 deselected** (matches the verified baseline of 15 passed, 0.03s;
re-ran live during this audit). The slice is CUDA-free (the daemon fakes inject a recorder
stand-in and `cfg_to_kwargs` is a pure function) → fast (~0.04s), but the `timeout 300` inner +
bash-tool outer wrap are mandatory (AGENTS.md Rule 1). `tests/test_recorder_host.py` contributed
**0** lite tests (`grep -c -i lite tests/test_recorder_host.py` = 0); all 15 selected tests are in
`tests/test_daemon.py`. (`-k lite` also matches the config param ids `lite_model` /
`lite_post_speech_silence_duration`, which is why the count is 15 and not 4 — the kwargs isolation
+ fixed-value guards whose `cfg` fixture carries the lite fields are also selected.)

### Test → clause mapping

| Clause | Covering test (`tests/test_daemon.py`) | What it asserts |
|---|---|---|
| (a) mode→lite chain | (no dedicated kwargs test — the chain is verified by reading `daemon.py`/`recorder_host.py` + exercised live by `test_idle_and_gpu.sh` T7 + `test_feed_audio.py` lite tests; the `mode=="lite"`→`lite=True` derivation is a one-line literal at `recorder_host.py:458`) | the mode is threaded `_load_host("lite")`→`RecorderHost(mode=)`→`_worker_main(mode=)`→`lite=True`→`build_recorder(lite=)` |
| (b) one-model kwargs | `test_cfg_to_kwargs_lite_mode_uses_one_model` @L138 | lite: `model`=`realtime_model_type`="small.en" + `use_main_model_for_realtime`=True; normal: `model`="distil-large-v3" + `realtime_model_type`="small.en" + `use_main_model_for_realtime`=False |
| (b)+(d) CPU one-model | `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en` @L165 | lite on CPU: `model`=`realtime_model_type`="tiny.en"; `use_main_model_for_realtime` stays True (one-model invariant preserved on CPU fallback) |
| (isolation) | `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal` @L185 | ONLY `{model, realtime_model_type, use_main_model_for_realtime, post_speech_silence_duration}` differ between lite and normal; every other kwarg is identical (the lite delta is exactly the 4 documented fields) |
| (c) silence gate | `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` @L216 | lite `post_speech_silence_duration`=0.5, normal=0.6; and it is tunable (overriding `lite_post_speech_silence_duration` to 0.3 propagates) |

---

## 4. Non-defect nuances (NON-blocking — recorded so they are NOT mistaken for gaps)

### (i) Model identity is assigned in `cfg_to_kwargs` (`daemon.py`), NOT in `_worker_main` (`recorder_host.py`)

`_worker_main` does NOT set `model=` / `realtime_model_type=` itself — it calls
`build_recorder(lite=lite)` @L476 → `_construct(lite=lite)` @L311 → `cfg_to_kwargs(lite=True)`
@L311, which sets them (`resolved["final_model"]`/`["realtime_model"]` @L191-192 → kwargs
`"model"`/`"realtime_model_type"` @L201-202). This is the **correct layering**:
`cfg_to_kwargs` is the single source of truth for model identity (it owns the lite/CPU-fallback
resolution in one place), and the child is a thin pass-through that derives `lite` from `mode`
and threads it down. Clause (b) is satisfied via this chain, **not** by a literal `model=`
assignment in `_worker_main`. Do NOT flag the absence of a `model=` assignment in `_worker_main`
as a gap — it is the deliberate design.

### (ii) `tests/test_recorder_host.py` has ZERO lite tests

`grep -c -i lite tests/test_recorder_host.py` = 0. This is **not** a coverage gap: lite
CONSTRUCTION is unit-tested at the `cfg_to_kwargs` layer (`test_daemon.py`, 4 named tests in §3)
+ the `mode == "lite"` → `lite = True` derivation is a one-line literal at `recorder_host.py:458`
verified by reading + the live `test_idle_and_gpu.sh` T7 section and `test_feed_audio.py` lite
tests exercise the real child end-to-end. The child adds no model logic of its own — it is a
pass-through to `daemon.build_recorder`, which IS unit-tested. P1.M2.T3.S3 owns the detailed T7
live-test COVERAGE audit; this task records only the unit-level count.

### (iii) Two-site lite-CPU-fallback (`cfg_to_kwargs` + `_child_resolved_device`) — intentional duplication

The lite CPU substitute (`tiny.en`) is applied in TWO places that MUST agree:
1. **LOAD path** — `daemon.cfg_to_kwargs` (`daemon.py:190`): sets `resolved["final_model"]` /
   `resolved["realtime_model"]` = `tiny.en` (CPU) → this is what the recorder actually CONSTRUCTS.
2. **STATUS path** — `recorder_host._child_resolved_device` (`recorder_host.py:707-714`): sets
   `d["final_model"]` / `d["realtime_model"]` = `tiny.en` (CPU) → this is the dict the child sends
   back as its `'ready'` event, which seeds `daemon._resolved_device_cache` for `voicectl status`.

Both discriminate on `device == "cpu"` (NOT a `force_cpu` flag — `cfg_to_kwargs` has none; the
resolved device is the truth and also covers probe-failure / `cuda_check`→CPU). This is **not** a
defect — load and status must report the same model, and both do. Removing one site would make
`voicectl status` lie about what loaded. (delta §3.2 BUG-A rationale;
`test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en` covers the load path; the status path is
exercised live by `test_idle_and_gpu.sh` T7.)

### (iv) `lite` is a SPAWN-TIME property — mode-switch reload is P1.M2.T3.S2's scope

`lite` is derived once at child spawn from `mode` (`recorder_host.py:456-458` docstring + the
`lite = mode == "lite"` literal @L458). It cannot change without a reload — the resident child is
built for exactly one mode (PRD §4.2ter "Mode is a spawn-time property of the recorder-host
child"). The mode-switch RELOAD mechanic (`_load_host`'s `switch_mode` branch @L715-741: detect a
wrong-mode resident under the single-flight lock, tear it down via `_bounded_shutdown(5.0)`, then
respawn in the requested mode) is audited by **P1.M2.T3.S2**, NOT this task. This audit references
the mode threading (clause a) only; the reload logic itself is out of scope.

---

## 5. Conclusion

The lite-mode recorder construction faithfully implements **PRD §4.2ter ("Recorder construction
(lite)")** + the **§4.4 lite note** on all 4 clauses (a)–(d): the mode is threaded end-to-end from
`_load_host("lite")` through `RecorderHost(mode=)` into the child's `lite = mode == "lite"`
derivation and down into `cfg_to_kwargs(lite=True)` (clause a); lite sets the ONE-model kwargs
`model`=`realtime_model_type`=`lite_model` + `use_main_model_for_realtime=True` so the large
`distil-large-v3` never constructs (clause b); lite overrides `post_speech_silence_duration` to
its own snugger `lite_post_speech_silence_duration` (0.5 vs 0.6) — the perceived-latency lever
(clause c); and the CPU lite substitute (`tiny.en`) is applied consistently in BOTH the load path
(`cfg_to_kwargs`) and the status path (`_child_resolved_device`) so `voicectl status` reports what
actually loaded (clause d). All with `voice_typing/daemon.py` / `recorder_host.py` / `config.py`
file:line evidence; the `-k lite` slice is **15 passed, 204 deselected**.

This certifies the project's acceptance criteria:
- **#10 (lite arms using ONLY `lite_model`; its own shorter `post_speech_silence_duration`;
  observably snappier; ~half the VRAM)** — clause (b) certifies the one-model kwargs
  (`model`=`realtime_model_type`=`lite_model` + `use_main_model_for_realtime=True`) so the large
  model never loads → ~half the VRAM; clause (c) certifies the snugger silence gate
  (`post_speech_silence_duration`=0.5 vs 0.6) which, per PRD §4.2ter's latency-log finding, is what
  makes lite observably snappier (the silence wait swamps the small model's ~50 ms final-pass win);
  clause (d) certifies the CPU fallback keeps lite single-model with `tiny.en`; and clause (a)
  certifies the mode is reliably threaded from `_load_host("lite")` into the child so the above
  actually take effect on a `start-lite` / `toggle-lite` command.

**Verdict: ✅ COMPLIANT on all 4 clauses — no fix needed.** **No source or test files were
modified** (this is a read-only audit — the lite construction is PRD §4.2ter / §4.4 / acceptance
#10-compliant per this re-verification; no defect surfaced). The only artifact produced by this
subtask is this report. Adjacent concerns are correctly deferred: the **mode-switch reload
mechanic** (`_load_host` `switch_mode` branch) is P1.M2.T3.S2; the **T7 live-test coverage audit**
is P1.M2.T3.S3; and the **FULL common recorder kwargs** (all §4.4 params, `silero_backend`,
`no_log_file`, kwarg filtering) is P1.M2.T4.S1 — this task audits the LITE DELTA only (the 4 fields
lite changes) plus the end-to-end mode threading.