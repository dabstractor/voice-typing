# AGENTS.md — voice-typing

Read this BEFORE running any command. It exists because sessions in this directory have a
history of **hanging on long-running commands the agent cannot escape**, forcing a hard kill.

This repo is a **foreground server that never exits** (a CUDA faster-whisper daemon + a control
socket + live audio capture). Almost every interesting command here can block forever if you run
it naively. The two rules below are non-negotiable for any agent operating in this directory.

---

## Rule 1 — Every test/CLI command gets a *functional* timeout. No exceptions.

Every command that is not guaranteed to return in a few seconds MUST be run under a timeout that
will actually fire and hand control back to you. Two layers, both required:

1. **GNU `timeout` as the inner wrapper** — so the command self-terminates and you observe the
   failure (exit code `124` = timed out) instead of being killed mid-stream. This is how the
   repo's own tests do it.
2. **The `bash` tool's `timeout` parameter (seconds) as the harness-level hard backstop** on
   *every* invocation — set it generously above the inner `timeout`, so if the inner wrapper is
   ever bypassed the harness still reclaims the turn.

A command that "usually finishes" is not good enough. The whole point is the *one time* it wedges.

---

## Rule 2 — Run things so you can walk away. Never block the turn on a server.

- **Never run the daemon in the foreground.** `voice-typing-daemon` and
  `voice_typing/launch_daemon.sh` enter `VoiceTypingDaemon.run()`, which **blocks until quit or a
  signal**. If you exec it from a tool call, the session hangs forever. Period.
  - If a daemon *must* be up to reproduce or test something, start it via the systemd user unit
    (`systemctl --user start voice-typing`) or fully detached with `setsid ... </dev/null
    &disown`, **and** arrange a guaranteed teardown. Then poll readiness with a *timed*
    `voicectl status` (see below) — never an untimed one.
  - Default: assume a daemon is already running under systemd. Talk to it with `voicectl`. Do
    not spawn your own unless the task explicitly requires it.

- **Prefer short, bounded commands.** Prefer the unit tests over the heavy E2E shell scripts.
  Reach for `tests/test_idle_and_gpu.sh` / `tests/e2e_virtual_mic.sh` only when the task is
  literally about what they assert — they take 5–8 minutes, load CUDA models, and (the E2E one)
  **rebinds the system-wide PipeWire default audio source**. That global mutation is why an
  aborted run is worse here than a normal test.

---

## Rule 3 — Logging & scratch files: bound them. And never read a giant file before deleting it.

This rule is about *your* discipline as an agent working here, not about voice-typing code. A
recent **25 GB** runaway file under `/tmp` — written by an **unrelated** project's debug shim,
nothing to do with this repo — destabilized the whole machine, because `/tmp` here is a 32 GB
**tmpfs** (= RAM): a multi-GB append loop consumes main memory, not just disk. This repo's own
test scripts (`tests/*.sh`) create `mktemp -d` scratch in that same shared tmpfs, and any scratch
you create does too, so the same discipline protects sessions in this directory:

1. **`/tmp` is a RAM-backed tmpfs.** A runaway file there consumes main memory, not just disk —
   a multi-GB append loop will make the entire computer go haywire, exactly as it did. Treat any
   file you write under `/tmp` (or any `mktemp -d`) as spending RAM.

2. **Every log/trace file you create MUST be bounded.** No unguarded `>> file` in a loop. Pick
   one and say so in a comment: cap by size and truncate (`>> file` only when `stat -c%s < CAP`),
   rotate, use a ring/fixed-line-count buffer, or write at most N samples then stop. "It's just a
   debug log, I'll delete it after" is precisely the rationalization that produced the 25 GB file.

3. **PATH shims recurse infinitely if you `exec` the bare name.** That 25 GB file came from a
   shim like this: `echo "tmux-call: $*" >> calls.log; exec tmux -L sock "$@"` — bare `tmux`
   resolved back to
   **the shim itself**, so each call re-entered it and prepended another `-L sock` per level until
   `ARG_MAX`, writing one growing line per recursion. If you wrap a command on `PATH`, **always
   `exec` the real binary by absolute path** (`exec /usr/bin/tmux "$@"`), never the bare name. And
   never re-feed a logged command line back into a command.

