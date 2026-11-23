#!/usr/bin/env bash
# tests/d1_duck_evidence.sh — D1 (PRD §4.2quinquies) live acceptance evidence (P1.M2.T4.S1).
#
# Records re-runnable proof for the five §4.2quinquies acceptance scenarios against REAL sandbox
# daemons (one per duck_mode — the ducker is built once at init from cfg):
#   Phase 1  default/mpris (config with NO duck_mode key → flipped default engages):
#            a disposable MPRIS player pauses at arm (Δt < 1.5 s) and resumes at stop; a player
#            the USER resumed mid-dictation is never fought (rule c); a user-paused player
#            (never Playing at arm → never in the ledger) stays paused.
#   Phase 2  duck_mode="volume" on a DISPOSABLE null-sink: 40% → 15% at arm; a mid-arm user
#            change to 60% is KEPT at stop; a clean second cycle restores EXACTLY 40%.
#   Phase 3  duck_mode="off": ZERO "ducking:" journal lines across an arm/disarm cycle
#            (byte-identical to pre-D1 behavior).
#
# DISPOSABLE MEDIA TARGET: this host's mpv ships NO MPRIS plugin (verified: ~/.config/mpv/scripts
# has no mpv-mpris; mpv publishes no bus name) and VLC's instance registration is not
# playerctl-controllable. The script therefore launches a minimal GLib MPRIS stub (system
# python3/gi, heredoc'd below) owning UNIQUE bus names org.mpris.MediaPlayer2.vtdummy<N>. It
# answers exactly what voice_typing/ducking_mpris.py drives (busctl get-property PlaybackStatus /
# CanPause; call Pause/Play) and dies on its recorded PID. Operator media (e.g. a playing browser
# tab) is STILL paused at arm and resumed at stop by the real ducker — run when media is idle, or
# accept the transient pause/resume (correct behavior; noted in tests/D1_DUCK_EVIDENCE.md).
#
# SAFETY DISCIPLINE (AGENTS.md + PRP CRITICAL #3/#5/#6):
#   - sandbox daemons run with own XDG_RUNTIME_DIR/XDG_CONFIG_HOME → own control socket + state
#     file (voicectl in that env can NEVER reach the user's systemd daemon); sandbox configs set
#     output.backend="null" so an automated run can never type into the operator's windows;
#   - busctl --user / wpctl still need the REAL session bus + PipeWire: the sandbox runtime dir
#     gets SYMLINKS to the real bus/pipewire sockets (verified on this host) and
#     DBUS_SESSION_BUS_ADDRESS is pinned defensively;
#   - the systemd unit is STOPPED around the run (double-VRAM avoidance, test_idle_and_gpu.sh
#     precedent) and restarted in the trap only if it was active;
#   - teardown is by RECORDED PID only — never `pkill -f voice-typing` (that kills the user's
#     unit; it is wedge-recovery, not scripted teardown);
#   - the volume tier mutates the DEFAULT SINK: a disposable module-null-sink is loaded and made
#     default first; the original default is restored and the module is unloaded BY RECORDED
#     INDEX in the trap (never `unload-module module-null-sink` by name — it nukes ALL);
#   - every voicectl call is `timeout 30`-wrapped (control socket has no read timeout); the
#     script itself runs under `timeout 900`; log excerpts are bounded (head -40; /tmp is tmpfs).
#
# Usage:  timeout 900 bash tests/d1_duck_evidence.sh     # exit 0 iff every scenario PASSes
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VCTL="$REPO/.venv/bin/voicectl"
DAEMON_BIN="$REPO/.venv/bin/voice-typing-daemon"
UID_N="$(id -u)"
REAL_RUNTIME="/run/user/$UID_N"
REAL_BUS="unix:path=$REAL_RUNTIME/bus"

PASS=0
FAIL=0
SB=""
OLD_DEFAULT_SINK=""
NULL_SINK_NAME="vt_d1_null"
NULL_SINK_MODULE_IDX=""
UNIT_WAS_ACTIVE="no"
PLAYER_PIDS=()
DAEMON_PIDS=()
RUN_DIR=""            # set by start_sandbox_daemon (CALLER-SHELL global — functions that mutate
LAST_DAEMON_PID=""    # state must NOT be invoked via $(...) command substitution: the subshell's
PLAYER_NAME=""        # array/variable writes are lost; that bug leaked sandbox daemons once)
declare -a EVIDENCE_LINES=()

