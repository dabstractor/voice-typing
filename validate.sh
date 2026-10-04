#!/usr/bin/env bash
# validate.sh — comprehensive validation for voice-typing (validator-generated, temporary).
#
# Phases (only tooling that actually exists in this repo is included):
#   1  Lint            ruff check (the repo's configured linter; .ruff_cache present)
#   2  Unit tests      pure-python pytest batch (config/textproc/typing/ctl/socket/daemon/
#                      streaming/key-listener/prompt/recorder-host/feedback/systemd)
#   3  Offline ASR     tests/test_feed_audio.py — real CUDA model, WAV fixtures, no mic
#   4  E2E             tests/e2e_virtual_mic.sh — OPT-IN via RUN_E2E=1 (stops the systemd
#                      unit, rebinds the global default audio source for ~5-8 min, restores
#                      both via the script's trap + this wrapper). Not run by default.
#   5  Live smoke      control-plane checks against the running daemon (status, cancel
#                      idempotence, removed-command rejection). Never arms the mic.
#
# No mypy/pyright config and no formatter config exist in this repo — those phases are
# intentionally omitted (only existing tooling is run).
#
# AGENTS.md discipline honored: every non-trivial command is wrapped in an inner GNU
# `timeout`; voicectl calls are additionally bounded (control socket has no read timeout);
# the daemon is NEVER run in the foreground; no unbounded scratch files are written
# (output goes to stdout only).
#
# Usage:
#   ./validate.sh              # phases 1,2,3,5 (safe; ~2-3 min incl. CUDA load)
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

phase() {  # phase <name> <cmd...> — run one phase under an inner timeout, tally result.
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

# --- Phase 1: lint -------------------------------------------------------------
if [ -x "$RUFF" ]; then
  phase "lint (ruff check)" 120 "$RUFF" check voice_typing/ tests/
else
  echo "PHASE lint: SKIP (ruff not found at $RUFF)"
fi

# --- Phase 2: pure-python unit tests -------------------------------------------
phase "unit tests (pure-python)" 600 "$PY" -m pytest \
  tests/test_config.py tests/test_config_repo_default.py tests/test_textproc.py \
  tests/test_typing_backends.py tests/test_voicectl.py tests/test_control_socket.py \
  tests/test_cuda_check.py tests/test_feedback.py tests/test_systemd_unit.py \
  tests/test_daemon.py tests/test_streaming_core.py tests/test_streaming_commit.py \
  tests/test_streaming_freeze.py tests/test_key_listener.py tests/test_prompt_engine.py \
  tests/test_context_prompt_refresh.py tests/test_recorder_host.py -q

# --- Phase 3: offline ASR suite (CUDA, no mic) ----------------------------------
# Loads real models (~1 min cold). Uses its own recorder (use_microphone=False), so it
# is safe while the systemd daemon is running.
if [ -d tests/out ] && ls tests/out/*.wav >/dev/null 2>&1; then
  phase "offline ASR (test_feed_audio.py, CUDA)" 570 "$PY" -m pytest tests/test_feed_audio.py -q
else
  echo "PHASE offline ASR: SKIP (no tests/out/*.wav — run ./tests/make_test_audio.sh first)"
fi

# --- Phase 4: full E2E with virtual mic (OPT-IN) --------------------------------
# Heavy: stops the voice-typing systemd unit (preflight requires it), rebinds the global
# default PipeWire source to a null-sink monitor, plays WAVs, asserts criteria 2/3/4,
# then restores source + unit. The inner script has an EXIT trap; this wrapper additionally
# restores the systemd unit state no matter what.
if [ "${RUN_E2E:-0}" = "1" ]; then
  UNIT_WAS_ACTIVE=0
  systemctl --user is-active --quiet voice-typing 2>/dev/null && UNIT_WAS_ACTIVE=1
  systemctl --user stop voice-typing 2>/dev/null || true
  phase "E2E virtual mic (tests/e2e_virtual_mic.sh)" 880 ./tests/e2e_virtual_mic.sh
  if [ "$UNIT_WAS_ACTIVE" = "1" ]; then
    systemctl --user start voice-typing 2>/dev/null || true
    echo "(systemd unit voice-typing restarted — was active before this phase)"
  fi
else
  echo ""
  echo "PHASE E2E: SKIP (opt-in — re-run with RUN_E2E=1 ./validate.sh)"
fi

# --- Phase 5: live control-plane smoke (never arms the mic) ----------------------
echo ""
echo "==================================================================="
echo "=== PHASE: live control-plane smoke"
echo "==================================================================="
SMOKE_FAIL=0

# 5a. status answers (bounded — dead daemon must not wedge the run)
if timeout 15 "$VOICECTL" status >/dev/null 2>&1; then
  echo "[PASS] 5a voicectl status answers (daemon reachable)"
else
  rc=$?
  echo "[FAIL] 5a voicectl status exit=$rc (2 = daemon down; 124 = wedged socket)"
  SMOKE_FAIL=$((SMOKE_FAIL + 1))
fi

# 5b. removed command is rejected with exit 64 (usage), not sent / not wedged
timeout 15 "$VOICECTL" toggle-lite >/dev/null 2>&1
rc=$?
if [ "$rc" -eq 64 ]; then
  echo "[PASS] 5b voicectl toggle-lite rejected (exit 64, Rev 2 single-mode surface)"
else
  echo "[FAIL] 5b voicectl toggle-lite exit=$rc (expected 64)"
  SMOKE_FAIL=$((SMOKE_FAIL + 1))
fi

# 5c. cancel is idempotent while disarmed (Backspace-cancel fallback path, no-op)
timeout 30 "$VOICECTL" cancel >/dev/null 2>&1
rc=$?
if [ "$rc" -eq 0 ]; then
  echo "[PASS] 5c voicectl cancel idempotent no-op while disarmed (exit 0)"
else
  echo "[FAIL] 5c voicectl cancel exit=$rc (expected 0)"
  SMOKE_FAIL=$((SMOKE_FAIL + 1))
fi

if [ "$SMOKE_FAIL" -eq 0 ]; then
  echo "=== PHASE RESULT: live control-plane smoke — PASS"
  PASS=$((PASS + 1))
else
  echo "=== PHASE RESULT: live control-plane smoke — FAIL ($SMOKE_FAIL check(s))"
  FAIL=$((FAIL + 1))
  FAILED_PHASES+=("live control-plane smoke")
fi

# --- summary ---------------------------------------------------------------------
echo ""
echo "==================================================================="
echo "=== SUMMARY: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  printf '=== failed phases: %s\n' "${FAILED_PHASES[*]}"
  echo "=== see validation_report.md for the itemized findings"
  exit 1
fi
echo "=== all executed phases passed (E2E included only with RUN_E2E=1)"
exit 0
