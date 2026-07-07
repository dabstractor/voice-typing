# PRP — P1.M6.T1.S1: `install.sh` — idempotent setup entrypoint (sync → CUDA smoke → prefetch → systemd unit → XDG config → print snippets)

## Goal

**Feature Goal**: Add **`install.sh`** at the repo root — the single, re-runnable setup entrypoint that
wires together every artifact from P1.M1–M5 into a working, systemd-managed, **un-armed** daemon. It is
`#!/usr/bin/env bash` + `set -euo pipefail`, uses **explicit tool paths** (`/home/dustin/.local/bin/uv`,
`.venv/bin/python`, `/usr/bin/tmux`) because zsh aliases break bare names (PRD §2), and runs seven
ordered steps (PRD §5 + §4.9 + the item contract): (1) cd to repo root; (2) `uv sync`; (3) run
`voice_typing.cuda_check` under the launch_daemon.sh `LD_LIBRARY_PATH` env and PRINT the verdict
(cpu-fallback is a VALID outcome, never aborts); (4) run `voice_typing.prefetch` (idempotent, warn-only
on failure); (5) install+daemon-reload+enable+restart the systemd user unit from `systemd/voice-typing.service`;
(6) copy `config.toml` to `$XDG_CONFIG_HOME/voice-typing/config.toml` **only if absent**; (7) print the
usage + tmux status snippet + Hyprland source instruction. Closes PRD §4.9 + §5.

**Deliverable** (1 file — 1 ADD; **NO** new Python module, **NO** pyproject/uv.lock/config.toml/daemon
edit, **NO** systemd unit content — that is the SIBLING S2):
1. `install.sh` — NEW (repo root, sibling of `config.toml` per PRD §4.1). Full reference implementation
   pinned in "Implementation Blueprint" (copy-pasteable; verified against the live consumed interfaces).
   `chmod +x`. The printed stdout IS the user-facing install/usage quick-start (Mode A docs).

**Success Definition**:
- (a) `install.sh` is `bash -n`-clean and `/usr/bin/shellcheck`-clean (SC errors = 0; SC warnings about
  the intentional `$(...)` command substitution are acceptable if unavoidable, but the pinned source
  passes clean). `#!/usr/bin/env bash` + `set -euo pipefail`.
- (b) **Idempotent**: running it twice completes with exit 0 both times; the 2nd run does NOT re-download
  models (snapshot_download skips etag-matched blobs), does NOT overwrite the user's XDG config (`cp` only
  if absent), does NOT error on an already-enabled/restarted unit.
- (c) **Explicit paths**: every invocation of uv/python/tmux uses the FULL path (`/home/dustin/.local/bin/uv`,
  `<repo>/.venv/bin/python`); no bare `python`/`uv`/`pytest` (zsh alias hazard, PRD §2). bash, not zsh.
- (d) **CUDA smoke verdict printed, never fatal**: step (3) runs `python -m voice_typing.cuda_check` under
  the launch_daemon.sh-reproduced `LD_LIBRARY_PATH`; prints `VERDICT=cuda-ok|cpu-fallback-required`;
  `cpu-fallback-required` (cuda_check exit 1) is a VALID degraded mode — install.sh captures it with
  `|| true`/`if !` and continues (the daemon will run CPU mode).
- (e) **Prefetch warn-only**: step (4) runs `python -m voice_typing.prefetch`; on core-model failure
  (exit 1) prints a clear WARNING and continues (the daemon lazy-downloads missing models at first run).
- (f) **Service installed + running + un-armed**: step (5) copies `systemd/voice-typing.service` →
  `$XDG_CONFIG_HOME/systemd/user/voice-typing.service`, `daemon-reload`, `enable`, `restart`. After run:
  `systemctl --user is-active voice-typing` → `active`; `.venv/bin/voicectl status` → `listening: off`
  (the daemon starts NOT-listening by its own default, PRD §4.9 — never hot-mic on boot).
- (g) **Config copied if absent**: `$XDG_CONFIG_HOME/voice-typing/config.toml` exists after run (XDG unset →
  `~/.config/voice-typing/...`); re-run does NOT overwrite an existing file.
- (h) **Printed output (Mode A)** includes: the CUDA verdict; `voicectl toggle|start|stop|status|quit`
  usage; the 2-line tmux snippet (`set -g status-interval 1` + `status-right "#(<repo>/voice_typing/status.sh)"`);
  the Hyprland `source = <repo>/hypr-binds.conf` instruction (forward-looking — P2.M1 creates the file);
  the "daemon running, not listening" summary.
