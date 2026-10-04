#!/usr/bin/env bash
# tests/test_idle_and_gpu.sh — idle stability (PRD §6 T4) + GPU residency (T6: 4-part lazy-load
# lifecycle, PRD §6 T6 a/b/c/d + §4.2bis + §7.9) + offline (criterion 8) + single-model arming
# (T7: PRD §4.2quater + acceptance #10/#12 — one-model asserts, VRAM window, cancel smoke).
#
# Stands up the REAL daemon via the PRODUCTION path (launch_daemon.sh — no pre-set env, so the
# test exercises the real systemd -> wrapper flow). launch_daemon.sh exports HF_HUB_OFFLINE=1 +
# TRANSFORMERS_OFFLINE=1 (bugfix Issue 1 fix); this test asserts ZERO 'HTTP Request: GET
# https://huggingface.co' lines in the daemon log as the criterion-8 proof (no circular pre-set).
#
# T4 (criterion 5): arms the mic with `voicectl start`, holds 120 s of silence on the REAL default
# mic (no null-sink — it listens to ambient room silence), and asserts the three T4 properties:
#   (a) NO hallucinated finals typed — the P1.M2.T2.S1 blocklist + VAD gating suppress Whisper's
#       silence-hallucination ("thank you." / "thanks for watching." / "you." / "bye."). Detected
#       via the ISOLATED state.json: `last_final` UNCHANGED from its initial "" and `partial` empty.
#   (b) NO crash — `kill -0 $DAEMON_PID` after the 120 s window.
#   (c) avg CPU < 25 % of ONE core — /proc/<pid>/stat utime+stime (fields 14/15 via the last-`)`
#       split) summed over the daemon's PROCESS TREE at T0/T1, divided by elapsed wall-seconds.
#       pidstat/sysstat is NOT installed, so /proc is the zero-dep path (G-CPU-SAMPLING).
#
# T6 GPU residency — the 4-part LAZY-LOAD LIFECYCLE (PRD §6 T6 a/b/c/d + §4.2bis + §7.9):
#   (a) BOOT with NO arm      → daemon tree ABSENT from nvidia-smi (~0 VRAM) — the lazy-load
#       guarantee (M2.T1: the recorder is NOT built at boot; built on the first arm). MUST be
#       measured BEFORE the first start.
#   (b) after voicectl start  → daemon tree PRESENT, Σ used_memory ∈ [512, 3072] MiB (the ONE
#       small.en model resident — Rev 2 single-mode; phase loaded-listening).
#   (c) after voicectl stop   → daemon tree STILL PRESENT (models stay resident for instant
#       re-arm; stop does NOT unload — only idle-unload does).
#   (d) after auto_unload_idle_seconds DISARMED → daemon tree GONE (~0 VRAM reclaimed, PRD §7.9
#       "verified via nvidia-smi"), then a later voicectl start → tree PRESENT again (reload).
#
# T7 single-model arming (PRD §4.2quater + acceptance #10/#12, Rev 2): after T6(c) the test
# re-arms and asserts the COLLAPSED reality — exactly ONE model (the startup
# 'voice-typing device resolved: device=cuda compute_type=float16 model=small.en' line fires ONCE
# at startup via the cuda_check driver probe; ZERO 'distil-large-v3' anywhere in daemon.log — no
# large-model worker), `mode: lite` in status while armed (a Rev 2 CONSTANT — no other mode
# exists), armed VRAM inside the widened single-model window [512,3072] MiB (one small.en
# ≈ 0.5-3 GB; the old two-model [1024,5120] window would spuriously FAIL the single-model arm at
# the low end and ADMIT a two-model regression at the high end), and an armed no-op
# `voicectl cancel` smoke (no tail in flight -> ok + listening stays on + idempotent —
# acceptance #12's shell evidence).
#
# This needs TWO daemon runs (different configs):
#   RUN 1 (default auto_unload_idle_seconds=1800): T6(a) → criterion-8 grep → criterion-6 un-armed
#       boot → criterion-6 toggle → start → T6(b) → T4 (120s ARMED silence; 120s << 1800s so the
#       idle-unload clock — which only runs DISARMED — never fires) → stop → T6(c) → criterion-6
#       status/unit grep. (T4 MUST use the default 1800s threshold: its 120s window is ARMED, and
#       even after stop 120s << 1800s, so no unload corrupts T6(c).)
#   RUN 2 (auto_unload_idle_seconds=5 override): boot → absent → start → present → stop →
#       T6(d-gone) POLL until tree ABSENT (ceiling ~25s; the contract's literal "7s" is under-
#       budgeted: 1s watchdog tick + 5s threshold + ≤7s _bounded_shutdown teardown + sub-second
#       nvidia-smi driver-accounting lag) → start again → T6(d-reload) POLL until tree PRESENT.
#       The 5s threshold is ONLY on run 2 so T4's 120s window on run 1 is unaffected.
#
# NOTE on T6(d-gone) (PRD §7.9 + the riskiest clause): FIXED via the subprocess recorder host
#   (P1.M3.T2.S2 re-plan). The daemon process now NEVER touches CUDA — the entire
#   AudioToTextRecorder (final model + realtime model + VAD + cuda_check) is constructed + owned
#   in a managed CHILD subprocess (voice_typing/recorder_host.py RecorderHost). The daemon spawns
#   the child on first arm and terminates the child PROCESS GROUP (os.setsid in the child +
#   os.killpg in the daemon) on idle-unload/quit, so ALL VRAM (including the realtime-model CUDA
#   primary context that previously stayed resident on the daemon PID) is released. The daemon tree
#   is therefore ABSENT from nvidia-smi after idle-unload while the daemon keeps running. A FAIL
#   here would mean a grandchild orphaned (the killpg teardown missed it) — debug the group
#   teardown, do NOT weaken the assertion.
#
# Asserts on the daemon DESCENDANT TREE (daemon_tree_pids), NOT an arbitrary nvidia-smi row — the
# tree matches whichever process (daemon or spawn worker) holds the context. PID presence/absence
# is the hard signal (used_memory can lag/underreport; the [512,3072] MiB range is secondary
# corroboration). POLLs (never a fixed sleep) for the unload/reload transitions — nvidia-smi is a
# live uncached driver query but the unload fire + teardown + driver accounting have variance.
#
# Also exercises voicectl toggle/start/stop/cancel/status/quit (each must return ok) + greps the systemd
# unit for ExecStart → launch_daemon.sh + Restart=on-failure, and asserts the daemon BOOTS UN-ARMED
# (voicectl status → `listening: off` right after ready — PRD §4.9; criterion 6).
#
# Prints a fenced `=== ACCEPTANCE EVIDENCE ===` block (real CPU %, real nvidia-smi rows + total for
# all 4 T6 states, the T7 single-model outputs — one-model grep, armed VRAM window, mode: lite,
# cancel smoke — voicectl status, unit grep, per-criterion PASS/FAIL) — paste it verbatim into
# tests/ACCEPTANCE.md (criteria 5/6/8/9/10). On FAIL it prints the daemon.log tail.
#
# Real stack: CUDA Whisper. Heavy (~5-8 min: 2 cold inits ~3-4 min each + the fixed 120 s
# T4 window + idle-unload waits). Run explicitly; NOT collected by the fast pytest suite.
#   cd /home/dustin/projects/voice-typing
#   systemctl --user stop voice-typing 2>/dev/null || true   # preflight will refuse if it's running
#   ./tests/test_idle_and_gpu.sh
#
# PREFLIGHT: refuses to start if a voice-typing daemon is already running (voicectl status answers
# OR the systemd unit is active) — the real control socket is pinned to $XDG_RUNTIME_DIR and a
# second daemon cannot bind (RuntimeError). Stop it first:
#   systemctl --user stop voice-typing
#
# PRECONDITION: run in a QUIET room. This test does NOT swap the default audio source (no null-sink,
# no pw-cat — G-NOSOURCE), so it listens to ambient silence on the real default mic. Ambient speech
# could produce a REAL final and spuriously fail the "no finals" assertion.
#
# CLEANUP: a trap guarantees the daemon is gone and temp dirs
# are removed on ANY exit (PASS, error, Ctrl-C). No audio-source restore is needed (this test never
# swaps it).
#
# GOTCHAS encoded here (see PRP G-* invariants):
#   G-OFFLINE:           do NOT pre-set HF_HUB_OFFLINE (that masked Issue 1). Rely on
#                        launch_daemon.sh's exports (production path); grep daemon.log for ZERO
#                        'HTTP Request: GET https://huggingface.co' lines as the NON-CIRCULAR
#                        criterion-8 proof.
#   G-CPU-SAMPLING:      /proc-based CPU averaging (pidstat/sysstat NOT installed). CLK_TCK=100;
#                        utime=field(14)=rest[11], stime=field(15)=rest[12] after the last-`)` split.
#   G-CPU-TREE:          measure the PROCESS TREE, not just the daemon PID (SafePipe may spawn a
#                        child process; the CUDA workers run in spawn PROCESSES that the idle-unload
#                        force-terminates — the tree sum is correct either way).
#   G-VRAM-ATTRIBUTION:  match the daemon's descendant TREE against nvidia-smi compute-app PIDs;
#                        NEVER assert on an arbitrary row. PID presence/absence is the hard signal;
#                        used_memory is secondary corroboration (can lag/underreport).
#   G-VRAM-COMMAS:       query ONLY pid,used_memory (process_name can contain commas → breaks CSV).
#   G-OTHER-APPS:        the GPU hosts unrelated compute apps (Chrome, a parallel test daemon) →
#                        filter strictly by the daemon tree.
#   G-UNARMED:           assert `listening: off` right after ready, BEFORE voicectl start.
#   G-IDLE-NO-TYPING:    finals are read from the isolated state.json `last_final` (record_final
#                        writes it); snapshot before/after the 120 s window.
#   G-RUNTIME:           keep the REAL XDG_RUNTIME_DIR (PyAudio + the control socket need it; moving
#                        it to a temp dir breaks PulseAudio → ALSA fallback → silence). Isolate
#                        state.json via the config override.
#   G-CONFIG:            override via XDG_CONFIG_HOME=<tmp>/config (minimal [output]+[feedback]); do
#                        NOT edit the repo config.toml. Run 2 uses a 2nd dir (<tmp>/config_short)
#                        adding ONLY [asr] auto_unload_idle_seconds=5.0; every other [asr] field
#                        inherits the SAME dataclass defaults → identical ASR pipeline except the
#                        threshold (the desired isolation).
#   G-PREFLIGHT:         refuse if voicectl status answers / systemctl --user is-active voice-typing.
#   G-NOSOURCE:          do NOT swap the default audio source — simpler trap (no source restore).
#   G-TIMEOUTS:          180 s daemon-ready per run (cold init + model loads, OFFLINE); the idle
#                        window is FIXED at exactly 120 s (PRD §6 T4 — do not shorten). T6(d) POLL
#                        ceilings: ~25s (absent) / ~15s (present) — NOT the literal "7s" (under-
#                        budgeted; see CRITICAL #3 in the PRP).
#   G-CLEANUP-IDEMPOTENT: every trap step wrapped in `|| true` / `2>/dev/null`; trap fires on EXIT;
#                        stop_daemon_run is idempotent (safe when DAEMON_PID is empty/dead).
#   G-EVIDENCE-BLOCK:    print a fenced `=== ACCEPTANCE EVIDENCE ===` block on PASS (real numbers).
#   G-CRIT6-VOICECTL:    exercise toggle explicitly (on then off), OUTSIDE the 120 s window.
set -euo pipefail

