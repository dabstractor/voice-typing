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
#      set -g status-right "#(/home/<you>/projects/voice-typing/voice_typing/status.sh)"
#
#  Result: while listening, status-right shows "🎤 <current text>" — live partials as you
#  speak, then the finalized text once it is typed (record_final writes the final back into
#  the partial so the status matches the screen). Truncated to MAX (60) codepoints with a
#  trailing "…" on overflow; blank when idle. Widen it with:
#      tmux set-environment VOICE_TYPING_STATUS_MAX 80
#
# POSIX sh + jq only. NO `set -e`: a missing or malformed state.json must print an empty
# line with exit 0 (never abort). tmux's #(...) substitution captures stdout and IGNORES the
# exit code (so the empty line alone keeps status-right blank) — but a non-tmux caller that
# checks $? would see jq's non-zero exit (2 = missing file, 5 = corrupt JSON); the explicit
# `exit 0` at the end honors the documented zero-exit contract for every caller. The
# `2>/dev/null` + the jq `// ""` defaults guarantee empty-on-failure stdout.

STATE="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json"

# Render "🎤 <partial>" while listening (prefixed with ⚡ in LITE mode, PRD §4.2ter), else "".
# Truncate the whole line to MAX codepoints; on overflow drop the last char and append "…" so
# a long utterance is visibly cut rather than silently chopped. jq slicing is codepoint-based, so
# the 4-byte emoji glyphs count as 1 each.
# MAX defaults to 60; override for your status line with `tmux set-environment … MAX N`.
MAX="${VOICE_TYPING_STATUS_MAX:-60}"
jq -r --arg max "$MAX" '
  (if (.listening // false)
     then ((if (.mode == "lite") then "⚡" else "" end) + "🎤 " + (.partial // ""))
     else "" end) as $line
  | if ($line | length) > ($max | tonumber)
    then $line[:(($max | tonumber) - 1)] + "…"
    else $line end
' "$STATE" 2>/dev/null

# Issue 2 fix: always exit 0. jq exits non-zero on a missing (2) or corrupt (5) state.json; without this
# the script's exit code would be jq's, violating the "exit 0 (never abort)" contract documented above.
# stdout is already empty-on-failure (2>/dev/null + the jq // "" defaults); this zeroes the exit code only.
exit 0
