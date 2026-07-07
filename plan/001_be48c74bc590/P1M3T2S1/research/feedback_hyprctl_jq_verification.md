# Research — P1.M3.T2.S1 feedback.py (state file + hyprctl notify + status.sh)

Verified locally on the target machine (2026-07-06). Authoritative for the PRP.

## 1. hyprctl notify — verified syntax (does NOT trigger a notification)

```
$ command -v hyprctl && hyprctl version | head -1
/usr/bin/hyprctl
Hyprland 0.55.4 ...

$ hyprctl notify --help
usage: hyprctl [flags] notify <icon> <time_ms> <color> <message...>

icon:
    0       → Warning
    1       → Info
    2       → Hint
    3       → Error
    4       → Confused
    5       → Ok
    6 or -1 → No icon
...
$ echo "HIS=${HYPRLAND_INSTANCE_SIGNATURE}"   # set → running under Hyprland
```

CONCLUSIONS (lock into the hyprctl argv):
- `icon == -1` means **"No icon"** (verified) — so the leading glyph in the message
  string IS the visual (● / ✔ / ■). This is why PRD §4.6 embeds glyphs in the message.
- Canonical argv (matches item description verbatim):
  `["hyprctl", "notify", "-1", str(notify_ms), "rgb(88c0d0)", msg]`
- `message...` is variadic but we pass ONE quoted arg (the whole message incl. glyph).
- Hyprland notifications are **NOT replaceable by ID** (PRD §4.6) → notify at most on
  listening-start / each final / listening-stop. NEVER per-partial (would stack-spam).
- Use `check=False` + `try/except (OSError, subprocess.SubprocessError)` → fire-and-forget,
  swallow all errors (missing hyprctl binary when not under Hyprland, etc.).
- Suppress stdout/stderr (`subprocess.DEVNULL`) so hyprctl's `ok` ack doesn't clutter the
  daemon's journald logs (PRD §4.2 logs to stderr/journald).

## 2. status.sh jq query — verified correct

```
$ command -v jq && jq --version
/usr/bin/jq
jq-1.8.1-dirty
```

Query (PRD §4.6, adapted to a helper script): against a sample state.json
`{"listening":true,"phase":"speaking","partial":"this is what i am say","last_final":"...","ts":1.0}`:

| case | output | ok? |
|---|---|---|
| listening=true, partial set | `🎤 this is what i am say` | ✅ |
| listening=true, 200-char partial, `| cut -c1-60` | 60 chars (64 bytes incl. 4-byte emoji + newline) | ✅ |
| listening=false | (empty line) | ✅ |
| FILE MISSING (`2>/dev/null`) | (empty line, exit 0) | ✅ |

- `cut -c1-60` operates on CHARACTERS (not bytes) in this UTF-8 locale → the 🎤 counts as
  1 char, so truncation lands on 60 visible chars. Matches PRD §4.6 verbatim.
- Robust query: `if (.listening // false) then "🎤 " + (.partial // "…") else "" end` —
  the `// false` / `// "…"` defaults make it safe if a key is absent (older state files).
- DEFAULT path resolution in the script (no Python available in tmux status context):
  `${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/voice-typing/state.json` — `:-` treats empty
  XDG_RUNTIME_DIR as unset and falls back to `/run/user/<uid>`.
- DO NOT use `set -e` (a failure must print empty, never abort — tmux would otherwise show
  an error string in status-right). `2>/dev/null` + the pipe to `cut` already yields
  empty-on-failure with exit 0.
- Shebang `#!/bin/sh` (POSIX; tmux `#(...)` runs `/bin/sh`; jq+cut are POSIX).

## 3. Atomic state write — Python stdlib (no research needed, pinned for the implementer)

- `tempfile.mkstemp(dir=<same dir as target>, prefix=".state.", suffix=".tmp")` creates
  the temp file **in the same directory** as the target → `os.replace(tmp, target)` is a
  same-filesystem atomic rename (POSIX guarantee). Cross-dir would NOT be atomic.
- `tempfile.mkstemp` already creates the file mode **0o600** (Python 3 security default) →
  the final state.json (renamed in place) inherits 0o600. No `os.chmod` on the file needed.
- Parent dir: `os.makedirs(directory, exist_ok=True, mode=0o700)` → 0o700 regardless of
  umask (0o700 has no group/other bits for umask to mask). Item: "mkdir 0700". ✅
- `ts` field = `time.time()` (wall-clock epoch, matches the PRD sample 1783718400.123).
- Throttle clock = `time.monotonic()` (monotonic; never wall clock — immune to NTP jumps).
- Throttle: "≥10 Hz max" = min 0.1 s between partial disk writes. Only `update_partial` is
  throttled; `set_phase` / `record_final` / `set_listening` always write (PRD §4.6).

## 4. Test seams (match the established project pattern)

- hyprctl: `import subprocess` + `subprocess.run(...)` in feedback.py → tests
  `monkeypatch.setattr(subprocess, "run", fake)` (IDENTICAL mechanic to the typing_backends
  tests in tests/test_typing_backends.py — same `_Recorder` fixture shape).
- throttle: `import time` + `time.monotonic()` in feedback.py → tests
  `monkeypatch.setattr(time, "monotonic", fake_clock)` to advance the clock deterministically
  (NO timing flakiness; NO constructor seam needed → keeps `Feedback(cfg)` clean).
- round-trip: tests write to a `tmp_path` state_file and `json.load()` it back (true
  write→read; no private-getter seam needed).

## 5. Consumed contract — FeedbackConfig (already in voice_typing/config.py, P1.M2.T1.S1)

```python
@dataclass
class FeedbackConfig:
    state_file: str = ""       # "" → resolved_state_file() → $XDG_RUNTIME_DIR/voice-typing/state.json
    hypr_notify: bool = True
    notify_ms: int = 2500
    def resolved_state_file(self) -> str: ...   # raises RuntimeError if empty AND XDG_RUNTIME_DIR unset
```
- `resolved_state_file()` is the SINGLE source of truth for the path — feedback.py MUST call
  it (do not re-derive `$XDG_RUNTIME_DIR/voice-typing/state.json`). Tested in test_config.py.
- feedback.py imports ONLY `FeedbackConfig` from config (same purity rule as typing_backends:
  no cuda_check/torch/realtimestt/ctranslate2 — must load in CPU/test contexts).

## 6. Parallel-task / scope boundaries (from tasks.json + plan_status)

- voice_typing/typing_backends.py + tests/test_typing_backends.py are BOTH LANDED (69 tests
  collect). This task does NOT touch them.
- daemon.py (P1.M4.T1.*) will CONSUME Feedback: set_listening on gate flip, set_phase on
  on_recording_start/on_vad_detect_start, update_partial on on_realtime_transcription_
  stabilized, record_final on on_final. We define the API the daemon will call.
- install.sh (P1.M6.T1.S1) prints the tmux snippet that calls status.sh — out of scope here;
  status.sh's header comment is the user-facing integration doc (item DOCS: Mode A).
- Files THIS task creates (and ONLY these): voice_typing/feedback.py, voice_typing/status.sh,
  tests/test_feedback.py. Plus `chmod +x voice_typing/status.sh`.