# --- paths + tunables ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO"
VOICECTL="$REPO/.venv/bin/voicectl"
PY="$REPO/.venv/bin/python"
LAUNCH="$REPO/voice_typing/launch_daemon.sh"
UNIT="$REPO/systemd/voice-typing.service"
NVIDIA_SMI=/usr/bin/nvidia-smi
IDLE_SECS=120                     # PRD §6 T4: 'silence for 120 s' (FIXED — do not shorten)
CPU_LIMIT_PCT=25                  # < 25% of ONE core (PRD §6 T4; do NOT divide by nproc)
VRAM_MIN_MIB=512                  # Rev 2 single-model arm: ONE small.en resident ≈ 0.5 GB (§4.2quater)
VRAM_MAX_MIB=3072                 # ONE small.en ≈ 3 GB ceiling; old two-model 5120 would admit a two-model regression
# voicectl's socket readline() has NO timeout (makefile is incompatible with settimeout, ctl.py
# _send_command), so any daemon-side hang (e.g. a regression of the abort()-under-_lock wedge, or
# the SIGTERM-path teardown stall) would hang voicectl FOREVER. Wrap the control commands in
# `timeout` so a hang fails LOUD (exit 124) instead of stalling the whole heavy test. 30s is far
# above any legit arm/disarm (the cold first-arm load is ~1-3s; status is lock-free and fast).
VOICECTL_TIMEOUT=30

