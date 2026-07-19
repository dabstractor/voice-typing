# Research — P1.M5.T3.S2: Audit `tests/test_idle_and_gpu.sh` (PRD §6 T6 GPU lifecycle)

**Method:** STATIC audit (read-only). NOT run — the script loads CUDA models for ~5–8 min (2 cold
inits) + holds the real mic armed for 120 s (AGENTS.md + work-item: "do NOT run unless explicitly
required"). Findings cross-checked against the LIVE source the script drives.

**Subject:** `tests/test_idle_and_gpu.sh` (779 lines — NOT 364; that was the sibling e2e script).
Covers PRD §6 **T4** (idle stability, criterion 5) + **T6** (GPU lifecycle, 4-part) + criterion 6
(un-armed boot / toggle / unit grep) + criterion 8 (no-network / offline) + **T7** (lite mode-switch).
THIS item owns the **T6 + (g) timeout + (h) preflight** slice; T4 = P1.M5.T4.*, criteria 6/8/9 =
P1.M5.T5.*, T7 = covered here only as a scope note.

---

## 1. The 8-check matrix (work-item contract a–h) — verified against LIVE script + source

| # | check | script line(s) | LIVE-source evidence | verdict |
|---|---|---|---|---|
| (a) | queries `nvidia-smi --query-compute-apps=pid,used_memory` | `vram_tree_state()` L229; diagnostics L489, L716 | G-VRAM-COMMAS: 2-col query (process_name can contain commas → breaks CSV). `--format=csv,noheader`. Matches PRD §6 T6 wording exactly. | ✅ PASS |
| (b) | asserts daemon PID **absent** at boot (before first arm) | L447 `assert_vram_absent "$DAEMON_PID" "(a) boot: lazy-load ~0 VRAM"`; AFTER `wait_daemon_ready` L442, BEFORE `voicectl start` L476 | daemon.py lazy-load: recorder-host child spawned on FIRST arm (§4.2bis); boot = no child = no CUDA = tree ABSENT. `assert_vram_absent` checks `total==0`. | ✅ PASS |
| (c) | asserts PID **present** after arm | L476 `voicectl start` → L481 `wait_vram_present … 15` → L483 `assert_vram_present "$DAEMON_PID" "(b) armed: resident"` | `assert_vram_present` checks total ∈ [VRAM_MIN_MIB=1024, VRAM_MAX_MIB=5120] = ~1–5 GB (PRD §6 T6 b). Poll ceiling 15s (cold load ~1–3s). | ✅ PASS |
| (d) | asserts PID **remains** after stop | L538 `voicectl stop` (conditional on still-armed, see ISSUE-3) → L546 `assert_vram_present "$DAEMON_PID" "(c) disarmed: still resident"` | daemon.py: stop disarms but does NOT unload (only idle-unload does). Run 1 threshold 1800s ≫ 120s window → no unload fires. | ✅ PASS |
| (e) | asserts PID **gone** after idle-unload wait | RUN 2 (5s override): L700 `voicectl stop` → L707 `wait_vram_absent "$DAEMON_PID" 25` → L709 `assert_vram_absent "(d) after 5s idle-unload: ~0 VRAM reclaimed"` | daemon.py:1233-1239 idle-unload watchdog → `_bounded_shutdown(timeout=5.0)` (L1239/L739) = killpg the child group → ALL VRAM released while daemon LIVES. config.py:67 default 1800.0; Run 2 overrides to 5.0 via `XDG_CONFIG_HOME=$WORK/config_short`. | ✅ PASS — the §7.9 crux |
| (f) | asserts **re-arm reloads** | L727 `voicectl start (re-arm)` → L728 `wait_vram_present … 15` → L730 `assert_vram_present "(d) re-arm reloads: resident again"` | daemon.py `_load_host` rebuilds the recorder-host child on a fresh arm after unload (~1–3s single-flight). | ✅ PASS |
| (g) | `VOICECTL_TIMEOUT=30` wrapping **all** voicectl calls | L156 `VOICECTL_TIMEOUT=30`; L357 `voicectl() { timeout "$VOICECTL_TIMEOUT" "$VOICECTL" "$@"; }`; wraps **all control calls** (start/stop/toggle/toggle-lite/quit) — L469/470/476/538/592/602/630/640/667/687/700/727 | ctl.py:111-118: `makefile("r")` is incompatible with `settimeout` → **NO socket read timeout**; control calls can hang FOREVER on a wedged daemon. The wrapper fn bounds them. **BUT 13 `status` callsites are BARE** (L306,379,461,536,549,605,615,631,635,643,653,658,720) — by deliberate design ("status is lock-free + needs full output, never hangs"). | ✅ PASS (control) / ⚠️ MINOR (status deliberately unwrapped — §3) |
| (h) | preflight refuses if unit already running | L379-380 (`voicectl status` answers → die) + L382 (`systemctl --user is-active voice-typing` → die) | G-PREFLIGHT: the real control socket is pinned to `$XDG_RUNTIME_DIR`; a 2nd daemon can't bind (RuntimeError). Checks BOTH the socket AND the systemd unit. | ✅ PASS |

**Tally:** 7/8 PASS clean (a,b,c,d,e,f,h). Check (g) PASSES for the control calls (the actual hang
vectors) and has ONE minor/LOW observation (status deliberately unwrapped — §3). **No hard GAP** in
the T6 GPU-lifecycle logic itself. The script is the timeout-discipline PRECEDENT the sibling
`e2e_virtual_mic.sh` (P1.M5.T3.S1) cites — and correctly so for control calls.

---

## 2. PRD §6 T6 4-part lifecycle map (the oracle)

PRD §6 T6 a/b/c/d ↔ work-item checks (a)-(f), both present + correct:

| PRD §6 T6 clause | script block | work-item check | verdict |
|---|---|---|---|
| (a) idle never armed → PID NOT listed (~0 VRAM) | T6(a) L447 | (b) | ✅ |
| (b) armed → PID appears ~1–5 GB | T6(b) L481-484 | (c) | ✅ |
| (c) disarmed not quit → PID+memory REMAIN | T6(c) L546 | (d) | ✅ |
| (d) disarmed ≥ threshold → PID gone; later arm reloads | T6(d-gone) L707-709 + T6(d-reload) L728-730 | (e)+(f) | ✅ |

The 4-part lifecycle is the **sole real-CUDA proof for Acceptance #9** (idle-unload reclaims ~0 VRAM
+ a later arm reloads). The script is the only artifact that can prove #9. P1.M5.T5.S1 should credit
this script for #9 (T6(d) lifecycle) + criterion 5 (T4) + criterion 8 (offline grep) + criterion 6
(un-armed boot/unit grep).

