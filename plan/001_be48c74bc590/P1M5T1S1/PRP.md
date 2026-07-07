# PRP — P1.M5.T1.S1: `voicectl` client (`voice_typing/ctl.py`): socket connect, JSON line, human output, exit 0/1/2

## Goal

**Feature Goal**: Add **`voice_typing/ctl.py`** — the user-facing CLI client (`voicectl`) for the
voice-typing daemon. It connects to the daemon's control socket (P1.M4.T2.S1, **DONE**), sends ONE
JSON line `{"cmd":"<cmd>"}`, reads ONE JSON line, prints a **human-readable** result
(`listening: on`), and returns the right **exit code**: **0** on success (`ok:true`), **1** on a
logical failure (`ok:false`), **2** if the daemon is not running (socket absent / connection refused).
Stdlib-only, TDD'd by feeding canned JSON to a pure formatter with the socket mocked. This closes
the client half of PRD §4.8 + §4 architecture (`voicectl CLI → unix socket → daemon`).

**Deliverable** (2 files — 1 ADD source, 1 ADD tests; **NO** new module besides `ctl.py`,
**NO** pyproject edit — the `voicectl = "voice_typing.ctl:main"` entry is ALREADY declared by
P1.M1.T1.S1; implementing `main()` is what makes it resolve):
1. `voice_typing/ctl.py` — NEW. Module docstring listing the 5 subcommands (Mode A doc surface);
   `from voice_typing.daemon import _default_control_socket_path` (reuse the canonical resolver);
   pure `format_result(cmd, response) -> tuple[str, int]`; thin `send_command(socket_path, cmd) ->
   dict`; `main(argv=None) -> int` (argparse positional + orchestrate + print + return code); the
   `if __name__ == "__main__": sys.exit(main())` guard.
2. `tests/test_voicectl.py` — NEW. Three layers: (A) `format_result` pure-function tests fed canned
   JSON (the item's mandated TDD core); (B) real-socket round-trip via a live `ControlServer` +
   `_StubDaemon` on a tmp socket (reuses `test_control_socket.py` house patterns); (C) exit-2 paths
   (socket absent, stale-socket refused, XDG_RUNTIME_DIR unset).

**Success Definition**:
- (a) `voice_typing/ctl.py` + `tests/test_voicectl.py` `py_compile`-clean; `import voice_typing.ctl`
  succeeds and stays import-pure (NO `RealtimeSTT`/`torch`/`ctranslate2` in `sys.modules` after import);
  `main`, `format_result`, `send_command` are callable module attributes; `main()` returns an `int`.
- (b) **Exit codes are exact** (the central contract): success response (`ok:true`) → **0**; logical
  failure (`ok:false`, e.g. `unknown command`) → **1**; daemon not running (connect
  `FileNotFoundError`/`ConnectionRefusedError`/broad `OSError`, OR `_default_control_socket_path()`
  `RuntimeError` from unset `XDG_RUNTIME_DIR`) → **2**. Verified by unit + integration tests.
- (c) **Wire protocol matches P1.M4.T2.S1 verbatim**: sends `{"cmd":<cmd>}\n` (UTF-8) to
  `$XDG_RUNTIME_DIR/voice-typing/control.sock`; reads exactly ONE response line; `json.loads` it.
  A successful `toggle`/`start`/`stop`/`status` reply carries the 8-key status block; a successful
  `quit` reply is `{"ok":true,"shutting_down":true}` (NO `listening` key — formatter must not KeyError).
- (d) **Human output** (PRD §4.8): `toggle`/`start`/`stop` → `listening: on` / `listening: off`;
  `status` → a multi-line pretty print including `listening`, `partial`, `last_final`, `uptime_s`,
  `device`, `compute_type`, `final_model`, `realtime_model` (must show "partial and models loaded");
  `quit` → `shutting down`; `ok:false` → the daemon's error text. Output goes to **stdout** (exit-2 /
  usage-error diagnostics may go to stderr — see Implementation Tasks).
- (e) **Console-script entry resolves**: after implementation, the `voicectl` entry
  (`voice_typing.ctl:main`) imports cleanly (no `AttributeError`); `python -m voice_typing.ctl status`
  runs and exits 0/1/2. (The entry itself is pre-declared; no pyproject edit.)
- (f) **Backward compat**: the existing tests pass UNCHANGED (193 at the time of writing — P1.M4.T2/T3
  have merged); ~18 new tests pass; `.venv/bin/python -m pytest tests/ -q` green (~211 passed).
- (g) **No out-of-scope code:** NO daemon.py edit, NO README (P2.M1.T2.S1 owns the full usage table —
  Mode A = argparse help + module docstring ONLY), NO `install.sh` (P1.M6.T1.S1), NO systemd unit
  (P1.M6.T1.S2), NO Hyprland keybind (P2.M1.T1.S1), NO pyproject/config/uv.lock edit, NO new
  third-party dependency ("stdlib only").

## User Persona

**Target User**: Internal + end-user — three consumers read this surface:
1. **End users** (via the Hyprland keybind, P2.M1.T1.S1) — `voicectl toggle` arms/disarms the mic.
2. **Operators / devs** — `voicectl status` shows the live partial + loaded models + device;
   `voicectl quit` drains the daemon; exit codes drive shell scripts (`voicectl status || echo down`).
3. **The automated E2E test** (P1.M7.T3.S1, `e2e_virtual_mic.sh`) — drives the daemon via
   `voicectl toggle`/`status`/`stop` against a tmux pane and asserts typed content; it relies on the
   exact exit codes (0 on success) and stdout shape.

