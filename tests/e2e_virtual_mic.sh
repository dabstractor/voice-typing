#!/usr/bin/env bash
# tests/e2e_virtual_mic.sh — full E2E with virtual mic + tmux (PRD §6 T3; work item P1.M7.T3.S1).
#
# Stands up a real PipeWire null-sink (vt_test) + its monitor, points the system default input at
# the monitor, launches the REAL daemon with the tmux typing backend pointed at a 'voicetest' tmux
# pane, drives it with voicectl, plays utt_pause.wav + utt_multi.wav via pw-cat, and asserts the
# three PRD acceptance criteria that only a real-audio E2E can prove:
#
#   Criterion 2 (PRD §7.2): a >=3 s mid-dictation pause loses zero words. Both halves of
#                            utt_pause.wav (PAUSE_A + PAUSE_B) transcribe through the real mic path
#                            — PAUSE_B is the post-3s-pause half (the WhisperX-flaw regression).
#   Criterion 3 (PRD §7.3): live partials are observable in state.json WHILE audio plays.
#   Criterion 4 (PRD §7.4): nothing is typed while toggled off — after voicectl stop, playing one
#                            more WAV types nothing new (the on_final gate + the disarmed mic).
#
# A trap guarantees cleanup on ANY exit (PASS, error, Ctrl-C): restore the original default source,
# unload the null-sink module (by index), kill the tmux session, quit/kill the daemon, and remove
# temp files. THE USER'S DEFAULT SOURCE IS NEVER LEFT SWITCHED (PRD §6 T3 step 5, verbatim).
#
# Real stack: PipeWire + CUDA Whisper + tmux. Heavy (model load is the long pole). Run explicitly:
#   cd /home/dustin/projects/voice-typing
#   ./tests/make_test_audio.sh          # ensure tests/out/*.wav exist (idempotent)
#   ./tests/e2e_virtual_mic.sh
#
# PREFLIGHT: refuses to start if a voice-typing daemon is already running (voicectl status answers
# OR the systemd unit is active) — the real control socket is pinned to $XDG_RUNTIME_DIR and cannot
# be isolated without editing daemon.py, and set-default-source is global. Stop it first:
#   systemctl --user stop voice-typing
#
# GOTCHAS encoded here (see PRP G-* invariants):
#   G-CAPTURE:          read typed text via 'tmux capture-pane -p -S -' (NOT cat the file mid-stream
#                       — the daemon types literal keys with NO newline, so the pty canonical-mode
#                       buffers 'cat > file' input and the file stays empty). cat>file is an
#                       end-of-run cross-check only, after a C-d flush.
#   G-RUNTIME:          keep the REAL XDG_RUNTIME_DIR for the daemon + pactl/pw-cat (moving it to a
#                       temp dir breaks PyAudio's PulseAudio backend -> ALSA fallback -> the monitor
#                       is invisible -> silence). Isolate state.json via the config override.
#   G-SOURCE:           record ORIG_SRC BEFORE load-module; restore it + unload-module by INDEX in
#                       the trap (unloading by the module NAME unloads ALL null-sinks -> destructive).
#   G-TARGET:           pw-cat --target takes the SINK NAME (vt_test), not the monitor;
#                       capture-pane -t takes the SESSION (voicetest).
#   G-PREFLIGHT:        refuse if voicectl status answers / systemctl --user is-active voice-typing.
#   G-CONFIG:           override via XDG_CONFIG_HOME=<tmp>/config (minimal [output]+[feedback]); do
#                       NOT edit the repo config.toml. [asr]/[filter]/[log] inherit dataclass
#                       defaults (identical to repo config.toml) -> same production ASR pipeline.
#   G-TMUX-PATH:        ALWAYS /usr/bin/tmux (zsh aliases tmux; the daemon uses the same path).
#   G-ORDERING:         create the null-sink + set-default-source BEFORE launching the daemon —
#                       RealtimeSTT opens the PyAudio stream ONCE at construction on the default
#                       input AT THAT MOMENT (set_microphone only flips a flag, does not re-open).
#   G-FUZZY:            >=80% token overlap (case/punct-insensitive) via a python one-liner. espeak
#                       is robotic -> exact match is brittle; the 80% floor is the PRD's allowance.
#   G-POLL-TIMEOUTS:    180s daemon-ready (cuDNN/cuBLAS cold init + 2 model loads); 90s typed-text;
#                       0.2s partial-poll during playback.
#   G-CLEANUP-IDEMPOTENT: every trap step wrapped in '|| true' / '2>/dev/null'; trap fires on EXIT.
set -euo pipefail