---

## 3. Minor observation (NOT a hard gap) — (g): `status` calls deliberately unwrapped [LOW]

**Fact:** the `voicectl()` wrapper fn (L357) wraps ONLY control commands. 13 `"$VOICECTL" status`
callsites are invoked bare. The script documents the rationale at L352-356: "`status` is lock-free +
needs the full output, so callers invoke it directly (it never hangs)."

**Why it's mostly-correct:** `status` is lock-free (the daemon's status handler doesn't acquire
`_lock`), so it can't wedge on the operation lock the way `start`/`stop` can. The bare status calls
against a just-launched daemon (wait_daemon_ready) or a known-healthy daemon (post-ready captures)
see connection-refused (fast fail) when the socket isn't bound yet — NOT a hang.

**Why it's technically incomplete (AGENTS.md contradicts):** AGENTS.md Rule 1 says *"Always wrap:
`timeout 15 .venv/bin/voicectl status`"* with the rationale *"Lock-free and fast when healthy, but
still has no socket timeout — a dead daemon still wedges it."* ctl.py:111-118 confirms status uses
`makefile("r")` with NO read timeout → a daemon whose **control thread** is non-responsive (not just
the lock) still hangs status. "Lock-free" ≠ "the thread can't be wedged on something else."

**Most-exposed callsite — `wait_daemon_ready` L304-312:**
```bash
for _ in $(seq 1 360); do            # 360 x 0.5s = 180s budget
  if "$VOICECTL" status >/dev/null 2>&1; then return 0; fi   # ← bare; if THIS hangs, loop never advances
  kill -0 "$DAEMON_PID" 2>/dev/null || die "daemon exited ..."   # ← liveness check is AFTER status
  sleep 0.5
done
```
The 180s "budget" is a **count of iterations**, not a per-call timeout. A single hung `status` call
defeats it (the `kill -0` liveness check comes AFTER, so it never runs). Same shape in preflight L379
(a wedged pre-existing daemon hangs preflight forever).

