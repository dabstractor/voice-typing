#!/usr/bin/env bash
# tests/test_idle_and_gpu.sh — idle stability (PRD §6 T4) + GPU residency (T6) + offline (criterion 8).
#
# Stands up the REAL daemon via the PRODUCTION path (launch_daemon.sh — no pre-set env, so the
# test exercises the real systemd -> wrapper flow). launch_daemon.sh exports HF_HUB_OFFLINE=1 +
# TRANSFORMERS_OFFLINE=1 (bugfix Issue 1 fix); this test asserts ZERO 'HTTP Request: GET
# https://huggingface.co' lines in the daemon log as the criterion-8 proof (no circular pre-set).
# arms it with `voicectl start`, holds 120 s of silence on the REAL default mic (no null-sink — it
# listens to ambient room silence), and asserts the three T4 properties:
#   (a) NO hallucinated finals typed — the P1.M2.T2.S1 blocklist + VAD gating suppress Whisper's
#       silence-hallucination ("thank you." / "thanks for watching." / "you." / "bye."). Detected
#       via the tmux backend UNCHANGED (capture-pane reads the tty echo; G-CAPTURE) AND the ISOLATED
#       state.json `last_final` UNCHANGED from its initial "".
#   (b) NO crash — `kill -0 $DAEMON_PID` after the 120 s window.
#   (c) avg CPU < 25 % of ONE core — /proc/<pid>/stat utime+stime (fields 14/15 via the last-`)`
#       split) summed over the daemon's PROCESS TREE at T0/T1, divided by elapsed wall-seconds.
#       pidstat/sysstat is NOT installed, so /proc is the zero-dep path (G-CPU-SAMPLING).
#
# Then runs T6: `nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader` (comma-safe
# 2-column query — process_name can contain commas; G-VRAM-COMMAS), matches the daemon's descendant
# tree against the compute-app rows (G-VRAM-ATTRIBUTION; G-OTHER-APPS — the GPU hosts unrelated
# apps like Chrome / a parallel test daemon, so we filter strictly by the tree), and asserts ≥1
# matched row with Σ used_memory ∈ [1024, 5120] MiB (PRD §6 T6 "~1 and ~5 GB").
#
# Also exercises voicectl toggle/start/stop/status/quit (each must return ok) + greps the systemd
# unit for ExecStart → launch_daemon.sh + Restart=on-failure, and asserts the daemon BOOTS UN-ARMED
# (voicectl status → `listening: off` right after ready — PRD §4.9; criterion 6).
#
# Prints a fenced `=== ACCEPTANCE EVIDENCE ===` block (real CPU %, real nvidia-smi rows + total,
# voicectl status, unit grep, per-criterion PASS/FAIL) — paste it verbatim into
# tests/ACCEPTANCE.md (criteria 5/6/8). On FAIL it prints the daemon.log tail.
#
# Real stack: CUDA Whisper + tmux. Heavy (~3-4 min: cuDNN/cuBLAS cold init + 2 model loads + the
# fixed 120 s idle window). Run explicitly; NOT collected by the fast pytest suite.
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
# CLEANUP: a trap guarantees the daemon is gone, the `vtidle` tmux session is gone, and temp dirs
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
#                        child process; on Linux RealtimeSTT workers are threads, so the daemon PID
#                        stat already aggregates them — the tree sum is correct either way).
#   G-VRAM-ATTRIBUTION:  match the daemon's descendant TREE against nvidia-smi compute-app PIDs;
#                        NEVER assert on an arbitrary row.
#   G-VRAM-COMMAS:       query ONLY pid,used_memory (process_name can contain commas → breaks CSV).
#   G-OTHER-APPS:        the GPU hosts unrelated compute apps (Chrome, a parallel test daemon) →
#                        filter strictly by the daemon tree.
#   G-UNARMED:           assert `listening: off` right after ready, BEFORE voicectl start.
#   G-CAPTURE / G-IDLE-NO-TYPING: read typed text via `tmux capture-pane -p -S -` (the daemon types
#                        literal keys with NO newline → pty canonical-mode buffers `cat > file`);
#                        snapshot capture-pane + state.json last_final before/after the 120 s window.
#   G-RUNTIME:           keep the REAL XDG_RUNTIME_DIR (PyAudio + the control socket need it; moving
#                        it to a temp dir breaks PulseAudio → ALSA fallback → silence). Isolate
#                        state.json via the config override.
#   G-CONFIG:            override via XDG_CONFIG_HOME=<tmp>/config (minimal [output]+[feedback]); do
#                        NOT edit the repo config.toml. [asr]/[filter]/[log] inherit dataclass
#                        defaults (== repo config.toml) → same production ASR pipeline.
#   G-PREFLIGHT:         refuse if voicectl status answers / systemctl --user is-active voice-typing.
#   G-TMUX-NAME:         distinct session name `vtidle` (NOT T3's `voicetest`) so the two heavy
#                        parallel tests never collide. ALWAYS /usr/bin/tmux (zsh aliases it).
#   G-NOSOURCE:          do NOT swap the default audio source — simpler trap (no source restore).
#   G-TIMEOUTS:          180 s daemon-ready (cold init + 2 model loads, OFFLINE); the idle window is
#                        FIXED at exactly 120 s (PRD §6 T4 — do not shorten).
#   G-CLEANUP-IDEMPOTENT: every trap step wrapped in `|| true` / `2>/dev/null`; trap fires on EXIT.
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
TMUX_BIN=/usr/bin/tmux
NVIDIA_SMI=/usr/bin/nvidia-smi
TMUX_SESS=vtidle
# Bare session name (NOT 'vtidle:0.0'): this machine's tmux has window base-index=1, so the first
# window is 'vtidle:1.0', not ':0.0'. A bare session name targets the session's active pane
# regardless of base-index (verified for send-keys/capture-pane/kill-session), which is what the
# daemon's TmuxBackend needs (it passes cfg.output.tmux_target straight to 'send-keys -t'). Same
# convention as e2e_virtual_mic.sh.
TMUX_TARGET="vtidle"
IDLE_SECS=120                     # PRD §6 T4: 'silence for 120 s' (FIXED — do not shorten)
CPU_LIMIT_PCT=25                  # < 25% of ONE core (PRD §6 T4; do NOT divide by nproc)
VRAM_MIN_MIB=1024                 # PRD §6 T6: '~1 GB'
VRAM_MAX_MIB=5120                 # PRD §6 T6: '~5 GB'