- (i) **No out-of-scope code**: NO edit to `pyproject.toml`/`uv.lock`/`config.toml`/`daemon.py`/`ctl.py`/
  `launch_daemon.sh`/`cuda_check.py`/`prefetch.py`/`status.sh`/`config.py`; NO new Python module; NO
  creation of `systemd/voice-typing.service` content (S2 owns it — install.sh only COPIES it); NO README
  (P2.M1.T2.S1 owns the full usage doc — Mode A = install.sh's printed stdout ONLY); NO hypr-binds.conf
  (P2.M1.T1.S1); NO edit to `PRD.md`/`tasks.json`/`prd_snapshot.md`/`.gitignore`.

## User Persona

**Target User**: the repo owner (dustin) on this exact Arch/Hyprland box — installing or RE-installing
the daemon after a `git pull` / dependency bump. Three secondary consumers read install.sh's behavior:
1. **The systemd unit** (S2) — its `ExecStart` points at `voice_typing/launch_daemon.sh`; install.sh is
   what installs/enables/restarts it. install.sh assumes the unit's ExecStart uses the absolute path
   `/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh` (the contract), so it does NOT
   rewrite ExecStart.
2. **README** (P2.M1.T2.S1) — copies install.sh's printed usage/tmux/hypr snippets verbatim into the
   usage section. The strings must stay stable.
3. **Operators** — re-run `./install.sh` to refresh deps + re-prefetch + restart after editing config.

**Use Case**: `cd /home/dustin/projects/voice-typing && ./install.sh`. uv sync refreshes the venv; the
CUDA smoke prints the verdict; models prefetch into `~/.cache/huggingface`; the unit is installed and the
daemon started (not listening); config.toml lands in XDG for editing; the script prints the exact tmux +
hypr lines to paste. Re-running it is a safe no-op-ish refresh.

**Pain Points Addressed**: (1) PRD §5 + §4.9 specify an idempotent installer but none exists yet — every
prior subtask shipped a component; this is the glue. (2) The CUDA/cuDNN LD_LIBRARY_PATH story
(launch_daemon.sh) + the unit's ExecStart must be wired together or the service dlopens cuDNN and crashes.
(3) Without copying config.toml to XDG, the user's config edits don't survive reinstalls. (4) The tmux +
hypr integration lines must be printed exactly once, in one place (here), and copied to README later.

## Why

- **This is the setup entrypoint.** PRD §5 (installation steps) + §4.9 (systemd service) converge here:
  install.sh is THE thing a user runs to go from `git clone` to a running, un-armed, systemd-managed
  daemon. Every prior subtask (bootstrap, config, textproc, backends, feedback, daemon, voicectl) feeds it.
- **Idempotency is the contract.** Re-runs must not fail, must not re-download models, must not clobber
  user config. `set -euo pipefail` is kept STRICT (so real failures surface) but the two commands that
  legitimately exit nonzero (cuda_check exit 1 = CPU-fallback; prefetch exit 1 = core-model fail) are
  explicitly guarded so a valid/recoverable signal never aborts the install.
- **Explicit paths defeat the zsh-alias trap.** PRD §2: the user's zsh aliases `python`/`uv`/`pytest`.
  A bash script that calls bare `uv` may invoke the alias (or fail). install.sh hardcodes
  `/home/dustin/.local/bin/uv` and `.venv/bin/python` everywhere (every prior subtask did the same).
- **LD_LIBRARY_PATH + ExecStart alignment.** The daemon needs cuDNN/cuBLAS on the loader path at exec
  time. launch_daemon.sh sets it; the unit (S2) ExecStarts launch_daemon.sh. install.sh's CUDA smoke
  reproduces launch_daemon.sh's LD_LIBRARY_PATH export (sanctioned by cuda_check.py's docstring: "reproduce
  that wrapper's LD_LIBRARY_PATH export in the shell") so the smoke test reflects the real runtime env.
- **Mode A docs live here.** The item's DOCS note: install.sh's printed output IS the user-facing
  quick-start. README (P2.M1.T2.S1) copies it. So the printed strings are a product surface, kept stable.

## What

A single ~90-line bash script at the repo root, decomposed into: preflight (paths + session checks) →
7 ordered steps → a printed summary block. The EXACT source is pinned below (copy-pasteable; verified
against the live `launch_daemon.sh` LD one-liner, the `cuda_check.py`/`prefetch.py` CLI exits, the
`config.py` XDG resolution, and the `status.sh` snippet). No flags; no argparse; one linear flow.

### Success Criteria

- [ ] `install.sh` exists at repo root; `bash -n install.sh` clean; `/usr/bin/shellcheck install.sh` clean.
- [ ] `#!/usr/bin/env bash` + `set -euo pipefail`; all uv/python invocations use FULL paths.
- [ ] Step (2) `uv sync` runs; `.venv/bin/python` exists after it.
- [ ] Step (3) cuda smoke prints `VERDICT=` and does NOT abort on `cpu-fallback-required` (exit 1).
- [ ] Step (4) prefetch runs; on failure prints a WARNING and continues (exit 0 overall if rest ok).
- [ ] Step (5) unit installed to `$XDG_CONFIG_HOME/systemd/user/`; daemon-reload+enable+restart;
      `systemctl --user is-active voice-typing` → `active`.
- [ ] Step (6) `$XDG_CONFIG_HOME/voice-typing/config.toml` exists; re-run does NOT overwrite it.
- [ ] Step (7) prints usage + tmux snippet + hypr instruction + "not listening" summary.
- [ ] Idempotent: 2nd run exits 0, no model re-download, no config clobber, no enable error.
- [ ] Post-run `voicectl status` → `listening: off` (un-armed; no hot-mic on boot).
- [ ] No edit to pyproject/uv.lock/config.toml/daemon.py/ctl.py/launch_daemon.sh/cuda_check.py/
      prefetch.py/status.sh/config.py; no new Python module; no systemd unit content (S2); no README.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior codebase knowledge: the full `install.sh` source is pinned below
(verified against the live consumed interfaces); every consumed contract (launch_daemon.sh's LD one-liner,
cuda_check/prefetch CLI exits, config.py's XDG path, status.sh's snippet, the unit's ExecStart=launch_daemon.sh)
is quoted with file:line references; the systemd/bash semantics are cited with URLs; and every validation
command is executable as written (full `/usr/bin/shellcheck`, `/home/dustin/.local/bin/uv`, `.venv/bin/python`).

### Documentation & References

```yaml
# MUST READ — the design + verified facts (THIS is the spec).
- file: plan/001_be48c74bc590/P1M6T1S1/research/install_design.md
  why: "§1 the consumed-interface table (every input install.sh touches). §2 why install.sh reproduces
        launch_daemon.sh's LD_LIBRARY_PATH (cuda_check.py sanctions it). §3 the idempotency matrix
        (uv sync / cuda-check || true / prefetch warn-only / cp-if-absent / enable no-op / restart). §4
        the exact printed output (Mode A — README copies these strings). §5 gotchas G1-G8."
  critical: "G1: cuda_check exit 1 (cpu-fallback) + prefetch exit 1 (core-fail) MUST be ||-guarded or
             set -e aborts. G4: systemd/voice-typing.service is the SIBLING S2's output — install.sh
             copies it and fails CLEARLY if absent. G5: the daemon starts NOT-listening by its own
             default; install.sh passes no flag. G7: config-copy-after-start is safe (config search
             order falls back to repo config.toml)."

- file: plan/001_be48c74bc590/P1M6T1S1/research/external_citations.md
  why: "§1 systemd user units live in $XDG_CONFIG_HOME/systemd/user (ArchWiki Systemd/User) + daemon-reload
        required after unit-file change (freedesktop systemctl, serverfault). §2 set -e + || true (mohanpedala
        gist) — why the two nonzero-exit commands need guards. §3 cp-if-absent / mkdir -p idempotency.
        §4 systemctl --user needs a login session (XDG_RUNTIME_DIR)."

# MUST READ — the consumed contracts (live; quote the exact bits install.sh calls).
- file: voice_typing/launch_daemon.sh
  why: "(1) The SCRIPT_DIR repo-root idiom install.sh reuses: SCRIPT_DIR=$(cd $(dirname $0) && pwd).
        (2) The EXACT LD_LIBRARY_PATH python one-liner install.sh reproduces for the cuda smoke (the
        nvidia.cublas.lib/nvidia.cudnn.lib namespace-package __path__[0] resolver). The unit's ExecStart
        (S2) points at THIS script, so install.sh does not set LD_LIBRARY_PATH into the unit — it only
        reproduces the env for the one-shot cuda_check run."
  critical: "Do NOT exec launch_daemon.sh from install.sh — it execs the daemon. Reproduce ONLY its
             LD_LIBRARY_PATH export (sanctioned by cuda_check.py docstring). Do NOT edit launch_daemon.sh."

- file: voice_typing/cuda_check.py
  why: "The CLI install.sh runs in step (3): `python -m voice_typing.cuda_check` prints
        ctranslate2_version=, cuda_device_count=, torch_cuda_available=, VERDICT=<cuda-ok|cpu-fallback-
        required>, # <reason>, # resolved: device=.. . Exit 0 = cuda-ok, exit 1 = cpu-fallback-required.
        Docstring: 'cpu-fallback-required is a VALID degraded mode, not an error — callers under set -e
        should capture the VERDICT= line or || true.' That is EXACTLY what install.sh does. Also: it
        'does NOT load cuDNN' (driver-only probe), so it runs even if LD_LIBRARY_PATH is unset, but
        install.sh sets it anyway to be faithful to 'via launch_daemon.sh env'."
  critical: "cuda_check MUST NOT set LD_LIBRARY_PATH itself (docstring); install.sh sets it in the shell.
             Exit 1 must NOT abort install.sh (it is the valid CPU path)."

- file: voice_typing/prefetch.py
  why: "The CLI install.sh runs in step (4): `python -m voice_typing.prefetch` → CORE+OPTIONAL repos.
        _main() exits 0 iff ALL CORE repos cached; 1 on a CORE fail (OPTIONAL/turbo fails are warnings).
        snapshot_download skips etag-matched blobs -> re-runs are free (idempotent). On CORE fail the
        daemon lazy-downloads at first run, so install.sh treats prefetch failure as a WARNING + continue."
  critical: "Exit 1 (core fail) must NOT abort install.sh. Do NOT pass cache_dir/local_dir/force_download
             (prefetch.py docstring: they are load-bearing defaults)."

- file: voice_typing/config.py
  why: "The XDG_CONFIG_HOME resolution install.sh must MIRROR (do not import — bash): _xdg_config_path()
        = os.environ.get('XDG_CONFIG_HOME','').strip() or expanduser('~/.config'), joined with
        'voice-typing/config.toml'. So install.sh's config dest dir = ${XDG_CONFIG_HOME:-$HOME/.config}/
        voice-typing/config.toml. The systemd user dir uses the SAME XDG root: ${XDG_CONFIG_HOME:-$HOME/
        .config}/systemd/user/voice-typing.service."
  critical: "Mirror the fallback exactly (XDG unset/empty -> ~/.config). The config SEARCH ORDER is
             XDG -> repo -> defaults, so copying is for user-edit survival, not for the daemon to boot."

- file: voice_typing/status.sh
  why: "The tmux snippet install.sh prints in step (7) — copy the 2 lines from status.sh's header comment
        VERBATIM (status.sh owns the canonical wording; install.sh reprints it, README later reprints it):
          set -g status-interval 1
          set -g status-right \"#(<repo>/voice_typing/status.sh)\""
  critical: "Point the path at the absolute repo location of status.sh. Do NOT edit status.sh."

- file: config.toml
  why: "The repo default install.sh copies to XDG in step (6). It is at REPO ROOT (sibling of install.sh),
        referenced by repo-relative path. config.py _repo_config_path() resolves the same file."
  critical: "Copy only IF the dest is absent (cp-if-absent) — never overwrite the user's edited config."

- file: pyproject.toml
  why: "Confirms: name=voice-typing; [project.scripts] voicectl='voice_typing.ctl:main' and
        voice-typing-daemon='voice_typing.daemon:main' (P1.M1.T1.S1) — so .venv/bin/voicectl exists after
        uv sync (install.sh prints its usage). DO NOT edit pyproject."
  critical: "No new dependency, no script change. install.sh ADDS NOTHING to pyproject."

# MUST READ — the SIBLING that produces the unit install.sh installs.
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M6.T1.S2 creates systemd/voice-typing.service (ExecStart=launch_daemon.sh, Restart=on-failure,
        WantedBy=default.target, starts NOT-listening). install.sh COPIES that file — it does NOT author
        unit content. If S2 has not merged when S1 runs its own validation, systemd/voice-typing.service
        is absent and install.sh's step (5) fails CLEARLY ('missing — run P1.M6.T1.S2 first') rather than
        silently skip."
  critical: "install.sh references systemd/voice-typing.service by repo-relative path. Do NOT generate the
             unit here (scope boundary with S2)."

# External — the contract citations (verified reachable).
- url: https://wiki.archlinux.org/title/Systemd/User
  why: "User unit files live under ~/.config/systemd/user/ (= $XDG_CONFIG_HOME/systemd/user/); --user
        enable symlinks into default.target.wants (start at login); --user needs a user manager (login
        session, XDG_RUNTIME_DIR set). Backs the unit dir + the session preflight check."
- url: https://www.freedesktop.org/software/systemd/man/systemctl.html
  why: "'daemon-reload ... honors --user' — the documented reload after copying/editing a unit file.
        Backs the daemon-reload BEFORE enable/restart ordering."
- url: https://gist.github.com/mohanpedala/1e2ff5661761d3abd0385e8223e16425
  why: "set -e aborts on the first nonzero command; || true / if ! cmd; then is the sanctioned escape for
        commands whose nonzero exit is an expected signal (cuda_check exit 1, prefetch exit 1)."

# Background — the PRPs that produced the consumed interfaces.
- file: plan/001_be48c74bc590/P1M1T2S1/PRP.md   # launch_daemon.sh (the LD wrapper install.sh mirrors)
- file: plan/001_be48c74bc590/P1M1T2S2/PRP.md   # cuda_check.py (the smoke install.sh runs)
- file: plan/001_be48c74bc590/P1M1T3S1/PRP.md   # prefetch.py (step 4)
- file: plan/001_be48c74bc590/P1M2T1S2/PRP.md   # config.toml (the file copied to XDG; its header documents the copy)
- file: plan/001_be48c74bc590/P1M3T2S1/PRP.md   # status.sh (the snippet install.sh reprints)
- file: plan/001_be48c74bc590/P1M5T1S1/PRP.md   # voicectl (usage install.sh prints)
```

### Current Codebase tree (state at P1.M6.T1.S1 start — all of P1.M1–M5 landed or landing in parallel)

```bash
/home/dustin/projects/voice-typing/
├── .git/ .gitignore .venv/        # DO NOT touch .gitignore
├── PRD.md                         # READ-ONLY (§5 install steps, §4.9 systemd service, §2 zsh aliases)
├── config.toml                    # READ ONLY (copied to XDG in step 6)
├── pyproject.toml uv.lock         # DO NOT touch (voicectl + voice-typing-daemon entries already declared)
├── install.sh                     # ← CREATE (this task): repo root, chmod +x, the 7-step idempotent installer
├── voice_typing/
│   ├── __init__.py config.py textproc.py typing_backends.py feedback.py   # READ ONLY
│   ├── cuda_check.py prefetch.py launch_daemon.sh status.sh daemon.py ctl.py  # READ ONLY (consumed CLIs/wrapper/snippet)
└── tests/                         # READ ONLY (no new Python test this task — see Validation §testing gap)
```

### Desired Codebase tree with files to be added

```bash
install.sh                        # NEW — idempotent setup entrypoint (7 steps + printed Mode-A summary)
# NOTE: systemd/voice-typing.service is created by the SIBLING S2 (P1.M6.T1.S2), NOT here.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 (G1) — set -euo pipefail + two intentionally-nonzero commands. cuda_check exits 1 on
#   cpu-fallback-required (a VALID mode; cuda_check.py docstring) and prefetch exits 1 on a core-model
#   failure (recoverable — daemon lazy-downloads). A BARE invocation aborts the whole install under set -e.
#   Guard BOTH with the if-!-capture idiom: `if ! out="$(cmd 2>&1)"; then :; fi` (cuda) / `if ! cmd; then
#   warn; fi` (prefetch). Everything else (uv sync, systemctl, cp, mkdir) keeps abort-on-failure.

# CRITICAL #2 (G2) — FULL PATHS, bash not zsh. The user's zsh aliases python/uv/pytest (PRD §2). install.sh
#   is #!/usr/bin/env bash and hardcodes /home/dustin/.local/bin/uv and <repo>/.venv/bin/python everywhere.
#   Never bare `python`/`uv`. (/usr/bin/tmux is referenced in the printed snippet, not invoked.)

# CRITICAL #3 (G3) — XDG_CONFIG_HOME resolution MUST mirror voice_typing/config.py (bash, not import):
#   XDG_CONFIG_HOME unset/empty -> ~/.config. The config dest = $XDG/voice-typing/config.toml; the systemd
#   user dir = $XDG/systemd/user/voice-typing.service. Resolve XDG ONCE, reuse for both.

# CRITICAL #4 (G4) — S2 dependency. systemd/voice-typing.service is authored by the SIBLING P1.M6.T1.S2.
#   install.sh COPIES it (does not write unit content). If the file is absent, fail CLEARLY with a message
#   pointing at S2 — do NOT silently skip the service step. (At orchestrator run time S2 precedes this run.)

# CRITICAL #5 (G5) — no hot-mic. The daemon starts NOT-listening by its OWN default (daemon.py main() ->
#   daemon.run(); PRD §4.9). install.sh passes no flag; `systemctl restart` brings it up un-armed. The
#   acceptance check is `voicectl status` -> listening: off. Do NOT arm the mic in install.sh.

# CRITICAL #6 (G6) — systemctl --user needs a login session. It requires the per-user systemd manager
#   (XDG_RUNTIME_DIR set + D-Bus user bus). install.sh checks XDG_RUNTIME_DIR is set and errors clearly if
#   not. It is NOT meant for bare cron/SSH-without-session. (Consistent with the daemon's own
#   XDG_RUNTIME_DIR requirement for its socket + state file.)

# CRITICAL #7 (G7) — config-copy AFTER service-start is safe. The contract orders step (5) service then
#   (6) config copy. The daemon's config SEARCH ORDER (XDG -> repo -> defaults) falls back to the repo
#   config.toml when the XDG copy is absent, so the first start reads valid defaults. The XDG copy is for
#   the user's FUTURE edits to survive reinstalls, not for boot. Honor the contract order; do not reorder.

# CRITICAL #8 (G8) — restart vs start. Use `systemctl --user restart` (not `start`): restart starts a
#   stopped unit AND applies a freshly-copied unit file to a running one — the correct idempotent re-run
#   behavior. `enable` (without --now) symlinks into default.target.wants (start at login); `restart`
#   starts it now. daemon-reload BEFORE enable/restart so systemd reads the copied unit.

# CRITICAL #9 (G9) — LD_LIBRARY_PATH for the smoke. cuda_check does NOT set it (docstring); install.sh
#   reproduces launch_daemon.sh's export in the shell (the sanctioned manual-run path). If the nvidia
#   wheels aren't importable, warn + continue (cuda_check's driver-only probe still works). This is a few
#   lines of DELIBERATE duplication (cuda_check.py sanctions it), not a DRY violation.

# CRITICAL #10 (G10) — no bash test framework in the repo (pytest is Python-only). The gate is
#   bash -n (syntax) + /usr/bin/shellcheck (lint, installed) + a manual idempotency run + post-condition
#   checks (service active, voicectl status listening:off, XDG config present, no model re-download on
#   2nd run). bats / pytest-shell are OUT OF SCOPE (would be a new dependency + new convention).
```

## Implementation Blueprint

### Data models and structure

No data model. A single linear bash script: shebang → `set -euo pipefail` → path constants → repo-root
resolve → preflight (session + tools) → 7 steps → printed summary. No functions except `_setup_cuda_libs()`
(the LD_LIBRARY_PATH reproducer) and a couple of small helpers if helpful. Exit 0 on success, nonzero on
a real failure (preflight/tool/unit-source missing). NEVER nonzero on cuda-check/prefetch signals.

### `install.sh` reference implementation (research §1–§5 — implement verbatim; verified against live inputs)

```bash
#!/usr/bin/env bash
#
# install.sh — idempotent setup entrypoint for voice-typing (PRD §5, §4.9; P1.M6.T1.S1).
#
# WHAT THIS IS
#   The single script a user runs to go from `git clone` to a running, systemd-managed,
#   UN-ARMED voice-typing daemon. Re-runnable: a 2nd run refreshes deps, skips already-cached
#   models, never overwrites the user's XDG config, and never errors on an already-enabled unit.
#
# STEPS  (PRD §5 + §4.9 + the item contract)
#   (1) cd to repo root
#   (2) uv sync                              -> creates/refreshes .venv/
#   (3) cuda smoke under launch_daemon.sh env-> prints VERDICT=cuda-ok|cpu-fallback-required
#   (4) prefetch models                      -> ~/.cache/huggingface (idempotent; warn-only on fail)
#   (5) install + daemon-reload + enable + restart the systemd user unit
#   (6) copy config.toml to $XDG_CONFIG_HOME/voice-typing/ IF ABSENT
#   (7) print usage + tmux status snippet + Hyprland source instruction
#
# The daemon starts NOT-listening (PRD §4.9) — it never hot-mics on boot; `voicectl toggle` arms it.
#
# This script's stdout IS the user-facing install/usage quick-start (Mode A docs). README (P2.M1.T2.S1)
# copies the usage/tmux/hypr snippets verbatim — keep them stable.
#
# FULL PATHS are used for uv/python because the user's zsh aliases them (PRD §2). This is bash, not zsh.
set -euo pipefail

# --- explicit tool paths (zsh-alias hazard; PRD §2) ---
UV="/home/dustin/.local/bin/uv"

# --- repo root, CWD-independent (launch_daemon.sh SCRIPT_DIR idiom) ---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$SCRIPT_DIR"
cd "$REPO"
PY="$REPO/.venv/bin/python"

# --- preflight: we need a login session for `systemctl --user` + the daemon's own XDG_RUNTIME_DIR ---
if [ -z "${XDG_RUNTIME_DIR:-}" ]; then
  echo "install.sh: XDG_RUNTIME_DIR is not set — run this from a login session (systemctl --user needs it)." >&2
  exit 1
fi
command -v "$UV" >/dev/null 2>&1 || { echo "install.sh: uv not found at $UV" >&2; exit 1; }
command -v systemctl >/dev/null 2>&1 || { echo "install.sh: systemctl not found" >&2; exit 1; }

# XDG_CONFIG_HOME, mirroring voice_typing/config.py (unset/empty -> ~/.config).
XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"

# --- (2) uv sync -----------------------------------------------------------------
echo "==> [1/7] uv sync"
"$UV" sync
[ -x "$PY" ] || { echo "install.sh: $PY missing after uv sync" >&2; exit 1; }

# Reproduce launch_daemon.sh's LD_LIBRARY_PATH export for the cuda smoke. cuda_check.py MUST NOT set it
# itself (the dynamic linker reads it only at exec); the sanctioned manual-run path is "reproduce that
# wrapper's LD_LIBRARY_PATH export in the shell first" (cuda_check.py docstring). Same python one-liner
# as launch_daemon.sh (nvidia.*.lib namespace-package __path__[0] resolver).
_setup_cuda_libs() {
  if CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b
def _d(m):
    f=getattr(m,"__file__",None)
    return os.path.dirname(f) if f else next(iter(m.__path__))
print(_d(a)+":"+_d(b))' 2>/dev/null)"; then
    export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  else
    echo "install.sh: WARNING — nvidia wheels not importable; running cuda smoke without LD_LIBRARY_PATH (cpu-fallback expected)." >&2
  fi
}

# --- (3) cuda smoke (print verdict; exit 1 = cpu-fallback = VALID, do NOT abort) --
echo "==> [2/7] CUDA smoke"
_setup_cuda_libs
# cuda_check exits 1 on cpu-fallback-required (a valid degraded mode) — capture, never abort.
SMOKE=""
if ! SMOKE="$("$PY" -m voice_typing.cuda_check 2>&1)"; then
  :  # handled via VERDICT= below
fi
printf '%s\n' "$SMOKE" | sed 's/^/    /'
VERDICT="$(printf '%s\n' "$SMOKE" | sed -n 's/^VERDICT=//p')"
case "$VERDICT" in
  cuda-ok)                 echo "    -> GPU available: daemon will use CUDA." ;;
  cpu-fallback-required)   echo "    -> No usable CUDA: daemon will run in CPU mode (slower; functional)." ;;
  *) echo "    -> WARNING: could not parse cuda_check VERDICT." >&2 ;;
