# voicectl client (`voice_typing/ctl.py`) — design + verified facts (P1.M5.T1.S1)

## §0 Scope

Build the **client** half of the PRD §4.8 control surface: `voice_typing/ctl.py` with a `main()`
that connects to the daemon's control socket (P1.M4.T2.S1, **DONE**), sends one JSON line, reads
one JSON line, prints a human-readable result, and exits 0/1/2. The `voicectl` console-script
entry is ALREADY declared in `pyproject.toml` (`voicectl = "voice_typing.ctl:main"`, P1.M1.T1.S1);
this item implements the function so the entry resolves.

Two files (1 ADD source, 1 ADD test). **NO** new module besides `ctl.py`; **NO** pyproject edit;
**NO** daemon change; **NO** README (P2.M1.T2.S1 owns the usage table — Mode A = argparse help +
module docstring only).

## §1 The consumed contract — `ControlServer` protocol (P1.M4.T2.S1, verified in LIVE daemon.py)

Read directly from `/home/dustin/projects/voice-typing/voice_typing/daemon.py` (the shipped source).
ctl.py is the CLIENT; it speaks EXACTLY this wire protocol. Do not re-invent it.

**Socket path resolver (REUSE — single source of truth):**
```python
from voice_typing.daemon import _default_control_socket_path
# -> "$XDG_RUNTIME_DIR/voice-typing/control.sock"  (AF_UNIX SOCK_STREAM)
# raises RuntimeError if XDG_RUNTIME_DIR unset/empty (mirrors FeedbackConfig.resolved_state_file)
```
Why reuse (not replicate): it is ALREADY tested by `tests/test_control_socket.py`; daemon.py is
import-pure (only stdlib + already-landed pure modules at module top; RealtimeSTT/torch/ctranslate2
stay lazily imported inside `build_recorder`), so `import voice_typing.daemon` is cheap. One socket-
path convention = one edit site if it ever changes. Tests that need a different path monkeypatch
`voice_typing.ctl._default_control_socket_path` OR set `XDG_RUNTIME_DIR` to a tmp dir (the latter
exercises the real resolution — preferred).

**Request (one JSON object per line; PRD §4.2(3)):**
```
{"cmd":"toggle"|"start"|"stop"|"status"|"quit"}\n
```

**Responses (read ONE line, `json.loads` it):**
| cmd sent | daemon reply (dict) |
|---|---|
| `toggle` / `start` / `stop` / `status` | `{"ok":true, "listening":<bool>, "partial":<str>, "last_final":<str>, "uptime_s":<float>, "device":<str>, "compute_type":<str>, "final_model":<str>, "realtime_model":<str>}` (uniform payload = `{"ok":true, **status_snapshot()}`) |
| `quit` | `{"ok":true, "shutting_down":true}` (NO listening/partial keys — going down) |
| malformed JSON sent | `{"ok":false, "error":"malformed JSON: ..."}` |
| non-dict JSON sent | `{"ok":false, "error":"request must be a JSON object"}` |
| unknown/missing cmd | `{"ok":false, "error":"unknown command: ..."}` |

Key implication for formatting: a successful `quit` has `ok:true` but NO `listening` key, and a
successful `toggle/start/stop/status` has the full status block. The formatter MUST handle both
shapes without a KeyError (use `.get(...)`, and treat `shutting_down` as the quit signal).

## §2 Exit codes (item contract + PRD §4.8) — THE central requirement

| code | meaning | trigger |
|---|---|---|
| **0** | success | response `ok == true` |
| **1** | logical failure | response `ok == false` (daemon ran but rejected the cmd; e.g. unknown cmd) |
| **2** | daemon not running | socket connect fails — `FileNotFoundError` (path absent) or `ConnectionRefusedError` (stale socket file, no listener). Also: `_default_control_socket_path()` raises `RuntimeError` (XDG_RUNTIME_DIR unset) — daemon can't be running if its path is unresolvable |

