# Research Note — P1.M1.T2.S2: daemon.py + recorder_host.py mode collapse

Verified against the live tree (post-T1.S1 `7eed2bb`). Primary refs: `daemon_control_map.md` §1/§4/§6/§7
(line-verified map), `P1M1T2S1/PRP.md` (the 3-key cuda_check contract, parallel), the cfg_to_kwargs region
read verbatim (daemon.py:95-219).

## 1. Landing state (drives the sequencing)

- **T1.S1 (config schema) LANDED**: `AsrConfig.lite_model` is THE model field (config.py:52);
  `post_speech_silence_duration=0.6` still exists (57); `lite_post_speech_silence_duration=0.8` (58);
  NO `final_model`/`realtime_model` in AsrConfig. ⇒ daemon.py:152-153 (`cfg.asr.final_model` /
  `cfg.asr.realtime_model`) currently raises AttributeError — the intended red-transient T2.S2 fixes.
- **S1 (cuda_check 3-key) NOT yet landed** (cuda_check.py:48-49 still 4-key). Treat as contract:
  `CUDA_DEFAULTS={cuda,float16,small.en}`, `CPU_FALLBACK={cpu,int8,tiny.en}`,
  `resolve_device_and_models()` → 3-key. My cfg_to_kwargs reads `resolved["model"]` — S1 MUST land
  first. Gate: `grep -n '"model": "small.en"' voice_typing/cuda_check.py`.

## 2. The daemon.py edit sites (verified line numbers)

| site | line(s) | end state |
|---|---|---|
| `_FIXED_KWARGS` use_main_model_for_realtime | 101 | DELETE the entry (set explicitly in the single branch) |
| `_resolve_device_config` | 141-155 | 3-key defaults `{device, compute_type (derived), model: cfg.asr.lite_model}` |
| `cfg_to_kwargs(cfg, *, resolved=None, lite=False)` | 158-215 | drop `lite`; single branch: `model=realtime_model_type=resolved["model"]`, `use_main_model_for_realtime=True`, `post_speech_silence_duration=cfg.asr.lite_post_speech_silence_duration`; delete lite pre-kwargs (184-193) + lite overrides (205-214) |
| `build_recorder`/`_construct` `lite=` | 285-345 | drop the param (child always single-construction) |
| `self._mode` decl | 656 | DELETE |
| `_load_recorder` alias | 700-708 | DELETE (its docstring already says it's an alias) |
| `_load_host(mode="normal")` | 710-805 | no param; fast path resident+alive→True; DELETE switch branch (748-754); spawn passes NO mode (real path 762-767 drops `mode=mode`; fake path 768-772 likewise); publish drops `_mode=mode` (778) |
| `start()` | 1430-1439 | `_load_host()` (no arg) + arm |
| `start_lite()` | 1441-1451 | DELETE |
| `toggle()`/`toggle_lite()` | 1458-1516 | toggle: bare-`listening` condition → `_request_stop()` else `_load_host()`+`_arm()`; DELETE toggle_lite |
| `_arm` set_mode | 1039 | `self._feedback.set_mode("lite")` CONSTANT (schema stable, §4.6) |
| status_snapshot mode key | ~1632 | `"mode": "lite"` CONSTANT |
| status_snapshot model keys | 1641-1642 | replace `final_model`/`realtime_model` with ONE `"model": dev.get("model","unknown")` (14→13 keys) |
| `_unprobed_device_config` | 1669-1684 (used @573/942/1313) | 3-key `{device, compute_type, model: cfg.asr.lite_model}` |
| `_log_resolved_device` | 957-975 | print `model=%s` only (drop final_model=/realtime_model= args @970-975) |
| dispatch lite cases | 1989-2013 | DELETE both `start-lite` + `toggle-lite` arms (unknown-cmd reply covers them) |

## 3. The recorder_host.py edit sites

`mode` param @114; `self._mode` @125; `mode` property @168-170; spawn args include `self._mode` @195;
`_worker_main(..., mode)` @427; child `lite = mode == "lite"` @458; `build_recorder(..., lite=lite)`
@470+478; `_child_resolved_device(cfg, force_cpu, lite=)` @681-714 (overrides to lite_model in lite);
module docstring ready-payload shape @23 (4-key). ALL collapse: no mode anywhere; child builds the single
construction; `_child_resolved_device` → 3-key `{device, compute_type, model}` (CPU path → tiny.en);
ready payload 3-key (daemon caches `host.device` @782 — still works).

## 4. Simplification the collapse buys (worth stating in the PRP)

The old lite pre-kwargs block discriminated `"tiny.en" if resolved["device"]=="cpu" else
cfg.asr.lite_model` INSIDE cfg_to_kwargs. In the end state that mapping lives in ONE place —
cuda_check's CPU_FALLBACK (`tiny.en`) — because `resolve()` overrides defaults wholesale on no-CUDA.
cfg_to_kwargs just maps `resolved["model"]` to BOTH slots. No device discrimination in the daemon.

## 5. Test family to rewrite/delete (map §6, full list)

**test_daemon.py** — cfg_to_kwargs lite variants @138/165/185/216 (+ asserts @147-149, 179-182,
206-212, 225-238) → ONE single-path kwargs test. Mode/toggle family @2964-3070 (`start_lite_loads`,
`mode_switch_normal_to_lite_reloads`, `same_mode_arm_is_instant`, `toggle_lite_while_listening_stops`,
`status_snapshot_reports_mode`, `mode_switch_stops_outgoing_host`, `start_lite_after_idle_unload`) and
@3865-4060 (toggle_lite idle/disarm/switch×2, failed-cross-mode×2, honest-status×2, dispatch-cross-mode×2,
docstring test) → DELETE switches; keep single-path equivalents (start arms; toggle involution;
status mode constant; idle-unload→start reloads). `_construct/build_recorder` "lite" signature asserts
@2824-2835 → drop. `_cuda_resolve` stub @80-100 returns 3-key. CPU sites @2747/2769/2816 (S1 already
re-pinned to end-state expectations — they go GREEN when this lands).
**test_control_socket.py** — @131 dispatch lite cmds → DELETE; @143 status-carries-mode → KEEP (mode
stays). **test_recorder_host.py** — lite-flag/spawn-args tests → no mode in args. **test_voicectl.py**
@62/75 — SURVIVE as-is (pure ctl unit tests; mode render stays; `lite` cmds in `_COMMANDS` are S3's
collapse). **test_feedback.py** @138 etc. — untouched (set_mode stays; constant 'lite' from _arm).
Heavy: test_feed_audio.py @653/679 + test_idle_and_gpu.sh T7 @535-578 → P1.M3.T9.S1's (NOT here).

## 6. Sibling boundaries

S3 owns ctl.py `_COMMANDS`/argparse/loading-hint lite entries + hypr-binds + that voicectl test.
S4 owns prefetch.py CORE_REPOS + hypr-binds.conf:52 + ACCEPTANCE #10. feedback.py UNTOUCHED (set_mode
stays; `"mode":"normal"` default at feedback.py:99 is now just the pre-arm default — _arm writes 'lite').
config.py UNTOUCHED (T1.S1's `post_speech_silence_duration=0.6` @57 becomes an unused-in-kwargs field;
removing it is schema churn T1.S1 already settled — leave).