4. **When you FIND a giant scratch/log file, delete it directly — do not read it first.** Do not
   `cat`, `tail`-loop, `wc`, or pull it into context to "see what it is." Reading a multi-GB file
   is itself catastrophic (and pointless — it's scratch). `rm -f` it, then `df -h /tmp` to confirm.
   This is what "be careful not to dump too many logs before deleting" means: a 25 GB file should
   be removed on sight, not inspected.

5. **Tear down your own scratch on exit.** Every `mktemp -d`, PATH shim, and audit harness gets an
   `EXIT`/`INT` trap that removes it (`trap 'rm -rf "$SHIM"' EXIT`), and you verify the teardown
   ran. A leftover shim on `PATH` is worse than a leftover file — it keeps intercepting calls.

---

## The actual hang vectors in THIS repo (learn them)

| Command | Why it hangs | Safe form |
|---|---|---|
| `.venv/bin/voicectl {start,stop,toggle,toggle-lite,quit}` | The control socket has **no read timeout**. `ctl.py:send_command` uses `sock.makefile("r")`, which is incompatible with `settimeout`. If the daemon is wedged on its control lock (e.g. an abort-under-lock regression, a teardown stall), the call blocks **forever**. | **Always wrap:** `timeout 30 .venv/bin/voicectl <cmd>` (this is `VOICECTL_TIMEOUT=30` in `tests/test_idle_and_gpu.sh`). Treat `124` as "daemon wedged," not as "retry." |
| `.venv/bin/voicectl status` | Lock-free and fast *when healthy*, but still has no socket timeout — a dead daemon still wedges it. | `timeout 15 .venv/bin/voicectl status`. Use this as the readiness/liveness poll. |
| `uv run pytest …` / `.venv/bin/pytest …` | Several suites (`test_feed_audio.py`, `test_daemon.py`, `test_recorder_host.py`) load real CUDA models. Cold cuDNN/cuBLAS init + two model loads is minutes on first run, and a regression can deadlock on the recorder/GIL. | `timeout 600 uv run pytest <file> -q` (and set the `bash` tool `timeout` above that). Run a single file or `-k expr`, not the whole suite, when iterating. |
| `voice-typing-daemon`, `voice_typing/launch_daemon.sh` | `run()` blocks until quit/signal. **Never foreground.** | systemd unit, or `setsid … &disown` + a recorded teardown. See Rule 2. |
| `tests/test_idle_and_gpu.sh` | ~5–8 min: two cold inits + 120 s armed-idle + idle-unload waits. If a transition never settles, the poll loops spin and a `voicectl` inside it wedges. | It already wraps its own `voicectl` calls in `timeout`. Still: give the `bash` tool a `timeout` of **900** (15 min) and do not interrupt it mid-run. Preflight refuses to start if the unit is already running — `systemctl --user stop voice-typing` first. |
| `tests/e2e_virtual_mic.sh` | Heavy model load **and** rebinds the global default audio source via `pactl`. If aborted between `load-module` and the trap, the user's mic stays pointed at a test sink. | Same 900 s `bash` backstop. It has an `EXIT` trap that restores the source and unloads the module by index — let the trap run. If *you* abort it manually, you owe a cleanup (below). |

---

## Cleanup — when (not if) something wedges

If a timed command comes back `124`, or you otherwise leave the repo in a bad state, clean up
before doing anything else. Do not blindly retry — the process group may still hold the global
audio source and/or a wedged control socket, and a retry will just hang again behind the same
timeout. Run each of these **under `timeout`** too:

```sh
timeout 30 .venv/bin/voicectl quit 2>/dev/null || true        # ask the daemon to stop
systemctl --user stop voice-typing 2>/dev/null || true        # and/or the unit
pkill -TERM -f 'voice-typing-daemon|recorder_host' 2>/dev/null || true
pkill -KILL -f 'voice-typing-daemon|recorder_host' 2>/dev/null || true
# ONLY if an E2E run was interrupted — restore the user's real mic:
pactl set-default-source "$(pactl get-default-source 2>/dev/null)" 2>/dev/null || true
pactl unload-module module-null-sink 2>/dev/null || true       # nukes ALL null-sinks; use sparingly
```

Verify with `timeout 15 .venv/bin/voicectl status` (should report the daemon is down / exit 2)
and a quick `pactl list short sources` before re-running anything.

---

## TL;DR

- **Two timeouts on every non-trivial command:** inner `timeout`, outer `bash`-tool `timeout`.
- **`voicectl` always under `timeout 30`.** The control socket will never time out on its own.
- **Never run the daemon in the foreground.** Use systemd or a detached spawn with a teardown.
- **Prefer a single pytest file / `-k` filter over the whole suite;** prefer unit tests over the
  5–8-minute E2E shell scripts.
- **When something wedges, clean up the daemon tree and the audio source before retrying.**
- **Bound every scratch/log file you write** (under `/tmp` = tmpfs = RAM). Cap, rotate, or stop
  after N lines — never bare `>>` in a loop.
- **PATH shims `exec` the real binary by absolute path**, never the bare name (a bare name
  recurses into the shim — that exact bug made a 25 GB file in `/tmp`).
- **Giant scratch file found? `rm -f` it on sight** — don't `cat`/`tail`/`wc` it into context first.
