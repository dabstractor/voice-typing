# External citations — voicectl client (P1.M5.T1.S1)

## §1 Console-script entry points: return value IS the exit status

- **setuptools "Entry Points" guide** — https://setuptools.pypa.io/en/latest/userguide/entry_point.html
  Authoritative. A `[project.scripts]` entry (`voicectl = "voice_typing.ctl:main"`) generates a thin
  wrapper that imports the callable and invokes it. Hatchling (this project's build backend,
  `pyproject.toml [build-system] requires = ["hatchling"]`) generates the SAME standard wrapper form.
- **benjamintoll.com "On Python entry_points"** — https://benjamintoll.com/2021/04/04/on-python-entry_points/
  Quote: *"The return value of this function is used as the exit status."* Confirms `main() -> int`
  propagates the exit code without an internal `sys.exit`.
- **discuss.python.org "Packaging console scripts with interpreter options"** —
  https://discuss.python.org/t/packaging-console-scripts-with-interpreter-options/23842
  The wheel-installer-generated wrapper body is `sys.exit(ENTRYPOINT_VARIABLE())`. This is the exact
  form hatchling/setuptools emit. → `main()` returning 0/1/2 becomes the process exit code.
- **Chris Warrick "Python Apps the Right Way"** —
  https://chriswarrick.com/blog/2014/09/15/python-apps-the-right-way-entry_points-and-scripts/
  Recommended pattern: `sys.exit(main())` in the entry function. This PRP matches it (main() returns
  the code; the `__main__` guard does `sys.exit(main())`).

**Design consequence (G1):** `main()` must RETURN the int exit code, never `sys.exit(...)` internally.
Otherwise unit tests that assert the returned int break, and the wrapper would double-exit.

## §2 AF_UNIX socket connect error semantics (exit-2 mapping)

- **Python `socket` docs** — https://docs.python.org/3/library/socket.html
  `socket.socket(AF_UNIX, SOCK_STREAM).connect(path)`:
  - path does NOT exist → `FileNotFoundError` ("No such file or directory"). This is the "socket
    absent → daemon not running" case (item contract, exit 2).
  - path EXISTS (stale socket file left after a daemon crash/quit, or a non-socket file) but no
    process is `listen()`ing → `ConnectionRefusedError` ("Connection refused", errno 111). Also exit 2.
- **Python exception hierarchy** — https://docs.python.org/3/library/exceptions.html
  `FileNotFoundError`, `ConnectionRefusedError`, and `PermissionError` are ALL subclasses of `OSError`.
  → a single `except OSError` at connect covers every "can't reach the daemon" failure; map all to
  exit 2 with a clear message (the item contract names FileNotFoundError + ConnectionRefusedError;
  catching the broader OSError is a robustness superset that does not change the exit code).

## §3 Unix domain socket client pattern (one-shot, line protocol)

- **PyMOTW 3 "Unix Domain Sockets"** — https://pymotw.com/3/socket/uds.html
  Reference client: `s = socket.socket(AF_UNIX, SOCK_STREAM); s.connect(path)`. Confirms the
  connect-then-read sequence ctl.py uses.
- **Baeldung "Create Named Unix Sockets With Python"** — https://www.baeldung.com/linux/python-unix-sockets
  `makefile("r")` for line reads on a UDS socket. Matches the server's `makefile("w")` + flush-per-line
  contract (P1.M4.T2.S1 §3): the CLIENT reads exactly one line, then closes (one-shot).

## §4 argparse (positional with `choices`, subcommand-style help)

- **Python `argparse` docs** — https://docs.python.org/3/library/argparse.html
  - A positional with `choices=[...]` auto-generates the `{toggle,start,stop,status,quit}` "choose
    from" help in `--help` (Mode A doc surface).
  - `ArgumentParser(prog="voicectl", description=..., epilog=...)` for the module-docstring-equivalent
    CLI surface (the full usage table lives in the README, P2.M1.T2.S1 — do not duplicate it here).
  - argparse exits 2 on a usage error (unknown choice / missing arg) via SystemExit. This is
    argparse's convention and is ORTHOGONAL to our 0/1/2 daemon-interaction contract (G7).

## §5 (No new library) — stdlib-only constraint

The item mandates "dependency-light (stdlib only)". ctl.py uses `argparse`, `json`, `socket`, `sys`
(all stdlib) plus the single intra-package `from voice_typing.daemon import _default_control_socket_path`
(a stdlib-only module). No `pyproject.toml` dependency change.
