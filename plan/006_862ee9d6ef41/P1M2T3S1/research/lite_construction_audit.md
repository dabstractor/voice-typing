# Research — Lite recorder construction audit (P1.M2.T3.S1 vs PRD §4.2ter + §4.4)

## VERIFIED VERDICT: ✅ COMPLIANT — no source fix needed.

The lite recorder construction satisfies all 4 item clauses (a)-(d) on the live tree. The contract's
run target `tests/test_recorder_host.py tests/test_daemon.py -q -k lite` → **15 passed, 204 deselected
in 0.03s** (re-ran live). This note is the pre-verified audit; the implementing agent RE-VERIFIES by
reading the cited lines, re-running the tests, and transcribing `architecture/gap_lite.md`.

## §0. The 4 contract clauses — file:line evidence + verdict

| # | Clause (PRD §4.2ter/§4.4) | Code actual (file:line) | Verdict |
|---|---|---|---|
| (a) | `_load_host('lite')` passes `lite=True` to the child | daemon.py:698 `_load_host(mode="normal")`; :757 `factory(..., mode=mode)`→RecorderHost(mode="lite"); recorder_host.py:194-196 `ctx.Process(target=_worker_main, args=(...,self._mode))`; :421 `_worker_main(...,mode="normal")`; :458 `lite = mode == "lite"`; :476 `build_recorder(..., lite=lite)`; daemon.py:292/311 `build_recorder(..., lite=lite)`→`cfg_to_kwargs(cfg, resolved=resolved, lite=lite)`; daemon.py:752 `self._mode = mode` | ✅ COMPLIANT |
| (b) | lite sets `model=lite_model`, `realtime_model_type=lite_model`, `use_main_model_for_realtime=True` | daemon.py:184-192 (cfg_to_kwargs lite branch: `resolved["final_model"]=resolved["realtime_model"]=lite_model`); :200-204 kwargs `"model":resolved["final_model"]`, `"realtime_model_type":resolved["realtime_model"]` (both=small.en on CUDA); :206-209 `kwargs["use_main_model_for_realtime"]=True` (overrides `_FIXED_KWARGS` False @101) | ✅ COMPLIANT |
| (c) | `post_speech_silence_duration` overridden to `lite_post_speech_silence_duration` | daemon.py:203 common block `cfg.asr.post_speech_silence_duration` (0.6); :206-213 lite block `kwargs["post_speech_silence_duration"]=cfg.asr.lite_post_speech_silence_duration` (0.5) — overrides the common value; config.py:58 `post_speech_silence_duration: float = 0.6`; :59 `lite_post_speech_silence_duration: float = 0.5` | ✅ COMPLIANT |
| (d) | `_child_resolved_device` handles lite CPU fallback (tiny.en) | recorder_host.py:680 `_child_resolved_device(cfg, force_cpu, lite=False)`; :707-714 `if lite: lite_model="tiny.en" if d["device"]=="cpu" else cfg.asr.lite_model; d["final_model"]=d["realtime_model"]=lite_model`. ALSO the LOAD path daemon.py:184-192 does the same (`"tiny.en" if resolved["device"]=="cpu"`) — two-site consistency, see §2 | ✅ COMPLIANT |

## §1. The full mode→lite call chain (clause a, end to end)

```
daemon.start_lite()  @1376 / toggle_lite() @1426
  └─ self._load_host("lite")  @698                       # mode="lite"
       ├─ with self._lock: switch_mode = (resident.mode != "lite") @715-718  # mode-mismatch → reload
       ├─ if switch_mode: self._bounded_shutdown(5.0); self._host=None  @736-741   # tear wrong-mode child
       ├─ host = RecorderHost(..., mode="lite")  @751-757                    # mode threaded into the host
       │      └─ recorder_host.RecorderHost.__init__(..., mode="lite"): self._mode=mode  (property @168)
       ├─ ok = host.spawn()  @758
       │      └─ ctx.Process(target=_worker_main, args=(cfg, cmd_q, evt_q, abort_evt, force_cpu, self._mode))  @194-196
       │           └─ _worker_main(cfg, ..., mode="lite")  @421
       │                ├─ lite = mode == "lite"  @458                      # True
       │                └─ recorder = build_recorder(cfg, relay_fb, relay_lat, on_speech=..., lite=lite)  @476
       │                     └─ daemon.build_recorder(..., lite=True)  @323
       │                          └─ daemon._construct(..., lite=True)  @285
       │                               └─ kwargs = cfg_to_kwargs(cfg, resolved=resolved, lite=True)  @311
       │                                    # (b)+(c) applied HERE (daemon.py:184-213)
       ├─ with self._lock (re-acquire): self._mode = mode  @752             # resident mode tracked for status
       └─ return ok  @795
```
The chain is unbroken: `_load_host("lite")` → child built with `lite=True` → `cfg_to_kwargs(lite=True)`
→ the recorder kwargs carry small.en×2 + use_main_model_for_realtime=True + 0.5 silence. The CPU-fallback
retry (recorder_host.py:481-494) re-calls `build_recorder(..., force_cpu=True, lite=lite)` — `lite` is
PRESERVED across the retry (it is a per-mode property, not a device property), so a force_cpu lite build
still uses tiny.en. ✓

