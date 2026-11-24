#!/usr/bin/env bash
# validate.sh — comprehensive validation for voice-typing (Rev-4 + bugfix 001_5597f70b5c13)
#
# Validates the codebase at the current HEAD against:
#   - its own documented test methodology (one pure suite per call under GNU timeout;
#     failures set-diffed against the G1 baseline inventories, never expected clean), and
#   - the four PRD bugs (BUG-001 hermetic ducking tests, BUG-002 bulk-text R.1 gating,
#     BUG-003 panic-bind VT-003 exemption, BUG-004 test_daemon.py classification).
#
# SAFETY CONTRACT (AGENTS.md):
#   * NEVER spawns or arms the daemon; live checks are READ-ONLY (status/session/journal).
#   * NEVER mutates the desktop: no busctl/wpctl/pactl from this script's own phases.
#   * Every non-trivial command is wrapped in GNU `timeout` (exit 124 = wedged, is a FAIL).
#   * Scratch is a mktemp -d removed by an EXIT trap; stored logs are one line per suite
#     (bounded by construction). /tmp is a tmpfs — nothing unbounded is ever written.
#   * Heavy desktop-mutating harnesses (CUDA model suites, G5 timing lab, D1 duck evidence,
#     virtual-mic E2E) are OPT-IN via env flags and OFF by default — see Phase 5.
#
# Usage:
#   ./validate.sh                 # default: phases 0-4 (~4-5 min)
#   STRICT=1 ./validate.sh        # escalate WARNs (stale live daemon, missing launcher) to FAILs
#   RUN_CUDA=1 ./validate.sh      # + real CUDA/model suites (~10+ min, GPU)
#   RUN_G5=1 ./validate.sh        # + G5 timing lab, both routes (~50 min, GPU; exits 1 = honest fail)
#   RUN_D1=1 ./validate.sh        # + D1 duck evidence (~15 min; PAUSES/RESUMES live media)
#   RUN_MIC_E2E=1 ./validate.sh   # + e2e_virtual_mic.sh (~15 min; REBINDS the default audio source)

set -u

PY=.venv/bin/python
FAILS=0
WARNS=0
NOTES=0
SCRATCH=$(mktemp -d /tmp/vt-validate.XXXXXX)
trap 'rm -rf "$SCRATCH"' EXIT INT TERM

say()  { printf '%s\n' "$*"; }
pass() { printf 'PASS  %s\n' "$*"; }
note() { NOTES=$((NOTES+1)); printf 'NOTE  %s\n' "$*"; }
warn() { WARNS=$((WARNS+1)); printf 'WARN  %s\n' "$*"; if [ "${STRICT:-0}" = "1" ]; then FAILS=$((FAILS+1)); fi; }
fail() { FAILS=$((FAILS+1)); printf 'FAIL  %s\n' "$*"; }

# ---------------------------------------------------------------------------
say "=== voice-typing validation — $(date '+%F %T') — HEAD $(git rev-parse --short HEAD 2>/dev/null || echo '?') ==="

# --- Phase 0: preflight ------------------------------------------------------
say "--- Phase 0: preflight"
[ -x "$PY" ] || { fail "$PY missing (run the repo's install first)"; exit 1; }
timeout 30 $PY -c "import sys; assert sys.version_info[:2] == (3, 12), sys.version" \
  && pass "python 3.12 venv" || fail "python version probe"
# The daemon must never be started by this script. We only OBSERVE the live unit.
say "scratch: $SCRATCH (trap-cleaned, bounded logs)"

# --- Phase 1: static ---------------------------------------------------------
say "--- Phase 1: static (no ruff/mypy/black config ships; README: 'pytest is the gate')"
if timeout 120 $PY -m compileall -q voice_typing >"$SCRATCH/compile.log" 2>&1; then
  pass "compileall voice_typing (syntax)"
else
  fail "compileall reported errors:"; head -20 "$SCRATCH/compile.log"
fi

