# System Context — voice-typing Lite Mode Delta (plan 004)

> **Scope:** This document is the authoritative architecture reference for the **Lite Mode delta**
> (PRD §4.2ter). It documents the *existing* process-isolation architecture that the delta builds on,
> the *current implementation state* of the delta (substantially landed in the **uncommitted working
> tree**), the **confirmed bugs/gaps** vs the delta spec, and the **exact edit sites** downstream PRP
> agents must touch. Read this before any implementation subtask.

---

## 1. What this delta is

A second arming mode (`voicectl toggle-lite` / Hyprland `SUPER ALT, F`) that loads **only** the small
realtime model (`lite_model`, default `small.en`) and uses it for BOTH partials AND finals. The large
final model (`distil-large-v3`) never loads in lite mode. Benefit: ~half the VRAM + faster finals, at
lower accuracy. Switching modes costs one bounded ~1–3 s reload (teardown + respawn of the recorder
child).

The full spec is `plan/004_607e9cca32b7/delta_prd.md`. The graceful-stop drain (PRD §4.2 #2) is
**already implemented and out of scope** — confirmed by commits `5f32d74`, `495bdd2`, `5c83567` and
the `_request_stop`/`_begin_drain`/`_complete_drain` machinery in `daemon.py`.

---

## 2. The load-bearing architecture: recorder lives in a CHILD subprocess

The recorder (RealtimeSTT / faster-whisper / CTranslate2 / torch / CUDA) does **NOT** live in the
daemon process. It lives in a **spawned child subprocess** owned by `voice_typing/recorder_host.py`.
This is critical context — it is MORE advanced than the PRD §4.1 layout (which shows the recorder
directly in `daemon.py`) and every lite-mode concern must respect it.

```
daemon process (no CUDA, no torch import)
  └─ VoiceTypingDaemon
       ├─ self._host : RecorderHost   (handle to the child; lazily spawned on first arm)
       ├─ _load_host(mode)             (single-flight spawn; mode-aware teardown/respawn)
       ├─ _unload_host()               (single-flight bounded teardown for idle-unload)
       ├─ start_lite()/toggle_lite()   (arm in lite mode — NEW)
       └─ _arm()/_disarm()             (mic on/off via host.set_microphone; set_mode on arm)
                              │ IPC: mp queues (cmd_q, evt_q) + abort Event
                              ▼
child process (owns CUDA: torch, ctranslate2, faster-whisper, RealtimeSTT)
  └─ _worker_main(cfg, cmd_q, evt_q, abort_event, force_cpu, mode)
       └─ build_recorder(cfg, relay_fb, relay_lat, force_cpu=, lite=mode=="lite", on_speech=)
            └─ AudioToTextRecorder(model=, realtime_model_type=, use_main_model_for_realtime=, ...)
```

**Why this matters for lite mode:**
- The daemon stays CUDA-free. `self._mode` is a plain string on the daemon; the actual model choice
  happens in the CHILD via `build_recorder(lite=...)`.
- Mode-switch reload = kill the child PROCESS GROUP (`host.stop()` → `os.killpg`) + respawn — this is
  the SAME bounded-teardown machinery idle-unload uses (`_unload_host`). Killing the group releases
  ALL VRAM. Reuse it; do **not** write a second teardown path.
- `_child_resolved_device(cfg, force_cpu, lite)` (runs in the child) reports the resolved device +
  models back to the daemon on the `ready` event, so the daemon seeds `self._resolved_device_cache`
  WITHOUT probing CUDA itself.

---

## 3. Current implementation state (working tree, UNCOMMITTED)

`git status --porcelain` shows 7 modified files. The lite-mode FEATURE CODE is ~90% landed but
**breaks 66 existing tests** and has **2 confirmed spec bugs** + **3 missing pieces**. The changes are
uncommitted (no commit since `96fd9f1 Add Lite mode single-model arming spec`).

### 3.1 DONE (verify, do not rebuild) — edit sites

| Layer | File | What | Evidence |
|---|---|---|---|
| Config | `voice_typing/config.py:54` | `AsrConfig.lite_model: str = "small.en"` | field + `__post_init__` validation list includes `lite_model` (line 93) |
| Config | `config.toml` [asr] | `lite_model = "small.en"` line | with self-documenting comment |
| Construction | `voice_typing/daemon.py:159` | `cfg_to_kwargs(cfg, *, resolved=None, lite=False)` | lite branch sets `model=realtime_model_type=lite_model` + `use_main_model_for_realtime=True` |
| Construction | `voice_typing/daemon.py:280,311` | `_construct(lite=)`, `build_recorder(lite=)` | thread `lite` through |
| Daemon | `voice_typing/daemon.py:624` | `self._mode: str = "normal"` | boot default |
| Daemon | `voice_typing/daemon.py:680` | `_load_host(mode="normal")` | mode-switch: `switch_mode` detection (698-700), teardown-then-respawn (716-721), `mode=mode` to factory (732/737), `self._mode = mode` on success (746) |
| Daemon | `voice_typing/daemon.py:1318,1351` | `start_lite()`, `toggle_lite()` | call `_load_host("lite")` then `_arm()` |
| Daemon | `voice_typing/daemon.py:972` | `_arm()` calls `self._feedback.set_mode(self._mode)` | publishes armed mode |
| Daemon | `voice_typing/daemon.py:1480` | `status_snapshot()` includes `"mode": self._mode` | |
| Socket | `voice_typing/daemon.py:1808-1813` | `_dispatch` handles `start-lite`, `toggle-lite` | routes to `start_lite`/`toggle_lite` |
| Host | `voice_typing/recorder_host.py:113-125,169-170,195` | `RecorderHost.__init__(mode=)`, `mode` property, spawn `args` tuple includes `self._mode` | |
| Host | `voice_typing/recorder_host.py:456-498` | `_worker_main(..., mode)`: `lite = mode=="lite"`, `build_recorder(..., lite=lite)` on BOTH primary + force_cpu paths, `_child_resolved_device(cfg, force_cpu, lite=lite)` | |
| Host | `voice_typing/recorder_host.py:661-688` | `_child_resolved_device(cfg, force_cpu, lite=)` overrides final/realtime model to `lite_model` in lite | |
| Feedback | `voice_typing/feedback.py:99,145-150` | `_state["mode"]="normal"` default + `set_mode(mode)` | writes `self._state["mode"]` |
| ctl | `voice_typing/ctl.py:35,67,197` | `_COMMANDS` has `toggle-lite`/`start-lite`; `format_result` reads `mode`; loading hint covers lite variants | |
| Keybind | `hypr-binds.conf` | `SUPER ALT, F → toggle-lite` bind added | + header comment documents both binds |

### 3.2 CONFIRMED BUGS (must fix)

**BUG-A — CPU-lite-fallback gives the wrong model.** In `cfg_to_kwargs` (`daemon.py:178-184`) the lite
branch unconditionally sets `final_model = realtime_model = cfg.asr.lite_model` ("small.en"). But on
the `force_cpu` path the caller passes `resolved = dict(cuda_check.CPU_FALLBACK)`. Delta §3.2 mandates:
`mode=="lite"` + `force_cpu` → `model = realtime_model_type = "tiny.en"` (the CPU lite substitute,
mirroring how normal CPU-fallback maps `small.en`→`tiny.en`). **Current code yields `small.en`, not
`tiny.en`.** `cuda_check.CPU_FALLBACK` (cuda_check.py:53-58) = `{device:cpu, compute_type:int8,
final_model:small.en, realtime_model:tiny.en}`. Fix: in the lite branch, when `resolved["device"] ==
"cpu"` use `"tiny.en"` for both model fields instead of `cfg.asr.lite_model`.

**BUG-B — toggle semantics deviate from delta §3.4.** Current `toggle_lite()` (daemon.py:1351) and
`toggle()` (daemon.py:1314) both gate on `self._listening.is_set()`: an armed press of EITHER key
disarms. Delta §3.4 "pin these down" specifies **mode-specific** behavior:
- `toggle_lite()`: disarm iff currently armed-**in-lite**; otherwise arm in lite (so pressing F while
  armed-in-normal SWITCHES to lite — one reload).
- `toggle()`: disarm iff currently armed-**in-normal**; otherwise arm in normal (pressing D while
  armed-in-lite switches to normal).

The current `_listening.is_set()` condition must become `self._listening.is_set() and self._mode ==
<"lite"|"normal">`. The `hypr-binds.conf` header comment ("Both keys STOP when pressed while already
listening") and the `toggle_lite` docstring describe the CURRENT (deviating) behavior and must be
reconciled. **Decision:** follow delta §3.4 (it explicitly pins it down) unless the implementing agent
surfaces a concrete UX problem; if retained, the deviation must be documented and the spec note updated.

### 3.3 MISSING pieces (must add)

| Gap | Where | What |
|---|---|---|
| status.sh ⚡ lite prefix | `voice_typing/status.sh` (NOT modified) | jq render has no `.mode` handling. Add: when `.mode=="lite"` prefix the listening line with `⚡` instead of `🎤`. Use `.mode // "normal"` default so an older state.json (rolling restart) doesn't break. |
| Lite unit tests | `tests/test_config.py`, `test_recorder_host.py`, `test_daemon.py`, `test_control_socket.py`, `test_voicectl.py`, `test_feedback.py`, `test_status_sh.py` | delta §5 lists them. See §5 below. |
| T7 integration test | `tests/test_feed_audio.py` (lite variant) + `tests/test_idle_and_gpu.sh` | one-model resident + accuracy≥70% + lower latency + socket mode-switch. |
| README | `README.md` | config-table `lite_model`, Lite-mode subsection, Hotkey section (F bind), lifecycle note (~half VRAM). Mode B. |
| ACCEPTANCE.md | `tests/ACCEPTANCE.md` | T7 cross-check. |

### 3.4 BROKEN existing tests (66 failures) — root causes

The 90%-complete feature code changed signatures/shape that 66 existing tests pin. These are
mechanical reconciliation failures, not logic regressions. Each implementing subtask fixes the tests it
breaks (TDD §3 — tests ride with the work):

- **`tests/test_config_repo_default.py::test_repo_config_toml_has_no_extra_keys`** — the test's
  expected `[asr]` key set does not include `lite_model`. Add it.
- **`tests/test_feedback.py::test_state_shape_has_exactly_the_five_fields`** + **`test_snapshot_returns_a_copy_with_the_five_state_keys`** — assert the OLD 5-field state shape; `mode` is now a 6th field. Update to expect `mode` (and rename the "five" assertions).
- **`tests/test_daemon.py` (≈23 failures)** — `_load_host()` is now `_load_host(mode="normal")` and
  the spawn call passes `mode=mode` to the factory. Test fakes injected via `_host_factory` or the
  `recorder=`/`recorder_host=` seam don't accept `mode=`, and assertions on load/cold-arm/idle-unload
  hit the new mode-switch branch. The fakes (e.g. a `_FakeHost` / `_host_factory` callable) must accept
  and store `mode`, and `mode` defaults make the normal-mode path unchanged once fakes are reconciled.

**MOVING TARGET NOTE (important):** As of the breakdown pass, a concurrent process was actively
editing the working tree (the test-failure count dropped 66→3 in minutes as test fakes were
reconciled). The status above reflects the state at analysis time. **Two spec bugs (BUG-A CPU-lite,
BUG-B toggle semantics) were confirmed UNFIXED** at the final snapshot; status.sh ⚡ was DONE; T7 +
README were NOT present. Every implementing subtask MUST re-verify the current tree before editing
(the concurrent process may have landed more). Run
`.venv/bin/python -m pytest tests/ -q --ignore=tests/test_feed_audio.py` to see the live list.

---

## 4. Key facts / invariants downstream agents must NOT violate

1. **Daemon stays CUDA-free.** Never import torch/ctranslate2/RealtimeSTT in `daemon.py` at module top
   (it's lazy-imported inside `build_recorder`, which runs in the CHILD only). The daemon only ever
   holds a `RecorderHost` handle.
2. **Single-flight load/unload under `self._lock`.** `_load_host`/`_unload_host` acquire-release-
   reacquire `_lock`; never call them while holding `_lock` (deadlock). Mode-switch teardown reuses
   `_bounded_shutdown(timeout=5.0)` (the idle-unload path) — do NOT write a second teardown.
3. **`use_main_model_for_realtime=True` ⇒ exactly ONE model** (verified, see
   `realtimestt_lite_mode_verification.md`). This is what makes lite mode load only `small.en`. T7(a)
   re-asserts it.
4. **`on_final` gate + listen Event** are the source of truth for "is output armed"; `abort()` is a
   best-effort nudge only. The graceful drain (`_request_stop`) applies identically in lite mode.
5. **Shell aliases:** always use full paths in Bash calls — `/home/dustin/.local/bin/uv`,
   `.venv/bin/python`, `/usr/bin/tmux`. `python3`/`pip`/`tmux` are aliased in the interactive shell.
6. **Naming note:** the construction layer uses `lite: bool` (not the delta's `mode: str`). The
   DAEMON orchestration layer uses `mode: str` (needed for `self._mode` tracking + mode-switch). This
   split is acceptable and functional; do not churn the `lite: bool` API in the construction layer
   unless a test requires it — the `mode=="lite"` ↔ `lite=True` translation lives in `_worker_main`.

---

## 5. Lite-mode test matrix (delta §5) — what must exist when done

Unit (fast, CUDA-free):
- config: `lite_model` default "small.en", parsed from TOML, rejected if non-string.
- `cfg_to_kwargs(lite=True)`: `model == realtime_model_type == lite_model`, `use_main_model_for_realtime
  == True`, all other kwargs == normal mode. `mode="normal"` unchanged. **`lite=True, force_cpu` →
  `tiny.en`** (this also pins BUG-A's fix).
- recorder-host: `RecorderHost(..., mode="lite")` stores + passes `mode` into spawn `args`;
  `_child_resolved_device(cfg, False, lite=True)` reports `final_model==realtime_model==lite_model`
  (monkeypatched cuda_check).
- daemon: `self._mode` boot "normal"; `start_lite`/`toggle_lite` set mode "lite" + arm; arming lite
  while resident-in-normal triggers teardown-then-respawn (exactly one reload + new mode); arming lite
  while resident-in-lite is instant (no spawn); `status_snapshot()["mode"]` reflects `self._mode`;
  idle-unload then arm-lite reloads in lite.
- **toggle semantics (BUG-B):** `toggle_lite` while armed-in-normal → switches to lite (not stop);
  `toggle` while armed-in-lite → switches to normal (not stop). Each disarm only in its own mode.
- control socket: `toggle-lite`/`start-lite` dispatch → `toggle_lite`/`start_lite`; response carries
  `mode`.
- ctl: `toggle-lite`/`start-lite` accepted (not exit 64); `format_result` renders `mode:`.
- status.sh: `mode=="lite"` → `⚡`; `mode=="normal"` or absent → `🎤`; `.mode // "normal"` default.

Integration (T7): lite `feed_audio(utt_simple.wav)` → one model resident (no large model), finals over
the normal clean→type path, accuracy ≥70%, latency materially < normal; socket: `toggle-lite` arms
`mode:"lite"`, again disarms, then `toggle` reloads `mode:"normal"` (one reload), `status` reports mode.