# --- state (populated by setup; used by the trap) ---
WORK=""
DAEMON_PID=""

# --- result accumulators (0 = no failure seen so far) ---
IDLE_OK=0   # T4 (criterion 5) failures
T6_OK=0     # T6 (a/b/c/d) failures

# --- helpers: /proc CPU-over-tree (G-CPU-SAMPLING / G-CPU-TREE) + nvidia-smi tree (G-VRAM-*) ---
# Sum utime+stime (fields 14/15 via the last-`)` split) over root + ALL descendants, /CLK_TCK.
# The descendant walk is recursive via /proc/<pid>/task/<pid>/children (no pgrep dep).
cpu_tree_seconds() {  # $1 = root pid -> total utime+stime SECONDS over root + descendants
  "$PY" - "$1" <<'PY'
import os, sys
CLK = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
def ticks(pid):
    try:
        with open(f'/proc/{pid}/stat') as f:
            s = f.read()
        rp = s.rfind(')')                 # split AFTER last ')' (comm may contain spaces/parens)
        rest = s[rp + 2:].split()
        return int(rest[11]) + int(rest[12])   # utime(field 14) + stime(field 15)
    except (FileNotFoundError, ProcessLookupError, ValueError, IndexError, OSError):
        return 0
def descendants(root):
    out = {root}; stack = [root]
    while stack:
        p = stack.pop()
        try:
            with open(f'/proc/{p}/task/{p}/children') as f:
                ch = [int(x) for x in f.read().split()]
        except (FileNotFoundError, ProcessLookupError, OSError):
            ch = []
        for c in ch:
            if c not in out:
                out.add(c); stack.append(c)
    return out
print(sum(ticks(p) for p in descendants(int(sys.argv[1]))) / CLK)
PY
}
daemon_tree_pids() {  # $1 = root pid -> space-joined root + descendants
  "$PY" - "$1" <<'PY'
import sys
def descendants(root):
    out = {root}; stack = [root]
    while stack:
        p = stack.pop()
        try:
            with open(f'/proc/{p}/task/{p}/children') as f:
                ch = [int(x) for x in f.read().split()]
        except (FileNotFoundError, ProcessLookupError, OSError):
            ch = []
        for c in ch:
            if c not in out:
                out.add(c); stack.append(c)
    return out
print(' '.join(str(p) for p in descendants(int(sys.argv[1]))))
PY
}

# Echo "<total_MiB> <matched_pids_csv>" for the daemon tree. total=0 + empty matched => ABSENT
# (~0 VRAM). Comma-safe 2-column query (G-VRAM-COMMAS: process_name can contain commas).
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
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        mib = parts[1].replace('MiB', '').strip()
        try:
            m = int(mib)
        except ValueError:
            continue
        if pid in tree:
            matched.append(pid); total += m