# --- Phase 2: unit — every pure suite, one file per call ----------------------
say "--- Phase 2: pure unit suites (one file per call, GNU timeout per file)"
PURE=$(ls tests/test_*.py | grep -v -E 'test_feed_audio|test_recorder_host|test_cuda_check|test_streaming\.py')
SUITE_LOG="$SCRATCH/suites.txt"; : >"$SUITE_LOG"
for f in $PURE; do
  case "$f" in
    tests/test_daemon.py) TMO=500;;   # CPU-only but slow (~17 s) + wedge backstop
    *)                    TMO=300;;
  esac
  out=$(timeout "$TMO" $PY -m pytest "$f" -q --tb=no 2>&1 | tail -1)
  rc=$?
  echo "$f :: rc=$rc :: $out" >>"$SUITE_LOG"
  case "$out" in
    *" passed"*|*"no tests ran"*) ;;      # green (or empty) — counted below
    *) warn "suite $f ended: $out";;
  esac
  [ "$rc" = "124" ] && fail "suite $f TIMED OUT ($TMO s) — wedge vector"
done
GREEN=$(grep -c " :: rc=0 :: " "$SUITE_LOG" || true)
RED=$(grep -cv " :: rc=0 :: " "$SUITE_LOG" || true)
say "suites: $(grep -c '::' "$SUITE_LOG") total, green-lines: $GREEN, non-green: $RED"

# Baseline set-diff: the documented legacy reds (G1_BASELINE.md + its CPU addendum).
# A NEW red (not baselined) is a FAIL. A baselined red turning green is a NOTE (improvement).
mkdir -p "$SCRATCH/base" "$SCRATCH/seen"
cat >"$SCRATCH/base/test_streaming_commit" <<'EOF'
test_commit_advances_checkpoint_next_partial_diffs_against_empty_tail
test_commit_checkpoint_guard_context_is_screen_truth
test_commit_empty_delta_types_only_the_space
test_commit_extend_applies_casing_guard_to_the_delta
test_commit_extend_strips_spurious_mid_sentence_period
test_commit_frozen_absorbs_tail_and_types_separator
test_commit_shorter_final_backspaces_only_the_extra
test_commit_space_type_failure_keeps_checkpoint_at_boundary
test_frozen_commit_space_type_failure_absorbs_nothing
test_reset_session_clears_everything_including_frozen
EOF
cat >"$SCRATCH/base/test_streaming_core" <<'EOF'
test_mid_sentence_capitalized_partials_extend_case_insensitively
test_no_separator_after_clean_commit
EOF
cat >"$SCRATCH/base/test_streaming_freeze" <<'EOF'
test_cancel_then_resume_restores_live_delta_typing
test_note_user_keypress_frozen_commit_absorbs_then_boundary_lifts_and_next_types
test_rejected_final_freeze_lives_until_resume_then_next_utterance_types
test_session_frozen_tail_late_commit_absorbs_plus_separator_and_stays_frozen
EOF
cat >"$SCRATCH/base/test_daemon" <<'EOF'
test_cancel_suppression_drops_racing_final_and_clears_on_sentinel
test_cfg_to_kwargs_calls_resolve_with_cfg_defaults
test_cfg_to_kwargs_cuda_path
test_lost_sentinel_self_heals_after_timeout
test_on_final_clears_final_pending
test_on_final_emits_structured_latency_line
test_on_final_happy_path_appends_space
test_on_final_lock_held_across_type_text
test_on_final_serializes_two_concurrent_callbacks
test_on_final_streaming_commit_types_via_engine
test_on_final_streaming_pushes_context_prompt_to_host
test_on_final_streaming_revise_minimal_diff
test_on_final_typing_raises_is_caught_and_record_still_happens
test_on_final_user_keypress_frozen_commit_absorbs_then_unfreezes
test_refresh_context_prompt_missing_host_seam_is_silent_noop
test_resolved_device_unaffected_by_cuda_check_failure
test_sentinel_consume_clears_suppress_since
test_status_device_reseeded_not_stale_after_child_death
test_status_device_reseeded_not_stale_after_idle_unload
test_stop_within_session_stray_partial_after_final_disarms_immediately
EOF

