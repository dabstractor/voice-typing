# Research — P1.M3.T2.S2: rewrite tests/test_idle_and_gpu.sh T6 to 4-part lazy-load lifecycle + confirm T4

Ground truth verified by reading `tests/test_idle_and_gpu.sh`, `voice_typing/daemon.py`,
`voice_typing/config.py`, `voice_typing/ctl.py`, `voice_typing/launch_daemon.sh`,
`tests/ACCEPTANCE.md`, the idle-unload impl research (`P1.M3.T1S1/research/idle_unload_watchdog.md`),
and the parallel item's PRP (`P1M3T2S1/PRP.md`) on 2026-07-13.

This is the SHELL-level GPU-lifecycle half of P1.M3.T2. S1 (parallel) owns the fast pytest
(`tests/test_daemon.py`); THIS task owns the REAL-stack bash test (`tests/test_idle_and_gpu.sh`) that
proves the lazy-load lifecycle via real `nvidia-smi` output on the real CUDA stack. P1.M2.T1 (lazy
load), P1.M3.T1.S1 (idle-unload impl), P1.M1 (bounded teardown) are ALL COMPLETE prerequisites.

---

## 0. The lifecycle contract under test (daemon.py, LANDED — read, do NOT edit)

The daemon's model lifecycle (PRD §4.2bis) maps to 4 observable `nvidia-smi` states:

| lifecycle state | when | daemon internals | nvidia-smi compute-apps (daemon tree) |
|---|---|---|---|
| **unloaded (boot)** | after `run()` ready, BEFORE first arm | `_recorder=None`, `_models_loaded=False`, phase=`unloaded`, NO CUDA context | **ABSENT** (~0 VRAM) |
| **loaded/listening** | after `voicectl start` (first arm) | `_load_recorder()` built the recorder (small.en + distil-large-v3 onto GPU, ~1-3s, ~1.5-3GB); `_arm()` set `_disarmed_monotonic=None`; phase=`idle`→`listening` | **PRESENT**, Σ used_memory ∈ [1024, 5120] MiB |
| **loaded/not-listening** | after `voicectl stop` (disarm) | `_disarm()` stamped `_disarmed_monotonic=now`; recorder STAYS resident (stop does NOT unload); phase=`idle` | **STILL PRESENT** (models resident for instant re-arm) |
| **unloaded (idle-unload)** | after `auto_unload_idle_seconds` DISARMED | `_idle_unload_watchdog` (1s tick) → `_maybe_idle_unload()` → `_unload_recorder()` → `_bounded_shutdown()` tears down recorder, nulls `_recorder`, `_models_loaded=False`, phase=`unloaded` | **ABSENT again** (~0 VRAM reclaimed) |
| **loaded (reload)** | a later `voicectl start` after idle-unload | `_load_recorder()` rebuilds (~1-3s, single-flight); phase `loading`→`idle`→`listening` | **PRESENT again** |

Key daemon methods (do NOT edit — LANDED):
- `__init__` (daemon.py:457-469): lazy boot → `_recorder=None`, `_models_loaded=False`, `set_phase("unloaded")`. ~0 VRAM.
- `start()` (912-916): `_load_recorder()` (single-flight; builds on first arm) THEN `_arm()` under `_lock`.
- `_arm()` (699-707): `_disarmed_monotonic=None` (unload clock inactive while armed).
- `stop()` (920-926): `_disarm()` under `_lock` (sets `_disarmed_monotonic=now`) + `abort()` outside `_lock`. NO unload.
- `_idle_unload_watchdog()` (781-791): daemon thread, `while not _shutdown.wait(1.0): _maybe_idle_unload()`. Started from `run()` (606).
- `_maybe_idle_unload()` (793-816): threshold=`cfg.asr.auto_unload_idle_seconds`; `threshold<=0` disables; lock-free pre-check (not loaded OR listening OR `_disarmed_monotonic is None` OR elapsed<threshold → return); else `_unload_recorder()`.
- `_unload_recorder()` (818-853): re-check under `_lock` (incl. `_listening` race guard) → `_bounded_shutdown()` → `_recorder=None`/`_models_loaded=False`/`set_phase("unloaded")`.
- `_bounded_shutdown(timeout=10.0)` (976-1020): runs `recorder.shutdown()` in a daemon thread under a HARD 10s timeout; ON TIMEOUT force-terminates `transcript_process` + `reader_process` (the spawn-started CUDA/VRAM holders) → releases VRAM. This is what makes "PID gone after unload" assertable (see §4 risk).
- config: `AsrConfig.auto_unload_idle_seconds: float = 1800.0` (config.py:60). `0` disables. config.toml:37 documents it.

