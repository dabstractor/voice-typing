# install.sh design — P1.M6.T1.S1

The single idempotent setup entrypoint. Ties together every prior artifact. See external_citations.md
for the systemd/bash citations backing each decision.

## §1 — Consumed interfaces (READ-ONLY contracts; do NOT reimplement)

All of these EXIST at implementation start (plan_status: P1.M1–M5 Complete/Ready). Verified live.

| Input | File | Interface install.sh uses |
|---|---|---|
| Repo root | `$0` dir | `cd "$(dirname "$0")"` (launch_daemon.sh's `SCRIPT_DIR` idiom) |
| uv | `/home/dustin/.local/bin/uv` | `uv sync` (creates/refreshes `.venv/`) — FULL PATH (zsh alias hazard, PRD §2) |
| venv python | `<repo>/.venv/bin/python` | run cuda_check + prefetch + the LD_LIBRARY_PATH probe — FULL PATH |
| daemon entry | `voice_typing/launch_daemon.sh` | the unit's ExecStart points HERE (sets LD_LIBRARY_PATH, execs `python -m voice_typing.daemon`). install.sh does NOT exec it; it reproduces its LD_LIBRARY_PATH export for the cuda_check smoke (cuda_check.py docstring sanctions "reproduce that wrapper's LD_LIBRARY_PATH export in the shell"). |
| CUDA smoke | `voice_typing/cuda_check.py` | `python -m voice_typing.cuda_check` → stdout `VERDICT=cuda-ok\|cpu-fallback-required`; exit 0 (cuda-ok) / **1 (cpu-fallback = VALID)**. install.sh prints the verdict, NEVER aborts on it. |
| Model prefetch | `voice_typing/prefetch.py` | `python -m voice_typing.prefetch` → exit 0 if all CORE repos cached, **1 on core fail** (recoverable — daemon lazy-downloads). install.sh warns + continues on failure. Idempotent (snapshot_download skips etag-matched blobs). |
| Default config | `config.toml` (repo root) | copied to `$XDG_CONFIG_HOME/voice-typing/config.toml` IF ABSENT. config.py `_xdg_config_path()` resolves that exact path (XDG unset → `~/.config/voice-typing/config.toml`). |
| tmux helper | `voice_typing/status.sh` | install.sh prints the 2-line tmux snippet from status.sh's header: `set -g status-interval 1` + `status-right "#(.../status.sh)"`. |
| systemd unit | `systemd/voice-typing.service` | created by S2 (sibling subtask). install.sh copies it to `$XDG_CONFIG_HOME/systemd/user/voice-typing.service`, daemon-reload, enable, restart. ExecStart = launch_daemon.sh. The daemon starts NOT-listening (PRD §4.9). |
| voicectl | `.venv/bin/voicectl` (console script, P1.M5.T1.S1) | install.sh prints usage `voicectl toggle\|start\|stop\|status\|quit`. |

## §2 — The LD_LIBRARY_PATH smoke: why reproduce launch_daemon.sh's export

`cuda_check.py` probes `ctranslate2.get_cuda_device_count()`, which talks to the **CUDA driver only** and
does NOT load cuDNN — so cuda_check technically runs without LD_LIBRARY_PATH. BUT the item contract says
"run cuda_check.py via launch_daemon.sh env." launch_daemon.sh `exec`s the daemon (it can't run cuda_check
directly). The sanctioned manual path (cuda_check.py docstring) is: "reproduce that wrapper's
LD_LIBRARY_PATH export in the shell first." So install.sh factors a `_setup_cuda_libs()` that runs the
SAME python one-liner launch_daemon.sh uses (nvidia.cublas.lib / nvidia.cudnn.lib namespace-package
`__path__[0]` resolver) and exports LD_LIBRARY_PATH. If the nvidia wheels aren't importable, it warns and
continues (cuda_check's driver probe still works) — mirroring launch_daemon.sh's own fallback. This is a
few lines of duplication, deliberately sanctioned, not a violation of DRY.

## §3 — Idempotency matrix (re-run safety)

| Step | Command | Idempotent because |
|---|---|---|
| uv sync | `/home/dustin/.local/bin/uv sync` | no-op if lock satisfied; refreshes otherwise |
| cuda smoke | `python -m voice_typing.cuda_check \|\| true` | read-only probe; `|| true` keeps exit-1 (CPU-fallback) from aborting |
| prefetch | `python -m voice_typing.prefetch` (warn-on-fail) | snapshot_download skips etag-matched blobs |
| install unit | `cp systemd/voice-typing.service <userdir>/` | unconditional copy (cheap; ensures fresh unit); next reload picks it up |
| reload | `systemctl --user daemon-reload` | always safe (just refreshes in-memory defs) |
| enable | `systemctl --user enable voice-typing.service` | no-op + exit 0 if already enabled |
| restart | `systemctl --user restart voice-typing.service` | restarts running / starts stopped; applies fresh unit; never errors on re-run |
| config copy | `cp -n config.toml <XDG>/...` | `-n` = no-clobber → never overwrites the user's edited config |

`restart` is chosen over `start` so a re-run that updated the unit file actually applies it; `enable`
satisfies the "skip if already" intent (it's a no-op when enabled). This is stricter-but-correct vs the
literal "start" wording: a bare `start` on an already-running unit ignores a changed unit file.

## §4 — The printed output (Mode A = user-facing quick-start)

install.sh's stdout IS the install/usage doc (item DOCS: Mode A). It prints, after a successful run:

1. The CUDA VERDICT line (cuda-ok | cpu-fallback-required) + resolved device/models.
2. Usage:
   `voicectl toggle|start|stop|status|quit   (e.g. SUPER+ALT+D → toggle)`
3. The tmux status snippet (verbatim from status.sh's header):
   ```
   set -g status-interval 1
   set -g status-right "#(/home/dustin/projects/voice-typing/voice_typing/status.sh)"
   ```
   + the note: add these to ~/.tmux.conf (we never edit it for you).
4. The Hyprland instruction (P2.M1 forward-looking; hypr-binds.conf is created there):
   `source = /home/dustin/projects/voice-typing/hypr-binds.conf   # in ~/.config/hypr/hyprland.conf`
5. A final "daemon is running (not listening) — run `voicectl toggle` to arm" line.

These exact strings are copied into README by P2.M1.T2.S1 — keep them stable.

## §5 — Gotchas

- G1 (set -e): cuda_check exit 1 (cpu-fallback) + prefetch exit 1 (core fail) MUST be `|| true`/`if !`
  guarded or `set -e` aborts the whole install on a valid/recoverable signal.
- G2 (full paths): zsh aliases `python`/`pytest`/`uv`; ALWAYS use `/home/dustin/.local/bin/uv`,
  `<repo>/.venv/bin/python`, `/usr/bin/tmux`. install.sh is `#!/usr/bin/env bash` (not zsh).
- G3 (XDG_CONFIG_HOME resolution): mirror config.py — XDG unset/empty → `~/.config`. The systemd user
  dir is `$XDG_CONFIG_HOME/systemd/user` (same fallback). Resolve once, reuse for both config + unit.
- G4 (S2 dependency): `systemd/voice-typing.service` is produced by the SIBLING S2. install.sh references
  it at `systemd/voice-typing.service`. If S2 hasn't merged when S1 runs its own validation, the unit
  file is absent — install.sh must fail CLEARLY ("systemd/voice-typing.service missing — run P1.M6.T1.S2
  first") rather than silently skip the service step. (At orchestrator merge time S2 will precede/precede
  the real run; this guard makes the dependency explicit.)
- G5 (no hot-mic): the daemon starts NOT-listening by its OWN default (daemon.py main → daemon.run()).
  install.sh does not need to pass any flag; `systemctl restart` brings it up un-armed. Verify with
  `voicectl status` → `listening: off`.
- G6 (session requirement): `systemctl --user` needs XDG_RUNTIME_DIR + a user manager. install.sh checks
  XDG_RUNTIME_DIR is set and errors clearly if not (it is set in any login session).
- G7 (config-copy order): contract orders service-start (5) BEFORE config-copy (6). Safe because the
  daemon's config search order (XDG → repo → defaults) falls back to the repo `config.toml` when the XDG
  copy is absent — the first start still reads valid defaults. The XDG copy exists for the user's FUTURE
  edits to survive reinstalls.
- G8 (testing a bash script): the repo has NO bash test framework (pytest is Python-only). The gate is
  `bash -n` (syntax) + `/usr/bin/shellcheck` (lint, installed) + a manual idempotency run + the
  post-conditions (service active + `voicectl status` listening:off). bats/pytest-shell are out of scope.