# If this script runs INSIDE an existing tmux session, the inherited TMUX/TMUX_PANE env vars make
# 'tmux new-session' misbehave ('error connecting to /usr/bin/tmux' / 'Permission denied'). Unset
# them so every tmux call below (and the daemon's send-keys, which inherits this env) talks to the
# default server cleanly. The tmux binary PATH is held in TMUX_BIN — NOT the TMUX env var — so
# unsetting the env var does not clobber the path. (Same fix as e2e_virtual_mic.sh.)
unset TMUX TMUX_PANE TMUX_TMPDIR

# --- state (populated by setup; used by the trap) ---
WORK=""
DAEMON_PID=""

# --- cleanup (G-CLEANUP-IDEMPOTENT): idempotent + best-effort; fires on ANY exit.
# No audio-source restore here (G-NOSOURCE — this test never swaps it).
# Invoked indirectly via 'trap cleanup EXIT' below (shellcheck SC2329 is a false positive).
# shellcheck disable=SC2329
cleanup() {
  set +e
  echo "--- cleanup ---"
  # 1. daemon: ask quit (bounded), then SIGTERM the PID, poll up to 8s, then SIGKILL. Do NOT block
  #    on a bare `wait` — the daemon can be mid-shutdown releasing GPU VRAM and stall.
  if [ -n "${DAEMON_PID:-}" ] && kill -0 "$DAEMON_PID" 2>/dev/null; then
    timeout 5 "$VOICECTL" quit >/dev/null 2>&1
    kill -TERM "$DAEMON_PID" 2>/dev/null
    for _ in $(seq 1 16); do          # 16 x 0.5s = 8s grace for graceful shutdown
      kill -0 "$DAEMON_PID" 2>/dev/null || break
      sleep 0.5
    done
    if kill -0 "$DAEMON_PID" 2>/dev/null; then
      kill -KILL "$DAEMON_PID" 2>/dev/null
      wait "$DAEMON_PID" 2>/dev/null
    else
      wait "$DAEMON_PID" 2>/dev/null
    fi
    echo "daemon stopped (pid=$DAEMON_PID)"
  fi
  # 2. kill the tmux session.
  "$TMUX_BIN" kill-session -t "$TMUX_SESS" 2>/dev/null && echo "killed tmux session $TMUX_SESS"
  # 3. remove temp files.
  [ -n "${WORK:-}" ] && rm -rf "$WORK"
}
trap cleanup EXIT

