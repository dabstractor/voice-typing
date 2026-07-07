# P1.M4.T3.S1 — external citations (spawn guard, logging, journald)

Companion to `daemon_entrypoint_design.md`. These URLs corroborate the PRP's three external claims.
Produced by a researcher pass; the substance is well-established. One verbatim gap is flagged.

## 1. Python `spawn` re-imports the parent `__main__` → the guard is mandatory  [HIGH confidence]

- **Safe importing of main module:**
  https://docs.python.org/3/library/multiprocessing.html#safe-importing-of-main-module
  > "Make sure that the main module can be safely imported by a new Python interpreter without
  > causing unintended side effects (such as starting a new process). … protect the entry point of
  > the program by using `if __name__ == '__main__':` …"
- **Contexts and start methods (spawn):**
  https://docs.python.org/3/library/multiprocessing.html#contexts-and-start-methods
  > "spawn: The parent process starts a fresh python interpreter process." A fresh interpreter
  > imports the parent's `__main__` module → unguarded top-level code re-runs in the child →
  > recursive spawning. The guard makes that re-import a no-op in children.
- **`python -m` runs the module as `__main__`:** https://docs.python.org/3/library/__main__.html
  (confirms `__name__ == "__main__"` for the systemd ExecStart / launch_daemon.sh path.)

**RealtimeSTT uses spawn (independently verified on THIS machine — stronger than the README):**
the P1.M4.T2.S2 research (`shutdown_signals_design.md`) cites the INSTALLED source at exact lines:
`.venv/lib/python3.12/site-packages/RealtimeSTT/core/initialization.py:354-355,397,433` —
`transcript_process` + `reader_process` are `mp.Process` started with `mp.set_start_method("spawn")`.
So the spawn premise is source-verified, not README-only.

### Gap (non-blocking): RealtimeSTT README verbatim quote
The RealtimeSTT README (https://github.com/KoljaB/RealtimeSTT, raw:
https://raw.githubusercontent.com/KoljaB/RealtimeSTT/master/README.md — try `main` if `master` 404s)
documents the `if __name__ == "__main__":` requirement for multiprocessing, and every README example
is shown inside the guard. The byte-exact sentence + section anchor could not be retrieved this pass
(no web-fetch tool). To cite verbatim: open the raw README, ctrl-F `__main__` / `multiprocessing`.
This is a nice-to-have citation; the installed-source evidence above is authoritative and already
cited in the PRP via the T2.S2 research dependency, so the gap does not weaken the PRP.

## 2. `logging.basicConfig` → stderr is the default + idiomatic for services  [HIGH confidence]

- https://docs.python.org/3/library/logging.html#logging.basicConfig
  > "If *stream* is specified, the `StreamHandler` will be initialized with that stream; otherwise
  > **sys.stderr** is used."
  > "This function does nothing if the root logger already has handlers configured." (idempotent —
  > the property that makes `_setup_logging` a no-op under pytest caplog.)

**Nuance for the PRP:** `basicConfig()` ALREADY defaults its handler to `sys.stderr`, so
`stream=sys.stderr` in `_setup_logging` is explicit-but-harmless — the conventional, readable form.
The explicit form is retained (makes the stderr→journald intent obvious to a reader).

## 3. systemd/journald captures unit stderr  [HIGH confidence]

- https://www.freedesktop.org/software/systemd/man/systemd.exec.html — `StandardError=`
  > "Controls where file descriptor 2 (stderr) of the service processes is connected to. … The
  > default is `inherit`."
  For a user service the inherited stdout/stderr are connected to systemd-journald, so everything
  the daemon writes to fd 2 (all `logging` output) appears in `journalctl --user -u voice-typing`.
  No extra unit config is required (the PRD §4.9 unit does not set `StandardError=`). This is why
  `logging.basicConfig(stream=sys.stderr, ...)` is the right choice for PRD §4.2 "logging to stderr
  (journald picks it up under systemd)".
