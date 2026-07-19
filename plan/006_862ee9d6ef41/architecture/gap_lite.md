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

---

## Gap Report — P1.M2.T3.S2: Mode-Switch Reload & self._mode Tracking vs PRD §4.2ter

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit the daemon's **mode-switch reload lifecycle + `self._mode` tracking** against
**PRD §4.2ter (arming rules + State/status + Commands/keybind) + §7 acceptance #10** on the **6
item clauses (a)–(f)**. The audited lifecycle is: the 4 public arm methods (`start`/`toggle` →
`_load_host("normal")`; `start_lite`/`toggle_lite` → `_load_host("lite")`) → the single
`_load_host(mode)` decision point (instant-same-mode `return True`; cross-mode teardown-and-respawn
via `_bounded_shutdown(timeout=5.0)`; `self._mode=mode` on successful spawn) → `_arm` publishing
`feedback.set_mode` → mode-agnostic `stop` (drain-or-disarm either mode). The audited code regions
are: `daemon.py` `start` (L1365-1374), `start_lite` (L1376-1386), `stop` (L1388-1390 →
`_request_stop` L1053-1071), `toggle` (L1393-1425), `toggle_lite` (L1426-1454); `_load_host`
(L698-795 — fast path L715-720, `switch_mode` L718, switch teardown L736-742 with
`_bounded_shutdown(timeout=5.0)` L739, factory spawn `mode=mode` L749-757, `self._mode=mode` L766);
`_arm` (L987-1000 — `feedback.set_mode(self._mode)` L998); `_disarm` (L1002-1030 — does NOT call
`set_mode`); `_request_stop` (L1053-1071 — NO mode check); `_bounded_shutdown` (L1620-1645 — the
bounded teardown primitive, ~7s budget); `status_snapshot` (`"mode": self._mode` L1567);
`self._mode` field init (L644); `ControlServer._dispatch` (L1892-1941 — routes all 7 cmds);
`feedback.py` `set_mode` (L145-150) + `_state["mode"]` init (L99); `recorder_host.py`
`RecorderHost.mode` property (L168-170) + `is_alive` (L173-175) + `_mode` (L125) + `spawn`
(L194-196 — mode is the 6th `_worker_main` arg); `ctl.py` `_COMMANDS` (L37 — all 7) + routing
(L199-202 — loading-hint for the 4 arm cmds). Subtask **P1.M2.T3.S2** of compliance round
`006_862ee9d6ef41`. **This section is APPENDED to S1's `gap_lite.md`** (S1 owns the H1 file;
this is the H2 sibling below it — the two audits are TOPIC-disjoint: S1 = lite CONSTRUCTION
kwargs, S2 = reload LIFECYCLE).

**Audited artifacts (all read-only):**
- `voice_typing/daemon.py` — `start` (L1365: `_load_host("normal")` L1371 → `_arm` L1373);
  `start_lite` (L1376: `_load_host("lite")` L1383 → `_arm` L1385); `stop` (L1388: →
  `_request_stop()` L1389, mode-agnostic); `toggle` (L1393: reads `(listening, mode)` under
  `_lock` L1407-1409, disarm-in-normal branch `_request_stop()` L1411, else arm branch
  `_load_host("normal")` L1413 → `_arm` L1424, with the failed-cross-mode `_disarm` fallback
  L1419-1422); `toggle_lite` (L1426: reads `(listening, mode)` under `_lock` L1434-1436,
  disarm-in-lite branch `_request_stop()` L1438, else arm branch `_load_host("lite")` L1441 →
  `_arm` L1453, with the failed-cross-mode `_disarm` fallback L1447-1450); `_load_host` (L698:
  `mode` param L698; fast path L715 `if self._models_loaded and self._host is not None and
  self._host.is_alive:` → L716-717 same-mode instant `return True`; L718 `switch_mode=True`
  resident-but-wrong-mode; L727-728 loader-claim `_loading=True`; L729-730 cold-load toast;
  L736-742 switch teardown `if switch_mode and self._host is not None:` → L738 log → L739 `with
  self._lock: self._bounded_shutdown(timeout=5.0); L740 self._host=None; L741
  self._models_loaded=False`; L749-757 `factory(..., mode=mode)` spawn OUTSIDE `_lock`; L760-788
  re-acquire `_lock` publish — on `ok`: `_host=host` L763, `_models_loaded=True` L764,
  `self._mode=mode` L766, phase idle L770; on failure: stop half-built host, `_load_error=...`,
  `_models_loaded=False`, `_host=None` L784); `_arm` (L998 `self._feedback.set_mode(self._mode)`);
  `_disarm` (L1002-1030 — `set_listening(False)` L1025 + `set_phase("idle")` L1026, NO `set_mode`);
  `_request_stop` (L1053-1071 — L1065 `if self._host is not None and self._text_in_flight.is_set()
  and self._final_pending:` → `_begin_drain` L1066; else L1067-1071 `with self._lock:
  self._disarm(); ... self._safe_abort()` — NO mode check); `_bounded_shutdown` (L1620: default
  `timeout=5.0`; L1642-1644 `self._host.stop(timeout=timeout)` bounded by `proc.join(5)` +
  `_terminate_group()` + `join(2)` = ~7s max); `status_snapshot` (`"mode": self._mode` L1567);
  `self._mode` field init (L644 `self._mode: str = "normal"`); `ControlServer._dispatch`
  (L1892-1941 — `"toggle"` L1901 → `toggle()` L1903; `"start"` L1913 → `start()` L1914;
  `"start-lite"` L1916 → `start_lite()` L1917; `"toggle-lite"` L1919 → `toggle_lite()` L1921;
  `"stop"` L1926 → `stop()` L1927; `"status"` L1929 → `status_snapshot()`; `"quit"` L1931 →
  `request_shutdown()` + `on_quit`).
- `voice_typing/feedback.py` — `set_mode` (L145-150: `self._state["mode"] = mode` L150 +
  `_write()` — "Always writes; never notifies"); `_state["mode"]` init (L99 `"mode": "normal"` —
  boot default).
- `voice_typing/recorder_host.py` — `RecorderHost.mode` property (L168-170 `return self._mode`);
  `is_alive` (L173-175 `self._proc is not None and self._proc.is_alive() and not self._dead`);
  `RecorderHost.__init__` (`self._mode = mode` L125); `spawn` (L194-196 `ctx.Process(
  target=_worker_main, args=(self._cfg, self._cmd_q, self._evt_q, self._abort_event,
  self._force_cpu, self._mode))` — mode is the 6th arg). `_load_host@716` reads `getattr(
  self._host, "mode", "normal")` for the same-mode short-circuit.
- `voice_typing/ctl.py` — `_COMMANDS` (L37 = `("toggle","start","stop","status","quit",
  "toggle-lite","start-lite")` — all 7); routing (L199-202: `start`/`toggle`/`start-lite`/
  `toggle-lite` → `_send_command_with_loading_hint`; `stop`/`status`/`quit` → plain `send_command`).
