# Scout: launch_daemon.sh / status.sh / install.sh / systemd unit (from scout subagent)

## 1. voice_typing/status.sh — no exit 0; jq exit code propagates (Issue 2)

**Path:** `voice_typing/status.sh` (POSIX `#!/bin/sh`, 39 lines)

- **No `set -e`, no `exit` command** anywhere (grep confirms).
- **Last line is the jq call** (lines 34-39), NO trailing `exit 0`.
- **Exit code = jq's exit code**: 2 (missing file), 5 (corrupt JSON).
- **Fix anchor:** append `exit 0` after line 39.
- Header comment lines 23-25: "NO `set -e`... must print an empty line with exit 0 (never abort)."

The jq call (lines 34-39):
```sh
34  jq -r --arg max "$MAX" '
35    (if (.listening // false) then "🎤 " + (.partial // "") else "" end) as $line
36    | if ($line | length) > ($max | tonumber)
37      then $line[:(($max | tonumber) - 1)] + "…"
38      else $line end
39  ' "$STATE" 2>/dev/null
```

## 2. voice_typing/launch_daemon.sh — no offline exports; exec is last line (Issue 1)

**Path:** `voice_typing/launch_daemon.sh` (`#!/usr/bin/env bash`, 60 lines)

- **Does NOT export `HF_HUB_OFFLINE` or `TRANSFORMERS_OFFLINE`.** Zero matches.
- **Only `export` in file:** `LD_LIBRARY_PATH` at line 53.
- **`exec "$PY" -m voice_typing.daemon "$@"` is line 60** (final line).
- **Fix anchor:** insert the two export lines between line 58 (`fi`) and line 60 (`exec`).

```sh
53      export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
...
58  fi
59
60  exec "$PY" -m voice_typing.daemon "$@"
```

## 3. systemd/voice-typing.service — no Environment=; ExecStart → launch_daemon.sh

**Path:** `systemd/voice-typing.service` (40 lines)

- **No active `Environment=` directive** (only in comments).
- Active directives: `ExecStartPre=...import-environment WAYLAND_DISPLAY DISPLAY` (line 19),
  `ExecStart=.../launch_daemon.sh` (line 39), `Restart=on-failure` (line 40).
- **"DO NOT add Environment=LD_LIBRARY_PATH" comment at line 29-31.**

## 4. install.sh — step 4/7 restart + step 7/7 summary (Issue 4)

**Path:** `install.sh` (~165 lines, `set -euo pipefail`)

- **Step 4/7 restart at line 116:** `systemctl --user restart voice-typing.service`
- **Step 6/7 is-active check at line 142-146.**
- **Step 7/7 summary at line 149+** — the final usage print.
- **Post-restart journal grep would slot after line 116**, before line 142.
- **Summary line would slot in step [7/7]** (~line 149).

## 5. tests/test_systemd_unit.py — static drift-guard pattern (for new offline test)

**Path:** `tests/test_systemd_unit.py` (95 lines)

- Reads unit file **as text**, filters to non-comment, non-empty directive lines.
- Helper: `_unit_lines()` → `list[str]`.
- **3 existing tests:**
  1. `test_execstart_points_at_launch_daemon_wrapper` — ExecStart ends with launch_daemon.sh
  2. `test_execstartpre_imports_wayland_and_display_env` — ExecStartPre has import-environment + WAYLAND_DISPLAY + DISPLAY
  3. `test_restart_on_failure` — line == "Restart=on-failure"

**New-test opportunity:** `read_text()` on launch_daemon.sh, assert it contains
`export HF_HUB_OFFLINE=1` and `export TRANSFORMERS_OFFLINE=1`.

## 6. tests/test_idle_and_gpu.sh — the G-OFFLINE masking (lines 202-209)

```sh
206  export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1   ← THE MASKING
207  XDG_CONFIG_HOME="$WORK/config" "$LAUNCH" > "$WORK/daemon.log" 2>&1 &
208  DAEMON_PID=$!
209  echo "daemon launched OFFLINE (HF_HUB_OFFLINE=1) pid=$DAEMON_PID..."
```

**Masking CONFIRMED:** line 206 sets offline vars in the test shell BEFORE launching.
Test proves daemon CAN run offline, but NOT that the PRODUCTION path runs offline.
Fix: remove line 206's pre-set, rely on launch_daemon.sh exports, add journal grep.

## 7. Existing tests for status.sh — NONE

`grep -rn 'status\.sh' tests/` → only a comment in `test_feedback.py:351`.
No test asserts status.sh exit code or output. A new test is needed.