**Practical risk: LOW.** At `wait_daemon_ready` the daemon was just launched: either the socket isn't
bound (connection-refused = fast fail, NOT a hang) or it's bound + responsive. A wedged control
thread mid-cold-start is a narrow regression. At the post-ready status captures the daemon is known
healthy. The diagnostic status calls inside FAIL blocks are non-critical (already failing).

**Recommended fix (for a downstream remediation — NOT applied here; REPORT item):** add a
`voicectl_status()` helper `timeout 15 "$VOICECTL" status "$@"` (shorter timeout than control
calls — status is sub-second when healthy) and use it at the loop callsites (L306, L379) + the
captures, OR at minimum wrap the `wait_daemon_ready` + preflight loop calls (the two that have no
fallback). The `voicectl()` wrapper already proves the pattern.

**Severity framing for the report:** this is a **minor observation / LOW**, NOT a GAP. The control
calls — which are the actual, demonstrated hang vectors (start blocks on cold model load; stop/toggle
touch the lock) — ARE all wrapped. That satisfies the spirit + primary intent of AGENTS.md Rule 1.
The status gap is theoretical (narrow regression) + the script has a documented rationale. Record it
honestly so P1.M5.T5.S1 credits the timeout discipline correctly (control ✅, status ✅-with-caveat).

---

## 4. Other notable design points (all CORRECT — recorded for completeness, NOT gaps)

1. **Test-time threshold compression (1800s → 5s override):** T6(d) idle-unload on the default
   1800s threshold would take 30 min — impractical + would corrupt T4's 120s armed window on Run 1.
   The script uses a **2-run design**: Run 1 = default 1800s (so T4's 120s armed window + T6(c)'s
   disarmed-resident assertion are unaffected — 120s ≪ 1800s); Run 2 = `[asr]
   auto_unload_idle_seconds=5.0` override via a 2nd `XDG_CONFIG_HOME` (`$WORK/config_short`) so the
   idle-unload fires in test-bounded time. CORRECT isolation: every other [asr] field inherits the
   SAME dataclass defaults (config.py:67 default 1800.0) → identical ASR pipeline except the
   threshold. (G-CONFIG invariant.)

2. **ISSUE-3 / auto_stop interaction (T6(c) subtlety):** `auto_stop_idle_seconds` default = 30.0
   (config.py:65). During T4's 120s armed-silence window, auto-stop disarms the mic at ~30s (no
   speech). So by T6(c)'s assertion time the mic is ALREADY disarmed. The script handles this
   correctly (L531-542): re-checks status, only issues `voicectl stop` if still armed, else notes
   auto-stop already disarmed. T6(c)'s assertion (disarmed+resident) is valid EITHER way (auto_stop
   "disarms but does NOT unload — hands off to idle-unload timer"). The comment cites commit 81d2ad8
   ("gate abort() on in-flight text") making a redundant stop safe. CORRECT + well-documented.

