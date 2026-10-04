#!/usr/bin/env bash
# validate.sh — comprehensive validation for voice-typing (validator-generated, temporary).
#
# Mirrors the REAL user workflows documented in README.md / tests/ACCEPTANCE.md and the
# repo's own tooling. Only phases whose tooling actually exists are included (no mypy /
# pyright / formatter configs exist in this repo — those phases are intentionally omitted).
#
#   1  Lint             ruff check (the repo's linter; .ruff_cache present)
#   2  Shell syntax     bash -n on every repo shell script (cheap static gate)
#   3  Unit tests       pure-python pytest batch (config/textproc/typing/ctl/socket/daemon/
#                       streaming units/key-listener/prompt/recorder-host/feedback/systemd)
#   4  Streaming E2E    tests/test_streaming.py — REAL small.en decode stream through the REAL
#                       StreamingOutput engine + context-prompt executor, RecordingTypingBackend
#                       double (no real keystrokes, no mic). PRD §6 T8 (a)-(g).
#   5  Offline ASR      tests/test_feed_audio.py — real CUDA model, WAV fixtures, no mic.
#   6  Live lifecycle   control-plane + systemd journey against the REAL running daemon:
#                       status / unknown-cmd / malformed-JSON over the raw socket, removed
#                       Rev-1 commands rejected, cancel idempotence, THEN a full
#                       voicectl-quit → systemctl start cycle asserting the PRD §4.9 boot
#                       contract (starts NOT listening, NOT loaded, ~0 VRAM at boot — T6a)
#                       and bounded teardown (no 90 s hang). NEVER arms the mic (arming with
#                       the real wtype backend would type into the focused window).
#   7  E2E virtual mic  OPT-IN via RUN_E2E=1: tests/e2e_virtual_mic.sh — full T3 journey with
#                       the REAL daemon on a PipeWire null-sink monitor + null typing backend
#                       (rebinds the global default audio source for ~5-8 min; trap restores;
#                       this wrapper additionally restores the systemd unit state).
#
# AGENTS.md discipline honored: every non-trivial command is wrapped in an inner GNU `timeout`
# (exit 124 = it fired) and each phase runs under the harness-level backstop; voicectl calls
# are bounded (the control socket has no read timeout); the daemon is NEVER run in the
# foreground; no unbounded scratch files are written (stdout only).
#
# Usage:
#   ./validate.sh              # phases 1-6 (safe; heavy CUDA phases included)
#   RUN_E2E=1 ./validate.sh    # adds the full virtual-mic E2E (~6-9 min)
#
# Exit code: 0 iff every executed phase passed.

set -u

REPO="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
cd "$REPO"

PY="$REPO/.venv/bin/python"
VOICECTL="$REPO/.venv/bin/voicectl"
RUFF="/home/dustin/.local/bin/ruff"

PASS=0
FAIL=0
FAILED_PHASES=()

phase() {  # phase <name> <timeout_s> <cmd...> — run one phase under an inner timeout, tally.
  local name="$1"; shift
  local tmo="$1"; shift
  echo ""
  echo "==================================================================="
  echo "=== PHASE: $name"
  echo "==================================================================="
  if timeout "$tmo" "$@"; then
    echo "=== PHASE RESULT: $name — PASS"
    PASS=$((PASS + 1))
  else
    local rc=$?
    echo "=== PHASE RESULT: $name — FAIL (exit $rc; 124 = inner timeout fired)"
    FAIL=$((FAIL + 1))
    FAILED_PHASES+=("$name")
  fi
}

echo "voice-typing validation — $(date -Is)"
echo "repo: $REPO"
echo "HEAD: $(git -C "$REPO" log --oneline -1 2>/dev/null || echo '(not a git checkout)')"

# --- Phase 1: lint ---------------------------------------------------------------
if [ -x "$RUFF" ]; then
  phase "lint (ruff check)" 120 "$RUFF" check voice_typing/ tests/
else
  echo "PHASE lint: SKIP (ruff not found at $RUFF)"
fi