**Python socket error mapping (verified, Python 3.12; all are `OSError` subclasses):**
- Connect to a NON-EXISTENT AF_UNIX path → `FileNotFoundError` (socket file absent).
- Connect to a path that EXISTS but has NO listener (stale socket after daemon quit, or a non-socket
  file) → `ConnectionRefusedError`.
- Permission denied on the socket dir/file → `PermissionError`.
- Catch `(FileNotFoundError, ConnectionRefusedError)` explicitly (the contract's named cases), PLUS
  a broader `OSError` safety net + the path-resolution `RuntimeError` → ALL map to exit 2 with a
  clear "daemon not running: …" message. (A connect-time OSError of any kind means the daemon is
  effectively unreachable from this client's perspective.)

**Console-script exit-code propagation (verified):** hatchling/setuptools `[project.scripts]`
wrappers are generated as `sys.exit(main())` (the wheel-installer form is
`sys.exit(ENTRYPOINT_VARIABLE())`; setuptools docs + benjamintoll.com confirm "the return value of
this function is used as the exit status"). THEREFORE `main()` must RETURN the int exit code; it
must NOT call `sys.exit(...)` internally (that would prevent return-based unit testing + would
double-exit under the wrapper). The `if __name__ == "__main__": sys.exit(main())` guard handles the
`python -m voice_typing.ctl` path (house pattern: see `voice_typing/cuda_check.py`). ctl.py has NO
multiprocessing (unlike daemon.py), so the `__main__` guard here is convention, not a spawn-correctness
requirement.

## §3 Module decomposition (TDD-friendly — the item mandates unit-testing the format/exit logic by
       feeding canned JSON with the socket mocked)

Split so the **pure** decision logic is testable with zero I/O:

```
voice_typing/ctl.py
  _COMMANDS = ("toggle", "start", "stop", "status", "quit")      # constant
  def format_result(cmd: str, response: dict) -> tuple[str, int]  # PURE: (human text, exit code)
  def send_command(socket_path: str, cmd: str) -> dict            # thin socket I/O (injectable path)
  def main(argv: list[str] | None = None) -> int                  # argparse + orchestrate + print + return
  if __name__ == "__main__": sys.exit(main())
```

- **`format_result(cmd, response)`** is the unit-test workhorse. NEVER touches a socket. Rules:
  - `response.get("ok") is not True` → `("error: " + response.get("error","unknown error"), 1)`.
  - `response.get("shutting_down")` (quit path) → `("shutting down", 0)`.
  - `cmd == "status"` → a multi-line string incl. `listening`, `partial`, `last_final`, `uptime_s`,
    `device`, `compute_type`, `final_model`, `realtime_model`; exit 0. (PRD §4.8 "status pretty-prints
    the state incl. partial and models loaded".) Recommended layout (pin for tests — assert SUBSTRINGS):
    ```
    listening: on
    partial: <partial or empty>
    last: <last_final or empty>
    uptime: <uptime_s>s
    device: <device> (<compute_type>)
    models: <final_model> + <realtime_model>
    ```
  - else (toggle/start/stop) → `("listening: " + ("on" if response.get("listening") else "off"), 0)`.
    Defensive `.get("listening")` (quit has no key, but that path is handled above).
- **`send_command(socket_path, cmd)`** opens `AF_UNIX SOCK_STREAM`, `connect(socket_path)` (raises
  FileNotFoundError/ConnectionRefusedError on failure → propagates to main), writes
  `json.dumps({"cmd": cmd}) + "\n"`, reads exactly ONE line via `makefile("r", encoding="utf-8",
  newline="\n").readline()`, returns `json.loads(line)`. Empty line / malformed JSON in the RESPONSE
  → raise `ValueError` (caught in main → exit 1, "malformed response"). Use `with`/`try/finally` to
  close the socket. CRITICAL: read ONE line then close (voicectl is one-shot; do not loop). Use
  `makefile("r")` (NOT `settimeout`) — matches the server's `makefile("w")` flush-per-line contract
  and avoids the "makefile raises if socket has a timeout" trap documented in P1.M4.T2.S1 §3.
- **`main(argv)`**: argparse (`prog="voicectl"`; one POSITIONAL `cmd` with `choices=_COMMANDS` and a
  description/epilog that LISTS the 5 subcommands — Mode A docs surface); resolve socket path (catch
  `RuntimeError` → print "daemon not running (XDG_RUNTIME_DIR not set)" + return 2); try
  `send_command` → on `OSError` (FileNotFoundError/ConnectionRefused/Permission/broad) → print
  "daemon not running" + return 2; on `ValueError` (bad response) → print message + return 1;
  otherwise `text, code = format_result(cmd, resp)`; `print(text)`; `return code`. main() never raises
  (all paths return an int).

**Why a positional with `choices=`, not `add_subparsers`:** the PRD usage is exactly
`voicectl <cmd>` (one word), `choices=` auto-generates the `{toggle,start,stop,status,quit}` "choose
from" help, and the description/epilog satisfies "module docstring listing the 5 subcommands"
(Mode A). Subparsers add a heavier parser tree for no behavioral gain. (Either is acceptable; this
PRP mandates the simpler positional form for determinism.)

## §4 Test strategy (`tests/test_voicectl.py`, NEW) — mirrors `tests/test_control_socket.py` house style

Three layers, NO RealtimeSTT / NO CUDA / NO real daemon:

**Layer A — `format_result` pure-function tests (canned JSON; the item's mandated TDD core):**
- toggle/start with listening True → `("listening: on", 0)`; stop with False → `("listening: off", 0)`.
- quit response → `("shutting down", 0)`.
- status response (full 8-key dict) → exit 0 and the text CONTAINS "listening: on", the partial
  substring, "distil-large-v3", "small.en", the device, uptime.
- ok:false responses (`{"ok":false,"error":"unknown command: 'x'"}`, malformed-JSON error, non-dict
  error) → exit 1 and the text contains the error.
- defensive: ok:true but missing `listening` (hypothetical) does not raise.

**Layer B — real-socket round-trip (reuse `ControlServer` + a `_StubDaemon`, exactly like
`test_control_socket.py`):** set `monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_xdg))` so
`_default_control_socket_path()` resolves to `tmp_xdg/voice-typing/control.sock`; start a
`daemon.ControlServer(_StubDaemon(), socket_path=<that path>)`; call `ctl.main(["status"])` (and
toggle/start/stop/quit); assert the returned int (0) and capsys stdout substrings. Also assert
`ctl.main(["quit"])` returns 0 and prints "shutting down" (the stub records the quit call).

**Layer C — exit-2 paths (daemon not running):**
- XDG_RUNTIME_DIR set to a fresh tmp dir, NO server started → connect → `FileNotFoundError` →
  `ctl.main(["status"])` returns 2 and prints a "daemon not running" message.
- A stale socket file present (touch the path) but no listener → `ConnectionRefusedError` → return 2.
- XDG_RUNTIME_DIR UNSET (`monkeypatch.delenv`) → path resolution raises `RuntimeError` → return 2
  with the "XDG_RUNTIME_DIR not set" message (daemon can't be running).
- argparse rejects an unknown command BEFORE touching the socket (argparse `choices` → SystemExit 2
  from argparse, which is argparse's OWN usage-error exit; this is fine + expected — document it:
  an invalid subcommand is an argparse usage error, not a daemon-not-running error). NOTE:
  argparse's own exit code for a bad choice is 2 (its convention for usage errors); that is
  orthogonal to our 0/1/2 contract and acceptable. If you want to avoid the argparse-2 collision,
  catch `SystemExit` in main() — but the item's exit codes are about the DAEMON interaction, so
  letting argparse handle its own usage error is correct and simpler.

**Helpers:** reuse the `_StubDaemon` shape from `test_control_socket.py` (toggle/start/stop/
request_shutdown recording + canned `status_snapshot()`); reuse a `_wait_for` if an async assertion
is needed (the server replies synchronously, so usually not). NO `conftest.py` exists — keep tests
self-contained.

## §5 Coupling / parallel-context safety

- **Does NOT depend on P1.M4.T3.S1 (daemon `main()`).** ctl.py imports `voice_typing.daemon` ONLY for
  `_default_control_socket_path` (a module-level function added by P1.M4.T2.S1, already merged + live).
  Whether or not T3.S1 has merged is irrelevant to ctl.py. Zero merge risk with T3.S1.
- **Depends on P1.M4.T2.S1 (DONE):** `ControlServer`, `_default_control_socket_path`, the wire
  protocol shapes. Preflight asserts these are module attributes (they are, in the live source).
- **`pyproject.toml` is NOT edited** — the `voicectl = "voice_typing.ctl:main"` entry already exists
  (verified). Implementing `main()` is what makes it resolve.
- **Downstream consumers (do NOT build):** E2E test (P1.M7.T3.S1) calls `voicectl toggle/status/stop`;
  the Hyprland keybind (P2.M1.T1.S1) calls `voicectl toggle`; users. The contract (argv surface +
  exit codes + stdout) must stay stable — do not rename `main` or change its return type (int).

## §6 Validation commands (FULL venv paths — zsh aliases python/pytest)

```
.venv/bin/python -m py_compile voice_typing/ctl.py tests/test_voicectl.py
.venv/bin/python -m pytest tests/test_voicectl.py -v
.venv/bin/python -m pytest tests/ -q                       # expect 181 + ~18 new = ~199 passed
.venv/bin/python -c "import voice_typing.ctl as c; assert callable(c.main) and callable(c.format_result)"
# console-script entry resolves after uv sync / editable install:
.venv/bin/python -c "from voice_typing.ctl import main; print(type(main))"
```
mypy is NOT installed (do not list it). ruff is optional (/home/dustin/.local/bin/ruff);
py_compile + pytest are the authoritative gates. (Match every prior subtask's tooling discipline.)

## §7 Known gotchas

- **G1 — main() must RETURN the code, not `sys.exit` it.** The console-script wrapper already wraps
  with `sys.exit(main())` (§2). An internal `sys.exit` would break return-based tests and double-exit.
- **G2 — connect errors are OSError subclasses** (FileNotFoundError, ConnectionRefusedError,
  PermissionError). Catch them at connect; map to exit 2. Do NOT let them surface as a traceback.
- **G3 — read exactly ONE response line** then close. voicectl is one-shot. A loop would hang on the
  daemon's "connection stays open until client closes" design (the server's `_handle` reads in a loop
  but the CLIENT should send-one/read-one/exit).
- **G4 — `makefile("r")` not `settimeout`.** A timeout on the socket breaks makefile (P1.M4.T2.S1 §3).
  The daemon replies immediately after dispatch; no timeout is needed in practice. If you want a
  safety timeout, set it on the socket THEN unset (`s.settimeout(None)`) BEFORE makefile, or recv in a
  loop until `\n` with select — but the simplest correct path is blocking makefile (the daemon answers
  in milliseconds).
- **G5 — quit has no `listening` key.** The formatter must branch on `shutting_down` BEFORE reading
  `listening`, else `response["listening"]` KeyErrors on a quit reply.
- **G6 — `XDG_RUNTIME_DIR` unset → `RuntimeError` from `_default_control_socket_path`.** Catch it in
  main(); the daemon cannot be running if its socket path is unresolvable → exit 2.
- **G7 — argparse usage error exit code is 2 (argparse's own convention).** An unknown subcommand
  (e.g. `voicectl frobnicate`) exits 2 via argparse BEFORE the daemon is contacted. This is a USAGE
  error, not a "daemon not running" error; the same code (2) is coincidental and acceptable. Do not
  bend the design to avoid it.
- **G8 — import purity.** ctl.py imports only stdlib (argparse, json, socket, sys) + the single
  `from voice_typing.daemon import _default_control_socket_path` (daemon is import-pure). Do NOT add
  any third-party dependency (the item says "stdlib only"). No RealtimeSTT/torch import.
- **G9 — the `voicectl` console-script entry is ALREADY in pyproject.toml.** Do NOT edit pyproject.
  (Mirrors the T3.S1 finding that the entry was pre-declared.)