3. **Daemon-tree matching, not arbitrary nvidia-smi row (G-VRAM-ATTRIBUTION):** `daemon_tree_pids()`
   walks `/proc/<pid>/task/<pid>/children` recursively + matches against nvidia-smi PIDs. The GPU
   hosts unrelated compute apps (Chrome, a parallel test daemon) → filtering strictly by the daemon's
   descendant tree is essential. PID presence/absence is the HARD signal; used_memory (can lag/
   underreport) is secondary corroboration. The subprocess recorder-host model means the CUDA context
   lives on the CHILD PID, not the daemon PID — so tree-matching (not just the daemon PID) is what
   catches it. CORRECT + essential.

4. **Polling, never fixed sleeps (G-TIMEOUTS):** `wait_vram_absent`/`wait_vram_present` POLL every
   0.5s with a deadline ceiling (~25s absent / ~15s present). The contract's literal "7s" is
   explicitly noted as under-budgeted (1s watchdog tick + threshold + ≤7s `_bounded_shutdown` + driver
   accounting lag); the ceilings absorb the variance. CORRECT — a fixed `sleep 7` would flake.

5. **Cleanup trap (G-CLEANUP-IDEMPOTENT):** `trap cleanup EXIT` → `stop_daemon_run` (quit→SIGTERM→
   8s poll→SIGKILL, idempotent) → kill tmux session `vtidle` → rm `$WORK`. NO audio-source restore
   needed (G-NOSOURCE — this test never swaps the default audio source, unlike T3's e2e). Fires on
   ANY exit (pass/fail/Ctrl-C). Distinct tmux session name `vtidle` (≠ T3's `voicetest`) so the two
   heavy parallel tests never collide. CORRECT + simpler trap than e2e (no source restore).

6. **No-network / offline proof (criterion 8, NON-CIRCULAR):** the script does NOT pre-set
   `HF_HUB_OFFLINE` (that masked a past bug); it relies on `launch_daemon.sh`'s exports (production
   path) + greps the daemon log for ZERO `HTTP Request: GET https://huggingface.co` lines (L455-458).
   This is the non-circular criterion-8 proof. (Out of this item's scope — P1.M5.T5 — but present.)

---

## 5. Safe-to-run verdict

**YES (operator-present), with the (g) status caveat.**

- ✅ **Preflight refuses** if a daemon is already running (voicectl answers OR systemd-active) — won't
  collide with the user's real daemon (L379-382). AGENTS.md: "preflight refuses if the unit is
  already running — `systemctl --user stop voice-typing` first."
- ✅ **No global audio mutation:** this test does NOT swap the default audio source (G-NOSOURCE — no
  null-sink, no `pactl set-default-source`). It listens to ambient room silence on the REAL default
  mic. So there's NOTHING to restore on a crash — the trap is simpler + safer than e2e's. (Contrast
  with e2e_virtual_mic.sh, which rebinds the global source.)
- ✅ **Cleanup trap is robust + idempotent** (fires on any exit; stop_daemon_run is idempotent; kills
  tmux; rm temp). No audio-source-restore step needed.
- ⚠️ **(g) caveat:** a wedged daemon's control thread could hang a bare `status` call in
  `wait_daemon_ready` (L306) or preflight (L379) — no per-call timeout, the loop's `kill -0` liveness
  check is AFTER the status call, so the 180s budget is a count not a bound. **Low practical risk**
  (cold-start = connection-refused fast-fail; the wedge is a narrow regression) but an operator must
  be able to Ctrl-C it → **safe-but-not-unattended-safe** until the §3 status-timeout fix is applied.
- ⚠️ **Heavy:** ~5–8 min (2 cold cuDNN/cuBLAS inits + 120s armed idle + idle-unload waits). Run
  explicitly; NOT collected by the fast pytest suite. AGENTS.md: bash-tool `timeout` of **900** (15
  min); `systemctl --user stop voice-typing` first (preflight will refuse if it's running).
- 📌 **Precondition:** QUIET room (ambient speech could produce a real final + spuriously fail the
  "no finals" T4 assertion — but that's T4's concern, out of this item's T6 scope).

**Do NOT run during this audit item** (5–8 min + CUDA + heavy). The audit is STATIC. A later task
explicitly authorized to run it should apply the §3 status-timeout fix first for unattended safety.

---

## 6. LIVE-source line-number reference (for the report's evidence column)

```
tests/test_idle_and_gpu.sh:
  L156   VOICECTL_TIMEOUT=30
  L229/489/716   nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
  L253/263/278/286   assert_vram_absent / assert_vram_present / wait_vram_absent / wait_vram_present
  L357   voicectl() { timeout "$VOICECTL_TIMEOUT" "$VOICECTL" "$@"; }   (wraps CONTROL calls only)
  L306/379/461/536/549/605/615/631/635/643/653/658/720   bare "$VOICECTL" status   (the (g) nuance)
  L379-382   preflight refuse (voicectl answers OR systemd-active)
  L442   wait_daemon_ready (BEFORE T6(a))
  L447   assert_vram_absent "(a) boot: lazy-load ~0 VRAM"        → T6(a) = check (b)
  L476   voicectl start (Run 1)
  L481-484   wait_vram_present 15 + assert_vram_present "(b) armed"   → T6(b) = check (c)
  L538/546   voicectl stop + assert_vram_present "(c) disarmed"       → T6(c) = check (d)
  L700   voicectl stop (Run 2, 5s threshold)
  L707-709   wait_vram_absent 25 + assert_vram_absent "(d) idle-unload"  → T6(d-gone) = check (e)
  L727-730   voicectl start (re-arm) + assert_vram_present "(d) reloads" → T6(d-reload) = check (f)

voice_typing/ctl.py:
  L111-118   makefile("r") (incompatible w/ settimeout → NO socket read timeout). Root of the (g) nuance.

voice_typing/config.py:
  L65    auto_stop_idle_seconds: float = 30.0      (the ISSUE-3 / T4-T6(c) interaction)
  L67    auto_unload_idle_seconds: float = 1800.0  (PRD §4.2bis default; Run 2 overrides to 5.0)

voice_typing/daemon.py:
  L733-739   resident teardown under _lock → _bounded_shutdown(timeout=5.0)
  L831-833   idle-unload watchdog thread ("voice-typing-idle-unload")
  L1184/1222   threshold = self._cfg.asr.auto_unload_idle_seconds
  L1233-1239   "voice-typing idle-unload: %.1fs disarmed; unloading models" → _bounded_shutdown(timeout=5.0)
               (the killpg-after-join(5s) that releases ALL VRAM while the daemon LIVES — PRD §7.9)
```

## 7. Scope boundaries (for the implementing agent)

- **IN scope:** the T6 GPU-lifecycle assertions (checks a–f) + (g) timeout discipline + (h) preflight.
  These are the work-item's 8 checks.
- **OUT of scope (audited by sibling items — note presence, don't deep-audit):**
  - T4 idle stability (criterion 5: no hallucination / no crash / CPU<25%) → **P1.M5.T4.***
  - criterion 6 (un-armed boot / toggle / unit ExecStart+Restart grep) → **P1.M5.T5.S1**
  - criterion 8 (no-network / offline log grep) → **P1.M5.T5.S1**
  - T7 lite mode-switch roundtrip (acceptance #10) → note it's present + drives the real daemon
    mode-switch; full audit is P1.M5.T5 / the lite-mode item.
- **Do NOT run** the script (5–8 min, CUDA, heavy). STATIC read-only audit.
- **Do NOT edit** the script, any source, PRD.md, tasks.json, prd_snapshot.md, .gitignore. REPORT
  item — the ONLY output is `plan/006_862ee9d6ef41/P1M5T3S2/gap_gpu_test.md`.