die() { echo "FAIL: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# Read typed text from the tmux pane via capture-pane (reads the tty ECHO, live; G-CAPTURE).
# Drop blank lines + join wrapped lines into one space-separated string (same filter as T3).
# The `|| true` makes an EMPTY pane yield "" instead of aborting under `set -e` (grep exits 1 when
# every captured line is blank — the normal state before any text is typed).
capture_pane() {
  "$TMUX_BIN" capture-pane -t "$TMUX_SESS" -p -S - \
    | grep -v '^[[:space:]]*$' \
    | paste -sd ' ' \
    || true
}

# --- preflight (G-PREFLIGHT / G-DEPS) ---
have jq           || die "missing jq"
[ -x "$NVIDIA_SMI" ] || die "missing $NVIDIA_SMI"
[ -x "$TMUX_BIN" ]   || die "missing $TMUX_BIN"
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

# --- setup (G-CONFIG / G-RUNTIME / G-TMUX-NAME) ---
# G-CONFIG: temp XDG_CONFIG_HOME with a minimal config.toml overriding ONLY [output]+[feedback];
# [asr]/[filter]/[log] inherit dataclass defaults (== repo config.toml) -> same production ASR.
WORK="$(mktemp -d)"
mkdir -p "$WORK/config/voice-typing"
cat > "$WORK/config/voice-typing/config.toml" <<EOF
[output]
backend     = "tmux"
tmux_target = "$TMUX_TARGET"

[feedback]
state_file  = "$WORK/state.json"
hypr_notify = false
EOF
CAPFILE="$WORK/vt_out.txt"
rm -f "$CAPFILE"
# The pane runs 'cat > file' (honoring the contract). capture-pane reads the tty echo mid-stream
# (G-CAPTURE); the file is only an end-of-run cross-check after a C-d flush.
"$TMUX_BIN" new-session -d -s "$TMUX_SESS" "cat > '$CAPFILE'" || die "tmux new-session failed"
# Make the pane wide so typed text does not wrap.
"$TMUX_BIN" resize-window -t "$TMUX_SESS" -x 1000 2>/dev/null || true

# --- launch daemon OFFLINE (G-OFFLINE / G-RUNTIME / G-CONFIG) ---
# Real XDG_RUNTIME_DIR (PyAudio + the control socket need it; G-RUNTIME). Temp XDG_CONFIG_HOME
# (the override; G-CONFIG). HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 -> criterion 8 proof: if the
# daemon STARTS, goes ready, and survives 120 s armed idle, that is empirical proof the models
# load from cache with ZERO network. Do NOT also set HF_DATASETS_OFFLINE etc. — HF_HUB_OFFLINE
# covers faster-whisper's resolution. launch_daemon.sh execs python -> $! IS the python PID.
# offline vars come from launch_daemon.sh (bugfix Issue 1 fix) — do NOT pre-set here (that
# masked Issue 1; the post-ready grep guard below is the non-circular criterion-8 proof).
XDG_CONFIG_HOME="$WORK/config" "$LAUNCH" > "$WORK/daemon.log" 2>&1 &
DAEMON_PID=$!
echo "daemon launched via launch_daemon.sh (production path; offline vars via wrapper) pid=$DAEMON_PID; waiting for ready (up to 180s)..."

# --- wait for ready (G-TIMEOUTS) ---
ready=0
for _ in $(seq 1 360); do            # 360 x 0.5s = 180s
  if "$VOICECTL" status >/dev/null 2>&1; then ready=1; break; fi
  kill -0 "$DAEMON_PID" 2>/dev/null || die "daemon exited during startup (offline model load failed?); see $WORK/daemon.log"
  sleep 0.5
done
[ "$ready" = 1 ] || die "daemon not ready in 180s; see $WORK/daemon.log"

# --- criterion 8 (no-network): NON-CIRCULAR regression guard (bugfix Issue 1) ---
# The test did NOT pre-set HF_HUB_OFFLINE (that masked Issue 1). launch_daemon.sh exports it
# (S1); this grep proves the PRODUCTION path is offline by asserting the daemon log contains
# ZERO online huggingface.co requests. httpx logs 'HTTP Request: GET https://huggingface.co'
# to stderr (root StreamHandler from daemon._setup_logging) -> folded into daemon.log by the
# 2>&1 redirect at launch. Missing exports => online freshness check => match => FAIL.
if grep -q 'HTTP Request: GET https://huggingface.co' "$WORK/daemon.log"; then
  die "FAIL: daemon made network calls to huggingface.co (offline exports missing from launch_daemon.sh?); see $WORK/daemon.log"
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
"$VOICECTL" toggle >/dev/null || die "voicectl toggle (-> on) failed"
"$VOICECTL" toggle >/dev/null || die "voicectl toggle (-> off) failed"
echo "[PASS] criterion 6 (voicectl toggle): toggle on/off ok"

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

# --- T4 idle window (criterion 5, CRITICAL) (G-CAPTURE / G-IDLE-NO-TYPING / G-CPU-SAMPLING) ---
# Start the CPU clock at the same moment as voicectl start so the window IS the ARMED idle period.
cpu0="$(cpu_tree_seconds "$DAEMON_PID")"; wall0="$(date +%s)"
"$VOICECTL" start >/dev/null || die "voicectl start failed"
echo "listening armed (silent mic); holding ${IDLE_SECS}s of silence..."
typed_before="$(capture_pane)"
last_final_before="$(jq -r .last_final "$WORK/state.json" 2>/dev/null || true)"
sleep "$IDLE_SECS"
cpu1="$(cpu_tree_seconds "$DAEMON_PID")"; wall1="$(date +%s)"
typed_after="$(capture_pane)"
last_final_after="$(jq -r .last_final "$WORK/state.json" 2>/dev/null || true)"

IDLE_OK=0
# (a) no hallucinated finals typed (capture-pane UNCHANGED AND state.json last_final UNCHANGED).
if [ "$typed_before" = "$typed_after" ] && [ "$last_final_before" = "$last_final_after" ]; then
  echo "[PASS] criterion 5 (no hallucination): no finals typed, last_final unchanged across ${IDLE_SECS}s"
else
  echo "[FAIL] criterion 5 (hallucination guard): capture-pane or last_final CHANGED"
  echo "  typed before: '$typed_before'"
  echo "  typed after:  '$typed_after'"
  echo "  last_final before: '$last_final_before'"
  echo "  last_final after:  '$last_final_after'"
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

# --- T6 GPU residency (criterion 6 / criterion 8) (G-VRAM-ATTRIBUTION / G-VRAM-COMMAS / G-OTHER-APPS) ---
"$VOICECTL" stop >/dev/null || die "voicectl stop failed"
TREE="$(daemon_tree_pids "$DAEMON_PID")"
echo "daemon process tree: $TREE"
# Query ONLY pid,used_memory (comma-safe). Match the daemon tree; sum used_memory; assert >=1 match
# AND total in [1024, 5120] MiB.
VRAM_RAW="$("$NVIDIA_SMI" --query-compute-apps=pid,used_memory --format=csv,noheader 2>/dev/null || true)"
VRAM_VERDICT="$(printf '%s\n' "$VRAM_RAW" > "$WORK/nvidia_smi.csv"; "$PY" - "$WORK/nvidia_smi.csv" "$TREE" <<'PY'
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
            matched.append((pid, m)); total += m
print(f"matched={matched} total_MiB={total}")
sys.exit(0 if matched and 1024 <= total <= 5120 else 1)
PY
)" && VRAM_RC=0 || VRAM_RC=1
if [ "$VRAM_RC" = 0 ]; then
  echo "[PASS] criterion 6/T6 (GPU residency): $VRAM_VERDICT (range ${VRAM_MIN_MIB}-${VRAM_MAX_MIB} MiB)"