**Why T4 is unaffected by default config:** T4 holds 120s of ARMED silence. The idle-unload clock only
runs while DISARMED (`_disarmed_monotonic` is `None` while armed), and the default threshold is 1800s.
So T4's 120s armed window NEVER arms the idle-unload clock. T4 runs on the DEFAULT config (1800s).

---

## 1. The existing test structure (tests/test_idle_and_gpu.sh — what STAYS / GOES / CHANGES)

The file (~575 lines) is a single-daemon-run bash test. Structure today:

- **Header comment** (lines 1-57): documents T4 + T6 (single residency) + G-* gotchas. **CHANGE**: rewrite the T6 description to the 4-part lifecycle; keep T4 + all G-* invariants (they still hold).
- **Tunables** (60-75): `IDLE_SECS=120`, `VRAM_MIN_MIB=1024`, `VRAM_MAX_MIB=5120`, `TMUX_SESS=vtidle`. **KEEP**.
- **cleanup() trap** (95-130): inline daemon-stop (quit→SIGTERM→8s poll→SIGKILL) + tmux kill + temp rm. **REFACTOR**: extract the daemon-stop into a reusable `stop_daemon_run()` function; trap calls it on `$DAEMON_PID`. Needed because the rewrite has TWO daemon runs.
- **capture_pane()** (140-147): tmux capture for T4's no-typing assertion. **KEEP**.
- **Preflight** (150-168): deps + refuse-if-running. **KEEP**.
- **Setup** (170-185): temp `$WORK/config/voice-typing/config.toml` with `[output]`+`[feedback]`; tmux session. **KEEP + ADD** a second config dir `$WORK/config_short/` for run 2 (adds `[asr] auto_unload_idle_seconds=5.0`).
- **Launch + wait ready** (187-205): inline `$LAUNCH &; DAEMON_PID=$!` + 180s ready poll. **REFACTOR** into `launch_daemon_run()` + `wait_daemon_ready()` functions (called twice).
- **criterion 8 grep** (208-216): no-network. **KEEP** (run 1).
- **criterion 6 un-armed boot** (218-225): `listening: off` before start. **KEEP** (run 1).
- **criterion 6 toggle** (227-230). **KEEP** (run 1).
- **Helpers cpu_tree_seconds / daemon_tree_pids** (232-285): /proc Python heredocs. **KEEP** (both runs reuse them).
- **T4 idle window** (287-330): start → CPU0/wall0 → 120s → CPU1/wall1 → no-halluc/no-crash/CPU<25%. **KEEP** (run 1).
- **T6 GPU residency** (332-358): stop → nvidia-smi once → assert Σ in [1024,5120]. **REWRITE**: this is the section to replace with the 4-part lifecycle. The single post-stop nvidia-smi becomes T6(c); T6(a) is added before start; T6(b) is added after start (before the T4 window); T6(d) is a NEW run 2.
- **status/unit grep** (360-385). **KEEP** (run 1).
- **criterion 8 echo** (387-390). **KEEP**.
- **Evidence block** (392-411). **EXTEND** with all 4 T6 states' nvidia-smi output.
- **Result** (413-421): aggregate PASS/FAIL. **EXTEND** to include T6a/b/c/d verdicts.

