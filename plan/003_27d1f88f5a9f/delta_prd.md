# Delta PRD 003: Lazy model loading + idle unload + bounded teardown

**Status:** Approved for implementation. Proportional to a single medium feature. The previous session (plan 002) was a spec-sync verification that shipped no code; this delta is a **real implementation task** — the lazy-load feature described in the updated PRD §4.2bis is NOT yet built.

**Diff size (Previous PRD → Current PRD):** 43 insertions / 14 deletions in `PRD.md`, concentrated in §1 (GPU decision), §4.2 (recorder loop), a brand-new **§4.2bis** (model lifecycle), §4.4–§4.9 (config / feedback / voicectl / systemd), §6 T6 (rewritten), §7 (new criterion #9), §8 (3 new risk rows). It is one cohesive feature with an explicit internal prerequisite.

---

## 1. What changed (diff analysis)

The entire delta is a single feature: **models load lazily on first arm, stay resident, and unload after disarmed idle — with the shutdown hang fixed first.** Concretely, the PRD now requires:

| # | Change | Where (PRD) |
|---|---|---|
| D1 | Models load **lazily on first arm**, NOT at daemon boot. Boot with no arm = ~0 VRAM. | §1 GPU decision, §4.2(1), §4.2bis |
| D2 | New lifecycle state machine: `unloaded` (boot) → `loading` (first arm, ~1–3 s) → `loaded`/not-listening → `loaded`/listening. Single-flight load under a lock; load failure returns to `unloaded` with `ok:false`, no half-built recorder. | §4.2bis |
| D3 | `voicectl status` + state file expose `phase` (`unloaded`/`loading`/`idle`/`listening`/`speaking`) and `models_loaded: bool`. | §4.6, §4.8 |
| D4 | **Idle unload:** after `asr.auto_unload_idle_seconds` (default `1800.0` = 30 min) disarmed, tear the recorder down → `unloaded`, freeing ~1.5–3 GB VRAM. Next arm reloads. `0` disables. | §4.2bis (Idle unload), §4.5 |
| D5 | **Bounded teardown is a HARD PREREQUISITE for idle-unload.** `recorder.shutdown()` MUST be non-blocking (seconds, not the current ~90 s hang) — else idle-unload would wedge every 30 min and block racing re-arms. Hard timeout + force-cleanup of worker threads / `transcript_process`. | §4.2bis, §8 (new risk row) |
| D6 | `quit`/daemon-shutdown now tears down the (possibly lazily-built) recorder, also bounded. systemd unit starts **not-loaded**. | §4.9 |
| D7 | T6 rewritten as **GPU lifecycle (lazy load)** with 4 sub-assertions; new acceptance criterion #9 (unload works + bounded teardown). | §6 T6, §7 |

**Nothing was removed.** Two PRD sentences were reworded to reflect lazy load (the `install.sh` prefetch note, and the listening-gate "constructed once on first arm"). Idle auto-stop (`auto_stop_idle_seconds`, shipped in plan 002) is clarified to "disarm but not unload — hands off to the idle-unload clock."

---

## 2. Implementation status (verified this session — what exists vs. what's needed)

The codebase was inspected; **the lazy-load feature is entirely absent.** The shipped system builds the recorder at boot:

- **`voice_typing/daemon.py:447`** — `self._recorder = (... else build_recorder(cfg, feedback, ...))` inside `VoiceTypingDaemon.__init__`. Comment says *"construct-once … build recorder ONCE so models stay resident."* This is the **old behavior**; must become lazy. → **D1, D2**
- **`voice_typing/daemon.py:817–840` `shutdown()`** — calls `self._recorder.shutdown()` with **no timeout and no force-cleanup** of worker threads / `transcript_process`. Idempotent + defensive (won't double-call, won't re-raise) but **NOT bounded**. → **D5**
- **`systemd/voice-typing.service`** — has **no `TimeoutStopSec`**, so systemd's default 90 s applies → `SIGKILL` / `Failed with result 'timeout'`. This is exactly the hang the PRD calls out. → **D5, D6**
- **`voice_typing/config.py`** — has `auto_stop_idle_seconds` (line 58) but **no `auto_unload_idle_seconds`**. → **D4**
- **`config.toml:36`** — has `auto_stop_idle_seconds` but **no `auto_unload_idle_seconds`**. → **D4**
- **`voice_typing/feedback.py:85–88`** — state fields are `listening, phase, partial, last_final, ts`; `phase` cycles `idle`/`listening`/`speaking`. **No `models_loaded`; no `unloaded`/`loading` phases.** → **D2, D3**
- **`voice_typing/daemon.py:768 status_snapshot()`** — returns `listening, partial, last_final, uptime_s, device, compute_type, final_model, realtime_model, mic_ok, mic_error`. **No `phase` lifecycle, no `models_loaded`.** → **D3**
- **`voice_typing/ctl.py`** — status prints `listening / partial / … / models loaded` (static config), **no live `phase` / `models_loaded` / `loading models…` hint.** → **D3**
- **`tests/test_idle_and_gpu.sh`** — current T4/T6 asserts residency ("Confirm the models are resident in GPU VRAM"). Must become the **GPU-lifecycle** test. → **D7**

Existing patterns to reuse (do NOT re-invent):
- The `_idle_watchdog` thread (`daemon.py:653–656`, ticks via `self._shutdown.wait(1.0)`, re-checks deadline under `_lock`) is the **template** for the idle-unload watchdog — same shape, different deadline + a teardown action instead of a disarm.
- `_maybe_auto_stop()` (`daemon.py:581`) is the template for "check a deadline under the lock, perform a guarded transition."
- The `_lock` already serializes start/stop/toggle; the single-flight load/unload MUST use it (or a dedicated lock held by the same code paths) so an arm racing a teardown waits correctly.
- `request_shutdown()` (`daemon.py:743–752`) already calls `self._recorder.abort()` **outside** `_lock` (fixed Jul 11) to break a blocked `text()` — the bounded-teardown fix must preserve this non-lock-holding discipline.
- CPU-fallback path (`main()` around `daemon.py:1301`) builds a CPU recorder on construction failure; with lazy load this becomes "load fails → stay `unloaded`, report error + CPU-fallback hint" rather than building CPU eagerly.

---

## 3. Scope delta (the work)

This is a **medium feature** with one explicit prerequisite chain, so it is **1 phase / 3 milestones**. Each milestone is independently testable.

### Milestone M1 — Bounded teardown (PREREQUISITE, unblocks M3; also fixes the existing `quit` hang)
The `recorder.shutdown()` call must complete in seconds, not ~90 s. Root-cause the wedge (the journal shows `run() loop exiting` → 90 s → systemd `SIGKILL`; likely the `transcript_process` join or the mic stream close inside RealtimeSTT's `shutdown()`), then bound it.

- **M1.T1 — Make `VoiceTypingDaemon.shutdown()` bounded.** Wrap `self._recorder.shutdown()` in a hard timeout. If it exceeds the budget, force-clean the recorder's spawn-started worker threads (`transcript_process`, reader process) so the GPU/mic are actually released and the call returns. Keep it idempotent + best-effort (don't re-raise). Reference: `daemon.py:817–840`. Verify via real `voicectl quit` timing + `nvidia-smi` (VRAM released) + journald (no `SIGKILL`/timeout).
  - *Mode A docs (ride with this task):* update the `shutdown()` docstring + the module-top comment that currently tags this "P1.M4.T2.S2" / "LATER" (`daemon.py:11, 409`) — bounded teardown is now implemented, not deferred.
  - **M1.T1.S1** — Root-cause the ~90 s wedge: identify which RealtimeSTT step blocks (`transcript_process.join()`, reader-process teardown, mic stream close). Record findings.
  - **M1.T1.S2** — Implement bounded teardown: hard timeout + force-cleanup of the worker `transcript_process`/reader so VRAM is released and the call returns within budget. Keep idempotent + non-lock-holding.

- **M1.T2 — Bound systemd stop.** Add `TimeoutStopSec=` (short, e.g. 15 s) + an explicit `ExecStop=` (or rely on the socket `quit`) to `systemd/voice-typing.service` so systemd never waits the full default 90 s; document that the daemon's own bounded teardown makes this safe. (`systemd/voice-typing.service` currently has neither.)

### Milestone M2 — Lazy-load lifecycle (D1, D2, D3)
Defer recorder construction to the first arm; add the state machine; surface it in feedback + status.

- **M2.T1 — Defer construction to first arm, single-flight.** Remove the boot-time `build_recorder()` from `VoiceTypingDaemon.__init__` (`daemon.py:447`); start with `self._recorder = None`. The `start`/`toggle` control-socket handlers acquire a **single-flight** load (a second arm while `loading` waits on the in-flight one, never starts a second load). The main loop idles (`sleep 0.05; continue`) while `_recorder is None` (matches §4.2(1) pseudocode). On load failure: revert to `unloaded`, return `{"ok":false,"error":...}`, leave **no half-built recorder**; `status` reports the error + the CPU-fallback hint (§4.4). The arm command blocks during load and `voicectl` prints a `loading models…` hint.
  - *Mode A docs (ride with this task):* refresh the module-top + `__init__` comments (`daemon.py:52, 446`) that currently say "build_recorder() once in __init__" → "built lazily on first arm (§4.2bis)".
  - **M2.T1.S1** — Extract a `_load_recorder()` single-flight method (lock-guarded) returning success/failure; wire `start`/`toggle` to await it before arming. No double-load; no half-built recorder on failure.
  - **M2.T1.S2** — Thread the `loading models…` hint through `ctl.py` (status/`loading` phase) and ensure `voicectl` prints it while the first arm blocks.

- **M2.T2 — Lifecycle state machine + feedback wiring.** Add `unloaded`/`loading`/`loaded` lifecycle (distinct from the existing listening/speaking `phase`). Add `models_loaded: bool` to the feedback state (`feedback.py:85–88`) and emit a state-file write on every lifecycle transition (§4.6). `phase` reads as `unloaded`/`loading` when not loaded; cycles `idle`/`listening`/`speaking` once loaded.
  - *Mode A docs (ride with this task):* update the `feedback.py:10` module-top state-shape comment + the `idle` default (`feedback.py:86`) to the boot state `unloaded`, `models_loaded: false`.
  - **M2.T2.S1** — Expose `phase` + `models_loaded` from `status_snapshot()` (`daemon.py:768`) and render them in `ctl.py` status (replace/augment the static "models loaded" line with the live `phase`/`models_loaded`/error).

### Milestone M3 — Idle unload + config + T6 test + docs (D4, D7)
The slower watchdog that frees VRAM after a one-off use. Depends on M1 (bounded teardown) and M2 (lifecycle exists to tear down).

- **M3.T1 — Idle-unload watchdog + config knob.** Add `asr.auto_unload_idle_seconds: float = 1800.0` to `AsrConfig` (`config.py`) and `config.toml` (`0` disables). Add an `_idle_unload_watchdog` thread modeled on the existing `_idle_watchdog`: the clock starts when the mic disarms (manual stop, toggle-off, or the §4.5 auto-stop) and resets on any arm; time spent listening does not count. When the deadline fires it tears the recorder down **under the same single-flight lock as load** (so a racing arm waits for teardown then loads fresh), logs `voice-typing idle-unload: 1800.0s disarmed; unloading models`, transitions to `unloaded`, and frees VRAM via the M1 bounded teardown.
  - *Mode A docs (ride with this task):* the `auto_unload_idle_seconds` line in `config.toml` (self-documenting comment, mirroring the existing `auto_stop_idle_seconds` comment at `config.toml:36`); `config.py` docstring.
  - **M3.T1.S1** — Add the config knob (`config.py` + `config.toml`); add the watchdog thread; verify it composes with auto-stop (30 s disarm → 30 min unload) and that `0` disables.
  - **M3.T1.S2** — Verify teardown-vs-load race safety: an arm that arrives while idle-unload is tearing down waits, then loads fresh (never sees a half-torn-down recorder).

- **M3.T2 — Rewrite T6 as GPU-lifecycle (lazy load) + regression.** Convert `tests/test_idle_and_gpu.sh` (currently asserts residency) to the 4-part lifecycle assertion: (a) idle/never-armed → daemon PID **absent** from `nvidia-smi`; (b) armed → PID + ~1–5 GB; (c) disarmed (not quit) → **still resident**; (d) disarmed + idle ≥ `auto_unload_idle_seconds` → PID **gone**, reload reappears. Add fast unit tests for the new state machine + single-flight (inject a fake recorder, no CUDA). Run the full fast pytest suite as regression. (Acceptance #1, #6, #9.)
  - **M3.T2.S1** — Fast pytest: lifecycle transitions (`unloaded`→`loading`→`loaded`), single-flight (concurrent arms → one load), load-failure → `unloaded`/`ok:false`/no half-built recorder, idle-unload fires + resets on arm, `0` disables. Add to the existing `test_daemon.py` suite using its fake-recorder injection pattern.
  - **M3.T2.S2** — Rewrite `tests/test_idle_and_gpu.sh` T6 section to the 4 lifecycle assertions; confirm the existing T4 idle-stability checks still hold under lazy load; run full regression (fast suite + heavy shell tests on GPU cold init).

### Mode B — Sync changeset-level documentation (depends on M1–M3)
The lazy-load behavior is cross-cutting and the README currently contradicts it (`README.md:283` "Confirm the models are resident in GPU VRAM" assumes boot-time residency).

- **M3.T3 — README sweep.** (a) Add `asr.auto_unload_idle_seconds` to the config-tuning table (`README.md:132` neighborhood), mirroring the `auto_stop_idle_seconds` row. (b) Rewrite the "Confirm the models are resident" GPU section (`README.md:283`) to the lazy-load lifecycle: ~0 VRAM at boot, ~1–3 s on first arm, resident until `quit` or 30-min disarmed idle, reload on next arm. (c) Add a short "First arm loads models (~1–3 s, one-time per session)" note to the First-run section + the `loading models…` `voicectl` hint. (d) Note the bounded `quit` teardown (no more ~90 s systemd timeout). If `install.sh` prints a GPU-residency blurb, align it too.
  - **M3.T3.S1** — Apply the four README edits; grep the repo for stale "resident"/"2.8 GB"/"build recorder once" phrasing and fix any remaining drift.

---

## 4. Testing & acceptance (delta)

- **Fast (pytest):** new unit tests in M3.T2.S1 — lifecycle state machine, single-flight load, load-failure handling, idle-unload fire/reset/disable. Must join the existing green fast suite.
- **T6 (heavy, GPU cold init):** rewritten per M3.T2.S2 — the 4 lazy-load sub-assertions, proven by real `nvidia-smi` output.
- **Bounded teardown:** demonstrated by real `voicectl quit` completing in seconds + journald showing **no** `SIGKILL`/`Failed with result 'timeout'` + `nvidia-smi` showing VRAM released.
- **Regression:** all previously-green fast tests stay green; the existing `_idle_watchdog`/auto-stop behavior is unchanged (auto-stop still disarms at 30 s; it just no longer claims to unload).

**Delta acceptance (definition of done for THIS delta):**
1. After daemon boot with no arm, the daemon PID is absent from `nvidia-smi` (§7 #6, updated).
2. First arm loads models (~1–3 s, `voicectl` shows `loading models…`), subsequent arms are instant; a load failure returns to `unloaded` cleanly with `ok:false` + the CPU-fallback hint.
3. `voicectl status` + `state.json` show live `phase` (`unloaded`/`loading`/`idle`/`listening`/`speaking`) and `models_loaded`.
4. After `auto_unload_idle_seconds` disarmed, the recorder unloads (~0 VRAM via `nvidia-smi`) and a later arm reloads it (§7 #9).
5. `voicectl quit` / daemon shutdown completes in seconds (bounded teardown) — no 90 s systemd timeout.
6. README + config reflect the new knob + lazy-load lifecycle; fast suite green; T6 passes.

---

## 5. Risks (delta)

| Risk | Mitigation |
|---|---|
| `recorder.shutdown()` hangs ~90 s (current, on every `quit`) | **M1 is the prerequisite.** Root-cause + hard timeout + force-cleanup of worker threads/`transcript_process`. No idle-unload until this is bounded (§8 risk row). |
| Idle-unload fires every 30 min and wedges a re-arm | Teardown runs under the SAME single-flight lock as load; a racing arm waits, then loads fresh (M3.T1.S2). |
| First arm is slow (~1–3 s) | Accepted trade-off of lazy load (§8); `voicectl` prints `loading models…`; only the first arm per load/unload cycle pays it. |
| Load fails on first arm (CUDA/cuDNN) | Revert to `unloaded`, arm returns `ok:false` + error + CPU-fallback hint, no half-built recorder (§8). |
| Half-built recorder left after failed load | Single-flight `_load_recorder()` sets `self._recorder` only on success; failure path nulls any partial (M2.T1.S1). |
| Existing boot-time tests assume a resident recorder | Audit `test_daemon.py` fakes in M3.T2.S1; the injection pattern already lets tests pass a pre-built fake recorder, so tests that need "loaded" construct one explicitly. |
| T4 idle-stability test interacts with idle-unload | Idle-unload default is 30 min; T4's 120 s window never triggers it. Verify in M3.T2.S2 (mirrors the plan 002 auto-stop interaction check). |

---

## 6. Out of scope

- Waybar/eww overlay UI, voice commands, per-app profiles, a different STT engine — unchanged from PRD §9.
- Tightening the ~1–3 s first-arm load (e.g. lighter realtime model) — accepted as-is.
- The Moonshine/Voxtral true-streaming swap — still Future Work; the engine-isolation goal is unchanged (lazy load makes the single recorder a cleaner seam, but no API redesign).
