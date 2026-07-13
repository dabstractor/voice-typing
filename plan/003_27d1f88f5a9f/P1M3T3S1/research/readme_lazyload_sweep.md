# Research — P1.M3.T3.S1: README sweep for lazy-load + idle-unload + bounded teardown

Docs-only (Mode B) task. Input: README.md (stale, describes boot-time residency) → OUTPUT: README.md
accurately describing the lazy-load lifecycle. Source of truth for the NEW behavior: the LANDED code
(M2.T1 lazy-load + M3.T1.S1 idle-unload + M1.T1 bounded teardown, all Complete) + PRD §4.2bis/§4.5/§4.9.

---

## §0. The lazy-load lifecycle (VERBATIM from LANDED code — what the README must now describe)

| State | daemon.py site | What it means (user-facing) |
|---|---|---|
| `unloaded` | `__init__` 455-469; `feedback.set_phase` 468 | BOOT state. No recorder, no CUDA context, **~0 VRAM**. |
| `loading` | `_load_recorder` 512 | First arm in progress; building recorder + loading `small.en`+`distil-large-v3` (~1-3s). |
| `idle` | 549 (after load) | Loaded, mic disarmed. Instant re-arm from here. |
| `listening` | 199/205 (VAD callbacks) | Armed, transcribing. |
| (idle-unload) | `_unload_recorder` 818-852 → back to `unloaded` | After 30 min disarmed, tears down → ~0 VRAM. Next arm reloads. |

Key code facts (from scout recon):
- Boot: `self._recorder=None`, `self._models_loaded=False`, `phase="unloaded"` (daemon.py:455-469). ~0 VRAM.
- `_load_recorder()` (daemon.py:486-569) is **single-flight** under `_load_cond`; a second arm while
  `loading` waits, never starts a 2nd load. The heavy `build_recorder()` runs OUTSIDE `_lock` so
  `status`/`stop` stay responsive during the ~1-3s load.
- On total load failure (CUDA + CPU fallback both fail): returns to `unloaded`, arm replies
  `{"ok":false,"error":...}`, NO half-built recorder (daemon.py:553-560).
- Success log (VERBATIM, daemon.py:566): `voice-typing models loaded (lazy load complete); recorder resident`.
- Idle-unload log (VERBATIM, daemon.py:844-846): `voice-typing idle-unload: %.1fs disarmed; unloading models`
  (renders e.g. `voice-typing idle-unload: 1800.0s disarmed; unloading models`).
- Bounded teardown `_bounded_shutdown` (daemon.py:1030-1079): **HARD timeout = 10.0s**. On timeout,
  force-terminates `transcript_process` + `reader_process` (the CUDA/VRAM holders) so VRAM is released.
  This is the fix for the OLD ~90s quit hang (RealtimeSTT unbounded `Thread.join()`).
- `shutdown()`/`quit` (daemon.py:1088-1123, 1329-1338) delegates to `_bounded_shutdown` → **bounded ≤10s**,
  idempotent. `voicectl quit` → daemon replies `{"ok":true,"shutting_down":true}`.

## §1. The `voicectl status` surface (VERBATIM from ctl.py:85-93) — README example is STALE

