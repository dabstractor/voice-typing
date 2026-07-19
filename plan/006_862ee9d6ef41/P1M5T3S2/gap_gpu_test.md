# Audit — P1.M5.T3.S2: `tests/test_idle_and_gpu.sh` (PRD §6 T6 — GPU lifecycle, lazy load)

**Date:** 2025-01-22
**Method:** STATIC audit (read-only). NOT run — the script loads CUDA models for ~5–8 min (2 cold
inits + 120 s armed idle + idle-unload waits) (AGENTS.md + work-item: "do NOT run unless explicitly
required"). Findings cross-checked against the LIVE source the script drives.
**Verdict:** 7/8 checks PASS; **1 minor observation** — (g) `status` calls deliberately unwrapped
[LOW] (control calls ARE wrapped via the `voicectl()` fn). **No hard GAP** in the T6 GPU-lifecycle
logic. **Safe to run: YES (operator-present)** (preflight + robust trap + NO audio-source swap; caveat
= (g) status gap → not unattended-safe until fixed). The script is the **sole real-CUDA proof for
Acceptance #9** (T6(d) idle-unload reclaims ~0 VRAM + a later arm reloads).

---

## 1. The 8-check matrix (work-item contract a–h)

Every script line below was re-confirmed against the LIVE file (`tests/test_idle_and_gpu.sh`,
779 lines) and the LIVE source it drives (`voice_typing/{ctl,config,daemon}.py`).

| # | check | script line(s) | LIVE-source evidence | verdict |
|---|---|---|---|---|
| (a) | queries `nvidia-smi --query-compute-apps=pid,used_memory` | `vram_tree_state()` L229; diagnostics L489, L716 | G-VRAM-COMMAS: 2-col query (process_name can contain commas → breaks CSV); `--format=csv,noheader`. Matches PRD §6 T6 wording. nvidia-smi compute-apps lists ONLY procs with an active CUDA context. | ✅ PASS |
| (b) | asserts daemon PID **absent** at boot (before first arm) | L447 `assert_vram_absent "(a) boot: lazy-load ~0 VRAM"`; after `wait_daemon_ready` (Run 1 call L442; def L304), before `voicectl start` L476 | daemon.py lazy-load (§4.2bis): recorder-host child spawned on FIRST arm → boot = no child = no CUDA = tree ABSENT. `assert_vram_absent` checks `total==0`. | ✅ PASS |
| (c) | asserts PID **present** after arm | L476 start → L481 `wait_vram_present 15` → L483 `assert_vram_present "(b) armed: resident"` | total ∈ [VRAM_MIN=1024, VRAM_MAX=5120] MiB = ~1–5 GB (PRD §6 T6 b). Poll ceiling 15s (cold load ~1–3s). | ✅ PASS |
| (d) | asserts PID **remains** after stop | L538 `voicectl stop` (conditional, ISSUE-3) → L546 `assert_vram_present "(c) disarmed: still resident"` | stop disarms but does NOT unload (only idle-unload does); Run 1 threshold 1800s ≫ 120s → no unload fires. auto_stop=30.0 may pre-disarm (handled L531-542). | ✅ PASS |
| (e) | asserts PID **gone** after idle-unload wait | RUN 2 (5s override): L700 stop → L707 `wait_vram_absent 25` → L709 `assert_vram_absent "(d) after 5s idle-unload"` | daemon.py:1233-1239 idle-unload watchdog → `_bounded_shutdown(timeout=5.0)` (L1239/L739) = killpg child group → ALL VRAM released while daemon LIVES. config.py:67 default 1800.0; Run 2 overrides to 5.0. | ✅ PASS — §7.9 crux |
| (f) | asserts **re-arm reloads** | L727 start (re-arm) → L728 `wait_vram_present 15` → L730 `assert_vram_present "(d) re-arm reloads: resident again"` | daemon.py `_load_host` rebuilds the recorder-host child on a fresh arm after unload (~1–3s single-flight). | ✅ PASS |
| (g) | `VOICECTL_TIMEOUT=30` wrapping **all** voicectl calls | L156 `VOICECTL_TIMEOUT=30`; L357 `voicectl() { timeout … }` wraps ALL control calls (start/stop/toggle/toggle-lite/quit — L469, L470, L476, L538, L592, L602, L630, L640, L667, L687, L700, L727) | ctl.py:111-118: `makefile('r')` incompatible w/ `settimeout` → NO socket read timeout; control calls can hang FOREVER → the wrapper bounds them. **BUT 13 status callsites BARE** (L306, L379, L461, L536, L549, L605, L615, L631, L635, L643, L653, L658, L720) by deliberate design. | ✅ PASS (control) / ⚠️ MINOR (status) — §3 |
| (h) | preflight refuses if unit already running | L379-380 (`"$VOICECTL" status` answers → die) + L382 (`systemctl --user is-active voice-typing` → die) | G-PREFLIGHT: real control socket pinned to `$XDG_RUNTIME_DIR`; 2nd daemon can't bind. Checks BOTH socket AND systemd unit. | ✅ PASS |

**Tally:** 7/8 checks PASS clean (a,b,c,d,e,f,h). Check (g) PASSES for the control calls (the actual
hang vectors) and has ONE minor/LOW observation (status deliberately unwrapped — §3). **No hard GAP**
in the T6 GPU-lifecycle logic itself.

## 2. PRD §6 T6 4-part lifecycle map (the oracle)

| PRD §6 T6 clause | script block | work-item check | verdict |
|---|---|---|---|
| (a) idle never armed → PID NOT listed (~0 VRAM) | T6(a) L447 | (b) | ✅ COVERED |
| (b) armed → PID appears ~1–5 GB | T6(b) L481-484 | (c) | ✅ COVERED |
| (c) disarmed not quit → PID+memory REMAIN | T6(c) L546 | (d) | ✅ COVERED |
| (d) disarmed ≥ threshold → PID gone; later arm reloads | T6(d-gone) L707-709 + T6(d-reload) L728-730 | (e)+(f) | ✅ COVERED |

**Acceptance impact:** this script is the SOLE real-CUDA proof for Acceptance **#9** (idle-unload
reclaims ~0 VRAM via nvidia-smi + a later arm reloads). P1.M5.T5.S1 should credit it for #9 (T6(d)
lifecycle, all 4 states proven on real CUDA) + criterion 5 (T4) + criterion 8 (offline grep) +
criterion 6 (un-armed boot/unit grep) as side coverage.