# --- Phase 2: shell-script syntax ------------------------------------------------
# (cwd is already $REPO; relative paths keep the subshell hermetic)
phase "shell syntax (bash -n)" 60 bash -c '
  set -e
  for f in install.sh tests/e2e_virtual_mic.sh tests/test_idle_and_gpu.sh tests/make_test_audio.sh voice_typing/launch_daemon.sh; do
    bash -n "$f" || { echo "SYNTAX FAIL: $f"; exit 1; }
    echo "  ok: $f"
  done
  echo "all shell scripts parse"
'

# --- Phase 3: pure-python unit tests ----------------------------------------------
phase "unit tests (pure-python)" 600 "$PY" -m pytest \
  tests/test_config.py tests/test_config_repo_default.py tests/test_textproc.py \
  tests/test_typing_backends.py tests/test_voicectl.py tests/test_control_socket.py \
  tests/test_cuda_check.py tests/test_feedback.py tests/test_systemd_unit.py \
  tests/test_daemon.py tests/test_streaming_core.py tests/test_streaming_commit.py \
  tests/test_streaming_freeze.py tests/test_key_listener.py tests/test_prompt_engine.py \
  tests/test_context_prompt_refresh.py tests/test_recorder_host.py -q

# --- Phase 4: streaming-dictation E2E (REAL small.en decode, no mic/keystrokes) ----
# The Rev 2 core feature (PRD §6 T8 a-g): typed partials, in-place commits, pause-join,
# rolling context prompts, Backspace-cancel, user-key freeze, stranded-tail freeze.
phase "streaming E2E (test_streaming.py, CUDA)" 700 "$PY" -m pytest tests/test_streaming.py -q