esac

# --- (4) prefetch models (idempotent; warn + continue — daemon lazy-downloads on miss) -
echo "==> [3/7] prefetch models"
if ! "$PY" -m voice_typing.prefetch; then
  echo "install.sh: WARNING — prefetch reported a core-model failure; the daemon will download missing models on first run." >&2
fi

# --- (5) install + daemon-reload + enable + restart the systemd user unit -------------
echo "==> [4/7] install systemd user service"
SRC_UNIT="$REPO/systemd/voice-typing.service"
if [ ! -f "$SRC_UNIT" ]; then
  echo "install.sh: $SRC_UNIT missing — create it first (P1.M6.T1.S2)." >&2
  exit 1
fi
USER_UNIT_DIR="$XDG_CONFIG_HOME/systemd/user"
mkdir -p "$USER_UNIT_DIR"
cp "$SRC_UNIT" "$USER_UNIT_DIR/voice-typing.service"
systemctl --user daemon-reload
systemctl --user enable voice-typing.service
# restart (not start): starts a stopped unit AND applies a freshly-copied unit to a running one.
systemctl --user restart voice-typing.service

# --- (6) copy config.toml to XDG IF ABSENT (never overwrite the user's edits) ---------
echo "==> [5/7] config"
CFG_DIR="$XDG_CONFIG_HOME/voice-typing"
mkdir -p "$CFG_DIR"
if [ ! -f "$CFG_DIR/config.toml" ]; then
  cp "$REPO/config.toml" "$CFG_DIR/config.toml"
  echo "    installed $CFG_DIR/config.toml"