## 3. MINOR OBSERVATION (g) — `status` calls deliberately unwrapped [LOW]

**PASS half (control calls):** `VOICECTL_TIMEOUT=30` (L156) + the `voicectl()` wrapper fn (L357)
`voicectl() { timeout "$VOICECTL_TIMEOUT" "$VOICECTL" "$@"; }` wrap **ALL control calls**
(start/stop/toggle/toggle-lite/quit — L469, L470, L476, L538, L592, L602, L630, L640, L667, L687, L700,
L727). These are the actual hang vectors (`voicectl start` blocks on the cold model load; stop/toggle
touch the control lock). This satisfies the spirit + primary intent of AGENTS.md Rule 1. This script
is the timeout-discipline **PRECEDENT** the sibling `e2e_virtual_mic.sh` (P1.M5.T3.S1) cites —
correctly, for control calls.

**OBSERVATION half (status, [LOW]):** 13 `"$VOICECTL" status` callsites are invoked **bare** (L306,
L379, L461, L536, L549, L605, L615, L631, L635, L643, L653, L658, L720). The script documents the
rationale (L352-356): "`status` is lock-free + needs the full output, so callers invoke it directly
(it never hangs)."

**Why mostly-correct:** `status` is lock-free (the daemon's status handler doesn't acquire `_lock`),
so it can't wedge on the operation lock. Bare status against a just-launched daemon (wait_daemon_ready)
or a known-healthy daemon (post-ready captures) sees connection-refused (fast fail) when the socket
isn't bound — NOT a hang.

**Why technically incomplete (AGENTS.md contradicts):** AGENTS.md Rule 1 — *"Always wrap: `timeout 15
.venv/bin/voicectl status` … Lock-free and fast when healthy, but still has no socket timeout — a dead
daemon still wedges it."* ctl.py:111-118 confirms status uses `makefile('r')` with **NO read timeout**
→ a daemon whose **control thread** is non-responsive (not just the lock) still blocks status.
"Lock-free" ≠ "the thread can't be wedged on something else."

**Most-exposed callsite — `wait_daemon_ready` (L304-312):**
```bash
for _ in $(seq 1 360); do            # 360 x 0.5s = 180s budget
  if "$VOICECTL" status >/dev/null 2>&1; then return 0; fi   # ← bare; if THIS hangs, loop never advances
  kill -0 "$DAEMON_PID" 2>/dev/null || die "daemon exited ..."   # ← liveness check is AFTER status
  sleep 0.5