pass() { echo "PASS  $*"; PASS=$((PASS + 1)); EVIDENCE_LINES+=("PASS  $*"); }
fail() { echo "FAIL  $*"; FAIL=$((FAIL + 1)); EVIDENCE_LINES+=("FAIL  $*"); }
note() { echo "---  $*"; EVIDENCE_LINES+=("---  $*"); }

record_journal() {  # bounded journal excerpt -> stdout + evidence buffer
    local log="$1" pattern="$2" label="$3"
    local line
    line=$(grep -m1 "$pattern" "$log" 2>/dev/null || true)
    if [ -n "$line" ]; then note "$label: $line"; else note "$label: (line not found: $pattern)"; fi
}

cleanup() {
    for pid in "${PLAYER_PIDS[@]:-}"; do
        [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null
    done
    for pid in "${DAEMON_PIDS[@]:-}"; do
        [ -n "$pid" ] && kill -TERM "$pid" 2>/dev/null
    done
    sleep 1
    for pid in "${DAEMON_PIDS[@]:-}"; do
        [ -n "$pid" ] && kill -KILL "$pid" 2>/dev/null
    done
    # volume-tier exposure window: restore the operator's default sink + unload BY INDEX
    if [ -n "$OLD_DEFAULT_SINK" ]; then
        pactl set-default-sink "$OLD_DEFAULT_SINK" 2>/dev/null
    fi
    if [ -n "$NULL_SINK_MODULE_IDX" ]; then
        pactl unload-module "$NULL_SINK_MODULE_IDX" 2>/dev/null
    fi
    # double-VRAM avoidance: only restart the unit if the script stopped it
    if [ "$UNIT_WAS_ACTIVE" = "yes" ]; then
        systemctl --user start voice-typing 2>/dev/null
    fi
    [ -n "$SB" ] && rm -rf "$SB"
    return 0
}
trap cleanup EXIT

# ---------------------------------------------------------------- Phase 0: preflight
for bin in "$VCTL" "$DAEMON_BIN" /usr/bin/python3 /usr/bin/busctl /usr/bin/pactl /usr/bin/wpctl; do
    if [ ! -x "$bin" ]; then
        echo "FAIL  preflight: missing binary $bin"
        echo "      operator-checklist fallback: see tests/D1_DUCK_EVIDENCE.md (operator checklist)"
        exit 2
    fi
done
if ! /usr/bin/python3 -c "import gi" 2>/dev/null; then
    echo "FAIL  preflight: system python3 lacks PyGObject (no MPRIS stub possible)"
    echo "      operator-checklist fallback: see tests/D1_DUCK_EVIDENCE.md (operator checklist)"
    exit 2
fi
OLD_DEFAULT_SINK="$(pactl get-default-sink 2>/dev/null || true)"
if [ -z "$OLD_DEFAULT_SINK" ]; then fail "preflight: could not read the default sink"; exit 2; fi
UNIT_WAS_ACTIVE="no"
[ "$(systemctl --user is-active voice-typing 2>/dev/null)" = "active" ] && UNIT_WAS_ACTIVE="yes"
if [ "$UNIT_WAS_ACTIVE" = "yes" ]; then
    systemctl --user stop voice-typing   # one CUDA model set at a time (test_idle_and_gpu.sh precedent)
    sleep 1
fi
SB="$(mktemp -d /tmp/vt-d1-duck.XXXXXX)"   # tmpfs scratch — the trap removes it
cat > "$SB/mpris_stub.py" <<'PYEOF'
"""Minimal disposable MPRIS player for d1_duck_evidence.sh (system python3 + PyGObject).

Owns a UNIQUE bus name (argv[1], e.g. org.mpris.MediaPlayer2.vtdummy1), reports
PlaybackStatus="Playing", and honours Pause()/Play()/PlayPause() exactly as
voice_typing/ducking_mpris.py drives real players (busctl get-property + call). Runs until
killed (the script tears it down by its recorded PID). Touches ONLY the session bus.
"""
import sys
from gi.repository import GLib, Gio

NAME = sys.argv[1]
STATUS = {"value": "Playing"}

XML = """
<node>
  <interface name="org.mpris.MediaPlayer2.Player">
    <property name="PlaybackStatus" type="s" access="read"/>
    <property name="CanPause" type="b" access="read"/>
    <property name="CanPlay" type="b" access="read"/>
    <method name="Pause"/>
    <method name="Play"/>
    <method name="PlayPause"/>
  </interface>
  <interface name="org.mpris.MediaPlayer2">
    <property name="Identity" type="s" access="read"/>
    <property name="CanQuit" type="b" access="read"/>
  </interface>
</node>
"""


def on_method_call(conn, sender, path, iface, method, params, invocation):
    STATUS["value"] = "Paused" if method == "Pause" else "Playing"
    invocation.return_value()


def on_get_property(conn, sender, path, iface, prop):
    if prop == "PlaybackStatus":
        return GLib.Variant("s", STATUS["value"])
    if prop in ("CanPause", "CanPlay", "CanQuit"):
        return GLib.Variant("b", True)
    if prop == "Identity":
        return GLib.Variant("s", NAME)
    return None


def on_name_lost(*_a):
    sys.stderr.write("mpris-stub: lost the bus name; exiting\n")
    sys.exit(1)


info = Gio.DBusNodeInfo.new_for_xml(XML)
conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
for iface in info.interfaces:
    conn.register_object(
        "/org/mpris/MediaPlayer2", iface, on_method_call, on_get_property, None
    )
Gio.bus_own_name(
    Gio.BusType.SESSION, NAME, Gio.BusNameOwnerFlags.NONE, None, None, on_name_lost
)
GLib.MainLoop().run()
PYEOF
echo "== Phase 0: preflight OK (scratch=$SB, default-sink=$OLD_DEFAULT_SINK, unit was active=$UNIT_WAS_ACTIVE)"

# ---------------------------------------------------------------- helpers
start_sandbox_daemon() {  # $1=phase-n  $2=extra config lines ("" for the default/mpris phase).
    # Sets RUN_DIR + LAST_DAEMON_PID caller-shell globals (NEVER call this via $(...): the
    # state writes — DAEMON_PIDS bookkeeping — would be lost in the subshell).
    local n="$1" extra="$2"
    local run_dir="$SB/run-$n" cfg_dir="$SB/cfg-$n"
    mkdir -p "$run_dir/voice-typing" "$cfg_dir/voice-typing"
    # bridge the REAL session bus + PipeWire into the sandbox runtime dir (busctl --user / wpctl)
    ln -sfn "$REAL_RUNTIME/bus" "$run_dir/bus"
    ln -sfn "$REAL_RUNTIME/pipewire-0" "$run_dir/pipewire-0"
    ln -sfn "$REAL_RUNTIME/pipewire-0.lock" "$run_dir/pipewire-0.lock" 2>/dev/null
    {
        echo '[output]'
        echo 'backend = "null"'                    # CRITICAL: never type into the operator's windows
        echo ''
        echo '[asr]'
        echo 'auto_stop_idle_seconds = 0.0'        # auto-disarm must not race the scenario
        if [ -n "$extra" ]; then echo "$extra"; fi # e.g. '[audio]' + 'duck_mode = "volume"'
    } > "$cfg_dir/voice-typing/config.toml"
    XDG_RUNTIME_DIR="$run_dir" XDG_CONFIG_HOME="$cfg_dir" DBUS_SESSION_BUS_ADDRESS="$REAL_BUS" \
        setsid "$DAEMON_BIN" >> "$SB/daemon-$n.log" 2>&1 &disown
    local pid=$!
    DAEMON_PIDS+=("$pid")
    LAST_DAEMON_PID="$pid"
    local i=0
    until XDG_RUNTIME_DIR="$run_dir" timeout 15 "$VCTL" status >/dev/null 2>&1; do
        i=$((i + 1)); [ "$i" -gt 150 ] && { echo "FAIL  daemon-$n never became ready"; return 1; }
        sleep 0.2
    done
    RUN_DIR="$run_dir"
    return 0
}

stop_sandbox_daemon() {  # $1=run-dir  $2=daemon pid — recorded-PID teardown only
    local run_dir="$1" pid="$2"
    XDG_RUNTIME_DIR="$run_dir" timeout 30 "$VCTL" quit >/dev/null 2>&1
    sleep 1
    kill -TERM "$pid" 2>/dev/null
    sleep 1
    kill -KILL "$pid" 2>/dev/null
}

launch_player() {  # $1=N -> sets PLAYER_NAME (caller-shell global; no $(...) — see start_sandbox_daemon)
    local n="$1"
    local name="org.mpris.MediaPlayer2.vtdummy$n"
    XDG_RUNTIME_DIR="$REAL_RUNTIME" DBUS_SESSION_BUS_ADDRESS="$REAL_BUS" \
        setsid /usr/bin/python3 "$SB/mpris_stub.py" "$name" >> "$SB/player-$n.log" 2>&1 &disown
    local pid=$!
    PLAYER_PIDS+=("$pid")
    local i=0
    until [ "$(player_status "$name")" = "Playing" ] || [ "$i" -gt 50 ]; do i=$((i + 1)); sleep 0.1; done
    if [ "$(player_status "$name")" = "Playing" ]; then PLAYER_NAME="$name"; return 0; fi
    PLAYER_NAME=""
    return 1
}

player_status() {  # the EXACT read the ducker performs (busctl get-property, quoted value)
    XDG_RUNTIME_DIR="$REAL_RUNTIME" /usr/bin/busctl --user get-property "$1" \
        /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player PlaybackStatus 2>/dev/null \
        | grep -oE '"(Playing|Paused|Stopped)"' | head -1 | tr -d '"'
}

user_pause() {  # simulate the USER pausing a player (the ducker's own verb)
    XDG_RUNTIME_DIR="$REAL_RUNTIME" /usr/bin/busctl --user call "$1" \
        /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player Pause >/dev/null 2>&1
}

user_play() {
    XDG_RUNTIME_DIR="$REAL_RUNTIME" /usr/bin/busctl --user call "$1" \
        /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player Play >/dev/null 2>&1
}

wait_status() {  # $1=player  $2=expected  $3=max-tenths -> echoes elapsed ms; rc 0 iff seen
    local player="$1" want="$2" max="$3" i=0 t0 now
    t0=$(date +%s%N)
    while :; do
        [ "$(player_status "$player")" = "$want" ] && { now=$(date +%s%N); echo $(( (now - t0) / 1000000 )); return 0; }
        i=$((i + 1)); [ "$i" -gt "$max" ] && { echo "-1"; return 1; }
        sleep 0.1
    done
}

wait_log() {  # $1=log  $2=pattern  $3=max-tenths (default 50 = 5 s) -> rc 0 iff the pattern appears.
    # The engage/release journal lines are written by the ASYNC ducking worker — they can land
    # ~100 ms–1 s AFTER the arm/stop command returns, so assertions must poll, not instant-grep.
    local log="$1" pattern="$2" max="${3:-50}" i=0
    while :; do
        grep -q "$pattern" "$log" 2>/dev/null && return 0
        i=$((i + 1)); [ "$i" -gt "$max" ] && return 1
        sleep 0.1
    done
}

# ---------------------------------------------------------------- Phase 1: default/mpris
echo "== Phase 1: default (no duck_mode key -> flipped default engages; MPRIS pause/resume + sovereignty)"
RUN1=""; DPID1=""
start_sandbox_daemon 1 "" || { fail "phase1 daemon ready"; exit 1; }
RUN1="$RUN_DIR"; DPID1="$LAST_DAEMON_PID"
launch_player 1; P1="$PLAYER_NAME"; launch_player 2; P2="$PLAYER_NAME"; launch_player 3; P3="$PLAYER_NAME"
if [ -z "$P1" ] || [ -z "$P2" ] || [ -z "$P3" ]; then fail "phase1 stub players launched"; exit 1; fi
user_pause "$P3"; sleep 0.3                                   # S2: a user-paused player (never Playing at arm)
[ "$(player_status "$P1")" = "Playing" ] || { fail "phase1 p1 Playing before arm"; exit 1; }
T0=$(date +%s%N)
XDG_RUNTIME_DIR="$RUN1" timeout 30 "$VCTL" start >/dev/null 2>&1 || { fail "phase1 arm (voicectl start)"; exit 1; }
DT_MS=$(wait_status "$P1" "Paused" 150)                       # poll ≤15 s; the ASSERT is < 1500 ms
ARM_MS=$(( ($(date +%s%N) - T0) / 1000000 ))
if [ "$DT_MS" -ge 0 ] && [ "$DT_MS" -lt 1500 ]; then
    pass "mpris-pause<=1.5s (paused ${DT_MS}ms after the arm command returned; arm round-trip ${ARM_MS}ms)"
else
    fail "mpris-pause<=1.5s (paused dt=${DT_MS}ms)"
fi
wait_log "$SB/daemon-1.log" "ducking: paused MPRIS player(s):" \
    && pass "mpris-engage-journal-line" || fail "mpris-engage-journal-line"
record_journal "$SB/daemon-1.log" "ducking: paused MPRIS player(s):" "journal"
# S1 sovereignty: the USER resumes p2 mid-dictation -> at release the daemon must NOT fight them
user_play "$P2"; sleep 0.3
[ "$(player_status "$P2")" = "Playing" ] && pass "sovereignty-user-resume-mid-arm" || fail "sovereignty-user-resume-mid-arm (setup)"
XDG_RUNTIME_DIR="$RUN1" timeout 30 "$VCTL" stop >/dev/null 2>&1 || fail "phase1 disarm"
DT2=$(wait_status "$P1" "Playing" 100)
if [ "$DT2" -ge 0 ]; then pass "mpris-resume-at-stop (resumed after ${DT2}ms)"; else fail "mpris-resume-at-stop"; fi
wait_log "$SB/daemon-1.log" "ducking: resumed MPRIS player(s):" \
    && pass "mpris-release-journal-line" || fail "mpris-release-journal-line"
RESUMED_LINE=$(grep -m1 "ducking: resumed MPRIS player(s):" "$SB/daemon-1.log" || true)
if echo "$RESUMED_LINE" | grep -q "vtdummy2"; then
    fail "sovereignty-user-resume-honored (p2 was re-resumed by the daemon)"
else
    pass "sovereignty-user-resume-honored (p2 not in the resumed ledger)"
fi
sleep 0.5
[ "$(player_status "$P3")" = "Paused" ] && pass "sovereignty-user-paused-stays-paused" || fail "sovereignty-user-paused-stays-paused"
record_journal "$SB/daemon-1.log" "ducking: resumed MPRIS player(s):" "journal"
stop_sandbox_daemon "$RUN1" "$DPID1"

# ---------------------------------------------------------------- Phase 2: volume tier
echo "== Phase 2: duck_mode=\"volume\" on a disposable null-sink (15% duck; user sovereignty; exact restore)"
pactl load-module module-null-sink sink_name="$NULL_SINK_NAME" > "$SB/nullsink.out" 2>/dev/null
NULL_SINK_MODULE_IDX=$(grep -oE '[0-9]+' "$SB/nullsink.out" | head -1)
if [ -z "$NULL_SINK_MODULE_IDX" ]; then fail "phase2 null-sink load"; exit 1; fi
pactl set-default-sink "$NULL_SINK_NAME" || { fail "phase2 default-sink swap"; exit 1; }
RUN2=""; DPID2=""
PHASE2_CFG='[audio]
duck_mode = "volume"'
start_sandbox_daemon 2 "$PHASE2_CFG" || { fail "phase2 daemon ready"; exit 1; }
RUN2="$RUN_DIR"; DPID2="$LAST_DAEMON_PID"
set_vol() { wpctl set-volume "$(default_sink_node)" "$1" >/dev/null 2>&1; }
get_vol_pct() { wpctl get-volume "$(default_sink_node)" 2>/dev/null | awk '{printf "%d", $2 * 100 + 0.5}'; }
# This host's wpctl has NO @DEFAULT_AUDIO_TARGET@ placeholder — resolve the DEFAULT SINK's
# concrete node id exactly the way voice_typing/ducking_volume.py does (the '*' line of the
# Sinks block of `wpctl status`) and address it by numeric id.
default_sink_node() {
    wpctl status 2>/dev/null \
        | awk '/Sinks:/{f=1;next} /Sources:|Config:/{f=0} f' \
        | grep -oE '\*\s+[0-9]+\.' | grep -oE '[0-9]+' | head -1
}

set_vol 0.40; sleep 0.5; [ "$(default_sink_node)" ] && [ "$(get_vol_pct)" = "40" ] || fail "phase2 preset 40% (node $(default_sink_node), got $(get_vol_pct)%)"
XDG_RUNTIME_DIR="$RUN2" timeout 30 "$VCTL" start >/dev/null 2>&1 || fail "phase2 arm"
D=0; while [ "$(get_vol_pct)" != "15" ] && [ "$D" -lt 50 ]; do sleep 0.1; D=$((D + 1)); done
[ "$(get_vol_pct)" = "15" ] && pass "volume-duck-15 (40% -> 15% at arm)" || fail "volume-duck-15 (got $(get_vol_pct)%)"
record_journal "$SB/daemon-2.log" "ducking: sink volume" "journal"
set_vol 0.60; sleep 0.3                                        # the USER changes volume mid-dictation
XDG_RUNTIME_DIR="$RUN2" timeout 30 "$VCTL" stop >/dev/null 2>&1 || fail "phase2 disarm"
sleep 1.5
[ "$(get_vol_pct)" = "60" ] && pass "volume-user-60-kept (mid-arm change survives release)" || fail "volume-user-60-kept (got $(get_vol_pct)%)"
grep -q "volume was changed mid-dictation" "$SB/daemon-2.log" \
    && pass "volume-user-journal-line" || fail "volume-user-journal-line"
record_journal "$SB/daemon-2.log" "volume was changed mid-dictation" "journal"

set_vol 0.40; sleep 0.3                                        # second cycle: clean duck + EXACT restore
XDG_RUNTIME_DIR="$RUN2" timeout 30 "$VCTL" start >/dev/null 2>&1 || fail "phase2 arm (cycle 2)"
D=0; while [ "$(get_vol_pct)" != "15" ] && [ "$D" -lt 50 ]; do sleep 0.1; D=$((D + 1)); done
XDG_RUNTIME_DIR="$RUN2" timeout 30 "$VCTL" stop >/dev/null 2>&1 || fail "phase2 disarm (cycle 2)"
D=0; while [ "$(get_vol_pct)" != "40" ] && [ "$D" -lt 50 ]; do sleep 0.1; D=$((D + 1)); done
[ "$(get_vol_pct)" = "40" ] && pass "volume-exact-restore (15% -> exactly 40%)" || fail "volume-exact-restore (got $(get_vol_pct)%)"
record_journal "$SB/daemon-2.log" "restored sink volume" "journal"
stop_sandbox_daemon "$RUN2" "$DPID2"
# end the exposure window ASAP (the trap repeats this on crash paths)
pactl set-default-sink "$OLD_DEFAULT_SINK" 2>/dev/null
pactl unload-module "$NULL_SINK_MODULE_IDX" 2>/dev/null
NULL_SINK_MODULE_IDX=""

# ---------------------------------------------------------------- Phase 3: off
echo "== Phase 3: duck_mode=\"off\" (byte-identical to pre-D1: zero ducking journal lines)"
RUN3=""; DPID3=""
PHASE3_CFG='[audio]
duck_mode = "off"'
start_sandbox_daemon 3 "$PHASE3_CFG" || { fail "phase3 daemon ready"; exit 1; }
RUN3="$RUN_DIR"; DPID3="$LAST_DAEMON_PID"
XDG_RUNTIME_DIR="$RUN3" timeout 30 "$VCTL" start >/dev/null 2>&1 || fail "phase3 arm"
sleep 1
XDG_RUNTIME_DIR="$RUN3" timeout 30 "$VCTL" stop >/dev/null 2>&1 || fail "phase3 disarm"
sleep 0.5
ZERO=$(grep -c "ducking:" "$SB/daemon-3.log" 2>/dev/null)
ZERO=${ZERO:-0}   # missing log file counts as 0; plain grep -c already prints 0 (no || echo — that duplicated the 0)
[ "$ZERO" = "0" ] && pass "off-zero-ducking-lines (arm/disarm cycle logged no ducking: lines)" \
                  || fail "off-zero-ducking-lines (found $ZERO)"
stop_sandbox_daemon "$RUN3" "$DPID3"

# ---------------------------------------------------------------- summary
echo "== Evidence excerpt (bounded; recorded in tests/D1_DUCK_EVIDENCE.md) =="
printf '%s\n' "${EVIDENCE_LINES[@]}"
echo "== Restore checks: default-sink=$(pactl get-default-sink 2>/dev/null) (want $OLD_DEFAULT_SINK); unit=$(systemctl --user is-active voice-typing 2>/dev/null) (was $UNIT_WAS_ACTIVE)"
if [ "$FAIL" -eq 0 ]; then
    echo "ALL $PASS SCENARIOS PASS"
    exit 0
fi
echo "$FAIL SCENARIO(S) FAILED ($PASS passed)"
exit 1