# --- paths + canonical fuzzy targets (PINNED VERBATIM from tests/make_test_audio.sh; PRD §6) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO"
VOICECTL="$REPO/.venv/bin/voicectl"
PY="$REPO/.venv/bin/python"
LAUNCH="$REPO/voice_typing/launch_daemon.sh"
WAV_DIR="$REPO/tests/out"
PAUSE_WAV="$WAV_DIR/utt_pause.wav"
MULTI_WAV="$WAV_DIR/utt_multi.wav"
SIMPLE_WAV="$WAV_DIR/utt_simple.wav"
TMUX_BIN=/usr/bin/tmux
SINK=vt_test
TMUX_SESS=voicetest
# Bare session name (NOT 'voicetest:0.0'): this machine's tmux has window base-index=1, so the
# first window is 'voicetest:1.0', not ':0.0'. A bare session name targets the session's active
# pane regardless of base-index (verified: send-keys/capture-pane/kill-session all accept it),
# which is what G-TARGET means ('capture-pane target is the SESSION'). The daemon's
# TmuxBackend passes cfg.output.tmux_target straight to 'send-keys -t', so it must match this.
TMUX_TARGET="voicetest"

# If this script runs INSIDE an existing tmux session (e.g. the developer's terminal is a tmux
# pane), the inherited TMUX/TMUX_PANE env vars make 'tmux new-session' misbehave ('error
# connecting to /usr/bin/tmux' / 'Permission denied') because the client tries to bind to the
# parent client's context. Unset them so every 'tmux' call below (and the daemon's send-keys,
# which inherits this env) talks to the default server cleanly. The daemon's TmuxBackend invokes
# '/usr/bin/tmux send-keys -t <target> -l' WITHOUT -L, so it uses the default socket too — both
# sides reach the same 'voicetest' session as long as neither has TMUX set.
# NOTE: the tmux binary PATH is held in TMUX_BIN (below) — NOT the TMUX env var — so unsetting the
# env var here does not clobber the path.
unset TMUX TMUX_PANE TMUX_TMPDIR

# The 5 canonical references (single source: tests/make_test_audio.sh). Do NOT paraphrase.
PAUSE_A="I want to test whether this system"   # first half of utt_pause.wav
PAUSE_B="keeps listening after a pause."       # second half, AFTER the 3.0 s gap — THE regression
MULTI_1="The weather looks good today."        # utt_multi.wav sentence 1
MULTI_2="I need to buy some groceries."        # utt_multi.wav sentence 2
MULTI_3="Let us meet at the cafe."             # utt_multi.wav sentence 3

# --- state (populated by setup; used by the trap) ---
WORK=""
ORIG_SRC=""
MODIDX=""
DAEMON_PID=""