done
```
The 180s "budget" is a **count of iterations**, not a per-call timeout. A single hung `status` call
defeats it (the `kill -0` liveness check comes AFTER, so it never runs). Same shape in preflight (L379).

**Practical risk: LOW.** At `wait_daemon_ready` the daemon was just launched: socket-not-bound =
connection-refused (fast fail, NOT a hang); socket-bound = responsive. A wedged control thread mid-
cold-start is a narrow regression. Post-ready status captures are against a known-healthy daemon.
Diagnostic status calls inside FAIL blocks are non-critical (already failing).

**Recommended fix (for a downstream REMEDIATION task — NOT applied here; REPORT item):** add a
`voicectl_status()` helper `timeout 15 "$VOICECTL" status "$@"` (shorter timeout than control calls —
status is sub-second when healthy) and use it at the loop callsites (L306, L379) + the captures, OR at
minimum wrap the `wait_daemon_ready` + preflight loop calls (the two with no fallback). The existing
`voicectl()` wrapper already proves the pattern.

**Severity:** MINOR OBSERVATION / LOW — NOT a GAP. The control calls (the demonstrated hang vectors)
ARE wrapped → the AGENTS.md Rule 1 headline is honored. Contrast with the sibling e2e_virtual_mic.sh
(P1.M5.T3.S1): THAT script does NOT wrap its control calls (`"$VOICECTL" start` L228, `"$VOICECTL"
stop` L330 — both bare, no `voicectl()` wrapper, no `VOICECTL_TIMEOUT` — a real HIGH gap); THIS script
DOES wrap them. The shared blind spot between both is bare status calls — a strictly smaller,
lower-risk observation than e2e's control-call gap.

## 4. Correct-design notes (NOT gaps — recorded for completeness)

1. **Test-time threshold compression (1800s → 5s 2-run design):** T6(d) idle-unload on the default
   1800s threshold would take 30 min — impractical AND would corrupt T4's 120s armed window on Run 1.
   The script uses 2 runs: Run 1 = default 1800s (so T4's 120s + T6(c)'s disarmed-resident assertion
   are unaffected — 120s ≪ 1800s); Run 2 = `[asr] auto_unload_idle_seconds=5.0` override via a 2nd
   `XDG_CONFIG_HOME` (`$WORK/config_short`) so idle-unload fires in bounded time. Correct isolation:
   every other [asr] field inherits the SAME dataclass defaults (config.py:67) → identical ASR
   pipeline except the threshold. (G-CONFIG.) ✅
2. **ISSUE-3 / auto_stop interaction (T6(c) subtlety):** `auto_stop_idle_seconds` default = 30.0
   (config.py:65) disarms the mic ~30s into T4's 120s silence window → T6(c) may run against an
   already-disarmed daemon. The script handles this correctly (L531-542: re-checks status, only issues
   `voicectl stop` if still armed, else notes auto-stop already disarmed). T6(c)'s assertion (disarmed
   +resident) is valid EITHER way (auto_stop "disarms but does NOT unload"). The comment cites commit
   81d2ad8 making a redundant stop safe. ✅
3. **Daemon-tree matching, not arbitrary nvidia-smi row (G-VRAM-ATTRIBUTION):** `daemon_tree_pids()`
   (L205) walks `/proc/<pid>/task/<pid>/children` recursively + matches against nvidia-smi PIDs. The GPU
   hosts unrelated compute apps (Chrome, a parallel test daemon) → strict tree filtering is essential.
   PID presence/absence is the HARD signal; used_memory (can lag/underreport) is secondary corroboration.
   The subprocess recorder-host model means the CUDA context lives on the CHILD PID — so tree-matching
   (not just the daemon PID) is what catches it. ✅ essential
4. **Polling, never fixed sleeps (G-TIMEOUTS):** `wait_vram_absent`/`wait_vram_present` POLL every 0.5s
   with a deadline ceiling (~25s absent / ~15s present). The contract's literal "7s" is explicitly
   noted as under-budgeted (1s tick + threshold + ≤7s `_bounded_shutdown` + driver-accounting lag);
   the ceilings absorb the variance. A fixed `sleep 7` would flake. ✅
5. **Robust idempotent cleanup trap (G-CLEANUP-IDEMPOTENT):** `trap cleanup EXIT` → `stop_daemon_run`
   (quit→SIGTERM→8s poll→SIGKILL, idempotent) → kill tmux `vtidle` → rm `$WORK`. Every step `|| true`.
   Distinct tmux session `vtidle` (≠ e2e's `voicetest`) so the two heavy parallel tests never collide.
   ✅
6. **No global audio mutation (G-NOSOURCE):** this test does NOT swap the default audio source (no
   null-sink, no `pactl set-default-source`) — listens to ambient silence on the REAL default mic. So
   there's NOTHING to restore on a crash → simpler + safer trap than e2e (no source-restore step). ✅
7. **No-network / offline proof (criterion 8, NON-CIRCULAR — out of scope, noted):** the script does
   NOT pre-set `HF_HUB_OFFLINE` (that masked a past bug); relies on `launch_daemon.sh`'s exports +
   greps the daemon log for ZERO `HTTP Request: GET https://huggingface.co` lines (L455-458). (Audited
   by P1.M5.T5.S1.) ✅