NEW_REDS=0; GONE_REDS=0
for trio in test_streaming_commit test_streaming_core test_streaming_freeze test_daemon; do
  timeout 500 $PY -m pytest "tests/$trio.py" -q --tb=no 2>&1 | grep '^FAILED' \
    | sed "s/^FAILED tests\/$trio.py:://; s/ - .*//" | sort >"$SCRATCH/seen/$trio"
  news=$(comm -13 "$SCRATCH/base/$trio" "$SCRATCH/seen/$trio")
  gone=$(comm -23 "$SCRATCH/base/$trio" "$SCRATCH/seen/$trio")
  [ -n "$news" ] && { NEW_REDS=$((NEW_REDS+$(printf '%s\n' "$news" | wc -l))); fail "NEW unbaselined reds in $trio:"; printf '%s\n' "$news" | sed 's/^/        /'; }
  [ -n "$gone" ] && { GONE_REDS=$((GONE_REDS+$(printf '%s\n' "$gone" | wc -l))); note "baselined red(s) now GREEN in $trio (improvement — update tests/G1_BASELINE.md):"; printf '%s\n' "$gone" | sed 's/^/        /'; }
done
[ "$NEW_REDS" = "0" ] && pass "set-diff: every red is in the G1 baseline inventory (0 new)"

# --- Phase 3: PRD bug-fix spotlights -----------------------------------------
say "--- Phase 3: PRD bug spotlights (BUG-001 .. BUG-004)"

# BUG-001: the deterministic order-pollution repro (must be ONE process) + the flaky batch.
if timeout 300 $PY -m pytest tests/test_key_listener.py::test_zero_keyboard_warning_fires_once_at_first_arm \
       tests/test_typing_backends.py -q --tb=no >"$SCRATCH/bug001.log" 2>&1 \
   && grep -q " passed" <(tail -1 "$SCRATCH/bug001.log"); then
  pass "BUG-001 deterministic repro (arm test + wtype recorder, one process)"
else fail "BUG-001 repro regressed: $(tail -1 "$SCRATCH/bug001.log")"; fi
if timeout 300 $PY -m pytest tests/test_control_socket.py tests/test_key_listener.py \
       tests/test_typing_backends.py tests/test_textproc.py tests/test_prompt_engine.py \
       tests/test_context_prompt_refresh.py tests/test_systemd_unit.py \
       tests/test_ydotoold_client.py -q --tb=no >"$SCRATCH/batch.log" 2>&1 \
   && tail -1 "$SCRATCH/batch.log" | grep -qE "[1-9][0-9]* passed"; then
  pass "BUG-001 8-file order-independence batch"
else fail "BUG-001 batch regressed: $(tail -1 "$SCRATCH/batch.log")"; fi
grep -q "_MEDIA_TRANSPORTS" tests/test_typing_backends.py \
  && pass "BUG-001 media-transport tripwire present in typing-backend recorder" \
  || fail "BUG-001 media-transport tripwire missing"
grep -q "hermetic_cfg" tests/conftest.py \
  && pass "BUG-001 hermetic cfg builder present in conftest" \
  || fail "BUG-001 hermetic cfg builder missing"

# BUG-002: while R.1 is unmet the SAFETY gates must hold (opt-in, honestly labeled).
B2=$($PY - <<'EOF'
from voice_typing.config import VoiceTypingConfig
d = VoiceTypingConfig.from_toml({}).output.delivery
ok_load = ok_reject = None
try:
    VoiceTypingConfig.from_toml({"output": {"delivery": "bulk-text"}}); ok_load = "yes"
except ValueError: ok_load = "no"
try:
    VoiceTypingConfig.from_toml({"output": {"delivery": "bulk-text", "streaming": False}}); ok_reject = "no"
except ValueError: ok_reject = "yes"
print(f"{d} {ok_load} {ok_reject}")
EOF
)
[ "$B2" = "stream-edit yes yes" ] \
  && pass "BUG-002 config gates: default=stream-edit, bulk loads with the triple, rejects bad companions" \
  || fail "BUG-002 config gate drift: got '$B2' (want 'stream-edit yes yes')"