**Use Case**: The daemon runs as a systemd user service (started NOT listening, PRD §4.9). The user
hits SUPER+ALT+D → `voicectl toggle` → connects, sends `{"cmd":"toggle"}\n`, reads
`{"ok":true,"listening":true,...}\n`, prints `listening: on`, exits 0. The daemon armed the mic;
partials flow; finals are typed. `voicectl status` prints the live partial + models. `voicectl quit`
prints `shutting down`, exit 0 (the daemon's `on_quit` runs `recorder.shutdown()`). If the daemon is
not running, `voicectl status` prints a clear "daemon not running" message and exits 2.

**Pain Points Addressed**: (1) PRD §4.8 + §4 architecture put `voicectl` at the center of the UX, but
no client exists yet — this item ships it. (2) Shell scripts / the E2E test need deterministic exit
codes (0/1/2) to branch on. (3) Operators need a one-glance `status` (live partial, not the throttled
disk file; loaded models, not config intent). (4) Without `main()`, the pre-declared `voicectl`
console script fails at runtime with `AttributeError`.

## Why

- **This is the user's only control surface.** PRD §4 architecture + §4.8 make `voicectl` the
  command-and-control for the whole daemon (toggle arming, status, quit). The keybind (P2.M1.T1.S1),
  the tmux status, and the E2E test (P1.M7.T3.S1) are all downstream of it. T5 unblocks P1.M7.T3 +
  P2.M1.T1.
- **Exit codes are the contract shell scripts test against.** The item pins 0/1/2 precisely:
  `voicectl status` in `set -e` must not abort a script when the daemon is merely stopped (ok:true →
  0); an unknown-command reply must surface as a logical failure (1); a dead daemon must be
  distinguishable as 2 so a wrapper can `systemctl --user start voice-typing`. Getting these wrong
  breaks the E2E test + any Hyprland binding that checks the result.
- **The pure formatter is the testable core.** The item mandates "unit-test the response-formatting/
  exit-code logic by feeding canned JSON (mock the socket)." Splitting `format_result` (pure, no I/O)
  from `send_command` (thin socket I/O) makes the central logic trivially testable with zero sockets,
  and leaves a small injectable seam (`socket_path` arg) for the real-socket integration layer.
- **Reusing `_default_control_socket_path()` is DRY + correct.** It is the canonical socket-path
  resolver (P1.M4.T2.S1), already tested, and `voice_typing.daemon` is import-pure (no RealtimeSTT at
  module top). One socket-path convention → one edit site. Replicating the 3-line function would
  create a drift hazard.

## What

A single small module, decomposed into a pure decision function + a thin socket function + a thin
orchestrator. The **exact code** is pinned in "Implementation Blueprint" (copy-pasteable; verified
against the live `daemon.py` `_default_control_socket_path` + the `ControlServer` protocol from
P1.M4.T2.S1). All imports are stdlib + the one intra-package resolver.

### Success Criteria

- [ ] `voice_typing/ctl.py` exists; `import voice_typing.ctl` succeeds + stays import-pure (no
      RealtimeSTT/torch/ctranslate2 in `sys.modules`).
- [ ] `main`, `format_result`, `send_command` are callable; `main()` returns an `int`.
- [ ] Exit codes EXACT: ok:true → 0; ok:false → 1; connect OSError / path-resolution RuntimeError → 2.
- [ ] Wire format: sends `{"cmd":<cmd>}\n` UTF-8 to `$XDG_RUNTIME_DIR/voice-typing/control.sock`;
      reads one line; handles the quit shape (no `listening` key) without KeyError.
- [ ] Human output: toggle/start/stop → `listening: on|off`; status → multi-line incl. partial +
      models + device + uptime; quit → `shutting down`; ok:false → error text.
- [ ] `voicectl` console-script entry imports cleanly (no `AttributeError`).
- [ ] `.venv/bin/python -m pytest tests/ -q` green (~199 passed); existing 181 unchanged.
- [ ] No pyproject/config/uv.lock/daemon.py edit; no new third-party dep.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior codebase knowledge: the exact `ctl.py` source (module docstring
+ `_COMMANDS` + `format_result` + `send_command` + `main` + the `__main__` guard) and a full test
skeleton are pinned below; the consumed contract (the `ControlServer` protocol + `_default_control_
socket_path`) is quoted verbatim from the LIVE `daemon.py`; the exit-code semantics + the Python
socket-error mapping are documented with citations; and the validation commands are executable as
written (full `.venv/bin/python` paths).

### Documentation & References

```yaml
# MUST READ — the work-item design + verified facts (THIS is the spec).
- file: plan/001_be48c74bc590/P1M5T1S1/research/voicectl_client_design.md
  why: "§1 the EXACT consumed wire protocol (response shapes tests pin) + the _default_control_socket_
        path reuse rationale. §2 exit codes (0/1/2) + the socket-error mapping (FileNotFoundError/
        ConnectionRefusedError -> 2) + console-script exit-code propagation (main() RETURNS the code).
        §3 module decomposition (format_result PURE / send_command thin / main orchestrator). §4 test
        strategy (3 layers). §5 coupling/parallel-context safety (does NOT depend on P1.M4.T3.S1).
        §6 validation commands. §7 gotchas (G1-G9)."
  critical: "main() must RETURN the int (the console-script wrapper already does sys.exit(main()));
             never sys.exit() inside main() (G1). The quit reply has NO listening key -> formatter
             branches on shutting_down FIRST (G5). Read exactly ONE response line then close (G3).
             Use makefile('r'), NOT settimeout (G4)."

- file: plan/001_be48c74bc590/P1M5T1S1/research/external_citations.md
  why: "§1 console-script wrappers do sys.exit(main()) -> return value is exit status (setuptools docs,
        benjamintoll, discuss.python). §2 AF_UNIX connect raises FileNotFoundError (path absent) /
        ConnectionRefusedError (stale file, no listener) / PermissionError — all OSError subclasses.
        §3 UDS client pattern. §4 argparse choices + usage-error exit 2 (orthogonal to our contract)."

# MUST READ — the module being CONSUMED (live; P1.M4.T2.S1 merged). ctl.py imports one symbol from it.
- file: voice_typing/daemon.py
  why: "The consumed contract. (1) `_default_control_socket_path()` -> '$XDG_RUNTIME_DIR/voice-typing/
        control.sock'; raises RuntimeError if XDG_RUNTIME_DIR unset/empty. ctl.py REUSES it
        (`from voice_typing.daemon import _default_control_socket_path`). (2) `class ControlServer`
        + its `_dispatch`/`status_snapshot` — the EXACT response shapes ctl.py must format:
        toggle/start/stop/status -> {'ok':True, 'listening':.., 'partial':.., 'last_final':..,
        'uptime_s':.., 'device':.., 'compute_type':.., 'final_model':.., 'realtime_model':..};
        quit -> {'ok':True,'shutting_down':True}; malformed/non-dict/unknown -> {'ok':False,
        'error':..}. (3) daemon.py is import-PURE (module top = stdlib + textproc/typing_backends/
        cuda_check/config; RealtimeSTT imported lazily inside build_recorder) so importing it for the
        resolver is cheap and side-effect-free."
  critical: "Do NOT edit daemon.py. Do NOT re-invent the protocol — match these shapes exactly or
             format_result will KeyError. The socket path convention is OWNED here (_default_control_
             socket_path) — reuse, do not duplicate."

# MUST READ — the house console-script main()/guard pattern (match its form exactly).
- file: voice_typing/cuda_check.py
  why: "The reference for a [project.scripts] entry point + guard in THIS repo: a `_main() -> int` that
        RETURNS an exit code, guarded by `if __name__ == '__main__': sys.exit(_main())`. ctl.py follows
        the SAME form (main() returns int; guard does sys.exit(main())). Confirms the house convention
        for exit-code propagation."

# MUST READ — the house test patterns for the control socket (mirror in test_voicectl.py).
- file: tests/test_control_socket.py
  why: "The patterns to REUSE: `_StubDaemon` (records toggle/start/stop/request_shutdown + canned
        status_snapshot()), the explicit `socket_path=` under pytest tmp_path (NO XDG_RUNTIME_DIR dep
        for dispatch tests), a `_send(path, msg)` one-shot client helper, `_wait_for(predicate)`. For
        ctl's Layer-B integration test, set XDG_RUNTIME_DIR=tmp so _default_control_socket_path()
        resolves to a tmp socket, start a real ControlServer(_StubDaemon()), then call ctl.main([..])."
  critical: "NO RealtimeSTT / NO CUDA / NO real VoiceTypingDaemon in tests (use _StubDaemon). Reuse
             _StubDaemon's shape verbatim so the canned status_snapshot matches what a real daemon
             returns (the 8 keys)."

# External — the contract citations (verified).
- url: https://setuptools.pypa.io/en/latest/userguide/entry_point.html
  why: "[project.scripts] generates a wrapper that calls the entry callable. Hatchling (this repo's
        build backend) emits the same standard wrapper."
- url: https://discuss.python.org/t/packaging-console-scripts-with-interpreter-options/23842
  why: "The wheel-installer wrapper body is `sys.exit(ENTRYPOINT_VARIABLE())` -> main()'s return value
        becomes the process exit code (why main() returns int, G1)."
- url: https://docs.python.org/3/library/socket.html
  why: "AF_UNIX SOCK_STREAM connect(): path absent -> FileNotFoundError; path exists but no listener ->
        ConnectionRefusedError. Both OSError subclasses (the exit-2 mapping)."
- url: https://docs.python.org/3/library/exceptions.html
  why: "FileNotFoundError / ConnectionRefusedError / PermissionError are all OSError subclasses -> a
        single `except OSError` at connect covers every can't-reach-daemon failure."
- url: https://docs.python.org/3/library/argparse.html
  why: "Positional with choices=[...] auto-generates the {toggle,start,stop,status,quit} 'choose from'
        help (Mode A doc surface). argparse exits 2 on a usage error (unknown choice) — orthogonal to
        our 0/1/2 daemon-interaction contract (G7)."

# Background — the protocol PRP (house style + the consumed surface).
- file: plan/001_be48c74bc590/P1M4T2S1/PRP.md
  why: "Pins ControlServer + _default_control_socket_path + the uniform status payload + the makefile
        flush-per-line contract. The protocol ctl.py speaks."

# Downstream — the consumers this item feeds (do NOT build).
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M7.T3.S1 (e2e_virtual_mic.sh) drives voicectl toggle/status/stop; P2.M1.T1.S1 (Hyprland
        keybind) calls voicectl toggle; P2.M1.T2.S1 (README) documents the usage table. Confirms the
        contract (argv surface + exit codes + stdout) must stay stable."
  critical: "Do NOT build the README/install.sh/systemd unit/keybind here. main() is the contract —
             do not rename it or change its return type (int)."
```

### Current Codebase tree (state at P1.M5.T1.S1 start — 193 passing; ControlServer + _default_control_socket_path live from P1.M4.T2.S1; daemon.main + signal/shutdown from P1.M4.T2.S2/T3.S1 also merged but NOT consumed here)

```bash
/home/dustin/projects/voice-typing/
├── .git/ .gitignore .venv/        # DO NOT touch .gitignore
├── PRD.md                         # READ-ONLY (§4.8 voicectl, §4 architecture, §4.2(3) socket)
├── config.toml pyproject.toml uv.lock   # DO NOT touch (voicectl entry ALREADY declared; no new deps)
├── voice_typing/
│   ├── __init__.py                # DO NOT touch
│   ├── cuda_check.py              # READ ONLY (house main()/guard pattern reference)
│   ├── config.py textproc.py typing_backends.py status.sh launch_daemon.sh prefetch.py  # unrelated
│   ├── feedback.py daemon.py     # READ ONLY (consume _default_control_socket_path + the protocol)
│   └── ctl.py                    # ← CREATE (Task 1): module docstring + _COMMANDS + format_result() +
│                                 #   send_command() + main() + the if __name__ == "__main__": guard.
└── tests/
    ├── test_config.py test_config_repo_default.py test_textproc.py test_typing_backends.py
    ├── test_feedback.py test_daemon.py test_control_socket.py   # regression baseline (DO NOT edit)
    └── test_voicectl.py          # ← CREATE (Task 2): format_result unit + real-socket round-trip + exit-2.
```

### Desired Codebase tree with files to be added

```bash
voice_typing/ctl.py                # NEW — voicectl client (argparse + socket + pure formatter + main + guard)
tests/test_voicectl.py             # NEW — 3-layer tests (format_result / round-trip / exit-2)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 (G1) — main() must RETURN the exit code, NEVER sys.exit() internally. The [project.
#   scripts] wrapper (hatchling/setuptools) already wraps with sys.exit(main()) (setuptools docs +
#   discuss.python.org: the wheel-installer body is sys.exit(ENTRYPOINT_VARIABLE())). An internal
#   sys.exit would (a) break return-based unit tests that assert the int, and (b) double-exit under
#   the wrapper. The if __name__ == "__main__": guard does sys.exit(main()) for the -m path (matches
#   voice_typing/cuda_check.py). ctl.py has NO multiprocessing (unlike daemon.py), so the guard is
#   convention, not a spawn-correctness requirement. (research §2.)

# CRITICAL #2 (G2) — connect errors are OSError subclasses. AF_UNIX SOCK_STREAM connect(path):
#   path absent -> FileNotFoundError; stale file/no listener -> ConnectionRefusedError; perms ->
#   PermissionError. ALL are OSError subclasses (Python exceptions hierarchy). Catch them at connect
#   and map to exit 2 ("daemon not running"). Catch the broader OSError as a safety net (it is a
#   superset of the contract's named cases; same exit code). Do NOT let any surface as a traceback.

# CRITICAL #3 (G3) — read exactly ONE response line, then close. voicectl is ONE-SHOT. The server's
#   _handle reads requests in a loop per connection, but the CLIENT sends one, reads one, exits. A
#   client read-loop would hang waiting for the daemon to close the connection.

# CRITICAL #4 (G4) — use makefile("r", encoding="utf-8", newline="\n") to read the line, NOT
#   socket.settimeout. makefile() RAISES if the socket has a timeout set ("must be in blocking mode",
#   P1.M4.T2.S1 §3). The daemon replies in milliseconds after dispatch; blocking makefile is the
#   simplest correct path and matches the server's makefile("w") + flush-per-line contract.

# CRITICAL #5 (G5) — the quit reply has NO listening key. A successful quit is {"ok":true,
#   "shutting_down":true}. format_result MUST branch on response.get("shutting_down") BEFORE touching
#   response["listening"], or it KeyErrors on quit. (toggle/start/stop/status carry the full 8-key
#   block; quit does not.)

# CRITICAL #6 (G6) — XDG_RUNTIME_DIR unset -> _default_control_socket_path() raises RuntimeError. The
#   daemon cannot be running if its socket path is unresolvable. Catch RuntimeError in main() and map
#   to exit 2 ("daemon not running: XDG_RUNTIME_DIR not set"). Tests cover this via monkeypatch.delenv.

# CRITICAL #7 (G7) — argparse usage-error exit code is 2 (argparse's OWN convention for a bad choice
#   / missing arg), surfaced via SystemExit BEFORE the daemon is contacted. This is a USAGE error,
#   orthogonal to our 0/1/2 daemon-interaction contract; the coincidental 2 is acceptable. Do NOT
#   bend the design to avoid it. (An unknown subcommand is genuinely a usage error, not a daemon
#   status.) Let argparse handle it.

# CRITICAL #8 (G8) — import purity. ctl.py imports only stdlib (argparse, json, socket, sys) + the
#   single `from voice_typing.daemon import _default_control_socket_path` (daemon is import-pure).
#   NO third-party dependency ("stdlib only", item contract). No RealtimeSTT/torch/ctranslate2 import.

# CRITICAL #9 (G9) — the voicectl [project.scripts] entry is ALREADY in pyproject.toml (P1.M1.T1.S1;
#   verified: `voicectl = "voice_typing.ctl:main"`). Do NOT edit pyproject.toml. Implementing main()
#   is what makes the entry resolve. (Mirrors the P1.M4.T3.S1 finding that voice-typing-daemon was
#   pre-declared.)

# CRITICAL #10 — stdout vs stderr. Human RESULT text (listening: on, status block, shutting down) goes
#   to STDOUT (the E2E test + users read it; shell `$(voicectl status)` capture). Diagnostic messages
#   for exit 2 ("daemon not running: …") and the ok:false error text: error text to STDOUT is fine
#   (it IS the human result for a logical failure) but the "daemon not running" connect-failure
#   message is better on STDERR (it's a diagnostic, not a result). Pick consistently; this PRP puts
#   the ok:false error text on stdout (it's the command's human output) and the exit-2 daemon-not-
#   running message on stderr (it's a transport diagnostic). Tests assert on both via capsys/capfd.

# CRITICAL #11 — FULL PATHS for tooling (zsh aliases python/pytest). ALWAYS
#   `.venv/bin/python -m pytest` / `.venv/bin/python -m py_compile` (never bare python/pytest).
#   mypy is NOT installed — do NOT list it. ruff is optional (/home/dustin/.local/bin/ruff);
#   py_compile + pytest are the authoritative gates. (Match every prior subtask.)
```

## Implementation Blueprint

### Data models and structure

No persistent data model. Four module-level callables + one constant + the guard:

```python
_COMMANDS: tuple[str, ...] = ("toggle", "start", "stop", "status", "quit")
format_result(cmd: str, response: dict) -> tuple[str, int]   # PURE: (human text, exit code)
send_command(socket_path: str, cmd: str) -> dict             # thin socket I/O (injectable path)
main(argv: list[str] | None = None) -> int                   # argparse + orchestrate + print + return
# + the module-level guard: if __name__ == "__main__": sys.exit(main())
```

`main()` holds only transient orchestration state (`cmd`, the resolved `socket_path`, the `response`).

### `voice_typing/ctl.py` reference implementation (research §3 — implement verbatim; verified against the live `daemon.py`)

```python
"""voicectl — command-line client for the voice-typing daemon (PRD §4.8, §4 architecture).

Connects to the daemon's AF_UNIX control socket ($XDG_RUNTIME_DIR/voice-typing/control.sock,
P1.M4.T2.S1), sends ONE JSON line {"cmd": <cmd>}, reads ONE JSON-line response, prints a
human-readable result, and exits:

    0  success            (daemon replied {"ok": true, ...})
    1  logical failure    (daemon replied {"ok": false, "error": ...})
    2  daemon not running (socket absent / connection refused / XDG_RUNTIME_DIR unset)

Subcommands (PRD §4.8):

    toggle   arm/disarm the mic (flip the listening gate)
    start    arm the mic (start listening)
    stop     disarm the mic (stop listening)
    status   pretty-print listening + partial + last final + uptime + device + loaded models
    quit     request a clean daemon shutdown (releases GPU workers)

Usage:  voicectl <toggle|start|stop|status|quit>
        (the full usage table is in the project README; this is the user-facing CLI surface.)

Stdlib-only: argparse, json, socket, sys + the shared socket-path resolver from voice_typing.daemon.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys

from voice_typing.daemon import _default_control_socket_path  # canonical resolver (P1.M4.T2.S1); reuse, do not duplicate

_COMMANDS: tuple[str, ...] = ("toggle", "start", "stop", "status", "quit")


def format_result(cmd: str, response: dict) -> tuple[str, int]:
    """Render a daemon JSON response as (human-readable text, exit code) — PURE, no I/O.

    Exit code: 0 if response["ok"] is true, else 1 (logical failure). The text:
      - ok:false                      -> the daemon's error text ("error: <...>")
      - quit ({"ok":true,"shutting_down":true}) -> "shutting down"  (NO listening key -> branch first)
      - status                        -> multi-line: listening, partial, last_final, uptime, device,
                                        compute_type, final_model, realtime_model  (PRD §4.8 "incl.
                                        partial and models loaded")
      - toggle/start/stop             -> "listening: on" / "listening: off"

    Defensive .get(...) everywhere so a missing key never raises (the protocol guarantees the 8-key
    block for toggle/start/stop/status, but .get keeps the unit tests + future shapes safe).
    """
    if response.get("ok") is not True:
        return f"error: {response.get('error', 'unknown error')}", 1
    if response.get("shutting_down"):           # quit reply (no listening key) -> branch BEFORE .get("listening")
        return "shutting down", 0
    if cmd == "status":
        listening = "on" if response.get("listening") else "off"
        partial = response.get("partial", "") or ""
        last_final = response.get("last_final", "") or ""
        uptime = response.get("uptime_s", 0.0)
        device = response.get("device", "unknown")
        compute_type = response.get("compute_type", "unknown")
        final_model = response.get("final_model", "unknown")
        realtime_model = response.get("realtime_model", "unknown")
        text = (
            f"listening: {listening}\n"
            f"partial: {partial}\n"
            f"last: {last_final}\n"
            f"uptime: {uptime}s\n"
            f"device: {device} ({compute_type})\n"
            f"models: {final_model} + {realtime_model}"
        )
        return text, 0
    # toggle / start / stop
    return f"listening: {'on' if response.get('listening') else 'off'}", 0


def send_command(socket_path: str, cmd: str) -> dict:
    """Open the control socket, send {"cmd": <cmd>}\\n, read ONE JSON line, return the parsed dict.

    Raises OSError (FileNotFoundError / ConnectionRefusedError / PermissionError) if the daemon is
    unreachable at connect time — caller maps to exit 2. Raises ValueError if the daemon replies with
    an empty or non-JSON line (a protocol error) — caller maps to exit 1. Uses makefile("r") (NOT
    settimeout — makefile raises if the socket has a timeout, P1.M4.T2.S1 §3). Reads exactly ONE line
    then closes (voicectl is one-shot).
    """
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(socket_path)   # raises FileNotFoundError/ConnectionRefusedError/PermissionError
        sock.sendall((json.dumps({"cmd": cmd}) + "\n").encode("utf-8"))
        with sock.makefile("r", encoding="utf-8", newline="\n") as rfile:
            line = rfile.readline()
    if not line:
        raise ValueError("daemon closed the connection without replying")
    return json.loads(line)         # json.JSONDecodeError is a ValueError subclass


def _build_parser() -> argparse.ArgumentParser:
    """argparse with one positional `cmd` over the 5 subcommands (Mode A doc surface)."""
    parser = argparse.ArgumentParser(
        prog="voicectl",
        description=(
            "Control the voice-typing daemon. Connects to the control socket, sends one command, "
            "prints the result. Exits 0 on success, 1 on a logical failure, 2 if the daemon is not running."
        ),
        epilog="subcommands: toggle, start, stop, status, quit  (see the project README for the full usage table)",
    )
    parser.add_argument(
        "cmd",
        choices=_COMMANDS,
        help="toggle | start | stop | status | quit",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """voicectl entry point: parse -> resolve socket -> send -> format -> print -> return exit code.

    Returns 0 (success), 1 (logical failure / protocol error), or 2 (daemon not running). NEVER
    raises: every path returns an int (the [project.scripts] wrapper does sys.exit(main())). argparse
    handles usage errors itself (SystemExit 2 on an unknown choice — a usage error, not a daemon
    status; G7).
    """
    args = _build_parser().parse_args(argv)
    cmd: str = args.cmd

    # 1. Resolve the socket path. XDG_RUNTIME_DIR unset -> RuntimeError -> daemon can't be running.
    try:
        socket_path = _default_control_socket_path()
    except RuntimeError:
        print("voicectl: daemon not running (XDG_RUNTIME_DIR is not set)", file=sys.stderr)
        return 2

    # 2. Talk to the daemon. Connect OSError -> exit 2; protocol ValueError -> exit 1.
    try:
        response = send_command(socket_path, cmd)
    except OSError as exc:                       # FileNotFoundError / ConnectionRefusedError / PermissionError
        print(f"voicectl: daemon not running ({exc.strerror or exc})", file=sys.stderr)
        return 2
    except ValueError as exc:                    # empty / malformed response line
        print(f"voicectl: {exc}", file=sys.stderr)
        return 1

    # 3. Format + print the human result; return the exit code.
    text, code = format_result(cmd, response)
    print(text)
    return code


if __name__ == "__main__":
    # Console-script-style guard (matches voice_typing/cuda_check.py). sys.exit propagates main()'s
    # exit code to the shell. (The [project.scripts] `voicectl` wrapper already does sys.exit(main()).)
    sys.exit(main())
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — confirm the live state + consumed surface + the baseline.
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/daemon.py && echo ok
      .venv/bin/python -m pytest tests/ -q 2>&1 | tail -1      # expect ~193 passed (P1.M4.T2/T3 merged)
      .venv/bin/python -c "
import sys, voice_typing.daemon as d
# Consumed contract from P1.M4.T2.S1 (DONE; must be live).
assert hasattr(d, '_default_control_socket_path'), 'P1.M4.T2.S1 not merged: _default_control_socket_path missing — STOP'
assert hasattr(d, 'ControlServer'), 'P1.M4.T2.S1 not merged: ControlServer missing — STOP'
# The console-script entry is ALREADY declared (do not edit pyproject).
import tomllib
with open('pyproject.toml','rb') as f: pp = tomllib.load(f)
assert pp['project']['scripts']['voicectl'] == 'voice_typing.ctl:main', 'voicectl entry missing/changed'
# ctl.py targets not yet present.
import importlib.util
assert importlib.util.find_spec('voice_typing.ctl') is None, 'ctl.py already exists (unexpected)'
# Import purity of the consumed module (cheap reuse).
assert not [m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules], 'daemon import not pure'
print('consumed surface + pyproject entry + import purity OK; baseline green')
"
  - EXPECTED: ~193 passed; _default_control_socket_path + ControlServer present (HARD GATE — if missing,
    P1.M4.T2.S1 hasn't merged; STOP); the pyproject `voicectl` entry == 'voice_typing.ctl:main';
    voice_typing.ctl not yet importable; daemon import-pure. NOTE: this item does NOT depend on
    P1.M4.T3.S1 (daemon main()) — verified: daemon.main/_setup_logging now exist (T3.S1 merged) but
    ctl.py imports ONLY _default_control_socket_path; whether T3.S1 merged is irrelevant to ctl.py.
  - DO NOT create/edit any file, run uv sync/add, or touch other modules.

Task 1: CREATE voice_typing/ctl.py — module docstring + _COMMANDS + format_result() + send_command()
        + _build_parser() + main() + the if __name__ == "__main__": guard.
  - FILE: voice_typing/ctl.py (NEW). Use the reference implementation above VERBATIM (verified against
    the live daemon.py protocol + the exit-code/socket-error mapping).
  - KEEP: stdlib-only imports (argparse, json, socket, sys) + the one
    `from voice_typing.daemon import _default_control_socket_path`. main() RETURNS int (never sys.exit
    inside it — G1). The guard does sys.exit(main()).
  - DO NOT: edit daemon.py / pyproject.toml / config.py / config.toml / uv.lock / feedback.py /
    cuda_check.py; add any third-party dependency; call sys.exit() inside main() or format_result;
    use socket.settimeout (use makefile — G4); read more than one response line (G3); write a README
    (P2.M1.T2.S1 owns the usage table — Mode A = argparse help + module docstring ONLY); add a 2nd
    main() or touch the daemon.

Task 2: CREATE tests/test_voicectl.py — 3-layer tests (format_result unit / real-socket round-trip /
        exit-2). See "Task 2 SOURCE" below.
  - FILE: tests/test_voicectl.py (NEW).
  - PATTERNS: (Layer A) feed CANNED dicts to format_result — assert exact text + exit code, no socket.
    (Layer B) reuse the _StubDaemon shape + an explicit tmp socket; set XDG_RUNTIME_DIR so
    _default_control_socket_path() resolves to the tmp path; start a real daemon.ControlServer; call
    ctl.main([..]); assert the returned int + capsys stdout. (Layer C) exit-2: socket absent
    (FileNotFoundError), stale socket no listener (ConnectionRefusedError), XDG_RUNTIME_DIR unset
    (RuntimeError). Use capfd for stderr assertions (the exit-2 messages go to stderr).
  - COVERAGE: every _COMMANDS branch in format_result; ok:false (3 error shapes); the quit no-listening-
    key branch (G5); status multi-line contains partial + final_model + realtime_model + device +
    uptime; real round-trip toggle/listening-on + status + quit; exit-2 on absent socket; exit-2 on
    refused (stale file); exit-2 on XDG_RUNTIME_DIR unset; import purity (no RealtimeSTT in sys.modules
    after import voice_typing.ctl); main() returns int; _build_parser rejects unknown cmd (SystemExit 2).
  - DO NOT: import RealtimeSTT/torch/ctranslate2; build a real VoiceTypingDaemon (use _StubDaemon);
    depend on the real XDG_RUNTIME_DIR (monkeypatch.setenv/delenv); sleep() gratuitously.

Task 3: VALIDATE — run the Validation Loop L1-L4. Iterate until all gates pass.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M5.T1.S1: voicectl client (voice_typing/ctl.py: socket connect, JSON line, human output, exit 0/1/2)".
```

#### Task 2 SOURCE — `tests/test_voicectl.py` (skeleton; expand to ~18 tests)

```python
"""Unit + integration tests for voice_typing.ctl (P1.M5.T1.S1).

Three layers (research §4):
  A. format_result() — pure function fed CANNED JSON (the item's mandated TDD core); no socket.
  B. real-socket round-trip — a live daemon.ControlServer + _StubDaemon on a tmp socket; ctl.main([..])
     connects, sends, formats, returns the exit code; assert stdout (capsys).
  C. exit-2 paths — socket absent (FileNotFoundError), stale socket no listener (ConnectionRefusedError),
     XDG_RUNTIME_DIR unset (RuntimeError).

NO RealtimeSTT / NO CUDA / NO real VoiceTypingDaemon. Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_voicectl.py -v
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time as _time

import pytest

from voice_typing import ctl, daemon


# ---------------------------------------------------------------------------
# canned daemon status_snapshot (matches daemon.ControlServer._dispatch output)
# ---------------------------------------------------------------------------
_STATUS_ON = {
    "ok": True, "listening": True, "partial": "hello wor", "last_final": "previous sentence.",
    "uptime_s": 12.345, "device": "cuda", "compute_type": "float16",
    "final_model": "distil-large-v3", "realtime_model": "small.en",
}


# --- Layer A: format_result (pure; canned JSON) --------------------------------------------

def test_format_toggle_on():
    assert ctl.format_result("toggle", {**_STATUS_ON, "listening": True}) == ("listening: on", 0)
def test_format_toggle_off():
    assert ctl.format_result("toggle", {**_STATUS_ON, "listening": False}) == ("listening: off", 0)
def test_format_start_on():
    assert ctl.format_result("start", {**_STATUS_ON, "listening": True}) == ("listening: on", 0)
def test_format_stop_off():
    assert ctl.format_result("stop", {**_STATUS_ON, "listening": False}) == ("listening: off", 0)
def test_format_quit_no_listening_key():
    # quit reply is {"ok":true,"shutting_down":true} — NO listening key -> must not KeyError
    assert ctl.format_result("quit", {"ok": True, "shutting_down": True}) == ("shutting down", 0)
def test_format_status_multiline_has_partial_and_models():
    text, code = ctl.format_result("status", _STATUS_ON)
    assert code == 0
    assert "listening: on" in text
    assert "hello wor" in text                      # partial
    assert "distil-large-v3" in text and "small.en" in text   # models loaded
    assert "cuda" in text and "float16" in text      # device + compute_type
    assert "12.345" in text                          # uptime
def test_format_ok_false_unknown_command():
    text, code = ctl.format_result("toggle", {"ok": False, "error": "unknown command: 'x'"})
    assert code == 1 and "unknown command" in text
def test_format_ok_false_malformed_json_error():
    text, code = ctl.format_result("status", {"ok": False, "error": "malformed JSON: ..."})
    assert code == 1 and "malformed JSON" in text
def test_format_ok_false_missing_error_key_is_defensive():
    text, code = ctl.format_result("toggle", {"ok": False})
    assert code == 1 and "unknown error" in text


# --- Layer B: real-socket round-trip (live ControlServer + _StubDaemon) --------------------

class _StubDaemon:
    """Duck-type VoiceTypingDaemon for round-trip tests (mirror tests/test_control_socket.py)."""
    def __init__(self):
        self.calls = []
        self._listening = False
    def toggle(self): self.calls.append("toggle"); self._listening = not self._listening
    def start(self): self.calls.append("start"); self._listening = True
    def stop(self): self.calls.append("stop"); self._listening = False
    def request_shutdown(self): self.calls.append("quit")
    def is_listening(self): return self._listening
    def status_snapshot(self):
        return {**_STATUS_ON, "listening": self._listening}


@pytest.fixture
def running_server(monkeypatch, tmp_path):
    """A ControlServer on a tmp socket; XDG_RUNTIME_DIR pointed at tmp_path so ctl resolves it."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    socket_path = str(tmp_path / "voice-typing" / "control.sock")
    srv = daemon.ControlServer(_StubDaemon(), socket_path=socket_path)
    srv.start()
    yield srv, socket_path
    srv.stop()


def test_main_status_round_trip_returns_zero_and_prints(capsys, running_server):
    srv, path = running_server
    code = ctl.main(["status"])
    out = capsys.readouterr().out
    assert code == 0
    assert "listening: off" in out and "distil-large-v3" in out

def test_main_toggle_then_status_lists_on(capsys, running_server):
    srv, path = running_server
    assert ctl.main(["toggle"]) == 0
    capsys.readouterr()
    assert ctl.main(["status"]) == 0
    assert "listening: on" in capsys.readouterr().out

def test_main_quit_returns_zero_and_says_shutting_down(capsys, running_server):
    srv, path = running_server
    code = ctl.main(["quit"])
    assert code == 0
    assert "shutting down" in capsys.readouterr().out
    assert srv._daemon.calls == ["quit"]


# --- Layer C: exit-2 paths (daemon not running) -------------------------------------------

def test_main_exit2_when_socket_absent(monkeypatch, tmp_path, capfd):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))   # path resolves but file does NOT exist
    code = ctl.main(["status"])
    err = capfd.readouterr().err
    assert code == 2 and "not running" in err

def test_main_exit2_when_stale_socket_no_listener(monkeypatch, tmp_path, capfd):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    sockdir = tmp_path / "voice-typing"; sockdir.mkdir()
    (sockdir / "control.sock").touch()                     # stale file present, nothing listening
    code = ctl.main(["status"])
    assert code == 2 and "not running" in capfd.readouterr().err

def test_main_exit2_when_xdg_runtime_dir_unset(monkeypatch, capfd):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    code = ctl.main(["status"])
    assert code == 2 and "not running" in capfd.readouterr().err


# --- argparse / structural ---------------------------------------------------------------

def test_main_rejects_unknown_command():
    with pytest.raises(SystemExit) as exc:                 # argparse usage error (exit 2, G7)
        ctl.main(["frobnicate"])
    assert exc.value.code == 2

def test_module_imports_pure_and_exposes_symbols():
    import importlib
    assert importlib.util.find_spec("voice_typing.ctl") is not None
    assert callable(ctl.main) and callable(ctl.format_result) and callable(ctl.send_command)
    # main()'s exit code is an int — proven by Layers A/B/C asserting exact ints; here just the shape:
    assert ctl.format_result("status", _STATUS_ON)[1] == 0   # returns a tuple whose [1] is the int code
    # ctl.py imports no heavy ML libs (stdlib + voice_typing.daemon, which is itself import-pure).
    assert not [m for m in ("RealtimeSTT", "torch", "ctranslate2") if m in sys.modules]
```

### Integration Points

```yaml
CONSOLE SCRIPT:
  - entry: "[project.scripts] voicectl = 'voice_typing.ctl:main'"  # ALREADY declared (P1.M1.T1.S1) — DO NOT edit pyproject
  - effect: implementing main() makes `voicectl <cmd>` + `python -m voice_typing.ctl <cmd>` resolve

SOCKET (consumed, READ-ONLY):
  - path: "$XDG_RUNTIME_DIR/voice-typing/control.sock"  # owned by voice_typing.daemon._default_control_socket_path (REUSE)
  - protocol: one JSON line in {"cmd":<cmd>}, one JSON line out  # owned by daemon.ControlServer (P1.M4.T2.S1)

NO database / NO config change / NO migration / NO new env var.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
# After creating ctl.py + test_voicectl.py — fix before proceeding.
.venv/bin/python -m py_compile voice_typing/ctl.py tests/test_voicectl.py
# Optional (ruff is at /home/dustin/.local/bin/ruff; may be absent — skip if so):
ruff check voice_typing/ctl.py tests/test_voicectl.py 2>/dev/null || true
# Import purity + presence:
.venv/bin/python -c "
import sys
from voice_typing import ctl
assert callable(ctl.main) and callable(ctl.format_result) and callable(ctl.send_command)
assert isinstance(ctl.format_result('status', {'ok':True,'listening':False,'partial':'','last_final':'','uptime_s':0.0,'device':'cpu','compute_type':'int8','final_model':'small.en','realtime_model':'tiny.en'})[1], int)
assert not [m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules], 'import purity broken'
print('ctl.py compiles, symbols present, import-pure OK')
"
# Expected: Zero errors. If errors exist, READ the output and fix before proceeding.
```

### Level 2: Unit Tests (Component Validation)

```bash
# The item's mandated TDD core (format_result, canned JSON) + round-trip + exit-2.
.venv/bin/python -m pytest tests/test_voicectl.py -v

# Full suite (regression + new). Expect ~211 passed (193 baseline + ~18 new).
.venv/bin/python -m pytest tests/ -q

# Expected: All tests pass. If failing, debug root cause and fix implementation (not the contract).
```

### Level 3: Integration Testing (System Validation) — requires a running daemon (optional; the unit
### round-trip Layer B already exercises the real socket + ControlServer)

```bash
# Manual smoke (a real daemon must be running for this; skip in CI/headless if no daemon):
#   .venv/bin/voicectl status        # expect "listening: off\n..." + exit 0
#   .venv/bin/voicectl toggle        # expect "listening: on" + exit 0
#   .venv/bin/voicectl status        # expect "listening: on\n..." + exit 0
#   .venv/bin/voicectl quit          # expect "shutting down" + exit 0
# Daemon-not-running:
#   systemctl --user stop voice-typing 2>/dev/null; .venv/bin/voicectl status; echo "exit=$?"  # expect exit=2

# Console-script entry resolves (the key deliverable — main() exists):
.venv/bin/python -c "from voice_typing.ctl import main; print('voicectl entry callable:', callable(main))"

# Module-run path (the __main__ guard):
.venv/bin/python -m voice_typing.ctl status; echo "exit=$?"   # 0/1/2 depending on daemon state
# Expected: human-readable output + exit code 0/1/2 as specified.
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Exit-code contract is the domain-specific guarantee — assert via the shell (manual, daemon running):
#   .venv/bin/voicectl status && echo OK              # OK printed only if exit 0
#   .venv/bin/voicectl frobnicate; echo "exit=$?"     # exit=2 (argparse usage error, G7)
# Wire-format fidelity: the unit round-trip (Layer B) already pins the exact request/response shapes
# against a live ControlServer, so no extra harness is needed.
# Expected: exit codes behave as documented for every subcommand + the not-running case.
```

## Final Validation Checklist

### Technical Validation

- [ ] All 4 validation levels completed successfully.
- [ ] `.venv/bin/python -m py_compile voice_typing/ctl.py tests/test_voicectl.py` clean.
- [ ] `.venv/bin/python -m pytest tests/ -q` green (~211 passed); existing 193 UNCHANGED.
- [ ] Import purity: `RealtimeSTT`/`torch`/`ctranslate2` NOT in `sys.modules` after `import voice_typing.ctl`.
- [ ] (mypy NOT installed — do not run; ruff optional.)

### Feature Validation

- [ ] Exit codes EXACT: ok:true → 0; ok:false → 1; connect OSError / path RuntimeError → 2.
- [ ] Wire format: `{"cmd":<cmd>}\n` to `$XDG_RUNTIME_DIR/voice-typing/control.sock`; one line read.
- [ ] Human output: toggle/start/stop → `listening: on|off`; status → partial + models + device +
      uptime; quit → `shutting down`; ok:false → error text.
- [ ] quit reply (no `listening` key) handled without KeyError (G5).
- [ ] `voicectl` console-script entry resolves (no `AttributeError`); `python -m voice_typing.ctl` runs.
- [ ] Error cases handled gracefully (no tracebacks for absent/refused socket; clear stderr message).

### Code Quality Validation

- [ ] Follows house patterns (`main() -> int` + `sys.exit(main())` guard mirrors `cuda_check.py`).
- [ ] Reuses `daemon._default_control_socket_path` (single source of truth); no protocol duplication.
- [ ] File placement matches the desired tree (voice_typing/ctl.py + tests/test_voicectl.py).
- [ ] Pure `format_result` is separated from I/O (TDD-friendly; fully unit-tested with canned JSON).
- [ ] Stdlib-only; no new third-party dependency.
- [ ] pyproject.toml/config.py/config.toml/uv.lock/daemon.py UNCHANGED.

### Documentation & Deployment

- [ ] Module docstring lists the 5 subcommands + exit-code semantics (Mode A user-facing CLI surface).
- [ ] argparse `description`/`epilog`/`help` strings are clear (the README usage table is P2.M1.T2.S1).
- [ ] No new env vars / config keys.

---

## Anti-Patterns to Avoid

- ❌ Don't `sys.exit()` inside `main()`/`format_result` — return the code (the wrapper already exits).
- ❌ Don't re-invent the wire protocol or the socket path — consume `daemon`'s (P1.M4.T2.S1 owns them).
- ❌ Don't `socket.settimeout` then `makefile` (makefile raises with a timeout — use blocking makefile).
- ❌ Don't read more than one response line (voicectl is one-shot; a read-loop hangs).
- ❌ Don't hardcode the socket path — resolve via `_default_control_socket_path()` (XDG_RUNTIME_DIR).
- ❌ Don't let a connect `OSError` surface as a traceback — catch it → exit 2.
- ❌ Don't edit `pyproject.toml` (the `voicectl` entry is already declared) or `daemon.py`.
- ❌ Don't add a third-party dependency ("stdlib only").
- ❌ Don't write the README usage table here (P2.M1.T2.S1) — Mode A = argparse help + module docstring only.
- ❌ Don't catch `BaseException`/blanket `Exception` where the contract wants specific OSError handling.

---

## Confidence Score

**9/10.** The consumed contract (`ControlServer` + `_default_control_socket_path` + the exact response
shapes) is quoted verbatim from the LIVE `daemon.py`; the exit-code semantics + Python socket-error
mapping are documented with authoritative citations; the reference implementation is copy-pasteable and
verified against the live protocol; and the 3-layer test skeleton pins every branch. The one residual
uncertainty (not -1): the precise wording of the multi-line `status` block is implementer-chosen (the
PRP pins a recommended layout + asserts substrings, so tests are robust to exact wording). No dependency
on the in-flight P1.M4.T3.S1 (ctl.py has its own `main()`; it imports only `_default_control_socket_path`,
which is already live), so timing risk is zero.