# --- cleanup (G-SOURCE / G-CLEANUP-IDEMPOTENT): idempotent + best-effort; fires on ANY exit.
# Invoked indirectly via 'trap cleanup EXIT' below (shellcheck SC2329 is a false positive).
# shellcheck disable=SC2329
cleanup() {
  set +e
  echo "--- cleanup ---"
  # 1. daemon: stop the PROCESS directly + bounded (do NOT block on 'voicectl quit' — it can hang
  #    if the daemon is mid-shutdown releasing GPU VRAM). Ask quit with a 5s cap, then SIGTERM the
  #    PID, poll up to 8s for it to exit, then SIGKILL. This guarantees cleanup never stalls.
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
  # 2. restore the global default source FIRST (PRD §6 T3 step 5 hard rule).
  if [ -n "${ORIG_SRC:-}" ]; then
    pactl set-default-source "$ORIG_SRC" 2>/dev/null && echo "restored default source: $ORIG_SRC"
  fi
  # 3. unload the null-sink by INDEX (NEVER by the module name; G-SOURCE).
  if [ -n "${MODIDX:-}" ]; then
    pactl unload-module "$MODIDX" 2>/dev/null && echo "unloaded module $MODIDX"
  fi
  # 4. kill the tmux session.
  "$TMUX_BIN" kill-session -t "$TMUX_SESS" 2>/dev/null && echo "killed tmux session $TMUX_SESS"
  # 5. remove temp files.
  [ -n "${WORK:-}" ] && rm -rf "$WORK"
  # 6. verify no trace (G-SOURCE hard rule — warn, do not mask the test result).
  if pactl list short sources 2>/dev/null | grep -q "vt_test"; then
    echo "WARN: vt_test still present in pactl sources" >&2
  fi
}
trap cleanup EXIT