# --- Phase 5: offline ASR suite (CUDA, no mic) -------------------------------------
# PRD §6 T1/T7: feed WAVs via feed_audio, assert pause-keeps-listening, finals, latency.
if [ -d tests/out ] && ls tests/out/*.wav >/dev/null 2>&1; then
  phase "offline ASR (test_feed_audio.py, CUDA)" 570 "$PY" -m pytest tests/test_feed_audio.py -q
else
  echo "PHASE offline ASR: SKIP (no tests/out/*.wav — run ./tests/make_test_audio.sh first)"
fi

# --- Phase 6: live control-plane + systemd lifecycle (never arms the mic) -----------
echo ""
echo "==================================================================="
echo "=== PHASE: live control-plane + systemd lifecycle"
echo "==================================================================="
SMOKE_FAIL=0
smoke() {  # smoke <label> <expected_rc> <cmd...>
  local label="$1" expected="$2"; shift 2
  timeout 30 "$@" >/dev/null 2>&1
  local rc=$?
  if [ "$rc" -eq "$expected" ]; then
    echo "[PASS] $label (exit $rc)"
  else
    echo "[FAIL] $label exit=$rc (expected $expected)"
    SMOKE_FAIL=$((SMOKE_FAIL + 1))
  fi
}

UNIT_WAS_ACTIVE=0
systemctl --user is-active --quiet voice-typing 2>/dev/null && UNIT_WAS_ACTIVE=1

# 6a. status answers (bounded — a dead daemon must exit 2, a wedged one 124)
timeout 15 "$VOICECTL" status >/dev/null 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
  echo "[PASS] 6a voicectl status answers (daemon reachable)"
else
  echo "[FAIL] 6a voicectl status exit=$rc (2 = daemon down; 124 = wedged socket)"
  SMOKE_FAIL=$((SMOKE_FAIL + 1))
fi

# 6b. removed Rev-1 commands are rejected client-side with exit 64 (usage)
smoke "6b voicectl toggle-lite rejected (exit 64, Rev 2 single-mode surface)" 64 "$VOICECTL" toggle-lite
smoke "6b voicectl start-lite rejected (exit 64)" 64 "$VOICECTL" start-lite

# 6c. cancel is idempotent while disarmed (Backspace-cancel fallback path, no-op)
smoke "6c voicectl cancel idempotent no-op (exit 0)" 0 "$VOICECTL" cancel

# 6d. raw-socket protocol robustness (daemon §4.2(3)): malformed JSON and unknown
#     commands get {"ok":false,...} answers over the wire, not crashes/hangs.
SOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/control.sock"
RAW_PROTO_FAIL=0
raw_probe() {  # raw_probe <payload> — send one line over the control socket, echo the reply
  local payload="$1"
  PAYLOAD="$payload" SOCKPATH="$SOCK" timeout 15 .venv/bin/python - <<'PYEOF' 2>/dev/null
import os, socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(10)
s.connect(os.environ["SOCKPATH"])
try:
    s.sendall((os.environ["PAYLOAD"] + "\n").encode())
    data = b""
    while b"\n" not in data:
        chunk = s.recv(4096)
        if not chunk:
            break
        data += chunk
    print(data.decode(errors="replace").strip())
finally:
    s.close()
PYEOF
}
if [ -S "$SOCK" ]; then
  reply="$(raw_probe 'not json at all')"
  case "$reply" in
    *'"ok": false'*|*'"ok":false'*) echo "[PASS] 6d-1 malformed JSON answered ok:false (got: ${reply:0:80})" ;;
    *) echo "[FAIL] 6d-1 malformed JSON reply: ${reply:0:120}"; RAW_PROTO_FAIL=1 ;;
  esac
  reply="$(raw_probe '{"cmd":"bogus"}')"
  case "$reply" in
    *'unknown command'*) echo "[PASS] 6d-2 unknown command answered with error (got: ${reply:0:80})" ;;
    *) echo "[FAIL] 6d-2 unknown command reply: ${reply:0:120}"; RAW_PROTO_FAIL=1 ;;
  esac
else
  echo "[WARN] 6d control socket not found at $SOCK — skipping raw protocol probes"
fi
if [ "$RAW_PROTO_FAIL" -ne 0 ]; then SMOKE_FAIL=$((SMOKE_FAIL + 1)); fi

# 6e. FULL lifecycle journey (README "First run" + PRD §4.9 / T6a):
#     voicectl quit (bounded teardown — must answer well under TimeoutStopSec=15's manual
#     equivalent), socket disappears, systemctl start brings it back NOT listening + NOT
#     loaded + the daemon PID absent from nvidia-smi (lazy load, ~0 VRAM at boot).
echo "--- 6e lifecycle: quit → start → boot-state assertions ---"
if [ "$UNIT_WAS_ACTIVE" = "1" ]; then
  T0=$(date +%s%N)
  if timeout 30 "$VOICECTL" quit >/dev/null 2>&1; then
    T1=$(date +%s%N)
    MS=$(( (T1 - T0) / 1000000 ))
    echo "[PASS] 6e-1 voicectl quit answered in ${MS}ms (bounded teardown)"
    if [ "$MS" -gt 15000 ]; then
      echo "[FAIL] 6e-1 quit took ${MS}ms — exceeds the 15s bounded-teardown budget"
      SMOKE_FAIL=$((SMOKE_FAIL + 1))
    fi
  else
    echo "[FAIL] 6e-1 voicectl quit failed/timed out"
    SMOKE_FAIL=$((SMOKE_FAIL + 1))
  fi
  # wait for the socket to disappear (daemon fully down), bounded
  ok_down=1
  for _ in $(seq 1 40); do
    [ -S "$SOCK" ] || { ok_down=0; break; }
    sleep 0.25
  done
  if [ "$ok_down" = "0" ]; then
    echo "[PASS] 6e-2 control socket removed after quit"
  else
    echo "[FAIL] 6e-2 control socket still present 10s after quit"
    SMOKE_FAIL=$((SMOKE_FAIL + 1))
  fi
  systemctl --user start voice-typing 2>/dev/null || true
  ok_up=1
  for _ in $(seq 1 60); do
    if timeout 15 "$VOICECTL" status >/dev/null 2>&1; then ok_up=0; break; fi
    sleep 0.5
  done
  if [ "$ok_up" = "0" ]; then
    echo "[PASS] 6e-3 daemon back up after systemctl start"
  else
    echo "[FAIL] 6e-3 daemon did not come back within 30s"
    SMOKE_FAIL=$((SMOKE_FAIL + 1))
  fi
  ST="$(timeout 15 "$VOICECTL" status 2>&1)"
  echo "$ST" | grep -q '^listening: off' && echo "[PASS] 6e-4 boots NOT listening (no hot-mic)" \
    || { echo "[FAIL] 6e-4 listening is not off at boot"; SMOKE_FAIL=$((SMOKE_FAIL + 1)); }
  echo "$ST" | grep -q '^phase: unloaded' && echo "[PASS] 6e-5 boots unloaded (lazy load)" \
    || { echo "[FAIL] 6e-5 phase is not unloaded at boot"; SMOKE_FAIL=$((SMOKE_FAIL + 1)); }
  # T6a: ~0 VRAM at boot — the daemon's MainPID must not appear in nvidia-smi compute apps.
  MAINPID="$(systemctl --user show -p MainPID --value voice-typing 2>/dev/null)"
  if [ -n "${MAINPID:-}" ] && [ "$MAINPID" != "0" ] && command -v nvidia-smi >/dev/null 2>&1; then
    if nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | tr -d ' ' | grep -qx "$MAINPID"; then
      echo "[FAIL] 6e-6 daemon PID $MAINPID holds GPU memory at boot (lazy-load violated)"
      SMOKE_FAIL=$((SMOKE_FAIL + 1))
    else
      echo "[PASS] 6e-6 daemon PID $MAINPID absent from nvidia-smi at boot (~0 VRAM)"
    fi
  else
    echo "[WARN] 6e-6 could not check VRAM (MainPID='$MAINPID' or no nvidia-smi)"
  fi
else
  echo "--- 6e SKIP (systemd unit was not active when validation started) ---"
  systemctl --user start voice-typing 2>/dev/null || true
fi

if [ "$SMOKE_FAIL" -eq 0 ]; then
  echo "=== PHASE RESULT: live control-plane + systemd lifecycle — PASS"
  PASS=$((PASS + 1))
else
  echo "=== PHASE RESULT: live control-plane + systemd lifecycle — FAIL ($SMOKE_FAIL check(s))"
  FAIL=$((FAIL + 1))
  FAILED_PHASES+=("live control-plane + systemd lifecycle")
fi

# --- Phase 7: full E2E with virtual mic (OPT-IN) -----------------------------------
if [ "${RUN_E2E:-0}" = "1" ]; then
  systemctl --user stop voice-typing 2>/dev/null || true
  phase "E2E virtual mic (tests/e2e_virtual_mic.sh)" 880 ./tests/e2e_virtual_mic.sh
  # Belt-and-suspenders restore (the script's own trap already restores source + module).
  systemctl --user start voice-typing 2>/dev/null || true
else
  echo ""
  echo "PHASE E2E: SKIP (opt-in — re-run with RUN_E2E=1 ./validate.sh)"
fi

# --- Phase 8: idle stability + GPU lifecycle suite (OPT-IN) -------------------------
# tests/test_idle_and_gpu.sh — PRD §6 T4 (120 s silence, no hallucination, CPU) + T6 (lazy
# load / armed / disarmed-resident / idle-unload VRAM states) + the single-model block.
# ~5–8 min: two cold CUDA inits + 120 s armed idle + idle-unload waits. Preflight refuses
# to start while the unit is active — stop it here, restart after (restores state).
if [ "${RUN_IDLE_GPU:-0}" = "1" ]; then
  systemctl --user stop voice-typing 2>/dev/null || true
  phase "idle+GPU lifecycle (tests/test_idle_and_gpu.sh)" 780 ./tests/test_idle_and_gpu.sh
  systemctl --user start voice-typing 2>/dev/null || true
else
  echo "PHASE idle+GPU: SKIP (opt-in — re-run with RUN_IDLE_GPU=1 ./validate.sh)"
fi

# --- summary ------------------------------------------------------------------------
echo ""
echo "==================================================================="
echo "=== SUMMARY: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  printf '=== failed phases: %s\n' "${FAILED_PHASES[*]}"
  echo "=== see validation_report.md for the itemized findings"
  # ensure the user's daemon is running no matter what
  systemctl --user start voice-typing 2>/dev/null || true
  exit 1
fi
echo "=== all executed phases passed (E2E included only with RUN_E2E=1)"
systemctl --user is-active --quiet voice-typing 2>/dev/null || systemctl --user start voice-typing 2>/dev/null || true
exit 0
