#!/usr/bin/env bash
#
# install.sh — idempotent setup entrypoint for voice-typing (PRD §5, §4.9; P1.M6.T1.S1).
#
# WHAT THIS IS
#   The single script a user runs to go from `git clone` to a running, systemd-managed,
#   UN-ARMED voice-typing daemon. Re-runnable: a 2nd run refreshes deps, skips already-cached
#   models, never overwrites the user's XDG config, and never errors on an already-enabled unit.
#
# STEPS  (PRD §5 + §4.9 + the item contract)
#   (1) cd to repo root
#   (2) uv sync                              -> creates/refreshes .venv/
#   (3) cuda smoke under launch_daemon.sh env-> prints VERDICT=cuda-ok|cpu-fallback-required
#   (4) prefetch models                      -> ~/.cache/huggingface (idempotent; warn-only on fail)
#   (5) install + daemon-reload + enable + restart the systemd user unit
#   (6) copy config.toml to $XDG_CONFIG_HOME/voice-typing/ IF ABSENT
#   (7) print usage + tmux status snippet + Hyprland source instruction
#
# The daemon starts NOT-listening (PRD §4.9) — it never hot-mics on boot; `voicectl toggle` arms it.
#
# This script's stdout IS the user-facing install/usage quick-start (Mode A docs). README (P2.M1.T2.S1)
# copies the usage/tmux/hypr snippets verbatim — keep them stable.
#
# FULL PATHS are used for uv/python because the user's zsh aliases them (PRD §2). This is bash, not zsh.
set -euo pipefail

# --- explicit tool paths (zsh-alias hazard; PRD §2) ---
UV="/home/dustin/.local/bin/uv"

# --- repo root, CWD-independent (launch_daemon.sh SCRIPT_DIR idiom) ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$SCRIPT_DIR"
cd "$REPO"
PY="$REPO/.venv/bin/python"

# --- preflight: we need a login session for `systemctl --user` + the daemon's own XDG_RUNTIME_DIR ---
if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
  echo "install.sh: XDG_RUNTIME_DIR is not set — run this from a login session (systemctl --user needs it)." >&2
  exit 1
fi
command -v "$UV" >/dev/null 2>&1 || { echo "install.sh: uv not found at $UV" >&2; exit 1; }
command -v systemctl >/dev/null 2>&1 || { echo "install.sh: systemctl not found" >&2; exit 1; }

# --- preflight: PyAudio needs the portaudio system library (PRD §5 step 2). On a fresh
#     clone without it, uv sync installs the wheel but the daemon later fails at PyAudio
#     dlopen with a confusing "NOT active — check journalctl". Catch it here with an
#     actionable message. pacman -Q returns non-zero when the package is absent; the
#     `if !`/`elif !` guards keep its return code from aborting the script under set -e.
#     Non-Arch hosts (no pacman) get a warn-and-continue. ---
if ! command -v pacman >/dev/null 2>&1; then
  echo "install.sh: pacman not found — skipping portaudio check (non-Arch host). Install PyAudio's portaudio dependency manually." >&2
elif ! pacman -Q portaudio >/dev/null 2>&1; then
  echo "install.sh: portaudio not installed (PyAudio system dependency). Run: sudo pacman -S --noconfirm portaudio, then re-run ./install.sh" >&2
  exit 1
fi

# XDG_CONFIG_HOME, mirroring voice_typing/config.py (unset/empty -> ~/.config).
XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

# --- (2) uv sync -----------------------------------------------------------------
echo "==> [1/7] uv sync"
"$UV" sync
[ -x "$PY" ] || { echo "install.sh: $PY missing after uv sync" >&2; exit 1; }

# Reproduce launch_daemon.sh's LD_LIBRARY_PATH export for the cuda smoke. cuda_check.py MUST NOT set it
# itself (the dynamic linker reads it only at exec); the sanctioned manual-run path is "reproduce that
# wrapper's LD_LIBRARY_PATH export in the shell first" (cuda_check.py docstring). Same python one-liner
# as launch_daemon.sh (nvidia.*.lib namespace-package __path__[0] resolver).
_setup_cuda_libs() {
  if CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b
def _d(m):
    f=getattr(m,"__file__",None)
    return os.path.dirname(f) if f else next(iter(m.__path__))
print(_d(a)+":"+_d(b))' 2>/dev/null)"; then
    export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  else
    echo "install.sh: WARNING — nvidia wheels not importable; running cuda smoke without LD_LIBRARY_PATH (cpu-fallback expected)." >&2
  fi
}

# --- (3) cuda smoke (print verdict; exit 1 = cpu-fallback = VALID, do NOT abort) --
echo "==> [2/7] CUDA smoke"
_setup_cuda_libs
# cuda_check exits 1 on cpu-fallback-required (a valid degraded mode) — capture, never abort.
SMOKE=""
if ! SMOKE="$("$PY" -m voice_typing.cuda_check 2>&1)"; then
  :  # handled via VERDICT= below
fi
printf '%s\n' "$SMOKE" | sed 's/^/    /'
VERDICT="$(printf '%s\n' "$SMOKE" | sed -n 's/^VERDICT=//p')"
case "$VERDICT" in
  cuda-ok)                 echo "    -> GPU available: daemon will use CUDA." ;;
  cpu-fallback-required)   echo "    -> No usable CUDA: daemon will run in CPU mode (slower; functional)." ;;
  *) echo "    -> WARNING: could not parse cuda_check VERDICT." >&2 ;;