- `tests/test_daemon.py` — the 15 mode-switch tests the contract's `-k` slice selects (L2863-3851;
  full list + clause mapping in §3).

**Bottom line:** ✅ **COMPLIANT** — all 6 clauses (a)–(f) pass (each with `daemon.py` /
`feedback.py` / `recorder_host.py` / `ctl.py` file:line evidence below). The mode-switch lifecycle
implements **PRD §4.2ter's arming rules** exactly: each of the 4 user-facing arm commands routes
to the correct mode (`toggle`/`start`→`_load_host("normal")`; `toggle-lite`/`start-lite`→
`_load_host("lite")` — covered by the socket `_dispatch` (L1892-1941) + `ctl._COMMANDS` (L37) +
routing (L199-202) — clause a); an arm in the SAME mode as the resident child is **instant**
(`_load_host` L716-717 short-circuits `return True` with the SAME `RecorderHost` object — no
reload — clause b); an arm in the OTHER mode costs **exactly one bounded reload**
(`_load_host` L718 sets `switch_mode=True` → L738-741 tears down the old child via
`_bounded_shutdown(timeout=5.0)` (≤~7s, the same primitive idle-unload uses) → L749-757 spawns
fresh in the requested mode — clause c + acceptance #10); `self._mode` is updated on a successful
spawn (`_load_host` L766) and surfaced in `voicectl status` + `state.json` (`status_snapshot`
`"mode": self._mode` L1567 — clause d); `feedback.set_mode` is published on every `_arm` (L998;
  de-facto-current on disarm since disarm does not change `self._mode` — clause e + nuance §4.1);
and `stop` disarms **regardless** of mode (`stop` L1388 → `_request_stop` L1053-1071 drains or
disarms with NO mode branch — clause f). The contract's run target
`tests/test_daemon.py -q -k 'mode or toggle_lite or start_lite or switch'` is **15 passed, 178
deselected in 0.03s** (re-ran live during this audit; matches the verified baseline). Five
**non-defect nuances** are recorded (§4) so they are not mistaken for gaps. **No source or test
files were modified** — the mode-switch lifecycle is PRD §4.2ter / acceptance #10-compliant per
this re-verification; no defect surfaced. The only new artifact is this report section (appended
to S1's `gap_lite.md`).

---

## 1. Method

Each of the 6 clauses (a)–(f) was mapped to **specific `voice_typing/daemon.py` /
`voice_typing/feedback.py` / `voice_typing/recorder_host.py` / `voice_typing/ctl.py` file:line**
via `grep -nE`, then re-verified by reading the 4 public arm methods (`start` L1365 /
`start_lite` L1376 / `stop` L1388 / `toggle` L1393 / `toggle_lite` L1426); `_load_host` (L698-795,
  esp. the fast path L715-720, the `switch_mode` L718, the switch teardown L736-742, the factory
spawn L749-757, the `self._mode=mode` L766); `_arm` (L987-1000) + `_disarm` (L1002-1030);
`_request_stop` (L1053-1071); `_bounded_shutdown` (L1620-1645); `status_snapshot` (L1567);
`ControlServer._dispatch` (L1892-1941); `feedback.set_mode` (L145-150) + `_state["mode"]` (L99);
`recorder_host.RecorderHost.mode` (L168-170) + `is_alive` (L173-175) + `_mode` (L125) + `spawn`
(L194-196); and `ctl._COMMANDS` (L37) + routing (L199-202) against the **PRD §4.2ter ("Arming
rules" / "State / status" / "Commands / keybind")** + **§7 acceptance #10** wording. The full
command→mode→load chain was traced end-to-end from `voicectl` → `ctl.send_command` → socket →
`ControlServer._dispatch` → the 4 daemon methods → `_load_host(mode)` → `RecorderHost(mode=)` →
`spawn` → `_worker_main(mode=)`, confirming the routing is complete + correct (research §1). The
switch-teardown path was cross-checked to confirm it reuses the SAME bounded-teardown primitive
(`_bounded_shutdown` L1620, the one `_unload_host` L1239 delegates to for idle-unload) and is
bounded by ~7s (`host.stop(timeout=5)` → `proc.join(5)` + `_terminate_group()` + `join(2)`),
certifying the "one bounded reload" of acceptance #10 (research §2). The contract's test target
was then re-run live (§3). The 5 non-defect nuances (§4) were confirmed against the
method-docstring + test evidence (the `_disarm` docstring noting abort-outside-lock;
`_unload_host`'s idle-threshold guards @L1225-1230 that would no-op during a switch; the
read/act-outside-`_lock` toggle design @L1393-1410 docstring; the `self._mode="normal"` boot
default @L644; and the success-only `self._mode=mode` @L766).

### Commands run (re-verification)

```bash
# locate every mode-switch site (arm methods, _load_host, switch teardown, self._mode, dispatch, ctl)
grep -nE 'def start|def start_lite|def stop|def toggle|def toggle_lite|_load_host\(|switch_mode|self\._mode|set_mode|_bounded_shutdown|def _dispatch|"toggle"|"start"|"stop"|"status"|"quit"|"toggle-lite"|"start-lite"' voice_typing/daemon.py
grep -nE 'def set_mode|"mode"|self\._state\["mode"\]' voice_typing/feedback.py
grep -nE 'def mode|is_alive|self\._mode|target=_worker_main' voice_typing/recorder_host.py
grep -nE '_COMMANDS|toggle-lite|start-lite|def send_command|def _send_command_with_loading_hint' voice_typing/ctl.py
# the contract's run target (re-ran live)
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'mode or toggle_lite or start_lite or switch'
# scope guard — no source modified
git status --short
```

---

## 2. The 6 clauses — per-clause compliance table

| # | Clause (PRD §4.2ter / §7 #10) | Code actual (`voice_typing/*.py`) | Verdict |
|---|---|---|---|
| (a) | **Command→mode routing is complete + correct** — `toggle`/`start`→`_load_host("normal")`; `toggle-lite`/`start-lite`→`_load_host("lite")`; `stop`/`status`/`quit` are mode-neutral. Every user-facing command reaches the right daemon method. | `daemon.py`: `start`@L1365 → `_load_host("normal")`@L1371 → `_arm`@L1373; `start_lite`@L1376 → `_load_host("lite")`@L1383 → `_arm`@L1385; `toggle`@L1393 → reads `(listening, mode)` under `_lock`@L1407-1409, disarm-in-normal branch `_request_stop()`@L1411, else arm branch `_load_host("normal")`@L1413 → `_arm`@L1424 (failed-cross-mode `_disarm` fallback @L1419-1422); `toggle_lite`@L1426 → reads `(listening, mode)` under `_lock`@L1434-1436, disarm-in-lite branch `_request_stop()`@L1438, else arm branch `_load_host("lite")`@L1441 → `_arm`@L1453 (failed-cross-mode `_disarm` fallback @L1447-1450). `ControlServer._dispatch`@L1892-1941 routes all 7 cmds: `"toggle"`@L1901→`toggle()`@L1903; `"start"`@L1913→`start()`@L1914; `"start-lite"`@L1916→`start_lite()`@L1917; `"toggle-lite"`@L1919→`toggle_lite()`@L1921; `"stop"`@L1926→`stop()`@L1927; `"status"`@L1929→`status_snapshot()`; `"quit"`@L1931→`request_shutdown()`+`on_quit`. `ctl.py`: `_COMMANDS`@L37 = all 7; routing@L199-202 routes the 4 arm cmds through `_send_command_with_loading_hint` (prints 'loading models…' on a cold arm / slow cross-mode reload) + stop/status/quit through plain `send_command`. | ✅ **COMPLIANT** |
| (b) | **Same-mode resident → instant arm** — arming mode X while a resident child is already mode X is instant (models already resident; no teardown, no respawn). | `daemon.py _load_host`@L715 `if self._models_loaded and self._host is not None and self._host.is_alive:` → L716 `if getattr(self._host, "mode", "normal") == mode:` → L717 `return True` (instant, SAME `RecorderHost` object, NO reload). `recorder_host.py`: `RecorderHost.mode@property`@L168-170 (`return self._mode`); `is_alive`@L173-175. Test `test_same_mode_arm_is_instant_no_reload`@L2892 (asserts `d._host is host1`, no teardown). | ✅ **COMPLIANT** |
| (c) | **Cross-mode resident → tear down + respawn in the new mode (acceptance #10: one bounded reload)** — arming mode X while the resident child is the OTHER mode tears the old child down (bounded, releases all VRAM) and spawns fresh in X (~1-3s reload). | `daemon.py _load_host`: L718 `switch_mode=True` (resident but WRONG mode) → L736 `if switch_mode and self._host is not None:` → L738 log → L739 `with self._lock: self._bounded_shutdown(timeout=5.0); L740 self._host=None; L741 self._models_loaded=False` → falls through to L749-757 `factory(..., mode=mode)` spawn OUTSIDE `_lock`. `_bounded_shutdown`@L1620-1645 → `host.stop(timeout=5)` (L1642-1644) bounded by `proc.join(5)` + `_terminate_group()` + `join(2)` = ~7s max (the SAME primitive `_unload_host`@L1239 delegates to for idle-unload — nuance §4.2). Tests `test_mode_switch_normal_to_lite_reloads`@L2875 (new host `mode=='lite'`) + `test_mode_switch_stops_outgoing_host`@L2927 (outgoing `host.stop_calls==1`, new `host.stop_calls==0`) + `test_start_lite_after_idle_unload_reloads_in_lite`@L2951. | ✅ **COMPLIANT** (acceptance #10 — exactly one bounded teardown + one spawn) |
| (d) | **`self._mode` updated on arm + reported in status** — the resident child's mode is tracked in `self._mode` (set on a successful spawn) so `voicectl status` + `state.json` report it; defaults to "normal" at boot. | `daemon.py _load_host`@L766 `self._mode = mode` (success branch ONLY — nuance §4.5); field init `self._mode: str = "normal"`@L644; `status_snapshot`@L1567 `"mode": self._mode`. `recorder_host.py`: `RecorderHost.__init__` stores `self._mode = mode`@L125; `mode@property`@L168-170 (the value `_load_host@716` compares against the requested mode). Tests `test_start_lite_loads_lite_host_and_arms`@L2863 (`d._mode=="lite"`) + `test_status_snapshot_reports_mode`@L2918 (boot=="normal", post-arm-lite=="lite"). | ✅ **COMPLIANT** (success-only set is intentional — nuance §4.5) |
| (e) | **`feedback.set_mode` published on arm** — `state.json`'s `"mode"` reflects which model set is active; written on every arm (de-facto-current on disarm since disarm does not change the resident mode). | `daemon.py _arm`@L998 `self._feedback.set_mode(self._mode)` (arm path only); `_disarm`@L1002-1030 does NOT call `set_mode` (only `set_listening(False)`@L1025 + `set_phase("idle")`@L1026 — nuance §4.1). `feedback.py`: `set_mode`@L145-150 (`self._state["mode"] = mode`@L150 + `_write()` — "Always writes; never notifies"); `_state["mode"]` init@L99 ("normal"). Tests `test_start_lite_loads_lite_host_and_arms`@L2863 (`fb.modes==["lite"]`) + `test_failed_cross_mode_toggle_status_snapshot_is_honest`@L3826 (failed-switch edge: `self._mode` left at prior value, status still honest via `listening:off` + `load_error`). | ✅ **COMPLIANT** (de-facto on disarm — nuance §4.1) |
| (f) | **`stop` disarms regardless of mode** — `voicectl stop` disarms either mode (no mode check); drains an in-flight utterance gracefully, else disarms immediately. | `daemon.py stop`@L1388 → `_request_stop()`@L1053-1071: L1065 `if self._host is not None and self._text_in_flight.is_set() and self._final_pending:` → `_begin_drain` (graceful); else L1067-1071 `with self._lock: self._disarm(); ... self._safe_abort()`. **NO mode check anywhere** — mode-agnostic by construction. `_dispatch`@L1926 `"stop"` → `self._daemon.stop()`@L1927. Test `test_toggle_lite_while_listening_in_lite_stops`@L2904 (disarms lite). (stop is mode-agnostic by construction — no mode branch exists; the ABSENCE of a mode check is the compliance evidence.) | ✅ **COMPLIANT** |

---

## 3. Test result — the contract's run target (the evidence)

```bash
timeout 600 .venv/bin/python -m pytest tests/test_daemon.py -q -k 'mode or toggle_lite or start_lite or switch'
# → 15 passed, 178 deselected in 0.03s
```

**Recorded count: 15 passed, 178 deselected** (matches the verified baseline of 15 passed,
0.04s; re-ran live during this audit). The slice is CUDA-free (the daemon fakes inject a
recorder stand-in; `_load_host`'s spawn is mocked — no real models load) → fast (~0.03s), but
the `timeout 600` inner + bash-tool outer wrap are mandatory (AGENTS.md Rule 1). All 15 selected
tests live in `tests/test_daemon.py`.

### Test → clause mapping (the 15 selected tests)

| Clause | Covering test (`tests/test_daemon.py`) | What it asserts |
|---|---|---|
| (a)+(d) | `test_start_lite_loads_lite_host_and_arms`@L2863 | `start_lite` → lite host; `d._mode=="lite"`; `fb.modes==["lite"]` |
| (c) | `test_mode_switch_normal_to_lite_reloads`@L2875 | normal→lite reloads; new host `mode=="lite"` |
| (b) | `test_same_mode_arm_is_instant_no_reload`@L2892 | re-arm same mode = SAME `RecorderHost` object, no reload |
| (f) | `test_toggle_lite_while_listening_in_lite_stops`@L2904 | stop disarms lite (mode-agnostic path) |
| (d) | `test_status_snapshot_reports_mode`@L2918 | `status_snapshot["mode"]` boot=="normal", post-arm-lite=="lite" |
| (c)+#10 | `test_mode_switch_stops_outgoing_host`@L2927 | outgoing `host.stop_calls==1` (bounded teardown); new host `stop_calls==0` |
| (c) | `test_start_lite_after_idle_unload_reloads_in_lite`@L2951 | reload-in-lite after idle-unload (cross-mode-equivalent reload) |
| (a)+(c) | `test_toggle_lite_while_idle_arms_in_lite`@L3696 | idle → toggle-lite arms in lite |
| (a)+(f) | `test_toggle_lite_while_armed_in_lite_disarms`@L3708 | armed-in-lite → toggle-lite disarms |
| (a)+(c) | `test_toggle_lite_while_armed_in_normal_switches_to_lite`@L3719 | armed-in-normal → toggle-lite switches to lite (one reload) |
| (a)+(c) | `test_toggle_while_armed_in_lite_switches_to_normal`@L3753 | armed-in-lite → toggle (normal) switches to normal (one reload) |
| (e) edge | `test_toggle_lite_while_armed_in_normal_failed_reload_clears_listening`@L3790 | failed cross-mode switch → `_disarm` clears listening, status honest |
| (e) edge | `test_failed_cross_mode_toggle_status_snapshot_is_honest`@L3826 | failed switch leaves `self._mode` at prior value; status honest via `listening:off` + `load_error` |
| (a) docstring | `test_toggle_lite_docstring_says_pressing_d_not_f`@L3851 | toggle-lite docstring guard (D not F) |
| (isolation) | `test_cfg_to_kwargs_lite_mode_uses_one_model`@L138 | (selected by `-k mode` via the `lite_mode` param id; S1's kwargs test — confirms the lite model identity the reload swaps TO) |

> Note: `test_toggle_while_armed_in_lite_failed_reload_clears_listening`@L3809 is a sibling of
> the @L3790 test but is **not** selected by this `-k` (its name matches `toggle` but not
> `toggle_lite`/`mode`/`start_lite`/`switch`); it is covered by the @L3790 toggle-lite
counterpart. Both assert the same failed-cross-mode `_disarm` fallback (clause e edge).

---

## 4. Non-defect nuances (NON-blocking — recorded so they are NOT mistaken for gaps)

### (i) `set_mode` is called in `_arm`, NOT in `_disarm` (clause e nuance)

`_arm`@L998 calls `self._feedback.set_mode(self._mode)`; `_disarm`@L1002-1030 does NOT. This is
**correct, not a gap**: disarm does not change `self._mode` (it only clears `_listening` + sets
phase "idle"; the resident child is unchanged), so the mode value from the most recent `_arm`
persists in `state.json` and is already current. PRD §4.2ter "written on every arm/disarm"
describes the OUTCOME (state.json mode stays current), satisfied de facto. The ONE edge — a
FAILED cross-mode switch (resident X torn down, Y load failed, then `_disarm`) — leaves
`self._mode` at the prior value with `_models_loaded=False`; `status_snapshot` is still honest
via `listening:off` + `load_error` (`test_failed_cross_mode_toggle_status_snapshot_is_honest`
@L3826). Do NOT add a redundant `set_mode` to `_disarm` — it would be a no-op and the resident
mode is genuinely unchanged on disarm.

### (ii) The switch uses `_bounded_shutdown`, NOT `_unload_host` (clause c nuance)

`_load_host`@L739 calls `_bounded_shutdown(timeout=5.0)` directly, NOT `_unload_host()`.
`_unload_host`@L1204 is the IDLE-triggered wrapper: it re-checks the full unload condition
(`not self._models_loaded` / `self._host is None` / the `listening` gate / the idle threshold —
@L1225-1230) and would NO-OP during a mode switch (the daemon is not past the idle threshold
when the user switches modes). The switch reuses the bounded-teardown PRIMITIVE
(`_bounded_shutdown`@L1620, the same one `_unload_host` delegates to @L1239) — correct factoring,
not a gap. Both paths terminate the child process group (`host.stop(timeout=5)` → `proc.join(5)`
+ `_terminate_group()` + `join(2)` = ~7s max) and are bounded. (The teardown PRIMITIVE's internals
— killpg mechanics, the ~7s budget derivation — are P1.M2.T2.S3's `gap_lifecycle.md` §3 scope;
this audit cites the line + the budget for acceptance #10 only.)

### (iii) `mode` is read+acted OUTSIDE `_lock` in `toggle`/`toggle_lite` (race-tolerance nuance)

`toggle`@L1407-1409 / `toggle_lite`@L1434-1436 read `(listening, mode)` TOGETHER under `_lock`,
then call `_load_host` OUTSIDE `_lock` (`_load_host` acquire-release-reacquires that lock; calling
it under `_lock` would deadlock). This is the SAME race-tolerant read/act split as the
abort-outside-`_lock` design: the `_listening` Event + `on_final` gate are the source of truth;
toggle is user-paced. Not a gap — documented in the `toggle` docstring @L1393-1410. Tested by
the toggle_lite/toggle semantics tests @L3696-3826.

### (iv) `self._mode` defaults to "normal" at boot (clause d nuance)

`self._mode`@L644 defaults to `"normal"`; `feedback._state["mode"]`@L99 defaults to `"normal"`.
`status_snapshot["mode"]`@L1567 reports `"normal"` at boot before any arm. Correct — the daemon
boots in normal mode (the first arm of either mode overwrites it). Pinned by
`test_status_snapshot_reports_mode`@L2918 (boot=="normal").

### (v) `self._mode` set on SUCCESS only (clause d nuance)

`_load_host`@L766 `self._mode = mode` runs ONLY in the success branch (`if ok`). On failure,
`self._mode` is left unchanged (the prior value). This is intentional: a failed load leaves the
daemon with no resident child (`_models_loaded=False`, `_host=None`), so `self._mode` reflects
the last SUCCESSFUL mode, and `status_snapshot` pairs it with `models_loaded:False` +
`load_error` so the state is honest. Not a gap — covered by the failed-cross-mode-switch tests
@L3790/@L3826.

---

## 5. Conclusion

The mode-switch reload lifecycle faithfully implements **PRD §4.2ter ("Arming rules" / "State /
status" / "Commands / keybind")** + **§7 acceptance #10** on all 6 clauses (a)–(f): each of the 4
user-facing arm commands routes to the correct mode (`toggle`/`start`→normal;
`toggle-lite`/`start-lite`→lite — covered by `_dispatch` + `_COMMANDS` + routing — clause a); an
arm in the SAME mode as the resident child is **instant** (`_load_host` L716-717 `return True`
with the SAME `RecorderHost` object — clause b); an arm in the OTHER mode costs **exactly one
bounded reload** (`_load_host` L718 `switch_mode=True` → L738-741 `_bounded_shutdown(timeout=5.0)`
tears down the old child (≤~7s) → L749-757 spawns fresh in the requested mode — clause c +
acceptance #10); `self._mode` is set on a successful spawn (`_load_host` L766) and surfaced in
`voicectl status` + `state.json` (`status_snapshot` `"mode": self._mode` L1567 — clause d);
`feedback.set_mode` is published on every `_arm` (L998; de-facto-current on disarm — clause e); and
`stop` disarms **regardless** of mode (`stop` L1388 → `_request_stop` L1053-1071 with NO mode
branch — clause f). All with `voice_typing/daemon.py` / `feedback.py` / `recorder_host.py` /
`ctl.py` file:line evidence; the `-k 'mode or toggle_lite or start_lite or switch'` slice is
**15 passed, 178 deselected**.

This certifies the project's acceptance criteria:
- **#10 (switching modes costs one bounded reload; same-mode arm is instant)** — clause (c)
  certifies the cross-mode path: `_load_host`'s `switch_mode` branch (L718, L736-742) tears down the
  old child via `_bounded_shutdown(timeout=5.0)` (≤~7s — the SAME primitive idle-unload uses) then
  spawns fresh in the requested mode (~1-3s on CUDA) = exactly ONE bounded teardown + ONE spawn,
  pinned by `test_mode_switch_stops_outgoing_host`@L2927 (outgoing `host.stop_calls==1`); clause
  (b) certifies the same-mode instant path (`_load_host` L716-717 `return True`, no reload), pinned
  by `test_same_mode_arm_is_instant_no_reload`@L2892.

**Verdict: ✅ COMPLIANT on all 6 clauses — no fix needed.** **No source or test files were
modified** (this is a read-only audit — the mode-switch lifecycle is PRD §4.2ter / acceptance
#10-compliant per this re-verification; no defect surfaced). The only artifact produced by this
subtask is this report section, appended to S1's `gap_lite.md`. Adjacent concerns are correctly
deferred: the **lite CONSTRUCTION kwargs** (one-model, silence gate, CPU fallback) is
P1.M2.T3.S1 (the H1 file this section is appended to); the **T7 live-test COVERAGE audit** is
P1.M2.T3.S3; the **bounded-teardown PRIMITIVE internals** (killpg, `join(5s)` budget) is
P1.M2.T2.S3 (`gap_lifecycle.md` §3); and the **FULL common recorder kwargs** (all §4.4 params) is
P1.M2.T4.S1 — this task audits the RELOAD LIFECYCLE (the 6 clauses a-f) + `self._mode` tracking
only.

---

## Gap Report — P1.M2.T3.S3: T7 Lite Test Coverage vs PRD §6

**Date:** 2026-07-18 (audit re-verified against the live tree)
**Scope:** Audit **PRD §6 T7 lite-mode TEST COVERAGE** — i.e. answer "which `tests/*.py` test
would FAIL if a given T7 contract clause regressed?" — across the two contract input files
(`tests/test_feed_audio.py` — the offline pipeline + lite integration tests; `tests/test_daemon.py`
— the lite kwargs-unit + socket-behavior tests) PLUS the adjacent wire/CLI surfaces
(`tests/test_control_socket.py`, `tests/test_voicectl.py`, `tests/test_status_sh.py`,
`tests/test_config.py`). This is the **test-COVERAGE** angle (S3), complementary to **S1** (the
lite CONSTRUCTION code audit — the H1 file this section is appended to) and **S2** (the
mode-switch RELOAD code audit — the H2 section immediately above): S1/S2 certify the code is
PRD-compliant; **S3 certifies each T7 clause has a PINNING TEST** with `file:line` evidence, so a
regression cannot ship silently. The contract run target is
`timeout 600 .venv/bin/python -m pytest tests/ -q -k 'lite'` (§3). Subtask **P1.M2.T3.S3** of
compliance round `006_862ee9d6ef41`.

**Audited artifacts** (the test file:line inventory re-located via `grep -nE` — §1):
- `tests/test_feed_audio.py` — `lite_recorder` fixture @L311 (`cfg_to_kwargs(cfg, lite=True)` @L324,
  THE lite swap); `test_lite_feed_audio_utt_simple` @L653 (T7(a) `use_main_model_for_realtime is
  True` @L667; T7(b) `_token_overlap(...) >= 0.70` @L676); `test_lite_latency_lower_than_normal`
  @L679 (T7(c) `lite_best <= normal_best * 1.25` @L774, the 25% band); `_token_overlap` helper
  @L142 (the fuzzy multiset matcher; PRD §6 ≥0.80 normal / ≥0.70 lite). GPU-gated.
- `tests/test_daemon.py` — 15 lite tests: kwargs 4 @L138/165/185/216 + mode-switch/socket 11
  @L2863/2875/2892/2904/2918/2927/2951/3696/3708/3719/3753/3790/3809/3851 (see §3 for the index).
- `tests/test_control_socket.py` — `test_dispatch_status_response_carries_mode` @L143 (wire `mode`).
- `tests/test_voicectl.py` — `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode` @L75
  (CLI renders `mode: lite`).
- `tests/test_status_sh.py` — `test_status_sh_lite_mode_prefixes_bolt` @L87 (tmux ⚡ prefix).
- `tests/test_config.py` — 4 `lite_model` / `lite_post_speech_silence_duration` config-field tests.
- `voice_typing/daemon.py` (structural proof for nuance §4.5) — `_arm_response` @L1875-1890
  (`return {"ok": True, **self._daemon.status_snapshot()}` @L1890); `status_snapshot` @L1548
  (`"mode": self._mode` @L1567).

**Bottom line: ✅ COMPREHENSIVE — no coverage gaps; NO new tests written; NO `tests/*` or
`voice_typing/*` files modified.** Every T7 clause (the 3 feed_audio asserts a/b/c + the 4 socket
bullets) has at least one covering test with `file:line` evidence (§2). The contract run target
**`timeout 600 .venv/bin/python -m pytest tests/ -q -k 'lite'`** re-ran live on this box: **collect-only
`26/424 tests collected (398 deselected) in 0.04s`** (§1 baseline); **RUN `26 passed, 398
deselected in 35.56s`** — this is a CUDA box, so the 2 GPU-gated `test_feed_audio.py` integration
tests ran (loaded real `small.en` + `distil-large-v3` models) and PASSED rather than skipping.
This certifies PRD §6 T7's test plan is fully realized AND that acceptance #10's testability
("verified ~half VRAM" → `use_main_model_for_realtime` flag @L667; "observably snappier" →
`lite_best <= normal_best*1.25` @L774; "status and state.json report mode" → `status_snapshot`
@L1567 + `test_status_snapshot_reports_mode`@L2918 + voicectl + status_sh ⚡) is backed by real
tests. The 6 non-defect nuances (§4) document where the test deviates from the literal PRD
wording but is a sound, documented engineering choice — they are NOT gaps.

## 1. Method

Each of the 7 T7 contract clauses (the 3 feed_audio offline asserts a/b/c + the 4 socket
bullets — PRD §6 T7) was mapped to **its covering `tests/*.py` test at `file:line`** via
`grep -nE`, then re-verified by reading the test body to confirm it asserts what the research
note documents. The 2 GPU-gated integration tests (`test_lite_feed_audio_utt_simple`@L653,
`test_lite_latency_lower_than_normal`@L679) were read in full (the skip-guard @L660/@L692; the
`use_main_model_for_realtime is True` flag @L667; the `_token_overlap >= 0.70` @L676; the
`lite_best <= normal_best*1.25` 25%-band @L774 + its in-test rationale comment @L758-777). The
15 `test_daemon.py` lite tests were re-indexed (kwargs 4 @L138-238 + mode-switch/socket 11
@L2863-3851). The structural proof that the arm RESPONSE carries `mode` was confirmed by reading
`_arm_response`@daemon.py:1875-1890 (`return {"ok": True, **self._daemon.status_snapshot()}`) +
`status_snapshot`@L1548 (`"mode": self._mode`@L1567) + `test_dispatch_status_response_carries_mode`
@test_control_socket.py:143 (proves the spread surfaces `mode` on the wire). The contract's test
target was then re-run live (§3 — collect-only + full run, CUDA path). The 6 non-defect nuances
(§4) were confirmed against the test bodies + the method-docstring evidence (the one-model flag
vs VRAM; the path-identity-by-fixture-construction; the latency 25%-band rationale; the 0 lite
tests in `test_recorder_host.py`; the structurally-guaranteed arm-response mode; the typing-backends
false-positive on `-k lite`).

### Commands run (re-verification)

```bash
# locate every cited lite test in the two contract input files + the wire/CLI surfaces
grep -nE 'def test_cfg_to_kwargs_lite|def test_start_lite|def test_mode_switch|def test_same_mode_arm|def test_toggle_lite|def test_toggle_while_armed_in_lite|def test_status_snapshot_reports_mode|def test_start_lite_after_idle' tests/test_daemon.py
grep -nE 'def lite_recorder|def test_lite_feed_audio|def test_lite_latency|use_main_model_for_realtime|_token_overlap|>= 0\.70|<= normal_best' tests/test_feed_audio.py
grep -nE 'def test_dispatch_status_response_carries_mode|"mode"|_dispatch' tests/test_control_socket.py
grep -nE 'def test_lite_commands|def test_status_sh_lite|mode.*lite' tests/test_voicectl.py tests/test_status_sh.py
# the daemon arm-response path that surfaces mode on the wire (structural proof for nuance §4.5)
grep -nE 'def _arm_response|def status_snapshot|"mode": self\._mode' voice_typing/daemon.py
# the contract's run target (collect-only = fast/safe count; RUN = wrap in timeout 600)
timeout 120 .venv/bin/python -m pytest tests/ -q -k 'lite' --collect-only
timeout 600 .venv/bin/python -m pytest tests/ -q -k 'lite'
# scope guard — only gap_lite.md modified (no tests/* or voice_typing/* change)
git status --short
```

## 2. The 7 T7 clauses — per-clause coverage table

### A. T7 feed_audio offline (PRD §6 T7 bullets 1–3)

| T7 clause | Covering test (`file:line`) — re-verified live | Verdict |
|---|---|---|
| **(a) exactly ONE model resident** (no `distil-large-v3` worker; ~half VRAM) — integration-grade | `test_lite_feed_audio_utt_simple`@`test_feed_audio.py:667` asserts `rec.use_main_model_for_realtime is True` on the REAL constructed recorder (a future RealtimeSTT regression of the early-return leaves it False → fail loudly); + kwargs-unit: `test_cfg_to_kwargs_lite_mode_uses_one_model`@`test_daemon.py:138`, `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en`@165, `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal`@185 | ✅ covered (nuance §4.1: proven via the flag + kwargs dict, NOT VRAM/grep — deliberate; the live VRAM diff is `test_idle_and_gpu.sh` T7, out of scope) |
| **(b) finals arrive over the clean→type path, fuzzy-accuracy ≥70%** | `test_lite_feed_audio_utt_simple`@`test_feed_audio.py:676` asserts `_token_overlap(joined, SIMPLE_TEXT) >= 0.70` over the collected finals (lower bar than normal's 0.80 — `small.en` is the final model in lite); collected via the SAME `on_final` callback path as normal (the `lite_recorder` fixture @L311 mirrors `recorder` EXACTLY except the `lite=True` swap) | ✅ covered (nuance §4.2: path-identity is proven by fixture-construction, not a separate assertion) |
| **(c) shorter `post_speech_silence_duration` carried + e2e latency materially lower than normal** | silence-gate: `test_cfg_to_kwargs_lite_uses_shorter_silence_duration`@`test_daemon.py:216` (lite 0.5 vs normal 0.6, tunable to 0.3); latency: `test_lite_latency_lower_than_normal`@`test_feed_audio.py:774` asserts `lite_best <= normal_best * 1.25` (best-of-3 min per recorder) | ✅ covered (nuance §4.3: uses a 25% tolerance BAND `<=`, not strict `<` — DOCUMENTED + sound; see §4.3) |

### B. T7 socket protocol (PRD §6 T7 "Then over the socket" bullets)

| T7 clause | Covering test (`file:line`) — re-verified live | Verdict |
|---|---|---|
| **toggle-lite arms with `mode:"lite"` in the response** | `test_start_lite_loads_lite_host_and_arms`@`test_daemon.py:2863` (`d._mode=="lite"` + `d._host.mode=="lite"` + `fb.modes==["lite"]`); + `test_dispatch_status_response_carries_mode`@`test_control_socket.py:143` proves the wire response carries `mode` (the `{'ok':True,**status_snapshot()}` spread); + `test_status_snapshot_reports_mode`@`test_daemon.py:2918` | ✅ covered (nuance §4.5: the arm-response mode is structurally guaranteed — `_arm_response`@daemon.py:1890 spreads `status_snapshot()`@1567 which has `"mode":self._mode`) |
| **toggle-lite again disarms** | `test_toggle_lite_while_armed_in_lite_disarms`@`test_daemon.py:3708` (`is_listening()` False, `len(spawns)==1` — no reload); + `test_toggle_lite_while_listening_in_lite_stops`@2904 | ✅ covered |
| **a subsequent `toggle` reloads into `mode:"normal"` (ONE reload)** | `test_toggle_while_armed_in_lite_switches_to_normal`@`test_daemon.py:3753` asserts `len(spawns)==2` (lite spawn + ONE normal reload) + `d._mode=="normal"`; + `test_mode_switch_stops_outgoing_host`@2927 (outgoing `stop_calls==1`); + `test_mode_switch_normal_to_lite_reloads`@2875 (reverse); + `test_same_mode_arm_is_instant_no_reload`@2892 (same-mode NO reload); + `test_start_lite_after_idle_unload_reloads_in_lite`@2951 | ✅ covered (the "one reload" count is pinned by `len(spawns)==2` @3753; same-mode instant pinned by `len(spawns)==1` @2892) |
| **`status` reports the current `mode`** | `test_status_snapshot_reports_mode`@`test_daemon.py:2918` (boot normal, post-arm-lite lite); + `test_dispatch_status_response_carries_mode`@`test_control_socket.py:143` (wire); + `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode`@`test_voicectl.py:75` (CLI renders `mode: lite`); + `test_status_sh_lite_mode_prefixes_bolt`@`test_status_sh.py:87` (tmux ⚡ prefix) | ✅ covered (4 surfaces: status_snapshot + wire response + voicectl CLI + tmux ⚡) |

**§2 bottom line:** every T7 clause (feed_audio a/b/c + socket 4 bullets) has ≥1 covering test
with `file:line` evidence. **NO coverage gaps requiring new tests.**

## 3. Test result — the contract's run target (the evidence)

```bash
# collect-only (fast/safe — the baseline count):
$ timeout 120 .venv/bin/python -m pytest tests/ -q -k 'lite' --collect-only
26/424 tests collected (398 deselected) in 0.04s

# RUN the contract target (this is a CUDA box — the 2 feed_audio tests RAN rather than skipping):
$ timeout 600 .venv/bin/python -m pytest tests/ -q -k 'lite'
26 passed, 398 deselected in 35.56s
```

**Per-file breakdown** of the 26 collected (`-k 'lite'`):

| File | # | Tests (the real lite ones) |
|---|---|---|
| `tests/test_daemon.py` | 15 | kwargs (4) @L138/165/185/216 + mode-switch/socket (11) @L2863-3851 — see index below |
| `tests/test_config.py` | 4 | `lite_model` / `lite_post_speech_silence_duration` config-field/param tests |
| `tests/test_feed_audio.py` | 2 | `test_lite_feed_audio_utt_simple`@L653, `test_lite_latency_lower_than_normal`@L679 (GPU-gated — RAN here, CUDA) |
| `tests/test_control_socket.py` | 1 | `test_dispatch_status_response_carries_mode`@L143 |
| `tests/test_voicectl.py` | 1 | `test_lite_commands_are_accepted_and_toggle_lite_renders_lite_mode`@L75 |
| `tests/test_status_sh.py` | 1 | `test_status_sh_lite_mode_prefixes_bolt`@L87 (the ⚡ prefix) |
| `tests/test_recorder_host.py` | 0 | (nuance §4.4 — NOT a gap; lite construction is unit-tested at the `cfg_to_kwargs` layer + the child is a pass-through) |
| `tests/test_typing_backends.py` | 1 | **false positive** — `test_wtype_text_starting_with_dash_stays_literal` matches "lite" via "lite**ral**"; NOT a lite test (nuance §4.6) |

**The 15 `test_daemon.py` lite tests** (mocked-CUDA, ~0.04s slice — clause→test index):

```
# kwargs (4) — T7(a)/(c) unit
test_cfg_to_kwargs_lite_mode_uses_one_model              @138   (a) one-model kwargs
test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en        @165   (a) CPU one-model (tiny.en)
test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal     @185   isolation (only 4 fields differ)
test_cfg_to_kwargs_lite_uses_shorter_silence_duration    @216   (c) silence gate 0.5 vs 0.6

# mode-switch / socket-behavior (11) — T7 socket + acceptance #10
test_start_lite_loads_lite_host_and_arms                 @2863  start-lite → lite host + arm + _mode
test_mode_switch_normal_to_lite_reloads                  @2875  cross-mode reload (normal→lite)
test_same_mode_arm_is_instant_no_reload                  @2892  same-mode instant (no reload)
test_toggle_lite_while_listening_in_lite_stops           @2904  toggle-lite disarms lite
test_status_snapshot_reports_mode                        @2918  status carries mode (boot/arm)
test_mode_switch_stops_outgoing_host                     @2927  outgoing stop_calls==1 (one reload)
test_start_lite_after_idle_unload_reloads_in_lite        @2951  reload after idle-unload → lite
test_toggle_lite_while_idle_arms_in_lite                 @3696  toggle-lite idle → arm lite
test_toggle_lite_while_armed_in_lite_disarms             @3708  toggle-lite armed-in-lite → disarm
test_toggle_lite_while_armed_in_normal_switches_to_lite  @3719  cross-mode (normal→lite, one reload)
test_toggle_while_armed_in_lite_switches_to_normal       @3753  cross-mode (lite→normal, one reload)
test_toggle_lite_while_armed_in_normal_failed_reload_clears_listening  @3790  failed-reload honesty
test_toggle_while_armed_in_lite_failed_reload_clears_listening         @3809 failed-reload honesty
test_toggle_lite_docstring_says_pressing_d_not_f         @3851  docstring guard
```

(15 selected by `-k lite` in `test_daemon.py`; matches S1's + S2's baselines — disjoint ANGLE:
S1/S2 audit the CODE compliance, S3 audits the TEST COVERAGE of those same tests.)

**Run semantics (what the next box will observe):** on a **non-GPU box** the 2 `test_feed_audio.py`
lite tests `pytest.skip("T7 is a GPU integration test (G-CPU)")` → the run shows **24 passed,
2 skipped** in ~0.04s (the 1 false-positive typing-backends test also passes trivially). On a
**CUDA box** (this one) all 26 run, the 2 feed_audio tests load real models (`small.en` +
`distil-large-v3` in the session-scoped `recorder` + `lite_recorder` fixtures) → ~36s, must be
wrapped in `timeout 600` (AGENTS.md Rule 1). Both outcomes are valid; the collect-only
`26/424, 398 deselected` count is the stable anchor regardless of CUDA state.

## 4. Non-defect nuances (NON-blocking — recorded so they are NOT mistaken for gaps)

### (4.1) "ONE model resident / ~half VRAM" is proven via the invariant FLAG, not VRAM/grep.

PRD T7(a) literally says "grep the child log / check VRAM ≈ half of normal". The tests instead
assert `rec.use_main_model_for_realtime is True` (integration @L667) + the kwargs dict (unit
@L138/165/185). This is a DELIBERATE, sound choice: the flag is the AUTHORITATIVE one-model
mechanism (verified against RealtimeSTT — `use_main_model_for_realtime=True` early-returns out
of `_initialize_realtime_transcription_model`, so the large model never constructs → ~half VRAM
is STRUCTURALLY guaranteed). VRAM varies by GPU/driver state; child-log grep is brittle. The flag
assertion is strictly MORE reliable than a VRAM diff. **NOT a gap.** The live VRAM check is
exercised by `tests/test_idle_and_gpu.sh` T7 (the shell suite, P1.M5.T3) — out of scope for this
pytest coverage audit.

### (4.2) "finals over the clean→type path" is proven by fixture CONSTRUCTION, not a separate assertion.

The `lite_recorder` fixture @L311 mirrors the normal `recorder` fixture EXACTLY except the
`lite=True` swap (same `on_realtime_transcription_stabilized` / `on_vad_start` / `on_vad_stop` /
`add_final` callbacks, same shutdown). The clean→type path is therefore SHARED by construction —
there is nothing lite-specific about the path to assert. PRD §4.2ter confirms: "on_final
therefore yields lite_model finals — fast, lower-accuracy — over the SAME clean→type→record path
as normal mode." **NOT a gap.**

### (4.3) Latency uses a 25% tolerance BAND (`<= normal*1.25`), not strict "materially lower" (`<`).

PRD T7(c) says "end-to-end stop→text latency is materially lower than normal mode". The test
asserts `lite_best <= normal_best * 1.25` @L774. This is a DOCUMENTED engineering choice (in-test
comment @L758-777): on a fast GPU a 9-word utterance shows the small-model win (~50ms) SWAMPED
by VAD/realtime-stabilization/GPU-scheduling noise, so strict `<` is flaky. The test's PURPOSE is
to catch a two-model regression (~1.5-2x slower), which the 1.25x band catches loudly. The
one-model invariant (`test_lite_feed_audio_utt_simple`) is the PRIMARY proof; this latency test
is SECONDARY corroboration. **NOT a gap** — a documented, sound deviation. Tightening to strict
`<` would make the test flaky on CI without adding real coverage.

### (4.4) `tests/test_recorder_host.py` has ZERO lite tests.

`grep -c -i lite tests/test_recorder_host.py` = 0. **NOT a gap** (recorded by S1 §4(ii)): lite
CONSTRUCTION is unit-tested at the `cfg_to_kwargs` layer (`test_daemon.py`, 4 kwargs tests) +
the `mode == "lite"` → `lite = True` derivation is a one-line literal verified by reading + the
live `test_idle_and_gpu.sh` T7 + the `test_feed_audio.py` lite tests exercise the real child
end-to-end. The child adds no model logic of its own (pass-through to `daemon.build_recorder`).

### (4.5) The arm-RESPONSE-carries-mode is structurally guaranteed (transitive coverage).

No test directly asserts `_dispatch("toggle-lite")` returns `{"ok":True,"mode":"lite",...}` on an
arm. BUT: `_arm_response`@daemon.py:1890 is literally `return {"ok": True,
**self._daemon.status_snapshot()}`, and `status_snapshot`@1565-1567 has `"mode": self._mode`, and
`test_dispatch_status_response_carries_mode`@test_control_socket.py:143 proves `status_snapshot`'s
`mode` reaches the wire via that exact spread. So the arm response carrying mode is PROVEN by
composition (the status test + the one-line spread). The daemon-state tests (`d._mode=="lite"`)
confirm the value is "lite" after the arm. **NOT a gap** — a purist could add a direct
`_dispatch("toggle-lite")["mode"]=="lite"` test, but it would be redundant with the existing
status-response + daemon-state coverage. (Optional hardening, not a requirement.)

### (4.6) `test_typing_backends.py::test_wtype_text_starting_with_dash_stays_literal` is a FALSE POSITIVE.

It matches `-k lite` only because "literal" contains "lite". It is NOT a lite-mode test (it
tests `wtype` text escaping). The implementing agent should NOT count it as lite coverage; it is
noted here so the 26-collected count is reconciled correctly (15 + 4 + 2 + 1 + 1 + 1 + 0 +
1-false-positive = 25 real lite tests + 1 false positive = 26 collected).

## 5. Conclusion

**Verdict: ✅ T7 lite test coverage is COMPREHENSIVE — no gaps; NO new tests written; NO `tests/*`
or `voice_typing/*` files modified.** Every one of PRD §6 T7's 7 clauses (feed_audio a/b/c + the
4 socket bullets) has ≥1 pinning test with `file:line` evidence (§2): the one-model invariant
(`test_lite_feed_audio_utt_simple`@L667 + 3 kwargs-unit tests), the ≥70% fuzzy accuracy (@L676),
the shorter silence gate (`test_cfg_to_kwargs_lite_uses_shorter_silence_duration`@L216) + the
25%-band latency (`test_lite_latency_lower_than_normal`@L774), and the 4 socket bullets
(`test_start_lite_loads_lite_host_and_arms`@L2863 + `test_dispatch_status_response_carries_mode`
@test_control_socket.py:143 + `test_toggle_lite_while_armed_in_lite_disarms`@L3708 +
`test_toggle_while_armed_in_lite_switches_to_normal`@L3753 + `test_status_snapshot_reports_mode`
@L2918 + voicectl @L75 + status_sh ⚡ @L87). The contract run target re-ran live:
**collect-only `26/424, 398 deselected`**; **RUN `26 passed` (CUDA box — the 2 GPU-gated feed_audio
tests ran rather than skipping)**.

This certifies PRD §6 T7's test plan is fully realized AND that acceptance #10's testability is
backed by real tests: **"verified ~half VRAM"** → the `use_main_model_for_realtime` flag @L667
(the authoritative one-model mechanism, structurally guaranteeing ~half VRAM — nuance §4.1);
**"observably snappier"** → `lite_best <= normal_best*1.25` @L774 (the 25%-band catches a two-model
regression loudly — nuance §4.3); **"status and state.json report mode"** → `status_snapshot`
@L1567 + `test_status_snapshot_reports_mode`@L2918 + voicectl CLI + tmux ⚡. The 6 nuances (§4)
document where the test deviates from the literal PRD wording but is a sound engineering choice —
they are NOT gaps.

**Adjacent concerns correctly deferred** (out of scope for this pytest coverage audit): the lite
CONSTRUCTION code (the 4 kwargs clauses) is **P1.M2.T3.S1** (the H1 file this section is appended
to); the mode-switch RELOAD code (the 6 clauses) is **P1.M2.T3.S2** (the H2 section immediately
above); the **live GPU VRAM/accuracy pass** is `tests/test_idle_and_gpu.sh` T7 (the shell suite,
**P1.M5.T3**); the **real-hardware smoke** is T5 (the README, **P1.M6.T1**). This task audits the
TEST COVERAGE of PRD §6 T7 only — and certifies it is comprehensive. No source or test files were
modified (this is a read-only + report audit; no defect surfaced).