else
  echo "    kept existing $CFG_DIR/config.toml (not overwritten)"
fi

# --- (7) print usage + tmux snippet + hypr instruction --------------------------------
echo "==> [6/7] daemon status"
# Give systemd a beat to mark the unit active, then report.
if systemctl --user is-active --quiet voice-typing.service; then
  echo "    voice-typing.service: active"
else
  echo "    voice-typing.service: NOT active — check 'journalctl --user -u voice-typing -e'" >&2
fi

echo
echo "==> [7/7] done — voice-typing installed"
echo "daemon : running and NOT listening (no hot-mic on boot). Run 'voicectl toggle' to arm the mic."
echo "CUDA   : ${VERDICT:-unknown}"
echo
echo "usage  : $REPO/.venv/bin/voicectl toggle|start|stop|status|quit"
echo "          (bind SUPER+ALT+D -> voicectl toggle; see the Hyprland note below)"
echo
echo "tmux status (add these TWO lines to ~/.tmux.conf — we never edit it for you):"
echo '  set -g status-interval 1'
echo "  set -g status-right \"#($REPO/voice_typing/status.sh)\""
echo
echo "Hyprland (after P2.M1 creates hypr-binds.conf), add to ~/.config/hypr/hyprland.conf:"
echo "  source = $REPO/hypr-binds.conf"
echo
echo "logs   : journalctl --user -u voice-typing -f"
echo "config : $CFG_DIR/config.toml"
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — confirm the live consumed surface + that the venv exists (so smoke/prefetch are runnable).
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/launch_daemon.sh && test -f voice_typing/cuda_check.py \
        && test -f voice_typing/prefetch.py && test -f voice_typing/status.sh \
        && test -f config.toml && test -f pyproject.toml && echo "consumed files OK"
      test -x .venv/bin/python && echo "venv OK" || echo "venv missing — uv sync (step 2) will create it"
      grep -n "voicectl\s*=" pyproject.toml            # expect: voicectl = "voice_typing.ctl:main"
      test ! -f install.sh && echo "install.sh absent (expected — this task creates it)"
      command -v /usr/bin/shellcheck >/dev/null && echo "shellcheck OK"
      test -x /home/dustin/.local/bin/uv && echo "uv OK"
  - EXPECTED: all consumed files present; voicectl entry declared; install.sh absent; shellcheck + uv on PATH.
    NOTE: systemd/voice-typing.service may be ABSENT (sibling S2 not yet merged) — that is EXPECTED at this
    task's own validation time; the real orchestrator run has S2 precede it. install.sh fails CLEARLY if absent.
  - DO NOT create/edit any file, run uv sync/add, or touch other modules.