esac

# --- (4) prefetch models (idempotent; warn + continue — daemon lazy-downloads on miss) -
echo "==> [3/7] prefetch models"
if ! "$PY" -m voice_typing.prefetch; then
  echo "install.sh: WARNING — prefetch reported a core-model failure; the daemon will download missing models on first run." >&2
fi

# --- (5) install + daemon-reload + enable + restart the systemd user unit -------------
echo "==> [4/7] install systemd user service"
SRC_UNIT="$REPO/systemd/voice-typing.service"
if [ ! -f "$SRC_UNIT" ]; then
  echo "install.sh: $SRC_UNIT missing — create it first (P1.M6.T1.S2)." >&2
  exit 1
fi
USER_UNIT_DIR="$XDG_CONFIG_HOME/systemd/user"
mkdir -p "$USER_UNIT_DIR"
cp "$SRC_UNIT" "$USER_UNIT_DIR/voice-typing.service"
systemctl --user daemon-reload
systemctl --user enable voice-typing.service
# restart (not start): starts a stopped unit AND applies a freshly-copied unit to a running one.
# timestamp captured BEFORE restart so the offline journal grep below sees only this run
RESTART_TS="$(date '+%Y-%m-%d %H:%M:%S')"
systemctl --user restart voice-typing.service

# Remove a stale realtimesst.log from a prior run (validation Issue 3; housekeeping). The
# no_log_file=True kwarg (PRD §4.2) makes the CURRENT daemon write only to stderr→journald, but
# runs before that fix (or without it) could leave a multi-MiB realtimesst.log in the repo. It is
# gitignored (*.log) so it is never committed; this just clears the disk clutter. The current
# daemon never appends to it, so removing it is always safe.
if [ -f "$REPO/realtimesst.log" ]; then
  rm -f "$REPO/realtimesst.log"
  echo "    removed stale realtimesst.log"
fi

# Offline regression guard (bugfix Issue 1 / Issue 4): launch_daemon.sh now exports
# HF_HUB_OFFLINE=1 + TRANSFORMERS_OFFLINE=1 (P1.M1.T1.S1), so the restarted daemon must load
# models from cache with ZERO network calls to huggingface.co. Wait for the control socket to
# answer (it binds AFTER recorder construction in main() -> any HF HTTP call is already logged),
# flush journald, then grep the post-restart journal and WARN (stderr, NOT fatal) on any match.
# The hard config gate is tests/test_systemd_unit.py::test_launch_daemon_exports_offline_vars;
# this is the install-time runtime surface. set-e-safe: the grep pipeline is in an `if`
# condition (errexit-exempt); a journalctl failure yields no match -> clean branch, no abort
# (same idiom as the cuda-smoke `if !` above).
for _ in $(seq 1 60); do                  # up to ~30s for cold CUDA init + 2 model loads
  if "$REPO/.venv/bin/voicectl" status >/dev/null 2>&1; then break; fi
  sleep 0.5
done
sleep 2                                   # let journald flush the startup HTTP lines
if journalctl --user -u voice-typing --since "$RESTART_TS" --no-pager 2>/dev/null \
    | grep -q 'HTTP Request: GET https://huggingface.co'; then
  echo "install.sh: WARNING — daemon made network calls to huggingface.co after restart;" \
       "offline exports (HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE) may be missing from launch_daemon.sh." >&2
else
  echo "    offline check: no huggingface.co network calls after restart (HF_HUB_OFFLINE=1 active)"
fi

# --- (6) copy config.toml to XDG IF ABSENT (never overwrite the user's edits) ---------
echo "==> [5/7] config"
CFG_DIR="$XDG_CONFIG_HOME/voice-typing"
mkdir -p "$CFG_DIR"
if [ ! -f "$CFG_DIR/config.toml" ]; then
  cp "$REPO/config.toml" "$CFG_DIR/config.toml"
  echo "    installed $CFG_DIR/config.toml"
else
  echo "    kept existing $CFG_DIR/config.toml (not overwritten)"
fi

# --- (7) print usage + tmux snippet + hypr instruction --------------------------------
echo "==> [6/7] daemon status"
# Give systemd a beat to mark the unit active, then report.
if systemctl --user is-active --quiet voice-typing.service; then
  echo "    voice-typing.service: active"
else
  echo "    voice-typing.service: NOT active — check 'journalctl --user -u voice-typing -e'" >&2
fi

echo
echo "==> [7/7] done — voice-typing installed"
echo "daemon : running and NOT listening (no hot-mic on boot). Run 'voicectl toggle' to arm the mic."
echo "CUDA   : ${VERDICT:-unknown}"
echo "offline: daemon runs fully local (HF_HUB_OFFLINE=1 via launch_daemon.sh) — no network at runtime"
echo
echo "usage  : $REPO/.venv/bin/voicectl toggle|start|stop|status|quit"
echo "          (bind SUPER+ALT+D -> voicectl toggle; see the Hyprland note below)"
echo
echo "tmux status (add these TWO lines to ~/.tmux.conf — we never edit it for you):"
echo '  set -g status-interval 1'
echo "  set -g status-right \"#($REPO/voice_typing/status.sh)\""
echo
echo "Hyprland — source the repo's hypr-binds.conf from ~/.config/hypr/hyprland.conf (add this line):"
echo "  source = $REPO/hypr-binds.conf"
echo
echo "logs   : journalctl --user -u voice-typing -f"
echo "config : $CFG_DIR/config.toml"
