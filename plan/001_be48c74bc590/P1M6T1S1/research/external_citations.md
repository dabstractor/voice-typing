# External citations — P1.M6.T1.S1 `install.sh`

Authoritative sources backing the install.sh design decisions. All verified reachable.

## §1 — systemd user units: install location + reload/enable/start semantics

- **ArchWiki — Systemd/User** https://wiki.archlinux.org/title/Systemd/User
  - WHY: the canonical reference for *user* (not system) units. Confirms user unit files live under
    `~/.config/systemd/user/` (i.e. `$XDG_CONFIG_HOME/systemd/user/`, XDG unset → `~/.config/systemd/user/`),
    that `systemctl --user enable <unit>` symlinks it into `default.target.wants` (start at login), and
    that a user manager / D-Bus session (→ `XDG_RUNTIME_DIR` set) must be running for `--user` to work.
  - CRITICAL: `enable` does NOT start the unit immediately; `--now` (or a separate `start`/`restart`) does.
    install.sh uses `daemon-reload` → `enable` → `restart` (restart both starts a stopped unit and
    applies a freshly-copied unit file to a running one — the idempotent re-run path).

- **freedesktop.org — systemctl(1)** https://www.freedesktop.org/software/systemd/man/systemctl.html
  - WHY: "If you want systemd to reload the configuration file of a unit, use the daemon-reload command.
    This command honors --user." → `systemctl --user daemon-reload` is the documented reload after
    copying/editing a unit file.
  - CRITICAL: without daemon-reload, systemd keeps the OLD in-memory unit definition; a copied unit file
    is not picked up until reload. install.sh reloads BEFORE enable/restart.

- **serverfault — "Do systemd unit files have to be reloaded when modified?"**
  https://serverfault.com/questions/700862
  - WHY: confirms daemon-reload is required after any unit-file change for it to take effect.

- **Stack Overflow — "Is daemon-reload called when the Unit is enabled with systemctl enable?"**
  https://stackoverflow.com/questions/60763802
  - WHY: `enable` reloads in most cases, but there are exceptions; an explicit `daemon-reload` is the
    safe, documented belt-and-braces. install.sh reloads explicitly.

## §2 — `set -euo pipefail` interaction with intentionally-nonzero commands

- **mohanpedala — "set -e, -u, -o, -x pipefail explanation"**
  https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
  - WHY: `set -e` aborts on the FIRST command with a nonzero exit status; `|| true` (or an `if ! cmd; then`)
    is the sanctioned escape hatch for commands whose nonzero exit is an EXPECTED, non-fatal signal.
  - CRITICAL (load-bearing for install.sh): two consumed commands legitimately exit nonzero:
    (1) `python -m voice_typing.cuda_check` exits **1** on `cpu-fallback-required` — a VALID degraded
        mode, NOT an install failure (cuda_check.py docstring: "cpu-fallback-required is a VALID degraded
        mode, not an error"). Under `set -e` a bare invocation would ABORT install.sh on a CPU-only box.
        install.sh captures it with `|| true` and prints the VERDICT= line regardless.
    (2) `python -m voice_typing.prefetch` exits **1** if a CORE model repo fails (prefetch._main). The
        daemon lazy-downloads at first run if a model is missing, so prefetch failure is a WARNING, not
        fatal. install.sh captures it and continues.
    `uv sync`, `systemctl`, `cp`, `mkdir` keep their "abort on failure" semantics.

- **Stack Overflow — "Difference of -e, -u and -o pipefail in bash exit status"**
  https://stackoverflow.com/questions/69570801
  - WHY: defines `pipefail` (pipeline exit = rightmost nonzero) — relevant because cuda_check's output is
    captured in a pipeline (`| tail`/`grep`); pipefail + the `|| true` guard together keep the script
    both strict and tolerant of the two known-nonzero commands.

## §3 — idempotent copy / "copy if absent"

- `cp -n` (GNU coreutils `--no-clobber`) is the idiomatic "copy only if the destination does not exist".
  Used for the config.toml → `$XDG_CONFIG_HOME/voice-typing/config.toml` copy so a re-run never clobbers
  the user's edited config. (`cp -n` is present on the Arch/coreutils install on this machine; `install.sh`
  could also test `[ -f dest ] || cp src dest` — equally valid; `cp -n` chosen for one-liner clarity.)
  `mkdir -p` is inherently idempotent (no error if the dir exists) → used for the XDG config + systemd
  user dirs.

## §4 — `systemctl --user` requires a user session

- ArchWiki Systemd/User (§1) + the opensuse/forum results: `systemctl --user` needs the per-user systemd
  manager running, which requires an active login session (`XDG_RUNTIME_DIR` set, D-Bus user bus up).
  install.sh is an INTERACTIVE setup script run by the user from their session — it MUST NOT be run under
  bare cron/SSH without a lingering session. (The daemon's own state-file + socket also need
  `XDG_RUNTIME_DIR`, per config.py/daemon.py — consistent constraint.) install.sh checks
  `XDG_RUNTIME_DIR` is set and errors clearly if not.