Task 1: CREATE install.sh at the repo root — the reference implementation above VERBATIM.
  - FILE: install.sh (NEW, repo root). Then `chmod +x install.sh`.
  - KEEP: #!/usr/bin/env bash + set -euo pipefail; FULL paths (/home/dustin/.local/bin/uv, .venv/bin/python);
    the if-!-capture guards on cuda_check + prefetch (G1); the cp-if-absent config copy (G3/G7); restart
    not start (G8); daemon-reload before enable/restart (G8); XDG_CONFIG_HOME fallback to ~/.config (G3);
    XDG_RUNTIME_DIR preflight (G6); the clear S2-missing failure (G4); the 7 printed summary blocks (Mode A).
  - DO NOT: exec launch_daemon.sh (reproduce ONLY its LD export); edit any Python file / pyproject / uv.lock
    / config.toml; author systemd/voice-typing.service content (S2); add a README (P2.M1.T2.S1); create
    hypr-binds.conf (P2.M1.T1.S1); arm the mic; reorder steps 5 and 6 (G7); use bare python/uv.

Task 2: VALIDATE — run the Validation Loop L1-L4. Iterate until all gates pass.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M6.T1.S1: idempotent install.sh (uv sync, CUDA smoke, prefetch, systemd unit, XDG config, print snippets)".
```

### Implementation Patterns & Key Details

```bash
# Pattern: capture a command whose nonzero exit is an EXPECTED signal (G1) — do NOT let set -e abort.
if ! SMOKE="$("$PY" -m voice_typing.cuda_check 2>&1)"; then :; fi   # exit 1 == cpu-fallback (valid)
if ! "$PY" -m voice_typing.prefetch; then echo "WARNING ..."; fi    # exit 1 == core-model fail (recoverable)