# --- helpers ---
die() { echo "FAIL: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# Read typed text from the tmux pane via capture-pane (reads the tty ECHO, live; G-CAPTURE).
# Drop blank lines + join wrapped lines into one space-separated string (G-CAPTURE-PANE-FILTER).
capture_pane() {
  "$TMUX_BIN" capture-pane -t "$TMUX_SESS" -p -S - \
    | grep -v '^[[:space:]]*$' \
    | paste -sd ' '
}

# --- preflight (G-PREFLIGHT / G-DEPS) ---
have pactl   || die "missing pactl (PipeWire pulse compat)"
have pw-cat  || die "missing pw-cat (PipeWire)"
[ -x "$TMUX_BIN" ] || die "missing $TMUX_BIN"
have jq      || die "missing jq"
[ -x "$VOICECTL" ] || die "missing $VOICECTL (run install / uv sync)"
[ -x "$PY" ]       || die "missing $PY"
for w in "$PAUSE_WAV" "$MULTI_WAV" "$SIMPLE_WAV"; do
  [ -f "$w" ] || die "missing $w (run ./tests/make_test_audio.sh)"
done
# refuse if a daemon is already running (real control socket is pinned; G-RUNTIME / G-PREFLIGHT).
if "$VOICECTL" status >/dev/null 2>&1; then
  die "a voice-typing daemon is already running (voicectl status answered). Stop it first: systemctl --user stop voice-typing"
fi
if systemctl --user is-active voice-typing >/dev/null 2>&1; then
  die "voice-typing systemd service is active; stop it first: systemctl --user stop voice-typing"
fi

# --- setup (G-SOURCE / G-ORDERING / G-CONFIG / G-RUNTIME) ---
# G-SOURCE: capture the original default source BEFORE any mutation.
ORIG_SRC="$(pactl get-default-source)" || die "pactl get-default-source failed"
echo "original default source: $ORIG_SRC"

# G-ORDERING: create the null-sink + set-default-source BEFORE launching the daemon (PyAudio opens
# the default input ONCE at recorder construction).
MODIDX="$(pactl load-module module-null-sink sink_name="$SINK" media.class=Audio/Sink)" \
  || die "load-module module-null-sink failed"
echo "loaded null-sink module index: $MODIDX"
pactl set-default-source "$SINK.monitor" || die "set-default-source $SINK.monitor failed"
echo "default source -> $SINK.monitor"

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
# Make the pane wide so typed text does not wrap (G-CAPTURE-PANE-FILTER).
"$TMUX_BIN" resize-window -t "$TMUX_SESS" -x 1000 2>/dev/null || true

# --- launch daemon (G-RUNTIME: REAL XDG_RUNTIME_DIR; G-CONFIG: temp XDG_CONFIG_HOME) ---
# NOTE: do NOT override XDG_RUNTIME_DIR here (PyAudio needs the real one; G-RUNTIME). launch_daemon.sh
# execs python -> $! IS the python PID -> kill it directly in the trap.
XDG_CONFIG_HOME="$WORK/config" "$LAUNCH" > "$WORK/daemon.log" 2>&1 &
DAEMON_PID=$!
echo "daemon launched (pid=$DAEMON_PID); waiting for ready (models load, up to 180s)..."

# --- wait for ready (G-POLL-TIMEOUTS) ---
ready=0
for _ in $(seq 1 360); do          # 360 x 0.5s = 180s
  if "$VOICECTL" status >/dev/null 2>&1; then ready=1; break; fi
  kill -0 "$DAEMON_PID" 2>/dev/null || die "daemon exited during startup; see $WORK/daemon.log"
  sleep 0.5
done
[ "$ready" = 1 ] || die "daemon not ready in 180s; see $WORK/daemon.log"
echo "daemon ready:"
"$VOICECTL" status || true

# --- RUN: arm, play, poll partials + typed text (criteria 2, 3 + all-segments) ---
"$VOICECTL" start >/dev/null || die "voicectl start failed"
echo "listening armed; playing utt_pause.wav then utt_multi.wav..."

# Poll state.json partials DURING playback (criterion 3; G-POLL-TIMEOUTS). Each non-empty 'partial'
# snapshot is appended to partials.log.
(
  for _ in $(seq 1 150); do        # 150 x 0.2s = 30s poll window
    p="$(jq -r .partial "$WORK/state.json" 2>/dev/null || true)"
    if [ -n "$p" ] && [ "$p" != "null" ]; then
      echo "$p" >> "$WORK/partials.log"
    fi
    sleep 0.2
  done
) &
PARTIALS_POLL=$!

# Play utt_pause.wav (2 finals: PAUSE_A + PAUSE_B) then utt_multi.wav (3 finals).
pw-cat -p --target "$SINK" "$PAUSE_WAV" || die "pw-cat playback pause failed"
sleep 1
pw-cat -p --target "$SINK" "$MULTI_WAV" || die "pw-cat playback multi failed"
wait "$PARTIALS_POLL" 2>/dev/null || true

# Poll capture-pane until all 5 refs fuzzy-match (G-CAPTURE / G-POLL-TIMEOUTS).
# NOTE: the captured text is passed as argv[1] (NOT via a pipe) because 'python - <<PY' reads the
# SCRIPT from the heredoc (stdin) — a pipe + heredoc conflict (shellcheck SC2259) would feed the
# python source to sys.stdin instead of the text.
typed=""
for _ in $(seq 1 180); do          # 180 x 0.5s = 90s
  typed="$(capture_pane)"
  if "$PY" - "$typed" "$PAUSE_A" "$PAUSE_B" "$MULTI_1" "$MULTI_2" "$MULTI_3" <<'PY' >/dev/null 2>&1
import re, string, sys
capt = sys.argv[1]
refs = sys.argv[2:]
def toks(s):
    return re.sub(rf"[{re.escape(string.punctuation)}]", " ", s.lower()).split()
def overlap(h, r):
    from collections import Counter
    hc, rc = Counter(toks(h)), Counter(toks(r))
    return (sum((hc & rc).values()) / len(rc)) if rc else 0.0
sys.exit(0 if all(overlap(capt, r) >= 0.80 for r in refs) else 1)
PY
  then break; fi
  sleep 0.5
done

# --- ASSERT criteria 2 + all-segments (G-FUZZY; prints per-ref overlaps + the captured text) ---
echo "--- assertions ---"
ALLREFS_OK=0
"$PY" - "$typed" "$PAUSE_A" "$PAUSE_B" "$MULTI_1" "$MULTI_2" "$MULTI_3" <<'PY' || ALLREFS_OK=1
import re, string, sys
capt = sys.argv[1]
refs = sys.argv[2:]
def toks(s):
    return re.sub(rf"[{re.escape(string.punctuation)}]", " ", s.lower()).split()
def overlap(h, r):
    from collections import Counter
    hc, rc = Counter(toks(h)), Counter(toks(r))
    return round((sum((hc & rc).values()) / len(rc)) if rc else 0.0, 3)
ok = True
for r in refs:
    o = overlap(capt, r)
    status = "PASS" if o >= 0.80 else "FAIL"
    if o < 0.80:
        ok = False
    print(f"  [{status}] fuzzy {o:.2f} vs {r!r}")
print(f"  captured text: {capt!r}")
sys.exit(0 if ok else 1)
PY

# --- criterion 2 specifically: BOTH PAUSE halves (the post-3s-pause half is the regression) ---
CRIT2_OK=0
"$PY" - "$typed" "$PAUSE_A" "$PAUSE_B" <<'PY' || CRIT2_OK=1
import re, string, sys
capt = sys.argv[1]
refs = sys.argv[2:]
def toks(s):
    return re.sub(rf"[{re.escape(string.punctuation)}]", " ", s.lower()).split()
def overlap(h, r):
    from collections import Counter
    hc, rc = Counter(toks(h)), Counter(toks(r))
    return round((sum((hc & rc).values()) / len(rc)) if rc else 0.0, 3)
ok = True
for label, r in (("PAUSE_A (pre-pause)", refs[0]), ("PAUSE_B (post-3s-pause)", refs[1])):
    o = overlap(capt, r)
    if o < 0.80:
        ok = False
    print(f"  [criterion 2 {'PASS' if o >= 0.80 else 'FAIL'}] {label}: fuzzy {o:.2f}")
sys.exit(0 if ok else 1)
PY

# --- criterion 3: live partials observed in state.json DURING playback ---
CRIT3_OK=0
if [ -s "$WORK/partials.log" ]; then
  CRIT3_OK=0
  echo "  [PASS] criterion 3: live partials observed in state.json ($(wc -l < "$WORK/partials.log") snapshots)"
else
  CRIT3_OK=1
  echo "  [FAIL] criterion 3: no non-empty partial snapshot during playback"
fi

# --- criterion 4: toggle-off gates output (G-CAPTURE diff) ---
before="$typed"
"$VOICECTL" stop >/dev/null || die "voicectl stop failed"
echo "listening disarmed; playing utt_simple.wav (must type NOTHING)..."
pw-cat -p --target "$SINK" "$SIMPLE_WAV" || die "pw-cat playback simple (toggle-off) failed"
sleep 4                          # let any in-flight final appear if the gate leaked
after="$(capture_pane)"
CRIT4_OK=0
if [ "$before" = "$after" ]; then
  echo "  [PASS] criterion 4: nothing typed after voicectl stop (toggle-off gates)"
else
  CRIT4_OK=1
  echo "  [FAIL] criterion 4: text changed after stop (gate leaked)"
  echo "           before: ${before@Q}"
  echo "           after:  ${after@Q}"
fi

# --- belt-and-suspenders: flush cat>file + cross-check (G-CAPTURE) ---
"$TMUX_BIN" send-keys -t "$TMUX_SESS" C-d 2>/dev/null || true
sleep 0.5
echo "  cat>file cross-check: $(cat "$CAPFILE" 2>/dev/null | tr '\n' ' ')"

# --- result ---
OVERALL=0
[ "$ALLREFS_OK" = 0 ] || OVERALL=1
[ "$CRIT2_OK" = 0 ]   || OVERALL=1
[ "$CRIT3_OK" = 0 ]   || OVERALL=1
[ "$CRIT4_OK" = 0 ]   || OVERALL=1

if [ "$OVERALL" = 0 ]; then
  echo "=== E2E PASS (criteria 2,3,4 + all 5 segments) ==="
  exit 0
else
  echo "=== E2E FAIL (see above; daemon log: $WORK/daemon.log) ==="
  tail -n 20 "$WORK/daemon.log" 2>/dev/null || true
  exit 1
fi