## §2. Two-site lite-CPU-fallback (load path + status path) — intentional duplication

The lite CPU substitute ("tiny.en") is applied in TWO places that MUST agree:
1. **LOAD path** — `daemon.cfg_to_kwargs` (daemon.py:184-192): sets `resolved["final_model"]`/
   `resolved["realtime_model"]` = tiny.en (CPU) — this is what the recorder actually CONSTRUCTS.
2. **STATUS path** — `recorder_host._child_resolved_device` (recorder_host.py:707-714): sets
   `d["final_model"]`/`d["realtime_model"]` = tiny.en (CPU) — this is the dict the child sends back as
   its 'ready' event, which seeds `daemon._resolved_device_cache` (daemon.py:765) for `voicectl status`.
Both discriminate on `device == "cpu"` (NOT a force_cpu flag — cfg_to_kwargs has none; the resolved
device is the truth and also covers probe-failure/cuda_check→CPU). This is NOT a defect — load and
status must report the same model, and both do. (delta §3.2 BUG-A rationale; test_cfg_to_kwargs_lite_
cpu_fallback_uses_tiny_en covers the load path; the status path is exercised live by test_idle_and_gpu.sh T7.)

## §3. Test evidence (contract run target, re-ran live)

```bash
timeout 300 .venv/bin/python -m pytest tests/test_recorder_host.py tests/test_daemon.py -q -k lite
# → 15 passed, 204 deselected in 0.03s
```
- `tests/test_recorder_host.py` has **ZERO** lite tests (`grep -c -i lite` = 0). All 15 selected tests are
  in `tests/test_daemon.py`. (The recorder-host child is a thin pass-through to `daemon.build_recorder`,
  which IS unit-tested; lite construction is verified at the kwargs layer + live. See nuance §4.2.)
- The load-bearing lite kwargs tests (test_daemon.py):
  - `test_cfg_to_kwargs_lite_mode_uses_one_model` @138 — model=realtime_model_type=small.en;
    use_main_model_for_realtime=True; normal mode = distil-large-v3 + False.  ← clause (b)
  - `test_cfg_to_kwargs_lite_cpu_fallback_uses_tiny_en` @165 — CPU → tiny.en; one-model flag stays True.  ← clause (d)
  - `test_cfg_to_kwargs_lite_keeps_all_other_kwargs_equal` @185 — ONLY {model, realtime_model_type,
    use_main_model_for_realtime, post_speech_silence_duration} differ; everything else identical.  ← isolation guard
  - `test_cfg_to_kwargs_lite_uses_shorter_silence_duration` @216 — lite=0.5, normal=0.6; tunable (0.3).  ← clause (c)
- NOTE: `-k lite` also matches config param ids (lite_model, lite_post_speech_silence_duration) — hence
  15 selected (not just 4). The 4 named tests above are the clause-specific assertions; the rest are
  the kwargs isolation + fixed-value guards whose cfg fixture carries the lite fields.

## §4. Non-defect nuances (record so they are not mistaken for gaps)

1. **Model identity is assigned in `cfg_to_kwargs` (daemon.py), NOT in `_worker_main` (recorder_host.py).**
   `_worker_main` does NOT set `model=`/`realtime_model_type=` itself — it calls
   `build_recorder(lite=lite)` → `cfg_to_kwargs(lite=True)`, which sets them (daemon.py:184-204). Correct
   layering: the kwargs builder is the single source of truth for model identity; the child is a
   pass-through. Clause (b) is satisfied via this chain, not by a literal assignment in _worker_main.