else
  echo "[FAIL] criterion 6/T6 (GPU residency): $VRAM_VERDICT"
  echo "  (daemon-tree PID not resident on the GPU, or Σ used_memory outside ${VRAM_MIN_MIB}-${VRAM_MAX_MIB} MiB)"
  echo "  full nvidia-smi compute-apps listing:"
  printf '  %s\n' "$VRAM_RAW"
  IDLE_OK=1
fi

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

# --- evidence block for tests/ACCEPTANCE.md (G-EVIDENCE-BLOCK) ---
echo
echo "=== ACCEPTANCE EVIDENCE (paste into tests/ACCEPTANCE.md, criteria 5/6/8) ==="
echo "daemon_pid: $DAEMON_PID"
echo "idle_seconds: $IDLE_SECS"
echo "cpu_avg_pct_of_one_core: $avg_pct"
echo "nvidia_smi_compute_apps (daemon tree): $VRAM_VERDICT"
echo "voicectl_status:"
while IFS= read -r _line; do echo "  $_line"; done <<EOF
$STATUS_RUN
EOF
echo "systemd_unit:"
echo "  $EXEC_LINE"
echo "  $RESTART_LINE"
echo "offline_env: via launch_daemon.sh exports (HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1); daemon.log HF-request grep: CLEAN"
echo "=== END ACCEPTANCE EVIDENCE ==="

# --- result ---
if [ "$IDLE_OK" = 0 ]; then
  echo "=== IDLE+GPU PASS (criteria 5, 6, 8) ==="
  exit 0
else
  echo "=== IDLE+GPU FAIL (see above; daemon log: $WORK/daemon.log) ==="
  tail -n 30 "$WORK/daemon.log" 2>/dev/null || true
  exit 1
fi