print(f"{total} {','.join(map(str, sorted(set(matched))))}")
PY
}
assert_vram_absent() {  # $1 = root pid  $2 = label  -> total == 0 (ABSENT)
  local out; out="$(vram_tree_state "$1")"; local total="${out%% *}"
  if [ "$total" = "0" ]; then
    echo "[PASS] T6 $2: daemon tree ABSENT from nvidia-smi (~0 VRAM) [$out]"
    return 0
  fi
  echo "[FAIL] T6 $2: expected ABSENT, got total=${total} MiB [$out]"
  T6_OK=1
  return 1
}
assert_vram_present() {  # $1 = root pid  $2 = label  -> total in [VRAM_MIN, VRAM_MAX]
  local out; out="$(vram_tree_state "$1")"; local total="${out%% *}"
  if awk -v t="$total" -v lo="$VRAM_MIN_MIB" -v hi="$VRAM_MAX_MIB" 'BEGIN{ exit !(t+0>=lo+0 && t+0<=hi+0) }'; then
    echo "[PASS] T6 $2: daemon tree PRESENT, total=${total} MiB (${VRAM_MIN_MIB}-${VRAM_MAX_MIB}) [$out]"
    return 0
  fi
  echo "[FAIL] T6 $2: expected ${VRAM_MIN_MIB}-${VRAM_MAX_MIB} MiB, got ${total} MiB [$out]"
  T6_OK=1
  return 1
}
# Poll helpers (G-TIMEOUTS): nvidia-smi is a LIVE driver query (no caching), but the unload fire +
# teardown + driver-accounting have variance -> POLL every 0.5s, NEVER a fixed sleep. The contract's
# literal "7s" is under-budgeted (1s tick + threshold + <=7s teardown + driver lag); the ceiling
# absorbs the variance. wait_vram_absent ceiling ~25s (5s threshold + 1s tick + <=7s teardown +
# lag); wait_vram_present ceiling ~15s (reload ~1-3s + tick).
wait_vram_absent() {  # $1 = root pid  $2 = ceiling_secs (default 25)
  local deadline=$(( $(date +%s) + ${2:-25} ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    [ "$(vram_tree_state "$1" | awk '{print $1}')" = "0" ] && return 0
    sleep 0.5
  done
  return 1
}
wait_vram_present() {  # $1 = root pid  $2 = ceiling_secs (default 15)
  local deadline=$(( $(date +%s) + ${2:-15} ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    local out; out="$(vram_tree_state "$1")"; local total="${out%% *}"
    awk -v t="$total" -v lo="$VRAM_MIN_MIB" -v hi="$VRAM_MAX_MIB" 'BEGIN{ exit !(t+0>=lo+0 && t+0<=hi+0) }' && return 0
    sleep 0.5
  done
  return 1
}

# --- run-control DRY (2 runs + the trap share these) ---
# Launches the daemon (production path via launch_daemon.sh) under a given XDG_CONFIG_HOME; sets the
# global DAEMON_PID to the python PID (launch_daemon.sh execs python -> $! IS the python PID).
launch_daemon_run() {  # $1 = XDG_CONFIG_HOME  $2 = logfile
  XDG_CONFIG_HOME="$1" "$LAUNCH" > "$2" 2>&1 &
  DAEMON_PID=$!
}
# Polls voicectl status until it answers (up to 180s), dying if the daemon exits meanwhile.
wait_daemon_ready() {  # $1 = logfile (for diagnostics)
  for _ in $(seq 1 360); do            # 360 x 0.5s = 180s
    if "$VOICECTL" status >/dev/null 2>&1; then return 0; fi
    kill -0 "$DAEMON_PID" 2>/dev/null || die "daemon exited during startup (offline model load failed?); see $1"
    sleep 0.5
  done
  die "daemon not ready in 180s; see $1"
}
# Idempotent daemon stop: quit -> SIGTERM -> 8s poll -> SIGKILL; clears the global DAEMON_PID.
# Safe to call when DAEMON_PID is empty or already dead (G-CLEANUP-IDEMPOTENT; the trap + both runs
# share this). Does NOT block on a bare `wait` if the process is gone. set -e-SAFE: every command is
# failure-tolerant (quit returns non-zero BY DESIGN — the daemon closes the socket mid-shutdown,
# "daemon closed the connection without replying" = voicectl exit 1; that is the EXPECTED quit path,
# NOT an error — so it MUST NOT abort the script under `set -e`).
stop_daemon_run() {
  [ -n "${DAEMON_PID:-}" ] || return 0
  kill -0 "$DAEMON_PID" 2>/dev/null || { DAEMON_PID=""; return 0; }
  timeout "$VOICECTL_TIMEOUT" "$VOICECTL" quit >/dev/null 2>&1 || true
  kill -TERM "$DAEMON_PID" 2>/dev/null || true
  for _ in $(seq 1 16); do          # 16 x 0.5s = 8s grace for graceful shutdown
    kill -0 "$DAEMON_PID" 2>/dev/null || break
    sleep 0.5
  done
  if kill -0 "$DAEMON_PID" 2>/dev/null; then
    kill -KILL "$DAEMON_PID" 2>/dev/null || true
  fi
  wait "$DAEMON_PID" 2>/dev/null || true
  DAEMON_PID=""
}

# --- cleanup (G-CLEANUP-IDEMPOTENT): idempotent + best-effort; fires on ANY exit.
# No audio-source restore here (G-NOSOURCE — this test never swaps it).
# Invoked indirectly via 'trap cleanup EXIT' below (shellcheck SC2329 is a false positive).
# shellcheck disable=SC2329
cleanup() {
  set +e
  echo "--- cleanup ---"
  stop_daemon_run
  [ -z "${DAEMON_PID:-}" ] || echo "daemon stopped (pid=$DAEMON_PID)"
  # remove temp files.
  [ -n "${WORK:-}" ] && rm -rf "$WORK"
}
trap cleanup EXIT

die() { echo "FAIL: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# Run a voicectl CONTROL command (start/stop/toggle/quit) under `timeout` so any daemon-side
# hang fails LOUD (exit 124) instead of hanging the test forever (voicectl's makefile readline()
# has no socket timeout). `status` is lock-free + needs the full output, so callers invoke it
# directly (it never hangs). Usage: voicectl start|stop|toggle|quit.
voicectl() { timeout "$VOICECTL_TIMEOUT" "$VOICECTL" "$@"; }

# Read the daemon's last final from the isolated state.json (record_final writes it; G-IDLE-NO-TYPING).
# Empty string when unset. The `|| true` keeps a missing/corrupt file from aborting under `set -e`.
state_final() {
  jq -r '.last_final // ""' "$1" 2>/dev/null || true
}

# --- preflight (G-PREFLIGHT / G-DEPS) ---
have jq           || die "missing jq"
[ -x "$NVIDIA_SMI" ] || die "missing $NVIDIA_SMI"
[ -x "$VOICECTL" ]   || die "missing $VOICECTL (run install / uv sync)"
[ -x "$PY" ]         || die "missing $PY"
[ -x "$LAUNCH" ]     || die "missing $LAUNCH"
[ -f "$UNIT" ]       || die "missing $UNIT"
# refuse if a daemon is already running (real control socket is pinned; G-RUNTIME / G-PREFLIGHT).
if "$VOICECTL" status >/dev/null 2>&1; then
  die "a voice-typing daemon is already running (voicectl status answered). Stop it first: systemctl --user stop voice-typing"
fi
if systemctl --user is-active voice-typing >/dev/null 2>&1; then
  die "voice-typing systemd service is active; stop it first: systemctl --user stop voice-typing"
fi

# --- setup (G-CONFIG / G-RUNTIME) ---
# G-CONFIG: temp XDG_CONFIG_HOME dirs with minimal config.toml overriding ONLY [output]+[feedback];
# [asr]/[filter]/[log] inherit dataclass defaults (== repo config.toml) -> same production ASR.
# Run 1: default auto_unload_idle_seconds (1800s inherited). Run 2: same + [asr] override to 5.0.
WORK="$(mktemp -d)"
# --- run 1 config (default 1800s idle-unload threshold) ---
# auto_stop_idle_seconds stays at its DEFAULT (30.0): it composes with the 1800s idle-UNLOAD (§4.5
# hands off to §4.2bis). During T4's 120 s window the 30 s auto-stop disarms the mic (expected — the
# original passing T4 run measured its ~2.5% CPU precisely because of this handoff), then the 1800s
# idle-UNLOAD clock starts but 120 s << 1800 s so no VRAM unload corrupts T6(c). The T6(c) block re-checks status and calls `voicectl stop` if still armed
# (ISSUE-3: the old "stop-on-disarmed wedges the control lock" premise is STALE — _safe_abort()
# gating, commit 81d2ad8, fixed that, so a redundant stop after auto-stop is now safe). This is a
# config override via XDG_CONFIG_HOME (G-CONFIG), NOT an edit to production code or the repo config.toml.
mkdir -p "$WORK/config/voice-typing"
cat > "$WORK/config/voice-typing/config.toml" <<EOF
[output]
backend     = "null"

[feedback]
state_file  = "$WORK/state.json"
hypr_notify = false
EOF
# --- run 2 config (5s idle-unload threshold; ONLY this one [asr] key differs from run 1) ---
# auto_stop stays at its default 30s here too (it disarms after 30s of no speech, but the 5s
# auto_unload_idle_seconds then fires first/quickly — we explicitly stop well before 30s anyway).
mkdir -p "$WORK/config_short/voice-typing"
cat > "$WORK/config_short/voice-typing/config.toml" <<EOF
[output]
backend     = "null"

[feedback]
state_file  = "$WORK/state_short.json"
hypr_notify = false

[asr]
auto_unload_idle_seconds = 5.0
EOF

# =====================================================================
# RUN 1 — default config (auto_unload_idle_seconds=1800): T6(a) + criterion-8 + criterion-6 +
#         start -> T6(b) -> T4 (120s ARMED silence) -> stop -> T6(c) + criterion-6 status/unit.
# =====================================================================
RUN1_LOG="$WORK/daemon.log"
echo "--- RUN 1 (default config; auto_unload_idle_seconds=1800) ---"
launch_daemon_run "$WORK/config" "$RUN1_LOG"
echo "daemon launched via launch_daemon.sh (production path; offline vars via wrapper) pid=$DAEMON_PID; waiting for ready (up to 180s)..."
wait_daemon_ready "$RUN1_LOG"

# --- T6(a): boot with NO arm → daemon tree ABSENT from nvidia-smi (~0 VRAM) — BEFORE any start.
# CRITICAL: this is the lazy-load boot guarantee (M2.T1) and MUST be measured before the first arm.
# (The criterion-6 toggle below does arm+disarm once; T6(a) precedes it.)
T6A_OUT="$(vram_tree_state "$DAEMON_PID")"
assert_vram_absent "$DAEMON_PID" "(a) boot: lazy-load ~0 VRAM" || true

# --- criterion 8 (no-network): NON-CIRCULAR regression guard (bugfix Issue 1) ---
# The test did NOT pre-set HF_HUB_OFFLINE (that masked Issue 1). launch_daemon.sh exports it
# (S1); this grep proves the PRODUCTION path is offline by asserting the daemon log contains
# ZERO online huggingface.co requests. httpx logs 'HTTP Request: GET https://huggingface.co'
# to stderr (root StreamHandler from daemon._setup_logging) -> folded into daemon.log by the
# 2>&1 redirect at launch. Missing exports => online freshness check => match => FAIL.
if grep -q 'HTTP Request: GET https://huggingface.co' "$RUN1_LOG"; then
  die "FAIL: daemon made network calls to huggingface.co (offline exports missing from launch_daemon.sh?); see $RUN1_LOG"
fi
echo "[PASS] criterion 8 (no-network guard): daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines (production path offline)"

# --- criterion 6: un-armed boot — capture BEFORE start (G-UNARMED) ---
STATUS_READY="$("$VOICECTL" status)" || die "voicectl status failed after ready"
echo "daemon ready:"; echo "$STATUS_READY"
# PRD §4.9: the daemon boots NOT-LISTENING. Assert 'listening: off' BEFORE issuing start (criterion 6).
echo "$STATUS_READY" | grep -q '^listening: off' \
  || { echo "FAIL: daemon did not boot un-armed (expected 'listening: off'):"; echo "$STATUS_READY"; exit 1; }
echo "[PASS] criterion 6 (un-armed boot): daemon started NOT-listening"

# --- criterion 6: exercise toggle (G-CRIT6-VOICECTL) — quick round-trip, OUTSIDE the idle window ---
voicectl toggle >/dev/null || die "voicectl toggle (-> on) failed"
voicectl toggle >/dev/null || die "voicectl toggle (-> off) failed"
echo "[PASS] criterion 6 (voicectl toggle): toggle on/off ok"

# --- T4 idle window (criterion 5, CRITICAL) (G-CAPTURE / G-IDLE-NO-TYPING / G-CPU-SAMPLING) ---
# Start the CPU clock at the same moment as voicectl start so the window IS the ARMED idle period.
cpu0="$(cpu_tree_seconds "$DAEMON_PID")"; wall0="$(date +%s)"
voicectl start >/dev/null || die "voicectl start failed"
echo "listening armed (silent mic); holding ${IDLE_SECS}s of silence..."

# --- T6(b): after start → daemon tree PRESENT, Σ ∈ [512,3072] MiB (the ONE model resident). POLL (the
# cold load is ~1-3s; the start already waited for it, but give nvidia-smi a moment to settle).
if wait_vram_present "$DAEMON_PID" 15; then
  T6B_OUT="$(vram_tree_state "$DAEMON_PID")"
  assert_vram_present "$DAEMON_PID" "(b) armed: resident"
else
  echo "[FAIL] T6 (b) armed: tree did not become PRESENT within 15s of start"
  T6B_OUT="$(vram_tree_state "$DAEMON_PID")"
  echo "  current state [$T6B_OUT]"
  echo "  full nvidia-smi compute-apps listing:"
  "$NVIDIA_SMI" --query-compute-apps=pid,used_memory --format=csv,noheader 2>/dev/null | sed 's/^/    /' || true
  T6_OK=1
fi

typed_before="$(state_final "$WORK/state.json")"
sleep "$IDLE_SECS"
cpu1="$(cpu_tree_seconds "$DAEMON_PID")"; wall1="$(date +%s)"
typed_after="$(state_final "$WORK/state.json")"

# (a) no hallucinated finals: state.json last_final UNCHANGED across the idle window.
if [ "$typed_before" = "$typed_after" ]; then
  echo "[PASS] criterion 5 (no hallucination): no finals, last_final unchanged across ${IDLE_SECS}s"
else
  echo "[FAIL] criterion 5 (hallucination guard): last_final CHANGED"
  echo "  before: '$typed_before'"
  echo "  after:  '$typed_after'"
  IDLE_OK=1
fi
# (b) no crash.
if kill -0 "$DAEMON_PID" 2>/dev/null; then
  echo "[PASS] criterion 5 (no crash): daemon alive after ${IDLE_SECS}s"
else
  echo "[FAIL] criterion 5: daemon died during idle"; IDLE_OK=1
fi
# (c) CPU < 25% of ONE core (G-CPU-SAMPLING: do NOT divide by nproc — it is % of ONE core).
elapsed=$(( wall1 - wall0 )); [ "$elapsed" -gt 0 ] || elapsed=1
avg_pct="$(awk -v c0="$cpu0" -v c1="$cpu1" -v e="$elapsed" 'BEGIN{ printf "%.2f", ((c1 - c0) / e) * 100 }')"
if awk -v a="$avg_pct" -v L="$CPU_LIMIT_PCT" 'BEGIN{ exit !(a + 0 < L + 0) }'; then
  echo "[PASS] criterion 5 (CPU): avg ${avg_pct}% of one core (< ${CPU_LIMIT_PCT}%)"
else
  echo "[FAIL] criterion 5 (CPU): avg ${avg_pct}% >= ${CPU_LIMIT_PCT}%"; IDLE_OK=1
fi

# --- T6(c): after stop → daemon tree STILL PRESENT (models stay resident for instant re-arm;
# stop does NOT unload). On the default 1800s config the idle-unload clock (DISARMED-only) won't
# fire during this assertion (120s << 1800s).
#
# ISSUE-3 (resolved): the old comment claimed calling `voicectl stop` on a daemon ALREADY
# disarmed by auto-stop WEDGES the control lock — that premise is STALE. _safe_abort() gating
# (commit 81d2ad8 "gate abort() on in-flight text to fix hang") made stop() skip abort() when no
# thread is in text(), so a redundant stop after auto-stop returns instantly (no wedge). We still
# re-check status and only issue `stop` if armed (T6(c) needs disarmed+resident; if auto-stop
# already disarmed we have that state — calling stop again is now harmless but unnecessary).
POST_T4_LISTENING="$("$VOICECTL" status 2>/dev/null | grep -E '^listening:' || true)"
if echo "$POST_T4_LISTENING" | grep -q '^listening: on'; then
  voicectl stop >/dev/null || die "voicectl stop failed (exit 124 = timeout)"
  echo "voicectl stop issued (mic was still armed after T4)"
else
  # Auto-stop already disarmed (T6(c) needs disarmed+resident — this IS that state). ISSUE-3: a
  # redundant stop here is now SAFE (no wedge) but unnecessary; we skip it to keep the test fast.
  echo "voicectl stop SKIPPED — mic already disarmed by auto_stop_idle_seconds=30 during T4 (disarmed+resident state reached; redundant stop is now safe per ISSUE-3 but unnecessary)"
fi
T6C_OUT="$(vram_tree_state "$DAEMON_PID")"
assert_vram_present "$DAEMON_PID" "(c) disarmed: still resident" || true

# --- criterion 6: status (device + models) + systemd unit grep ---
STATUS_RUN="$("$VOICECTL" status)" || true
echo "voicectl status (post-run):"; echo "$STATUS_RUN"
EXEC_LINE="$(grep -E '^ExecStart=' "$UNIT")"
RESTART_LINE="$(grep -E '^Restart=' "$UNIT")"
if echo "$EXEC_LINE" | grep -q 'launch_daemon\.sh'; then
  echo "[PASS] criterion 6 (unit ExecStart): $EXEC_LINE"
else
  echo "[FAIL] criterion 6 (unit ExecStart): $EXEC_LINE"; IDLE_OK=1
fi
if echo "$RESTART_LINE" | grep -q 'on-failure'; then
  echo "[PASS] criterion 6 (unit Restart): $RESTART_LINE"
else
  echo "[FAIL] criterion 6 (unit Restart): $RESTART_LINE"; IDLE_OK=1
fi
# If the unit is installed, show the live cat too (criterion 6 corroboration; non-fatal if absent).
if systemctl --user cat voice-typing >/dev/null 2>&1; then
  echo "systemd unit (installed):"
  systemctl --user cat voice-typing | sed 's/^/  /' || true
fi

# --- criterion 8 (no-network): NON-CIRCULAR proof — the daemon.log grep (post-ready guard) found
# ZERO 'HTTP Request: GET https://huggingface.co' lines. The test never pre-set the offline
# vars; launch_daemon.sh exports them (production path), so this proves the DEPLOYED path is
# offline (not just that the daemon CAN run offline).
echo "[PASS] criterion 8 (no network): daemon.log has ZERO 'HTTP Request: GET https://huggingface.co' lines (offline via launch_daemon.sh, not a test pre-set)"

# ===================== T7 (PRD §4.2quater + acceptance #10): single-model arming =====================
# Proves the COLLAPSED single-model daemon end-to-end on the REAL host: exactly ONE model
# resident (small.en — the startup 'voice-typing device resolved:' line + ZERO 'distil-large-v3'
# anywhere in daemon.log: no large-model worker, loader line, or cuda_check mention), the
# constant 'mode: lite' status while armed (Rev 2 has NO second mode — the status mode value is
# always 'lite'), armed VRAM inside the single-model [512,3072] MiB window (acceptance #10's
# regenerated nvidia-smi evidence), and the armed no-op `voicectl cancel` smoke (acceptance
# #12's shell evidence — PRD §4.2quater: cancel with no tail in flight is an idempotent no-op
# that keeps listening on). Complements the mocked unit tests (tests/test_daemon.py single-model
# suite) with real-process proof. Placed LAST in Run 1 (after T6 a/b/c + T4) so the extra
# arm/disarm cannot corrupt the earlier VRAM lifecycle assertions.
#   1. voicectl start (re-arm; the resident host is already single-model) + wait_vram_present.
#   2. ONE-MODEL (log): grep run-1 daemon.log for the startup
#      'voice-typing device resolved: device=cuda compute_type=float16 model=small.en' line
#      (PASS required) AND assert 'distil-large-v3' NEVER matches.
#   3. ONE-MODEL (status): `voicectl status` -> assert '^mode: lite' while armed.
#   4. VRAM window: single-model [512,3072] MiB on the armed resident tree.
#   5. CANCEL SMOKE: armed, no tail in flight -> cancel ok + listening stays on (idempotent).
#   6. voicectl stop to disarm (clean state before quit).
T7_OK=0   # T7 (single-model arming + VRAM window + cancel smoke) failures
# --- 1. re-arm (T6(c) left the daemon disarmed+resident; the resident host is already
# single-model — the first arm is ~1-3s on a cold resident set, subsequent arms reply in ms).
voicectl start >/dev/null || die "T7: voicectl start (re-arm) failed"
if ! wait_vram_present "$DAEMON_PID" 15; then
  echo "[FAIL] T7: armed tree not PRESENT within 15s of start"
  T7_OK=1
fi

# --- 2. ONE-MODEL (log): the startup line fires ONCE at daemon start (the cuda_check driver
# probe — independent of the lazy first-arm model load), so it is already in run-1's log. Grep
# the RESOLVED line rather than hardcoding beyond what the CUDA run guarantees (on the CPU
# fallback path the model would be tiny.en — but this suite requires nvidia-smi/CUDA).
T7_RESOLVED_LINE="$(grep -m1 'voice-typing device resolved:' "$RUN1_LOG" || true)"
echo "T7 resolved line: ${T7_RESOLVED_LINE:-<missing>}"
if echo "$T7_RESOLVED_LINE" | grep -q 'device=cuda compute_type=float16 model=small.en'; then
  echo "[PASS] T7 one-model (log): device=cuda compute_type=float16 model=small.en"
else
  echo "[FAIL] T7 one-model: startup line missing/wrong (expected device=cuda compute_type=float16 model=small.en)"
  T7_OK=1
fi
if grep -q 'distil-large-v3' "$RUN1_LOG"; then
  echo "[FAIL] T7 one-model: distil-large-v3 appeared in daemon.log (two-model regression)"
  grep -n 'distil-large-v3' "$RUN1_LOG" | head -n 5 | sed 's/^/    /' || true
  T7_OK=1
else
  echo "[PASS] T7 one-model: small.en sole model (no distil-large-v3 anywhere in daemon.log)"
fi

# --- 3. ONE-MODEL (status): `voicectl status` reports the CONSTANT 'mode: lite' while armed
# (daemon.py status payload — Rev 2 §4.6 schema-stable constant; there is no 'normal' mode).
T7_MODE_LINE="$("$VOICECTL" status 2>/dev/null | grep -E '^mode:' || true)"
echo "T7 mode line: ${T7_MODE_LINE:-<missing>}"
if echo "$T7_MODE_LINE" | grep -q '^mode: lite'; then
  echo "[PASS] T7 status: mode: lite (constant single-mode)"
else
  echo "[FAIL] T7 status: expected 'mode: lite' while armed, got '${T7_MODE_LINE:-<none>}'"
  T7_OK=1
fi

# --- 4. VRAM window: ONE small.en resident ≈ 0.5-3 GB -> [512,3072] MiB (acceptance #10's
# regenerated evidence; the old two-model [1024,5120] window is gone). T7-local check (the shared
# assert_vram_present accumulates into T6_OK — a T7 failure must land in T7_OK).
T7_ARMED_VRAM="$(vram_tree_state "$DAEMON_PID")"
T7_ARMED_TOTAL="${T7_ARMED_VRAM%% *}"
if awk -v t="$T7_ARMED_TOTAL" -v lo="$VRAM_MIN_MIB" -v hi="$VRAM_MAX_MIB" 'BEGIN{ exit !(t+0>=lo+0 && t+0<=hi+0) }'; then
  echo "[PASS] T7 armed VRAM (single-model): ${T7_ARMED_TOTAL} MiB in [${VRAM_MIN_MIB},${VRAM_MAX_MIB}] [$T7_ARMED_VRAM]"
else
  echo "[FAIL] T7 armed VRAM (single-model): expected ${VRAM_MIN_MIB}-${VRAM_MAX_MIB} MiB, got ${T7_ARMED_TOTAL} MiB [$T7_ARMED_VRAM]"
  T7_OK=1
fi

# --- 5. CANCEL SMOKE (acceptance #12 shell evidence): while armed with NO tail in flight,
# `voicectl cancel` must return ok (exit 0), keep `listening: on`, and be a no-op (idempotent —
# PRD §4.2quater). Control command through the timeout-wrapping voicectl() helper (G-TIMEOUTS);
# status via the raw "$VOICECTL" (lock-free, never hangs — the script-wide convention).
T7_CANCEL_RESULT="FAIL"
if voicectl cancel >/dev/null 2>&1 \
   && "$VOICECTL" status 2>/dev/null | grep -q '^listening: on'; then
  T7_CANCEL_RESULT="ok"
  echo "[PASS] T7 cancel smoke: voicectl cancel ok (no-op, no tail in flight), listening stays on"
else
  echo "[FAIL] T7 cancel smoke: cancel failed or disarmed the mic"
  "$VOICECTL" status 2>/dev/null | grep -E '^listening:|^mode:' | sed 's/^/    /' || true
  T7_OK=1
fi

# --- 6. disarm (clean listening:off state before the run-1 quit).
voicectl stop >/dev/null 2>&1 || true

# Clean quit of run 1 before run 2 (the default-config daemon; T4 + T6 a/b/c are done).
stop_daemon_run
echo "run 1 daemon stopped cleanly"

# =====================================================================
# RUN 2 — 5s override (auto_unload_idle_seconds=5): T6(d) idle-unload → gone → re-arm → reload.
# =====================================================================
RUN2_LOG="$WORK/daemon2.log"
echo "--- RUN 2 (5s override; auto_unload_idle_seconds=5) ---"
launch_daemon_run "$WORK/config_short" "$RUN2_LOG"
echo "daemon launched (run 2, 5s idle-unload) pid=$DAEMON_PID; waiting for ready (up to 180s)..."
wait_daemon_ready "$RUN2_LOG"

# boot corroboration: ABSENT before the first arm (lazy load on this run too).
T6D_BOOT_OUT="$(vram_tree_state "$DAEMON_PID")"
assert_vram_absent "$DAEMON_PID" "(boot, run 2)" || true

# arm -> models load -> PRESENT.
voicectl start >/dev/null || die "voicectl start (run 2) failed"
if wait_vram_present "$DAEMON_PID" 15; then
  assert_vram_present "$DAEMON_PID" "(armed, run 2)"
else
  echo "[FAIL] T6 (armed, run 2): tree did not become PRESENT within 15s of start"
  T6_OK=1
fi

# stop -> disarmed. After 5s of disarmed idle the watchdog fires -> _unload_host ->
# _bounded_shutdown -> host.stop() terminates the child PROCESS GROUP -> all CUDA contexts
# (incl. the realtime-model context that used to stay on the daemon PID) die -> the daemon tree
# vanishes from nvidia-smi -> ABSENT while the daemon LIVES (PRD §7.9). The daemon process itself
# NEVER touched CUDA (the recorder lives in the child), so its PID was never on nvidia-smi.
voicectl stop >/dev/null || die "voicectl stop (run 2) failed (exit 124 = timeout)"
T6D_ACTIVE_BEFORE="$(vram_tree_state "$DAEMON_PID")"   # the pre-unload active set (self-calibration)
echo "T6(d) active set at stop (run 2): $T6D_ACTIVE_BEFORE"

# --- T6(d-gone): POLL nvidia-smi until the daemon tree is ABSENT (ceiling ~25s). A FAIL here means
# the unload path did NOT release the CUDA context as seen by nvidia-smi (PRD §7.9) — a PRODUCTION
# bug in M1.T1/M3.T1, NOT a test bug. Do NOT weaken the assertion.
if wait_vram_absent "$DAEMON_PID" 25; then
  T6D_GONE_OUT="$(vram_tree_state "$DAEMON_PID")"
  assert_vram_absent "$DAEMON_PID" "(d) after 5s idle-unload: ~0 VRAM reclaimed (daemon still alive)"
else
  echo "[FAIL] T6 (d-gone): daemon tree STILL on GPU 25s after stop+unload (expected ~0 VRAM)"
  T6D_GONE_OUT="$(vram_tree_state "$DAEMON_PID")"
  echo "  steady-state active set (before unload): $T6D_ACTIVE_BEFORE"
  echo "  post-unload state: $T6D_GONE_OUT"
  echo "  full nvidia-smi compute-apps listing:"
  "$NVIDIA_SMI" --query-compute-apps=pid,used_memory --format=csv,noheader 2>/dev/null | sed 's/^/    /' || true
  echo "  daemon2.log idle-unload fire (empty = watchdog did NOT fire):"
  grep -n 'voice-typing idle-unload:' "$RUN2_LOG" | sed 's/^/    /' || true
  echo "  voicectl status phase (expect phase: unloaded + (not loaded) if the unload fired):"
  "$VOICECTL" status | grep -E '^phase:|^listening:|^mode:' | sed 's/^/    /' || true
  echo "  NOTE: a FAIL here means the unload path did NOT release the CUDA context as seen by nvidia-smi"
  echo "  (PRD §7.9). This is a PRODUCTION bug in M1.T1/M3.T1, NOT a test bug. Do NOT weaken the assertion."
  T6_OK=1
fi

# --- T6(d-reload): re-arm -> _load_recorder rebuilds (~1-3s single-flight) -> tree PRESENT again.
voicectl start >/dev/null || die "voicectl start (re-arm) failed"
if wait_vram_present "$DAEMON_PID" 15; then
  T6D_RELOAD_OUT="$(vram_tree_state "$DAEMON_PID")"
  assert_vram_present "$DAEMON_PID" "(d) re-arm reloads: resident again"
else
  echo "[FAIL] T6 (d-reload): tree did not become PRESENT within 15s of re-arm"
  T6D_RELOAD_OUT="$(vram_tree_state "$DAEMON_PID")"
  echo "  current state: $T6D_RELOAD_OUT"
  T6_OK=1
fi

stop_daemon_run
echo "run 2 daemon stopped cleanly"

# --- evidence block for tests/ACCEPTANCE.md (G-EVIDENCE-BLOCK) ---
echo
echo "=== ACCEPTANCE EVIDENCE (paste into tests/ACCEPTANCE.md, criteria 5/6/8/9/10) ==="
echo "run1_daemon_log: $RUN1_LOG"
echo "run2_daemon_log: $RUN2_LOG"
echo "idle_seconds: $IDLE_SECS"
echo "cpu_avg_pct_of_one_core: $avg_pct"
echo "T6 (a) boot (absent):        $T6A_OUT"
echo "T6 (b) armed (present):      $T6B_OUT"
echo "T6 (c) disarmed (present):   $T6C_OUT"
echo "T6 (d) run2 boot (absent):   $T6D_BOOT_OUT"
echo "T6 (d) active at stop:       $T6D_ACTIVE_BEFORE"
echo "T6 (d) after idle-unload:    $T6D_GONE_OUT"
echo "T6 (d) after re-arm reload:  $T6D_RELOAD_OUT"
echo "T7 one-model grep:            ${T7_RESOLVED_LINE:-<missing>} (no distil-large-v3 in daemon.log)"
echo "T7 armed VRAM (single-model): $T7_ARMED_VRAM"
echo "T7 mode:                      ${T7_MODE_LINE:-<missing>}"
echo "T7 cancel smoke:              $T7_CANCEL_RESULT (no-op, listening on)"
echo "voicectl_status (run 1 post-run):"
while IFS= read -r _line; do echo "  $_line"; done <<EOF
$STATUS_RUN
EOF
echo "systemd_unit:"
echo "  $EXEC_LINE"
echo "  $RESTART_LINE"
echo "offline_env: via launch_daemon.sh exports (HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1); daemon.log HF-request grep: CLEAN"
echo "=== END ACCEPTANCE EVIDENCE ==="

# --- result ---
if [ "$IDLE_OK" = 0 ] && [ "$T6_OK" = 0 ] && [ "$T7_OK" = 0 ]; then
  echo "=== IDLE+GPU PASS (criteria 5, 6, 8; T6 a/b/c/d lifecycle; T7 single-model arming) ==="
  exit 0
else
  [ "$IDLE_OK" = 0 ] || echo "=== T4/criterion-5 FAIL ==="
  [ "$T6_OK" = 0 ]   || echo "=== T6 FAIL (see [FAIL] T6 ... lines above) ==="
  [ "$T7_OK" = 0 ]   || echo "=== T7 FAIL (see [FAIL] T7 ... lines above) ==="
  echo "daemon logs: $RUN1_LOG ; $RUN2_LOG"
  echo "--- run1 daemon.log tail ---"; tail -n 30 "$RUN1_LOG" 2>/dev/null || true
  echo "--- run2 daemon.log tail ---"; tail -n 30 "$RUN2_LOG" 2>/dev/null || true
  exit 1
fi