2. **`tests/test_recorder_host.py` has no lite tests.** Lite CONSTRUCTION is unit-tested at the
   `cfg_to_kwargs` layer (test_daemon.py, 4 tests above) + the `mode=="lite"`→`lite=True` derivation is a
   one-line literal (recorder_host.py:458) verified by reading; the live `test_idle_and_gpu.sh` T7 section
   + `test_feed_audio.py` lite tests exercise the real child end-to-end. Not a gap — the child adds no
   model logic of its own.
3. **Two-site lite-CPU-fallback duplication** (§2): cfg_to_kwargs (load) + _child_resolved_device (status).
   Intentional; both agree (tiny.en on CPU, small.en on CUDA). The audit records both file:line sites.
4. **`lite` is a SPAWN-TIME property** (recorder_host.py:456-458 docstring + `lite = mode == "lite"`).
   It cannot change without a reload (the resident child is built for exactly one mode). Matches PRD §4.2ter
   "Mode is a spawn-time property of the recorder-host child." Mode-switch reload (the `switch_mode` branch
   in `_load_host` @715-741) is audited by **P1.M2.T3.S2**, NOT this task.

## §5. gap_lite.md structure (mirror the gap_*.md convention)

Location: `plan/006_862ee9d6ef41/architecture/gap_lite.md` (does NOT exist yet → CREATE; siblings:
gap_config.md, gap_textproc.md, gap_typing.md, gap_cuda_check.md, gap_daemon_loop.md, gap_lifecycle.md).
Format (mirror gap_lifecycle.md):
- Title: `# Gap Report — P1.M2.T3.S1: Lite Recorder Construction vs PRD §4.2ter`
- Date + Scope + Audited artifacts (file:line): daemon.py (cfg_to_kwargs @158-216, _construct @285-311,
  build_recorder @323-345, _load_host @698-795, start_lite @1376-1383, toggle_lite @1426-1441);
  recorder_host.py (_worker_main @421-510 esp. 456-498, _child_resolved_device @680-715, RecorderHost
  mode property @168 + spawn @181-228); config.py (lite_model @54, lite_post_speech_silence_duration @59).
- Bottom line: ✅ COMPLIANT (all 4 clauses) + the test count.
- §1 Method: grep commands + the test command (§3).
- §2 per-clause compliance table (§0 above) — PRD §4.2ter/§4.4 expected vs code actual vs verdict.
- §3 test evidence (15 passed, 204 deselected; the 4 named tests).
- §4 nuances (§4 above — the 4 non-defects).
- Conclusion: ties the verdict to PRD §4.2ter + §4.4 + acceptance #10 (lite uses ONLY lite_model; ~half
  VRAM; its own shorter post_speech_silence_duration so it's observably snappier).

## §6. Scope boundaries (disjoint from siblings — no conflict)

- **P1.M2.T2.S4 (parallel)** appends a `# §4` section to `gap_lifecycle.md` (idle AUTO-STOP watchdog,
  §4.5 auto_stop_idle_seconds). DISJOINT topic + DISJOINT file (it edits gap_lifecycle.md; this task
  creates gap_lite.md). No overlap.
- **P1.M2.T3.S2** (planned) audits the mode-switch RELOAD + `self._mode` tracking (`_load_host`
  switch_mode branch @715-741). THIS task (S1) audits the lite CONSTRUCTION kwargs only; it REFERENCES
  the mode-threading (clause a) but the reload mechanic itself is S2's scope.
- **P1.M2.T3.S3** (planned) verifies T7 lite test COVERAGE (test_feed_audio.py lite + test_idle_and_gpu.sh
  T7). THIS task records that those exist + the unit-level count, but the T7 coverage audit is S3.
- **P1.M2.T4.S1** (planned) audits the FULL recorder kwargs (all §4.4 params, silero_backend,
  no_log_file, kwarg filtering). THIS task audits the LITE DELTA only (the 4 fields lite changes); the
  common kwargs are T4.S1. Non-overlapping (lite delta vs common kwargs).