Actual current output (ctl.py:85-93):
```
listening: <on|off>
phase: <unloaded|loading|idle|listening|speaking>
partial: <...>
last: <...>
uptime: <N>s
device: <cuda|cpu> (<float16|int8>)
models: <final_model> + <realtime_model> (<loaded|not loaded>)
<mic_line>
```
- `phase:` line = ctl.py:87 (NEW vs README's stale example — README omits it).
- `models:` line marker = ctl.py:84 `loaded_marker = "loaded" if models_loaded else "not loaded"` →
  renders `... (loaded)` / `... (not loaded)` (README's stale example omits the marker).
- Conditional `load error: <msg>` line appended when `load_error` truthy (ctl.py:96).
- `mic: ok` | `mic: unavailable (<reason>)` | `mic: unavailable` (ctl.py:79-83).

### The "loading models…" hint (ctl.py:121-137, CLIENT-SIDE, STDERR)
- Printed ONLY for `start`/`toggle` via `_send_command_with_loading_hint` (ctl.py:121, routed 188-189).
- `_LOADING_HINT_DELAY = 0.3` (ctl.py:42): the hint fires ONLY if the daemon hasn't replied within 0.3s
  → triggers ONLY on a real first-arm load; resident arms reply in ms → no flicker.
- **EXACT user-facing text (ctl.py:133):** `loading models… (first arm, ~1–3 s)` — to **stderr**.
  (The README must mention this exact hint in the First-run note.)

## §2. The config knob (config.py:74-89 — LANDED; config.toml:37 already documents it)

```python
auto_stop_idle_seconds:   float = 30.0    # config.py:76  (README table row exists, line 132)
auto_unload_idle_seconds: float = 1800.0  # config.py:78  (README table row MISSING — add it)
```
- `auto_unload_idle_seconds` default `1800.0` (30 min); `0` disables (models stay resident until `quit`).
- config.toml:37 ALREADY documents it (M3.T1.S1, Mode A — do NOT re-edit). README table row is the gap.
- README.md:132 has the `auto_stop_idle_seconds` row; the new `auto_unload_idle_seconds` row goes right
  after it, mirroring its style (3-col table: Section.key | Default | Effect).

## §3. Stale-phrasing sweep RESULTS — README.md (the file being rewritten)

`grep -niE` across README.md for residency/boot/VRAM/nvidia-smi/loading models/timeout/hot-mic:

| Line | Text | Verdict |
|---|---|---|
| 46-47 | "running and NOT listening. It never hot-mics on boot." | ACCURATE but incomplete — should add "and not loaded (~0 VRAM until first arm)" per PRD §4.9. SMALL EDIT. |
| 132 | `\| asr.auto_stop_idle_seconds \| 30.0 \| ...` | KEEP + ADD `auto_unload_idle_seconds` row after it. |
| 266-277 | "Typical CUDA output:" status example block | **STALE** — missing `phase:` line + `(loaded)` marker (ctl.py:85-93 has both). UPDATE. |
| 283 | "Confirm the models are resident in GPU VRAM:" | **STALE** — implies always-resident (boot-time). REWRITE to lazy-load lifecycle (the headline edit (b)). |
| 286 | `nvidia-smi --query-compute-apps=pid,used_memory --format=csv` | KEEP the command but reframe it under the lazy-load narrative (check VRAM per state). |

README.md has **ZERO** mentions of: `phase`, `models_loaded`, `loading models`, `(loaded)`, `idle-unload`,
`auto_unload`, `lazy`, `unloaded`. All must be ADDED. No "2.8 GB"/"1.5-3 GB"/"build recorder once"/
"construct once"/"recorder resident at boot" strings appear in README.md (those were already scrubbed or
never present). The headline stale claim is the "Confirm the models are resident" framing (implies
boot-time residency).

## §4. Stale-phrasing sweep RESULTS — voice_typing/*.py (Mode A cross-check)

`grep -rniE` for `resident|2.8 GB|1.5-3 GB|build recorder once|construct once|recorder resident at boot|load at boot|boot-time`:

ALL hits are CORRECT lazy-load phrasing (describing post-first-arm residency), NOT stale boot-time claims:
- daemon.py:6 "constructed ONCE so models stay resident" — means after first load; correct.
- daemon.py:16-19 module docstring: explicitly describes the lazy-load motivation ("stays at ~0 VRAM;
  after the first arm the recorder stays resident so re-arms are instant"). CORRECT.
- daemon.py:566 log `"voice-typing models loaded (lazy load complete); recorder resident"` — CORRECT.
- daemon.py:590-591 "construct once, models resident, instant toggle-on" — explains why not to rebuild
  on every arm; correct.
- ctl.py:40,74,129,192 — all describe resident-arm fast path; correct.
- feedback.py:86,127 — boot state phase 'unloaded' + models_loaded False; CORRECT.

**CONCLUSION: Mode A code-comment updates are COMPLETE. NO voice_typing/*.py edits are needed (and would
be out of scope — those were Mode A tasks). The implementer should re-run the §4 grep to confirm no
regression, but should NOT edit code.**

## §5. install.sh — GPU-residency blurb check

`grep -niE 'resident|VRAM|GB|boot|models' install.sh`:
- Line 174: `echo "daemon : running and NOT listening (no hot-mic on boot). Run 'voicectl toggle' to arm the mic."`
- Lines 8,14,19,97,98,100,132: all about prefetch/offline/model download — NOT residency claims.

**install.sh does NOT print a GPU-residency blurb** (no "resident"/"GB"/"VRAM" claims). The contract
trigger ("If install.sh prints a GPU-residency blurb, align it too") is therefore NOT MET. install.sh
edits are OPTIONAL. RECOMMENDED (coherence, not contract): enhance line 174's echo to note the daemon
is also "not loaded (~0 VRAM; first `voicectl start` loads models, ~1-3s)" to match PRD §4.9. This is a
one-line echo edit, clearly optional. If the implementer is unsure, leave install.sh untouched (the
contract does not require it).

## §6. Exact README.md section map (headers + line ranges) — for precise edits

```
1   # voice-typing
14  ## Requirements
23  ## Install                      ← line 46-47 "running and NOT listening" (edit: add not-loaded)
49  ## First run                    ← ADD "first arm loads models" note + loading models… hint (edit c)
73  ## Hotkey (Hyprland)
100 ## tmux status line
117 ## Configuration                ← table rows 119-133; ADD auto_unload_idle_seconds after line 132 (edit a)
146   ### Voice-activity constants are NOT config keys
159 ## CPU-only mode
186 ## Troubleshooting              ← optional bounded-quit note (edit d) — or place in "Logs,status,stopping"
243 ## Logs, status, stopping       ← status example 266-277 (UPDATE); GPU section 283-286 (REWRITE, edit b);
                                     stop/quit 290-294 (ADD bounded-quit note, edit d)
```

## §7. PRD anchors (READ-ONLY contract — do NOT edit PRD.md)
- PRD §4.2bis (h2.3/h3.2): lazy-load lifecycle states + idle-unload + bounded-teardown hard requirement.
- PRD §4.5 (h2.3/h3.5): config.toml with `auto_unload_idle_seconds = 1800.0` + idle-stop/idle-unload prose.
- PRD §4.9 (h2.3/h3.9): "daemon starts not-listening and not-loaded (~0 VRAM at idle); first arm loads models ~1-3s".
- PRD §7.6/§7.9 (h2.6): acceptance — "starts un-armed and un-loaded (~0 VRAM until first arm)";
  "after auto_unload_idle_seconds ... unloads (~0 VRAM, verified via nvidia-smi) and a later arm reloads;
  teardown is bounded (completes in seconds, no 90s hang)".

## §8. Validation approach (docs task — no compile/test gate)
- The gate is: (1) `grep` proves NO stale boot-time-residency claim remains in README.md; (2) the new
  lifecycle prose + config row + hints are present and accurate vs §0/§1/§2; (3) the status example
  matches ctl.py:85-93 verbatim (phase + loaded marker); (4) `git status --short` shows ONLY README.md
  (+ optional install.sh); (5) markdown renders (code fences balanced). No pytest/ruff/bash gate applies.
- `rg -n` after edits: zero hits for stale patterns in README.md; the OLD "Confirm the models are resident"
  framing is gone; `phase:`/`(loaded)`/`loading models`/`auto_unload_idle_seconds`/`idle-unload`/
  `unloaded`/`~0 VRAM` all PRESENT.

## §9. Coordination with the parallel item (P1.M3.T2.S2)
- P1.M3.T2.S2 (parallel) edits `tests/test_idle_and_gpu.sh` + `tests/ACCEPTANCE.md`. THIS task edits
  `README.md` (+ optional `install.sh`). **Files are DISJOINT — no merge conflict.**
- This task consumes the LANDED code read-only (daemon.py/ctl.py/config.py). It does NOT touch tests.
- P1.M2.T2.S1 (Ready, the phase/models_loaded status wiring) is NOT yet Complete, but ctl.py ALREADY
  renders `phase:` + `(loaded)` per the LANDED scout recon — so the status example update is safe to
  document from the current code regardless of M2.T2.S1's final status.