The existing nvidia-smi Python heredoc (335-357) does: query `pid,used_memory` → match tree → `sys.exit(0 if matched and 1024<=total<=5120 else 1)`. This exits 1 when ABSENT — it CANNOT express "assert absent". **Must refactor** into a `vram_tree_state(pid)` that echoes `<total_MiB> <matched_pids_csv>` (total=0/empty = absent), plus `assert_vram_absent`/`assert_vram_present`/`wait_vram_absent`/`wait_vram_present` wrappers (see §3).

---

## 2. The 2-run design (the contract's prescribed structure)

The contract: "run T4 first (120s silence, default config), then T6 lifecycle assertions. For T6(d)
specifically, the config override to auto_unload_idle_seconds=5 is needed — start a second daemon run
or adjust the config dynamically. Consider running T6(d) as a separate daemon invocation."

**T6(a) MUST be measured BEFORE the first arm** (it is the lazy-load boot guarantee). Since T4's 120s
window is the ARMED period, T6(a) necessarily precedes T4's start. The clean ordering that honors all
4 sub-assertions AND keeps T4 green AND minimizes cold-init runs is **2 daemon runs**:

### RUN 1 — default config (`auto_unload_idle_seconds=1800`, so T4's 120s never fires unload)
1. boot + wait ready
2. **T6(a)** assert ABSENT (before any arm) ← NEW
3. criterion 8 grep, criterion 6 un-armed boot, criterion 6 toggle (KEEP)
4. `voicectl start`
5. **T6(b)** assert PRESENT in [1024,5120] ← MOVED (was post-stop; now post-start, where it belongs)
6. **T4** 120s armed silence → no-halluc / no-crash / CPU<25% (KEEP; the 1800s threshold never fires)
7. `voicectl stop`
8. **T6(c)** assert STILL PRESENT (models resident after disarm) ← NEW
9. criterion 6 status/unit grep (KEEP); collect run-1 evidence; `stop_daemon_run` (clean quit)

### RUN 2 — config override (`auto_unload_idle_seconds=5`)
10. boot + wait ready
11. assert ABSENT (boot corroboration)
12. `voicectl start` → assert PRESENT (armed)
13. `voicectl stop`
14. **T6(d-gone)** POLL nvidia-smi until daemon tree ABSENT (ceiling ~25s) → assert GONE ← NEW
15. `voicectl start` again
16. **T6(d-reload)** POLL nvidia-smi until daemon tree PRESENT again (ceiling ~15s) → assert reappears ← NEW
17. collect run-2 evidence; `stop_daemon_run` (trap also catches it)

Why 2 runs (not 3, not 1): T4 + T6(a/b/c) all need the DEFAULT config (T4's 120s armed window must not
trigger idle-unload; T6(c) must stay resident). T6(d) needs the 5s threshold. Putting T6(d) on run 1's
daemon would require reloading the config (impossible without restart) and would race T4. A 3rd run for
T6(a/b/c) is wasteful (each cold init is ~3-4 min). 2 runs is the minimum that satisfies every clause.

---

## 3. The nvidia-smi helper refactor (the reusable assertions)

Replace the single post-stop nvidia-smi block with a reusable state query + absent/present/poll wrappers.

