# Research Brief — `systemd/voice-typing.service` (P1.M6.T1.S2)

**Status:** VERIFIED against the live machine (July 7, 2026) + the landed source tree.
**Purpose:** Pin every fact the unit file depends on so the PRP is one-pass implementable.

---

## 1. The deliverable (one file, ~15 lines of INI)

`systemd/voice-typing.service` — a systemd **user** unit (installed by the sibling S1 `install.sh` into
`$XDG_CONFIG_HOME/systemd/user/`, i.e. `~/.config/systemd/user/`). It ExecStarts the LD_LIBRARY_PATH
wrapper (`launch_daemon.sh`), restarts on failure, and starts at login — but the daemon itself boots
**not-listening** (no hot-mic). Content is fixed by the contract + PRD §4.9 + the wrapper PRP.

The unit is intentionally MINIMAL. The contract names exactly these directives:
`Description`, `After=pipewire.service ydotool.service`, `ExecStart=<wrapper>`, `Restart=on-failure`,
`RestartSec=2`, `WantedBy=default.target`. Plus an inline comment (the item's DOCS = [Mode A]).

---

## 2. Why ExecStart → launch_daemon.sh (NOT `.venv/bin/python -m voice_typing.daemon`)

**This is the deliberate deviation from the PRD §4.9 LITERAL text.** PRD §4.9's placeholder reads:

```
ExecStart=/home/dustin/projects/voice-typing/.venv/bin/python -m voice_typing.daemon
# Environment=LD_LIBRARY_PATH=...   ← install.sh fills this in if the cudnn dlopen test requires it
```

The item CONTRACT overrides both halves of that placeholder, and `P1.M1.T2.S1` (the wrapper PRP)
documents the override as a binding downstream integration point:

> "ExecStart= MUST point at the ABSOLUTE source-tree path of this wrapper:
>  `ExecStart=/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh`
>  (NOT .venv/bin/python -m voice_typing.daemon as in PRD §4.9's placeholder — the wrapper replaces
>  that line.) … P1.M6.T1.S2 should REMOVE that placeholder line (or leave it commented with a note
>  'set by launch_daemon.sh, not here')."

**Why the wrapper wins** (research_faster_whisper_cuda.md §2, VERIFIED):
- faster-whisper/ctranslate2 load cuBLAS + cuDNN 9 `.so`s from the `nvidia-*-cu12` wheels.
- cuDNN 9's split sub-libs (`libcudnn_ops.so.9` etc.) are resolved transitively by the dynamic linker;
  the wheels ship no `$ORIGIN` RUNPATH for them → "cannot load libcudnn_ops" without LD_LIBRARY_PATH.
- `LD_LIBRARY_PATH` is read by `ld.so` **at execve**, NOT mutable after Python starts (research §2).
  So the path MUST be exported before `python` runs.
- The wrapper computes the lib dirs from the LIVE wheels on every launch (survives `uv sync`) and
  `exec`s python. A baked-in `Environment=LD_LIBRARY_PATH=…` in the unit would go stale on every
  wheel reinstall — exactly the brittleness the wrapper was built to avoid.
- Therefore: **do NOT set `Environment=LD_LIBRARY_PATH` in the unit.** The wrapper owns it. The PRD's
  commented placeholder is REPLACED by a comment stating the wrapper sets it dynamically.

The contract is explicit: *"Do NOT set Environment=LD_LIBRARY_PATH in the unit (the wrapper handles it
dynamically)."* This is §2's "option 1" (wrapper) beating "option 2" (unit Environment=).

---

## 3. Why `exec` in the wrapper makes `Type=simple` (the default) correct

