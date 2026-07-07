#!/bin/sh
# voice_typing/status.sh — tmux status-right helper (PRD §4.6).
#
# Prints a one-line "live partial" snippet for tmux's status-right by jq-reading the
# voice-typing daemon's state.json. Empty output when not listening (so status-right is
# blank when idle). Called every status-interval (1s) by tmux's #(...) substitution.
#
# =====================================================================
#  USER INTEGRATION  (item DOCS: Mode A — this comment IS the tmux doc)
# =====================================================================
#  Add these TWO lines to your ~/.tmux.conf (install.sh prints them; we never edit your
#  tmux.conf for you). Point the path at where this script lives:
#
#      set -g status-interval 1
#      set -g status-right "#(/home/dustin/projects/voice-typing/voice_typing/status.sh)"
#
#  Result: while listening, status-right shows "🎤 <live partial words>" (max 60 chars);
#  when idle it is blank. The partial comes from feedback.py's atomic state.json writes.
#
# POSIX sh + jq + cut only. NO `set -e`: a missing or malformed state.json must print an
# empty line with exit 0 (never abort) — otherwise tmux would show an error string in
# status-right. The `2>/dev/null` + the jq `//` defaults already guarantee empty-on-failure.

STATE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json"

# `// false` / `// "…"` make this safe if a key is absent (older/forward state files).
# `cut -c1-60` truncates to 60 CHARACTERS (not bytes) so the 4-byte 🎤 emoji counts as 1.
jq -r 'if (.listening // false) then "🎤 " + (.partial // "…") else "" end' "$STATE" 2>/dev/null \
  | cut -c1-60