```bash
# Echo "<total_MiB> <matched_pids_csv>" for the daemon tree. total=0 + empty matched => ABSENT (~0 VRAM).
# Comma-safe 2-col query (process_name omitted — it can contain commas; G-VRAM-COMMAS).
vram_tree_state() {  # $1 = root pid
  local tree; tree="$(daemon_tree_pids "$1")"
  "$NVIDIA_SMI" --query-compute-apps=pid,used_memory --format=csv,noheader 2>/dev/null > "$WORK/nvidia_smi.csv" || true
  "$PY" - "$WORK/nvidia_smi.csv" "$tree" <<'PY'
import sys
tree = set(int(x) for x in sys.argv[2].split())
matched = []; total = 0
with open(sys.argv[1]) as f:
    for line in f:
        parts = [p.strip() for p in line.split(',') if p.strip() != '']
        if len(parts) < 2: continue
        try: pid = int(parts[0])
        except ValueError: continue
        mib = parts[1].replace('MiB','').strip()
        try: m = int(mib)
        except ValueError: continue
        if pid in tree:
            matched.append(pid); total += m
print(f"{total} {','.join(map(str, sorted(set(matched))))}")
PY
}
assert_vram_absent()  { # $1=root pid $2=label  -> total==0
  local out; out="$(vram_tree_state "$1")"; local total="${out%% *}"
  if [ "$total" = "0" ]; then echo "[PASS] T6 $2: daemon tree ABSENT from nvidia-smi (~0 VRAM) [$out]"; return 0; fi
  echo "[FAIL] T6 $2: expected ABSENT, got total=${total} MiB [$out]"; T6_OK=1; return 1
}
assert_vram_present() { # $1=root pid $2=label  -> total in [VRAM_MIN,VRAM_MAX]
  local out; out="$(vram_tree_state "$1")"; local total="${out%% *}"
  if awk -v t="$total" -v lo="$VRAM_MIN_MIB" -v hi="$VRAM_MAX_MIB" 'BEGIN{ exit !(t+0>=lo+0 && t+0<=hi+0) }'; then
    echo "[PASS] T6 $2: daemon tree PRESENT, total=${total} MiB (${VRAM_MIN_MIB}-${VRAM_MAX_MIB}) [$out]"; return 0; fi
  echo "[FAIL] T6 $2: expected ${VRAM_MIN_MIB}-${VRAM_MAX_MIB} MiB, got ${total} MiB [$out]"; T6_OK=1; return 1
}
# Poll helpers: nvidia-smi is a LIVE driver query (no caching), but used_memory accounting + the unload
# fire/teardown timing have variance -> POLL, never fixed-sleep (see §4). Ceiling absorbs the variance.
wait_vram_absent()  { # $1=root pid $2=ceiling_secs(default 25)
  local deadline=$(( $(date +%s) + ${2:-25} ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    [ "$(vram_tree_state "$1" | awk '{print $1}')" = "0" ] && return 0; sleep 0.5; done; return 1
}
wait_vram_present() { # $1=root pid $2=ceiling_secs(default 15)
  local deadline=$(( $(date +%s) + ${2:-15} ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    local out; out="$(vram_tree_state "$1")"; local total="${out%% *}"
    awk -v t="$total" -v lo="$VRAM_MIN_MIB" -v hi="$VRAM_MAX_MIB" 'BEGIN{ exit !(t+0>=lo+0 && t+0<=hi+0) }' && return 0
    sleep 0.5; done; return 1
}
```

Run-control helpers (DRY the launch/wait/stop so both runs + the trap share them):
```bash
launch_daemon_run() { # $1=XDG_CONFIG_HOME $2=logfile  -> sets global DAEMON_PID
  XDG_CONFIG_HOME="$1" "$LAUNCH" > "$2" 2>&1 & DAEMON_PID=$!
}
wait_daemon_ready() { # $1=logfile  -> die if not ready in 180s or daemon died
  for _ in $(seq 1 360); do
    "$VOICECTL" status >/dev/null 2>&1 && return 0
    kill -0 "$DAEMON_PID" 2>/dev/null || die "daemon exited during startup; see $1"
    sleep 0.5
  done; die "daemon not ready in 180s; see $1"
}
stop_daemon_run() { # idempotent: quit -> SIGTERM -> 8s poll -> SIGKILL; clears global DAEMON_PID
  [ -n "${DAEMON_PID:-}" ] || return 0
  kill -0 "$DAEMON_PID" 2>/dev/null || { DAEMON_PID=""; return 0; }
  timeout 5 "$VOICECTL" quit >/dev/null 2>&1
  kill -TERM "$DAEMON_PID" 2>/dev/null
  for _ in $(seq 1 16); do kill -0 "$DAEMON_PID" 2>/dev/null || break; sleep 0.5; done
  if kill -0 "$DAEMON_PID" 2>/dev/null; then kill -KILL "$DAEMON_PID" 2>/dev/null; fi
  wait "$DAEMON_PID" 2>/dev/null; DAEMON_PID=""
}
```
The trap becomes: `stop_daemon_run; "$TMUX_BIN" kill-session ...; rm -rf "$WORK"`.