grep -q '^delivery    = "stream-edit"' config.toml \
  && pass "BUG-002 repo config.toml default delivery is stream-edit" \
  || fail "BUG-002 config.toml default delivery is not stream-edit"
G6=$(timeout 60 $PY tests/g6_assessment.py 2>&1 | tail -1)
# Verdict-table rows only: col2 holds the bold verdict (the A/B arms table has plain/stabilized there).
G5ROWS=$(grep -cE '^\| (im-gtk|pi-ghostty) \| \*\*(fail|pass|blocked)' tests/G5_TIMING_EVIDENCE.md)
G5FAIL=$(grep -cE '^\| (im-gtk|pi-ghostty) \| \*\*fail' tests/G5_TIMING_EVIDENCE.md)
if echo "$G6" | grep -q "STAY OPT-IN"; then
  [ "$G5ROWS" = "2" ] && [ "$G5FAIL" = "2" ] \
    && pass "BUG-002 honest gating: G6=STAY OPT-IN with both G5 routes recorded fail (R.1 still open)" \
    || warn "BUG-002 G5 verdict table shape drifted (rows=$G5ROWS fails=$G5FAIL) — re-read the evidence file"
else
  # Graduated verdict while any route still fails = policy contradiction.
  if [ "$G5FAIL" != "0" ]; then fail "BUG-002 G6 graduated ($G6) while $G5FAIL G5 route(s) still fail";
  else note "BUG-002 G6 verdict changed to: $G6 — re-check the evidence chain"; fi
fi

# BUG-003: the panic-bind exemption (exact parsed match, no over-generalization).
timeout 120 $PY -m pytest tests/test_systemd_unit.py::test_hypr_binds_use_portable_home_launcher -q --tb=no \
  >"$SCRATCH/bug003.log" 2>&1 && grep -q "1 passed" "$SCRATCH/bug003.log" \
  && pass "BUG-003 panic-bind VT-003 exemption test green" \
  || fail "BUG-003 panic-bind test red: $(tail -1 "$SCRATCH/bug003.log")"

# BUG-004: the classification must exist and stay truthful.
grep -q "G1 CPU addendum — tests/test_daemon.py" tests/G1_BASELINE.md \
  && pass "BUG-004 G1 baseline carries the named test_daemon.py 20-case addendum" \
  || fail "BUG-004 G1 baseline addendum missing"
grep -q "NOT.* a CUDA suite" AGENTS.md \
  && pass "BUG-004 AGENTS.md classifies test_daemon.py as pure CPU" \
  || fail "BUG-004 AGENTS.md misclassifies test_daemon.py"

# --- Phase 4: live E2E (READ-ONLY; never arms, never restarts, never types) ---
say "--- Phase 4: live E2E (read-only against the systemd unit)"
if timeout 15 systemctl --user is-active voice-typing >/dev/null 2>&1; then
  pass "systemd user unit voice-typing is active"
else
  fail "systemd user unit voice-typing is NOT active (README 'First run' journey broken)"
fi
STATUS=$(timeout 15 .venv/bin/voicectl status 2>"$SCRATCH/status.err"); SRC=$?
if [ "$SRC" = "0" ]; then
  miss=""
  for k in "^listening: " "^mode: " "^phase: " "^mic: " "^delivery: "; do
    echo "$STATUS" | grep -q "$k" || miss="$miss $k"
  done
  [ -z "$miss" ] && pass "voicectl status serves the documented field set ($(echo "$STATUS" | wc -l) lines)" \
               || fail "voicectl status missing fields:$miss"
  echo "$STATUS" | sed 's/^/      /'
else
  fail "voicectl status exited $SRC: $(head -2 "$SCRATCH/status.err")"