# Pattern: idempotent "copy if absent" (G3) — version-independent, always exits 0.
if [ ! -f "$CFG_DIR/config.toml" ]; then cp "$REPO/config.toml" "$CFG_DIR/config.toml"; fi

# Pattern: reproduce launch_daemon.sh's LD_LIBRARY_PATH (G9) — same nvidia.*.lib namespace resolver.
CUDA_LIBS="$("$PY" -c 'import os,nvidia.cublas.lib as a,nvidia.cudnn.lib as b
def _d(m):
    f=getattr(m,"__file__",None); return os.path.dirname(f) if f else next(iter(m.__path__))
print(_d(a)+":"+_d(b))' 2>/dev/null)" && export LD_LIBRARY_PATH="$CUDA_LIBS${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

# Pattern: systemd user unit install (G8) — daemon-reload BEFORE enable/restart; restart not start.
mkdir -p "$XDG_CONFIG_HOME/systemd/user"
cp "$REPO/systemd/voice-typing.service" "$XDG_CONFIG_HOME/systemd/user/voice-typing.service"
systemctl --user daemon-reload
systemctl --user enable  voice-typing.service   # idempotent (no-op + exit 0 if already enabled)
systemctl --user restart voice-typing.service   # starts stopped / applies fresh unit to running
```

### Integration Points

```yaml
SYSTEMD (user unit):
  - src:        "$REPO/systemd/voice-typing.service"          # authored by S2 (P1.M6.T1.S2)
  - dest:       "$XDG_CONFIG_HOME/systemd/user/voice-typing.service"   # XDG unset -> ~/.config/systemd/user/
  - commands:   systemctl --user daemon-reload; enable; restart
  - ExecStart:  the unit points at $REPO/voice_typing/launch_daemon.sh (contract) — install.sh does NOT set it