---

## 4. THE RISK — T6(d-gone): does idle-unload actually drop the PID from nvidia-smi?

This is the single highest-risk assertion. The PRD §7.9 contract is explicit: "After
`auto_unload_idle_seconds` of disarmed idle, the recorder unloads (~0 VRAM, verified via nvidia-smi)".
So the test MUST assert the daemon tree disappears from `--query-compute-apps` after idle-unload,
WHILE THE DAEMON PROCESS KEEPS RUNNING. Research (external brief) established the decisive factor:

- `nvidia-smi --query-compute-apps` is a **live, uncached** NVML driver query. A PID row is tied to an
  **active CUDA context** (not to bytes). The row appears when the context+allocation exist and
  **disappears when the context is destroyed** (explicit teardown OR process exit) — typically sub-second.
- `used_memory` can lag/underreport; **PID presence/absence is the hard signal**. Assert on the tree PID
  set, treat the [1024,5120] MiB range as secondary corroboration.
- **Decisive caveat:** whether the daemon PID vanishes without process exit depends on WHICH process
  holds the CUDA context. RealtimeSTT/ctranslate2 inference runs in spawn-started worker PROCESSES
  (`transcript_process`/`reader_process` — confirmed by daemon.py:1008-1018 `_bounded_shutdown`
  comment: "force-terminate the spawn-started transcript_process + reader_process (the CUDA-context/
  VRAM holders — terminating them releases VRAM immediately)"). Terminating those workers destroys
  their contexts → their PIDs vanish → the daemon tree is ABSENT from nvidia-smi → ~0 VRAM while the
  daemon lives. ✅ This is the design `_bounded_shutdown` (M1.T1) implements + relies on.
- **Counter-case (would FAIL):** if inference ran as THREADS inside the daemon (or the daemon itself
  created a CUDA context), the daemon PID would hold the context and PERSIST after teardown until
  reset/exit. The daemon code comment explicitly identifies the workers as spawn PROCESSES, so the
  design intends the ✅ case.

**Mitigations baked into the test (all in §3):**
1. **POLL, never fixed-sleep.** The contract's literal "wait 7s" is UNDER-BUDGETED: the unload fires at
   ~5-6s after stop (1s watchdog tick + 5s threshold; the stop may land just after a tick) PLUS teardown
   up to ≤10s PLUS sub-second driver accounting. A fixed 7s sleep flakes. `wait_vram_absent` polls every
   0.5s up to a 25s ceiling — absorbs tick alignment + teardown + driver lag. (This is a NECESSARY
   deviation from the literal "7s"; document it.)
2. **Assert on the daemon TREE PID set** (via `daemon_tree_pids`), not an arbitrary row — handles
   whichever process (daemon or worker) holds the context, and matches the existing passing T6 logic.