## 5. Scope — what is IN vs OUT of this audit

- **IN scope (this item):** T6 GPU lifecycle (checks a–f) + (g) timeout discipline + (h) preflight —
  the work-item's 8 checks.
- **OUT of scope (present in the script, audited by sibling items — noted, NOT deep-audited):**
  - T4 idle stability (criterion 5: no hallucination / no crash / CPU<25%) → **P1.M5.T4.\***
  - criterion 6 (un-armed boot / toggle / unit ExecStart+Restart grep) → **P1.M5.T5.S1**
  - criterion 8 (no-network / offline log grep) → **P1.M5.T5.S1**
  - T7 lite mode-switch roundtrip (acceptance #10: toggle-lite reload + VRAM≈half + toggle back) →
    note it drives the REAL daemon mode-switch (L581-660); full audit is P1.M5.T5 / the lite-mode item.

## 6. Safe-to-run verdict

**YES (operator-present)**, with the (g) status caveat.

- ✅ **Preflight refuses** if a daemon is already running (`"$VOICECTL" status` answers OR systemd-active,
  L379-382) — won't collide with the user's real daemon. AGENTS.md: "`systemctl --user stop
  voice-typing` first."
- ✅ **No global audio mutation (G-NOSOURCE):** this test does NOT swap the default audio source. It
  listens to ambient silence on the REAL default mic. So there is NOTHING to restore on a crash → the
  trap is simpler + safer than e2e's (no source-restore step). This is the **lowest-stakes heavy test
  in the repo.**
- ✅ **Cleanup trap is robust + idempotent:** `trap cleanup EXIT` fires on ANY exit (pass, fail,
  Ctrl-C). It stops the daemon bounded (quit→SIGTERM→8s→SIGKILL), kills the `vtidle` tmux session,
  removes temp files. Every step `|| true`; `stop_daemon_run` is idempotent (safe when DAEMON_PID is
  empty/dead).
- ⚠️ **(g) caveat:** a wedged daemon's control thread could hang a bare `status` call in
  `wait_daemon_ready` (L306) or preflight (L379) — no per-call timeout; the loop's `kill -0` liveness
  check is AFTER the status call, so the 180s budget is a count not a bound. **Low practical risk**
  (cold-start = connection-refused fast-fail; the wedge is a narrow regression) but an operator must
  be able to Ctrl-C it → **safe-but-not-unattended-safe** until the §3 status-timeout fix is applied.
- ⚠️ **Heavy:** ~5–8 min (2 cold cuDNN/cuBLAS inits + 120s armed idle + idle-unload waits). Run
  explicitly; NOT collected by the fast pytest suite. AGENTS.md: bash-tool `timeout` **900** (15 min);
  `systemctl --user stop voice-typing` first (preflight will refuse if it's running).
- 📌 **Precondition:** QUIET room (ambient speech could produce a real final + spuriously fail the
  "no finals" T4 assertion — T4's concern, out of this item's T6 scope).

**Do NOT run during this audit item** (AGENTS.md: ~5–8 min CUDA load). If a later task is explicitly
authorized to run it, apply the §3 status-timeout fix first for unattended/CI safety.

## 7. Cross-references

- Source-side audits (cite, don't re-derive): `architecture/gap_lifecycle.md` (lazy load + idle-unload
  + `_bounded_shutdown(timeout=5.0)` killpg), `architecture/gap_socket.md` (no socket timeout),
  `architecture/gap_recorder_kwargs.md` (the 2-model kwargs the VRAM range reflects).
- Sibling e2e script audit: `P1M5T3S1/PRP.md` + `P1M5T3S1/gap_e2e.md` (cites THIS script's
  VOICECTL_TIMEOUT=30 + voicectl() fn as the timeout precedent e2e SHOULD follow; e2e's GAP is the
  UNWRAPPED control calls — confirmed: e2e L228 `"$VOICECTL" start` + L330 `"$VOICECTL" stop` are bare;
  THIS script wraps them, so its only blind spot is bare status, strictly smaller).
- Acceptance evidence consumer: `P1.M5.T5.S1` (#9 T6(d) lifecycle = sole real-CUDA proof; (g) status
  caveat refines the timeout-credit picture).