CONFIG (XDG copy):
  - src:   "$REPO/config.toml"                                 # repo default (P1.M2.T1.S2)
  - dest:  "$XDG_CONFIG_HOME/voice-typing/config.toml"         # XDG unset -> ~/.config/voice-typing/...
  - rule:  copy IF ABSENT only (never overwrite user edits)

VENV (consumed, created by step 2):
  - python: "$REPO/.venv/bin/python"   # created by `uv sync`; used for cuda_check + prefetch + the LD probe
  - voicectl: "$REPO/.venv/bin/voicectl"  # console script (P1.M5.T1.S1); usage printed in step 7

MODELS (consumed, populated by step 4):
  - cache: ~/.cache/huggingface/hub   # prefetch.py default; faster-whisper reads it at daemon start

NO pyproject / uv.lock / config.toml / daemon.py / ctl.py edit. NO new dependency. NO new env var
(install.sh reads XDG_RUNTIME_DIR + XDG_CONFIG_HOME, both standard).
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
bash -n install.sh && echo "syntax OK"
/usr/bin/shellcheck install.sh        # installed at /usr/bin/shellcheck; expect 0 errors
# Structural invariants (grep — fast, no side effects):
grep -q 'set -euo pipefail'        install.sh && echo "strict mode OK"
grep -q '/home/dustin/.local/bin/uv' install.sh && echo "full uv path OK"
grep -q '\.venv/bin/python'         install.sh && echo "full python path OK"
grep -q 'if ! .*cuda_check'         install.sh && echo "cuda-check guarded (G1) OK"
grep -q 'if ! .*prefetch'           install.sh && echo "prefetch guarded (G1) OK"
grep -q 'daemon-reload'             install.sh && echo "daemon-reload present OK"
grep -q 'systemctl --user restart'  install.sh && echo "restart (not start) OK"
# Expected: all OK, shellcheck 0 errors. Fix before proceeding.
```

### Level 2: Component Validation (bash scripts have no Python unit tests — see note)

```bash
# The repo has NO bash test framework (pytest is Python-only). The structural grep checks above (L1) are
# the automated gate. The behavioral validation is L3 (a real run + post-conditions). OPTIONAL future
# hardening (OUT OF SCOPE here): bats-core or shellcheck in CI. Do NOT add a dependency this task.
echo "L2: no Python unit test applicable to a bash install script — covered by L1 (shellcheck) + L3 (run)."
```

### Level 3: Integration Testing (System Validation) — a real run; requires a login session + GPU optional

```bash
cd /home/dustin/projects/voice-typing
echo "$XDG_RUNTIME_DIR"          # MUST be set (preflight checks it)
./install.sh                     # expect: 7 steps, VERDICT= line, then the summary block

# Post-conditions (the acceptance checks):
systemctl --user is-active voice-typing.service      # expect: active
.venv/bin/voicectl status                            # expect: listening: off  (un-armed, G5)
test -f "${XDG_CONFIG_HOME:-$HOME/.config}/voice-typing/config.toml" && echo "XDG config present"
test -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/voice-typing.service" && echo "unit installed"

# Idempotency: run AGAIN; expect exit 0, no model re-download, config NOT overwritten.
sha256sum ~/.cache/huggingface/hub 2>/dev/null | head    # capture before 2nd run (model cache fingerprint)
CFG="${XDG_CONFIG_HOME:-$HOME/.config}/voice-typing/config.toml"
echo "# user edit $(date)" >> "$CFG"                      # simulate a user edit
./install.sh                                              # expect exit 0
grep -q "# user edit" "$CFG" && echo "user edit PRESERVED (idempotent config copy OK)"
journalctl --user -u voice-typing -n 20 --no-pager       # sanity: daemon logs, no crash loop
# Expected: service active, voicectl status listening:off, XDG config + unit present, 2nd run exit 0,
# user edit preserved, daemon not crash-looping.
```

### Level 4: Creative & Domain-Specific Validation

```bash
# CPU-fallback path (if you can force it): set device off / hide GPU is not required — cuda_check already
# prints VERDICT=cpu-fallback-required on a no-GPU box and install.sh MUST continue. Verify by reading the
# printed verdict line from a real run (L3). To simulate the guard without a GPU, you may temporarily run:
#   XDG_CONFIG_HOME=/tmp/vt-test XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" ./install.sh
# and confirm it does NOT abort on the cuda verdict and still installs the unit + config under /tmp/vt-test.