`launch_daemon.sh` ends in `exec "$PY" -m voice_typing.daemon "$@"` (P1.M1.T2.S1, research Q1):
`execve` replaces the bash image with Python in the SAME PID. systemd `Type=simple` (the default when
no `Type=` is given) considers the service started the moment the main PID exists, and tracks that PID
for `KillSignal=` delivery. So the unit needs NO explicit `Type=` — the default `simple` is correct,
and SIGTERM (systemd's default KillSignal) is delivered directly to Python. The daemon's signal
handlers (`install_shutdown_signal_handlers`, P1.M4.T2.S2) catch SIGTERM → clean shutdown
(`recorder.shutdown()` releases GPU VRAM; `ControlServer.stop()` unlinks the socket). **Do NOT add
`Type=` to the unit** — the contract does not name it, and the default is right. Adding `Type=forking`
or `Type=exec`-with-expectations would break the clean PID-tracking.

---

## 4. `Restart=on-failure` + `RestartSec=2` — semantics verified

- `Restart=on-failure` restarts the service only when the main process exits with a **nonzero** code,
  is killed by a signal (other than SIGHUP/SIGINT/SIGTERM/... per the table), times out, or trips a
  start-limit. It does NOT restart on a clean exit (code 0) or a clean `systemctl stop`.
- `daemon.py main()` (P1.M4.T3.S1) returns **1** on a fatal lifecycle error (config load fail,
  recorder/server init exception) and **0** on a clean shutdown (quit/signal). So `on-failure` restarts
  the daemon after a CRASH (the desired auto-recovery) but NOT after a clean `voicectl quit` (the
  desired user-driven stop). This is exactly the contract's intent.
- `RestartSec=2` sleeps 2 s before restarting — a sane back-off so a crash-looping daemon doesn't
  hammer the GPU/mic, while still recovering in 2 s. (systemd default RestartSec is 100ms; the contract
  explicitly raises it to 2 s.)
- The `StartLimitBurst`/`StartLimitInterval` defaults (5 restarts / 10 s) still apply — if the daemon
  genuinely can't start (e.g. missing models + a construction crash), systemd will stop restarting
  after the burst. That is acceptable (install.sh prefetches; the daemon lazy-downloads on miss).

---

## 5. `After=pipewire.service ydotool.service` — VERIFIED valid (both are user units)

A user unit's `After=` is honored ONLY against units in the SAME manager (the user manager) unless they
are explicitly cross-scope. On this exact machine (VERIFIED July 7, 2026):

| Unit | Scope | Loaded from | State |
|---|---|---|---|
| `pipewire.service` | **user** | `/usr/lib/systemd/user/pipewire.service` | active (running) |
| `ydotool.service` | **user** | (user manager) | enabled |

`systemctl --user list-unit-files | grep -E 'pipewire|ydotool'` returns both; `systemctl status` (system
scope) reports "could not be found" for both → they are USER units, the same manager our unit lives in.
So the `After=` ordering directive resolves correctly: systemd starts the daemon only after the audio
stack (PipeWire default source) and the typing fallback (ydotool uinput) are up. **Use exactly
`After=pipewire.service ydotool.service` (PRD §4.9 + contract) — both targets exist in-scope.**

Note: `After=` is an ORDERING dependency (not a REQUIRES). If pipewire/ydotool are not running at login,
the daemon still starts — it does not hard-depend. This is correct: the daemon's not-listening-at-boot
default means it won't touch the mic until armed, and PipeWire will be up by then.

---

## 6. Why the unit needs NO `Environment=` for `XDG_RUNTIME_DIR`

The daemon resolves its control socket (`$XDG_RUNTIME_DIR/voice-typing/control.sock`) and state file
(`$XDG_RUNTIME_DIR/voice-typing/state.json`) via `XDG_RUNTIME_DIR` (daemon.py
`_default_control_socket_path`, config.py `resolved_state_file`). The systemd **user manager** always
runs units with `XDG_RUNTIME_DIR=/run/user/$UID` already in the environment (verified: this session has
`XDG_RUNTIME_DIR=/run/user/1000`). So the unit needs NO `Environment=XDG_RUNTIME_DIR=...`. Adding one
would be redundant at best. (The sibling `install.sh` DOES preflight that `XDG_RUNTIME_DIR` is set in
the caller's shell, because IT invokes `systemctl --user` which needs the session — but the unit itself
inherits it from the user manager.)

---

## 7. "Starts not-listening" is enforced by the DAEMON, not the unit

The contract: *"Unit starts NOT-LISTENING (never hot-mic on boot; voicectl start/toggle arms it)."*
This is NOT a unit directive — there is no `ExecStart` arg or `Environment=` for listening state. It is
enforced by `daemon.py` (P1.M4.T1.S2): `VoiceTypingDaemon.__init__` constructs
`self._listening = threading.Event()` (cleared by default) and `run()` calls
`self._feedback.set_listening(False)`. The unit merely starts the process; the process arms the mic
only on an explicit `voicectl start`/`toggle` over the control socket. The acceptance check is
`voicectl status` → `listening: off` after `systemctl --user start`. **Do NOT add any listening-state
flag to the unit** — that would be dead config (the daemon ignores it).

---

## 8. `WantedBy=default.target` — start at login, not at boot

For a **user** unit, `WantedBy=default.target` symlinks the unit into
`~/.config/systemd/user/default.target.wants/` on `enable`, so it starts with the user's default
session (graphical login). It does NOT start at machine boot (that would be a system unit's
`multi-user.target`/`graphical.target`). This matches PRD §4.9 + the contract. Confirmed by the
existing user units on this box (e.g. `~/.config/systemd/user/default.target.wants/` exists with
several entries). The sibling `install.sh` runs `systemctl --user enable` (the symlink) + `restart`
(start now). **Use `WantedBy=default.target` exactly** (PRD §4.9).

---

## 9. The inline comment (the item's [Mode A] DOCS deliverable)

The item's DOCS note: *"[Mode A] Add an inline comment in the unit explaining the wrapper + un-armed-
start rationale (user-facing operational doc)."* systemd unit files accept `#` comments. The comment
must capture TWO rationales (both user-facing operational notes):

1. **ExecStart → wrapper**: the wrapper sets `LD_LIBRARY_PATH` for cuBLAS+cuDNN at exec; do NOT add
   `Environment=LD_LIBRARY_PATH` here (the wrapper recomputes from the live wheels; a baked value goes
   stale on `uv sync`). Point at PRD §8 risk row #1 (cuDNN cannot load libcudnn_ops).
2. **Un-armed start**: the daemon boots not-listening (no hot-mic on boot); `voicectl start`/`toggle`
   arms it. Point at PRD §4.9.

These comments are the operator-facing "why does ExecStart point at a .sh and why is there no
Environment= line" + "why does it say it's not listening" docs. README (P2.M1.T2.S1) may reprint them.

---

## 10. Validation tooling present (VERIFIED)

- `systemd-analyze verify <unit-file>` — the canonical static unit-file linter. Lints the file without
  starting it. Use `systemd-analyze verify systemd/voice-typing.service`. Catches unknown keys, syntax
  errors, bad ExecStart (missing binary), unresolvable `WantedBy=`/`After=` syntax.
- `/usr/bin/shellcheck` v0.11.0 — for any shell, but the unit is pure INI (shellcheck N/A; noted so
  the implementer doesn't waste a gate on it).
- `systemctl --user cat voice-typing` — after install.sh copies it, shows the RESOLVED unit (verifies
  the copy landed + systemd parsed it).
- `XDG_RUNTIME_DIR=/run/user/1000` set → `systemctl --user` works in this session.

---

## 11. Scope boundary with the sibling S1 (`install.sh`) and other tasks

- **S1 (install.sh) COPIES this unit** from `$REPO/systemd/voice-typing.service` to
  `$XDG_CONFIG_HOME/systemd/user/voice-typing.service`, then `daemon-reload`+`enable`+`restart`. S1
  does NOT author unit content (its PRP gotcha G4 + the integration contract). This task authors the
  content; S1 consumes it. **If this file is absent when S1 runs its validation, S1 fails CLEARLY**
  ("systemd/voice-typing.service missing — run P1.M6.T1.S2 first").
- **install.sh also `chmod +x`es `launch_daemon.sh`** (idempotent) — but the unit's `ExecStart=` does
  NOT depend on that (systemd ExecStart runs the binary directly via the path; the +x is required for
  systemd to exec it, set by P1.M1.T2.S1 in the source tree + re-asserted by install.sh).
- **NO edit** to `launch_daemon.sh`, `daemon.py`, `pyproject.toml`, `config.toml`, `install.sh`, or
  any Python module. NO README (P2.M1.T2.S1). NO hypr-binds.conf (P2.M1.T1.S1). The ONLY output is
  `systemd/voice-typing.service` (a new file in a new `systemd/` dir).
- **The unit is referenced by acceptance criterion 6** (PRD §7): the daemon runs as a systemd user
  service, restarts on failure, starts not-listening. The unit file is what makes that provable.

---

## 12. Summary of contract-driven unit content (the spec)

```ini
[Unit]
Description=Local voice typing daemon (RealtimeSTT)
After=pipewire.service ydotool.service

[Service]
# ExecStart points at the LD_LIBRARY_PATH wrapper (voice_typing/launch_daemon.sh), NOT python
# directly. faster-whisper/ctranslate2 need cuBLAS+cuDNN 9 .so's on LD_LIBRARY_PATH, which the
# dynamic linker reads ONLY at exec (ld.so(8)) — so the wrapper exports them BEFORE exec'ing
# python. Do NOT add `Environment=LD_LIBRARY_PATH=...` here: the wrapper recomputes the lib dirs
# from the LIVE nvidia wheels on every launch (survives `uv sync`); a baked value would go stale.
# (PRD §8 risk row #1: cuDNN "cannot load libcudnn_ops".)
#
# The daemon boots NOT-LISTENING (no hot-mic on boot). `voicectl start`/`toggle` arms the mic
# over the control socket. (PRD §4.9.)
ExecStart=/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
```