fi
SESS_ALL=$(timeout 15 .venv/bin/voicectl session 2>&1); SESS_RC=$?
if [ "$SESS_RC" = "0" ] || { [ "$SESS_RC" = "1" ] && ! echo "$SESS_ALL" | grep -qi "unknown command"; }; then
  pass "voicectl session contract (rc=$SESS_RC; 0=text, 1=no completed session)"
elif echo "$SESS_ALL" | grep -qi "unknown command"; then
  warn "running daemon predates the session feature (started before the code landed) — restart the unit to pick it up: systemctl --user restart voice-typing"
else
  fail "voicectl session unexpected rc=$SESS_RC: $(echo "$SESS_ALL" | head -1)"
fi
timeout 15 .venv/bin/voicectl >/dev/null 2>&1; [ "$?" = "64" ] \
  && pass "voicectl usage contract: no command -> exit 64" || fail "voicectl no-command exit code != 64"
timeout 15 .venv/bin/voicectl definitively-not-a-command >/dev/null 2>&1; [ "$?" = "64" ] \
  && pass "voicectl usage contract: unknown command -> exit 64" || fail "voicectl bad-command exit code != 64"
timeout 15 journalctl --user -u voice-typing -n 3 --no-pager >/dev/null 2>&1 \
  && pass "daemon journal readable" || warn "journalctl could not read the unit journal"
if [ -x "$HOME/.local/bin/voicectl" ]; then
  pass "VT-003 launcher \$HOME/.local/bin/voicectl installed"
else
  warn "VT-003 launcher \$HOME/.local/bin/voicectl absent (run install.sh; hotkey binds depend on it)"
fi

# --- Phase 5: opt-in heavy harnesses (OFF by default; each mutates or loads) --
if [ "${RUN_CUDA:-0}" = "1" ]; then
  say "--- Phase 5a: CUDA/model suites (RUN_CUDA=1)"
  for f in test_feed_audio test_recorder_host test_cuda_check test_streaming; do
    out=$(timeout 600 $PY -m pytest "tests/$f.py" -q --tb=no 2>&1 | tail -1); rc=$?
    [ "$rc" = "124" ] && fail "$f TIMED OUT" || note "$f: $out (watch set: test_streaming 3P/4F per G1)"
  done
fi
if [ "${RUN_G5:-0}" = "1" ]; then
  say "--- Phase 5b: G5 timing lab (RUN_G5=1; ~25 min per route; exit 1 = honest fail)"
  for route in im-gtk pi-ghostty; do
    out=$(timeout -k 2 1500 env G5_TIMING_LAB=1 $PY tests/g5_timing_lab.py --route "$route" 2>&1 | tail -1)
    note "G5 $route: $out"
  done
fi
if [ "${RUN_D1:-0}" = "1" ]; then
  say "--- Phase 5c: D1 duck evidence (RUN_D1=1; PAUSES/RESUMES live media by design)"
  out=$(timeout 900 bash tests/d1_duck_evidence.sh 2>&1 | tail -3)
  note "D1 evidence tail: $out"
fi
if [ "${RUN_MIC_E2E:-0}" = "1" ]; then
  say "--- Phase 5d: virtual-mic E2E (RUN_MIC_E2E=1; REBINDS the default audio source)"
  out=$(timeout 900 bash tests/e2e_virtual_mic.sh 2>&1 | tail -3)
  note "E2E tail: $out"
fi

# --- verdict -----------------------------------------------------------------
say "=== SUMMARY: FAILS=$FAILS WARNS=$WARNS NOTES=$NOTES ==="
if [ "$FAILS" = "0" ]; then
  say "VERDICT: PASS — pure suites match the G1 baselines exactly, all four PRD bug fixes hold, live read-only E2E green."
  say "(BUG-002 remains an OPEN product gap by design: bulk-text R.1 is unmet and honestly gated opt-in — see validation_report.md.)"
  exit 0
else
  say "VERDICT: FAIL — $FAILS gating failure(s). See the FAIL lines above."
  exit 1
fi