3. **Cross-check `voicectl status`** for `phase: unloaded` + `models: ... (not loaded)` after the unload
   (corroboration that the daemon's INTERNAL state transitioned even if nvidia-smi lags). ctl.py:84
   renders `loaded_marker = "loaded" if models_loaded else "not loaded"`; phase is on its own line
   (ctl.py:87). After reload, expect `phase: idle`/`listening` + `(loaded)`.
4. **On T6(d-gone) FAIL: fail loud with a diagnostic.** Capture: the steady-state active PID set
   (before stop), the post-unload compute-apps listing, the daemon.log tail (grep
   `voice-typing idle-unload:` to confirm the watchdog FIRED), and `voicectl status` phase. State
   explicitly: a FAIL here means the unload path did NOT release the CUDA context as seen by nvidia-smi
   — a PRODUCTION bug in M1.T1/M3.T1 (the test is correctly asserting PRD §7.9), NOT a test bug. Do NOT
   weaken the assertion to make it pass.
5. **Empirical precondition probe (optional, recommended for first run):** at the first armed steady
   state, log `vram_tree_state` once to capture WHICH PIDs hold the context (the "active set"). This
   self-calibrates the test and confirms the spawn-worker model on the target machine.

**Confidence per clause:** (a) boot-absent HIGH (lazy load Complete; nothing at boot touches CUDA — the
mic probe is PyAudio, not CUDA). (b) armed-present HIGH (the existing passing assertion, moved earlier).
(c) post-stop-still-present HIGH (stop does not unload by design). (d-gone) MEDIUM (depends on spawn-
worker context release — the design intends it, but it is the one assertion that reaches the real CUDA
teardown path; if it fails it surfaces a real bug). (d-reload) HIGH (`_load_recorder` rebuilds on arm).

---

## 5. config override mechanism (two XDG_CONFIG_HOME dirs)

The existing test creates ONE config dir `$WORK/config/voice-typing/config.toml` with `[output]`+
`[feedback]` only; `[asr]/[filter]/[log]` inherit dataclass defaults (== repo config.toml — verified
by the existing passing run). For run 2, create a SECOND dir `$WORK/config_short/voice-typing/
config.toml` that is IDENTICAL to run 1's PLUS:
```toml
[asr]
auto_unload_idle_seconds = 5.0
```
Adding ONLY this one `[asr]` key keeps every OTHER `[asr]` field at the SAME inherited defaults as
run 1 → run 1 and run 2 have IDENTICAL ASR pipelines except the idle-unload threshold (exactly the
desired isolation). Launch run 2 with `XDG_CONFIG_HOME="$WORK/config_short"`. Do NOT edit the repo
config.toml (G-CONFIG). The daemon reads `XDG_CONFIG_HOME/voice-typing/config.toml` (verified — the
existing test's override path).

**T4 must NOT use the 5s override** — T4's 120s ARMED window would, after a stop, leave the recorder
disarmed and the 5s clock would fire. T4 runs on run 1 (default 1800s). This is why run 2 is separate.

---

## 6. ctl.py status surface (for cross-check corroboration)

`voicectl status` pretty-prints (ctl.py:85-92):
```
listening: <on|off>
phase: <unloaded|loading|idle|listening|speaking>
partial: ...
last: ...
uptime: ...s
device: cuda (...) 
models: <final> + <realtime> (<loaded|not loaded>)
mic: ...
```
- After boot (T6(a)): `phase: unloaded`, `models: ... (not loaded)`, `listening: off`.
- After start (T6(b)): `phase: listening` (or `idle` mid-transition), `models: ... (loaded)`, `listening: on`.
- After stop (T6(c)): `phase: idle`, `models: ... (loaded)`, `listening: off`.
- After idle-unload (T6(d-gone)): `phase: unloaded`, `models: ... (not loaded)`, `listening: off`.
- After reload (T6(d-reload)): `phase: loading`→`listening`, `models: ... (loaded)`, `listening: on`.

These are SECONDARY corroboration only — the PRIMARY T6 assertions are nvidia-smi (the contract says
"proves all 4 lazy-load lifecycle sub-assertions via real nvidia-smi output"). Use status to diagnose a
flake (e.g. nvidia-smi lags but status shows `unloaded` → the unload fired, give nvidia-smi more time).

---

## 7. tests/ACCEPTANCE.md updates (DOCS, Mode A)

Two spots reference the OLD single-residency T6:
1. **Evidence example (line ~70):** `[PASS] criterion 6/T6 (GPU residency): matched=[(2499875, 2804)] total_MiB=2804 (range 1024-5120 MiB)` — replace with the 4-state lifecycle evidence (a/b/c/d) showing nvidia-smi for each.
2. **Explanatory paragraph (lines ~82-86):** "T6 GPU residency matches the daemon's descendant process tree against nvidia-smi ... only rows whose PID is in the daemon tree are summed." — rewrite to describe the 4-part lifecycle (boot-absent / armed-present / disarmed-still-present / idle-unloaded-gone / reloaded-present), keep the comma-safe + tree-filter + unrelated-apps notes (still true), and note the 2-run structure (default config for a/b/c + T4; 5s override for d).

Read ACCEPTANCE.md IN FULL before editing — find any other T6/residency references (grep `T6\|residen\|GPU` ) and update them consistently. The criterion-1 row (line ~28) still references `./tests/test_idle_and_gpu.sh` — keep it (still the T4+T6 vehicle).

---

## 8. Validation reality (this is a HEAVY real-stack bash test, NOT collected by pytest)

- The test runs the REAL daemon via launch_daemon.sh (production path), REAL CUDA Whisper + tmux, and
  takes ~5-8 min (2 cold inits ~3-4 min each + 120s T4 window + idle-unload waits). It is NOT collected
  by the fast pytest suite and is NOT run in CI/CPU contexts.
- **Validation = run the test, expect exit 0.** Preflight: `systemctl --user stop voice-typing` first
  (the test refuses if a daemon is running). Preconditions: CUDA GPU, models prefetched, QUIET room
  (T4 listens to ambient silence — ambient speech would spuriously fail the no-hallucination assertion).
- There is NO unit-test gate for this file (it is a bash integration test). `bash -n` (syntax check) is
  the cheap pre-run gate; `shellcheck` if available. The real gate is `./tests/test_idle_and_gpu.sh`
  exit 0 + the 4 T6 PASS lines in the evidence block.
- `T6_OK` accumulates failures across all 4 clauses + T4's `IDLE_OK`; the final verdict is PASS only if
  both are 0. Each clause prints `[PASS] T6 (a/b/c/d)...` with the real nvidia-smi numbers.
- Tooling: `.venv/bin/python` + `.venv/bin/voicectl` + `/usr/bin/nvidia-smi` + `/usr/bin/tmux` + `jq`.
  No new deps. mypy NOT installed (skip). ruff optional (NOT a gate for bash).

---

## 9. Coordination with the parallel item (P1.M3.T2.S1)

S1 edits `tests/test_daemon.py` (fast pytest, fakes, NO CUDA). THIS task (S2) edits
`tests/test_idle_and_gpu.sh` + `tests/ACCEPTANCE.md`. **The two files are disjoint** — no merge
conflict possible. S2 does NOT touch `tests/test_daemon.py`, `daemon.py`, `config.py`, `ctl.py`,
`config.toml`, `PRD.md`, `tasks.json`, `prd_snapshot.md`, `.gitignore`. S2 CONSUMES the LANDED
lifecycle impl (M2.T1 + M3.T1.S1 + M1.T1) — read-only.

## 10. The 4 T6 sub-assertions mapped to the contract (item LOGIC clauses a/b/c/d)

| clause | contract | run | assertion | nvidia-smi expectation |
|---|---|---|---|---|
| (a) | "after boot with NO arm → PID ABSENT" | 1, before start | `assert_vram_absent` | total==0, no tree PID |
| (b) | "after voicectl start → PID present with VRAM" | 1, after start | `wait_vram_present` + `assert_vram_present` | Σ ∈ [1024,5120] MiB |
| (c) | "after voicectl stop → still present" | 1, after stop | `assert_vram_present` | Σ ∈ [1024,5120] MiB (unchanged) |
| (d) | "after auto_unload_idle_seconds disarmed → PID gone; start → reappears" | 2 (5s override) | `wait_vram_absent`+`assert_vram_absent` then `wait_vram_present`+`assert_vram_present` | gone after ~5-25s; present again after reload |

T4 (120s silence, default config) runs on run 1 between T6(b) and T6(c) and is UNCHANGED in substance.