# S2-absent guard (G4): if systemd/voice-typing.service does not exist yet, install.sh must FAIL CLEARLY:
#   (cd /tmp && mkdir vt-guard && cp /home/dustin/projects/voice-typing/install.sh /tmp/vt-guard/ && \
#    cd /tmp/vt-guard && ./install.sh 2>&1 | grep -q 'systemd/voice-typing.service missing') && echo "G4 guard OK"
# (Only run this in a throwaway dir; the real run has S2 present.)

# No-hot-mic (G5) is asserted by `voicectl status` -> listening: off in L3.
# Explicit-paths (G2): `grep -cE '\b(uv|python|pytest)\b' install.sh | grep -qv '^0$'` should find NO bare
#   invocations outside comments (all use full paths). Spot-check by eye.
# Expected: CPU verdict does not abort; S2-absent fails clearly; daemon stays un-armed; no bare tool names.
```

## Final Validation Checklist

### Technical Validation

- [ ] `bash -n install.sh` clean; `/usr/bin/shellcheck install.sh` 0 errors.
- [ ] `set -euo pipefail` present; all uv/python invocations use FULL paths (G2).
- [ ] cuda_check + prefetch are `if !`-guarded (G1); never abort the install on their nonzero exit.
- [ ] `chmod +x install.sh`.
- [ ] (No mypy/pytest for a bash script — L1 shellcheck + L3 run are the gates.)

### Feature Validation

- [ ] Step (2) `uv sync` runs; `.venv/bin/python` exists after it.
- [ ] Step (3) prints `VERDICT=cuda-ok|cpu-fallback-required`; does NOT abort on cpu-fallback.
- [ ] Step (4) prefetch runs; warns + continues on failure (exit 0 overall if rest ok).
- [ ] Step (5) unit copied to `$XDG_CONFIG_HOME/systemd/user/`; daemon-reload+enable+restart;
      `systemctl --user is-active voice-typing` → `active`.
- [ ] Step (6) `$XDG_CONFIG_HOME/voice-typing/config.toml` exists; re-run preserves a user edit.
- [ ] Step (7) prints usage + tmux snippet + hypr instruction + "not listening" summary.
- [ ] Idempotent: 2nd run exit 0, no model re-download, no config clobber, no enable error.
- [ ] Post-run `voicectl status` → `listening: off` (un-armed; G5).

### Code Quality Validation

- [ ] Repo-root placement (sibling of config.toml; PRD §4.1); CWD-independent repo-root resolve.
- [ ] Mirrors `config.py`'s XDG_CONFIG_HOME fallback (unset → ~/.config) (G3).
- [ ] Reproduces launch_daemon.sh's LD_LIBRARY_PATH one-liner verbatim (G9).
- [ ] Fails CLEARLY if `systemd/voice-typing.service` is absent (G4); does NOT author unit content (S2).
- [ ] No edit to pyproject/uv.lock/config.toml/daemon.py/ctl.py/launch_daemon.sh/cuda_check.py/
      prefetch.py/status.sh/config.py; no new Python module; no README; no hypr-binds.conf.

### Documentation & Deployment

- [ ] Header comment documents the 7 steps + the no-hot-mic guarantee + the full-paths rationale.
- [ ] Printed summary is accurate + copy-paste-ready (README P2.M1.T2.S1 copies it verbatim).
- [ ] No new env vars (reads standard XDG_RUNTIME_DIR / XDG_CONFIG_HOME).

---

## Anti-Patterns to Avoid

- ❌ Don't let cuda_check/prefetch nonzero exits abort `set -e` — guard them (G1).
- ❌ Don't use bare `python`/`uv`/`pytest` — full paths (zsh aliases; G2).
- ❌ Don't `exec launch_daemon.sh` from install.sh — reproduce ONLY its LD_LIBRARY_PATH export (G9).
- ❌ Don't author `systemd/voice-typing.service` content here — S2 owns it; install.sh only COPIES (G4).
- ❌ Don't reorder steps 5 and 6 — the config-copy-after-start is safe by the search order (G7).
- ❌ Don't use `start` over `restart` — restart applies a fresh unit file on re-run (G8).
- ❌ Don't skip `daemon-reload` — systemd keeps the stale in-memory unit until reload (G8).
- ❌ Don't `cp` config unconditionally — copy IF ABSENT so user edits survive (G3).
- ❌ Don't arm the mic in install.sh — the daemon starts NOT-listening by default (G5).
- ❌ Don't add a bash test framework (bats) or a README — out of scope (G10); shellcheck + manual run.
- ❌ Don't catch all failures with `|| true` — keep uv sync/systemctl/cp/mkdir strict (real failures must surface).

---

## Confidence Score

**9/10.** Every consumed interface is quoted verbatim from the LIVE files (launch_daemon.sh's LD one-liner,
cuda_check/prefetch CLI exits + docstrings, config.py's `_xdg_config_path`, status.sh's snippet, the
pyproject scripts). The systemd user-unit install semantics (dir = `$XDG_CONFIG_HOME/systemd/user`,
daemon-reload before enable/restart, restart-not-start) are cited from ArchWiki/freedesktop. The full
install.sh source is copy-pasteable and verified against those inputs; the 4 validation levels are
executable as written. The one residual coupling: step (5) copies `systemd/voice-typing.service`, which
the SIBLING S2 authors — install.sh fails CLEARLY if it is absent (G4), and the orchestrator runs S2
before this task's real run, so timing risk is contained. No dependency on the in-flight P1.M5.T1.S1
(voicectl) beyond its console-script entry being declared (already true); install.sh only PRINTS its
usage, it does not call it.
