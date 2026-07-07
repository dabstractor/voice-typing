# PRP — P1.M6.T1.S2: `systemd/voice-typing.service` unit (ExecStart→wrapper, un-armed, auto-restart)

## Goal

**Feature Goal**: Create **`systemd/voice-typing.service`** — a systemd **user** service unit that
runs the voice-typing daemon via the LD_LIBRARY_PATH wrapper, auto-restarts on crash, and starts at
login — while the daemon itself boots **not-listening** (never hot-mic on boot). It is the install
target consumed by the sibling `install.sh` (P1.M6.T1.S1) and the artifact that satisfies PRD §4.9 +
acceptance criterion 6.

**Deliverable** (1 file — 1 ADD; **NO** edit to anything else):
1. `systemd/voice-typing.service` — NEW. A minimal systemd unit (INI): `[Unit]` (Description +
   `After=pipewire.service ydotool.service`), `[Service]` (`ExecStart=/home/dustin/projects/voice-
   typing/voice_typing/launch_daemon.sh`, `Restart=on-failure`, `RestartSec=2`, + the inline Mode-A
   comment explaining the wrapper + un-armed-start rationale), `[Install]` (`WantedBy=default.target`).
   Exact content pinned verbatim in the Implementation Blueprint (copy-pasteable).

**Success Definition**:
- (a) File exists at `systemd/voice-typing.service`; `systemd-analyze verify systemd/voice-typing.service`
  reports **no errors** (the canonical static unit-file linter; runs without starting anything).
- (b) ExecStart points at the **wrapper** `/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh`
  — NOT `.venv/bin/python -m voice_typing.daemon` (the PRD §4.9 placeholder is deliberately overridden
  by this item's contract + the wrapper PRP's binding integration point).
- (c) **No `Environment=LD_LIBRARY_PATH`** directive (commented or live) — the wrapper sets it
  dynamically at exec; the unit's inline comment says so. A baked value would go stale on `uv sync`.
- (d) `Restart=on-failure` + `RestartSec=2`; `daemon.py main()` returns 1 on a fatal lifecycle error
  (auto-restart) and 0 on clean shutdown (no restart) — semantics align.
- (e) `After=pipewire.service ydotool.service` — BOTH verified user-scope units on this machine, so
  the ordering resolves within the user manager.
- (f) `WantedBy=default.target` (user scope → starts at login, not boot).
- (g) Inline comment present explaining BOTH (1) the wrapper + no-Environment= rationale (PRD §8 risk
  row #1) and (2) the un-armed-start rationale (PRD §4.9) — this is the item's [Mode A] DOCS deliverable.
- (h) No out-of-scope edits: NO change to `launch_daemon.sh`/`daemon.py`/`install.sh`/`pyproject.toml`/
  `config.toml`/any Python module; NO README (P2.M1.T2.S1); NO hypr-binds.conf (P2.M1.T1.S1); NO
  `tasks.json`/`PRD.md`/`prd_snapshot.md`/`.gitignore`.

## User Persona

**Target User**: the repo owner (dustin) on this Arch/Hyprland box, AND the systemd user manager. The
unit's human reader is an **operator** debugging "why won't the daemon start / why does it crash on
cuDNN / why isn't it listening". The unit's machine reader is **systemd** (user manager) + the sibling
`install.sh` (which copies it).

**Use Case**: `install.sh` copies this file → `~/.config/systemd/user/voice-typing.service`, runs
`daemon-reload`, `enable` (symlink into `default.target.wants`), `restart` (start now). Thereafter:
systemd starts the daemon at every login (not-listening), restarts it within 2 s if it crashes, and an
operator inspects it with `systemctl --user status voice-typing` / `journalctl --user -u voice-typing`.

**Pain Points Addressed**: (1) PRD §4.9 + §5 require a systemd user service but none exists yet.
(2) The cuDNN `LD_LIBRARY_PATH` story (launch_daemon.sh) must be wired to ExecStart or the service
dlopens cuDNN and crash-loops at startup. (3) The daemon must NEVER hot-mic on boot (privacy); the unit
must make the un-armed default visible/auditable.

## Why

- **This is the run-time packaging.** install.sh (S1) is the SETUP entrypoint; this unit is what the
  setup INSTALLS so the daemon survives logout/reboot and auto-recovers from a crash. Together they
  close PRD §4.9 + §5.
- **ExecStart → wrapper is load-bearing.** The daemon crashes at startup with `cannot load
  libcudnn_ops.so.9` unless cuBLAS+cuDNN are on `LD_LIBRARY_PATH` before Python starts (research
  §2). The wrapper (P1.M1.T2.S1) computes those paths from the LIVE wheels and `exec`s python. Pointing
  ExecStart at the wrapper (instead of bare python) is what makes the service actually run on CUDA.
- **No baked `Environment=LD_LIBRARY_PATH`.** A literal path in the unit goes stale every time `uv sync`
  reinstalls/bumps the nvidia wheels. The wrapper recomputes on every launch — robust + idempotent.
  This is the deliberate rejection of PRD §4.9's `# Environment=LD_LIBRARY_PATH=... ← install.sh fills
  this in` placeholder (the wrapper supersedes it; S1 + research §2 confirm).
- **`Restart=on-failure` matches the daemon's exit codes.** `main()` returns 1 on a fatal init
  (auto-restart = self-healing) and 0 on a clean `voicectl quit`/SIGTERM (no restart = respects the
  user's stop). `RestartSec=2` is a sane back-off (the contract's explicit value, vs systemd's 100 ms
  default).
- **Un-armed start is a privacy property.** The daemon constructs its listening `threading.Event`
  cleared + calls `set_listening(False)` in `run()` — the unit merely starts the process. The inline
  comment documents this so an operator doesn't misread "active (running)" as "listening".
- **Scope discipline.** This task authors ONLY the unit content. install.sh COPIES it; it does NOT
  edit the unit. No other file is touched.

## What

A single ~20-line INI file in a NEW `systemd/` directory at the repo root. Three stanzas (`[Unit]`,
`[Service]`, `[Install]`), one inline comment block (the Mode-A operational doc). No `Type=` (the
default `simple` is correct because the wrapper `exec`s python → python is the main PID). No `Environment=`
of any kind (the user manager already exports `XDG_RUNTIME_DIR`; the wrapper sets `LD_LIBRARY_PATH`).
No `ExecStartPre`/`ExecStartPost` (CUDA smoke + prefetch live in install.sh, not the unit). The exact
content is pinned verbatim below.

### Success Criteria

- [ ] `systemd/voice-typing.service` exists; `systemd-analyze verify systemd/voice-typing.service`
      → **no errors**.
- [ ] `[Unit]` has `Description=` and `After=pipewire.service ydotool.service`.
- [ ] `[Service]` `ExecStart=/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh`
      (the WRAPPER, absolute path).
- [ ] `[Service]` `Restart=on-failure` + `RestartSec=2`.
- [ ] NO `Environment=` directive anywhere (commented or live).
- [ ] `[Install]` `WantedBy=default.target`.
- [ ] Inline comment explains the wrapper + no-Environment= rationale (PRD §8) AND the un-armed-start
      rationale (PRD §4.9).
- [ ] After install.sh copies it: `systemctl --user is-active voice-typing` → `active`; `voicectl status`
      → `listening: off` (un-armed).
- [ ] No edit to launch_daemon.sh/daemon.py/install.sh/pyproject.toml/config.toml/any module; no
      README; no hypr-binds.conf; no PRD.md/tasks.json/prd_snapshot.md/.gitignore.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior codebase knowledge: the full unit content is pinned verbatim
(verified against the live wrapper path, the live user-scope pipewire/ydotool units, and daemon.py's
exit-code semantics); every contract decision is cited to a file:line or URL; and every validation
command is executable as written (`systemd-analyze` + `systemctl --user` + `voicectl` all present in
this session, `XDG_RUNTIME_DIR=/run/user/1000` set).

### Documentation & References

```yaml
# MUST READ — the design + verified facts (THIS is the spec).
- file: plan/001_be48c74bc590/P1M6T1S2/research/unit_design.md
  why: "§2 the ExecStart→wrapper override of PRD §4.9's placeholder (binding from the wrapper PRP).
        §3 why Type= is left default (simple) — exec makes python the main PID. §4 Restart=on-failure +
        RestartSec=2 semantics vs main()'s 0/1 exit codes. §5 After= targets VERIFIED user-scope.
        §6 no Environment= for XDG_RUNTIME_DIR (user manager sets it). §7 un-armed-start is the
        daemon's job, not the unit's. §9 the inline-comment content (Mode A). §12 the final unit text."
  critical: "G1: ExecStart MUST be the wrapper path, NOT python. G2: NO Environment=LD_LIBRARY_PATH
             (commented or live) — the wrapper sets it; a baked value goes stale on uv sync. G3: the
             unit starts the process NOT-LISTENING by the daemon's own default — add no flag."

# MUST READ — the consumed wrapper (the binary ExecStart points at).
- file: voice_typing/launch_daemon.sh
  why: "(1) The absolute path the unit ExecStarts: /home/dustin/projects/voice-typing/voice_typing/
        launch_daemon.sh (verified via realpath). (2) The final `exec \"$PY\" -m voice_typing.daemon
        \"$@\"` line — exec replaces bash with python in the SAME PID, so systemd Type=simple (default)
        tracks python as the main PID + SIGTERM hits it directly (clean shutdown via P1.M4.T2.S2's
        handlers). (3) The header comment documents the LD_LIBRARY_PATH-at-exec rationale (PRD §8) —
        the unit's inline comment POINTS at the same rationale; do not duplicate the runbook, just
        reference it."
  critical: "Do NOT point ExecStart at .venv/bin/python directly (the unit would bypass the wrapper →
             cuDNN not found → crash-loop). Do NOT edit launch_daemon.sh. The wrapper's +x bit is
             required for systemd to exec it (set by P1.M1.T2.S1 in the tree; re-asserted by install.sh)."

# MUST READ — the daemon entry point (confirms exit-code semantics for Restart=).
- file: voice_typing/daemon.py
  why: "`main()` (line ~887) returns 1 on a fatal lifecycle error (config load fail, recorder/server
        init exception) and 0 on a clean shutdown (quit/SIGTERM). `run()` calls `self._feedback.
        set_listening(False)` at start (PRD §4.9: boots NOT-listening). The `if __name__ == \"__main__\"`
        guard + `sys.exit(main())` propagates the code to systemd (so Restart=on-failure fires only on
        the nonzero/crash path)."
  critical: "Restart=on-failure restarts ONLY on nonzero exit / crash — matches main() returning 1.
             A clean quit (code 0) does NOT restart (respects the user's stop). Do NOT edit daemon.py."

# MUST READ — the sibling S1 that COPIES this unit (the install-time contract).
- file: plan/001_be48c74bc590/P1M6T1S1/PRP.md
  why: "install.sh step (5) copies $REPO/systemd/voice-typing.service -> $XDG_CONFIG_HOME/systemd/user/
        voice-typing.service, then `systemctl --user daemon-reload; enable; restart`. Its gotcha G4 +
        the Integration Points state: install.sh COPIES the unit — it does NOT author unit content
        (this task owns the content). If this file is absent when S1 runs, S1 fails CLEARLY."
  critical: "This task and S1 are SIBLINGS (parallel). install.sh consumes the file by repo-relative
             path `systemd/voice-typing.service`. Do NOT make install.sh the one that writes the unit;
             do NOT duplicate install.sh's copy/daemon-reload/enable/restart here. This task = author
             the unit file only."

# External — systemd semantics cited (verified reachable).
- url: https://www.freedesktop.org/software/systemd/man/systemd.service.html
  why: "Type=simple (the default): systemd considers the unit started when the main process is forked
        off; the PID is tracked as the main service process. With `exec` in the wrapper, python IS that
        PID. Also documents Restart=on-failure (restart only on nonzero exit / signal kill / timeout)
        + RestartSec= (sleep before restart)."
- url: https://www.freedesktop.org/software/systemd/man/systemd.unit.html
  why: "After= is an ORDERING dependency (not Requires=); `#` starts a comment line. WantedBy= in
        [Install] is the target whose .wants/ gets the symlink on `enable`. For user units, default.target
        is the user session target."
- url: https://wiki.archlinux.org/title/Systemd/User
  why: "User units live under ~/.config/systemd/user/ (= $XDG_CONFIG_HOME/systemd/user/); the user
        manager exports XDG_RUNTIME_DIR=/run/user/$UID to all user units (so the unit needs no
        Environment= for it). default.target.wants/ is where `enable` symlinks."

# Background — the PRPs that produced the consumed interfaces.
- file: plan/001_be48c74bc590/P1M1T2S1/PRP.md    # launch_daemon.sh (ExecStart target; its Integration
                                                  #   Points MANDATE ExecStart→wrapper + removing the
                                                  #   PRD §4.9 Environment= placeholder).
- file: plan/001_be48c74bc590/P1M4T3S1/PRP.md     # daemon main() (the 0/1 exit codes Restart= reads).
- file: plan/001_be48c74bc590/P1M4T2S2/PRP.md     # signal handlers (SIGTERM→clean shutdown via the wrapper's exec→PID).
- file: plan/001_be48c74bc590/architecture/research_faster_whisper_cuda.md  # §2 cuDNN/LD_LIBRARY_PATH-at-exec (why the wrapper).
```

### Current Codebase tree (state at P1.M6.T1.S2 start)

```bash
/home/dustin/projects/voice-typing/
├── .git/ .gitignore .venv/        # DO NOT touch .gitignore
├── PRD.md                         # READ-ONLY (§4.9 the unit template; §5 install; §8 cuDNN risk row)
├── config.toml                    # READ ONLY (not referenced by the unit)
├── pyproject.toml uv.lock         # DO NOT touch
├── install.sh                     # SIBLING S1 (parallel; CONSUMES this unit — does NOT author it)
├── systemd/                       # ← CREATE this dir + the file below (the ONLY new artifact)
│   └── voice-typing.service       # ← CREATE (this task)
└── voice_typing/
    ├── launch_daemon.sh           # ExecStart target (absolute path below); READ ONLY
    ├── daemon.py                  # main() exit codes Restart= reads; boots not-listening; READ ONLY
    └── (config.py ctl.py feedback.py ...)  # READ ONLY (not referenced by the unit)
```

### Desired Codebase tree with files to be added

```bash
systemd/                           # NEW dir
└── voice-typing.service           # NEW — the systemd user unit (this task's sole output)
# NOTHING ELSE. install.sh is the sibling S1; launch_daemon.sh/daemon.py are already landed.
```

### Known Gotchas of our codebase & Library Quirks

```bash
# CRITICAL #1 (G1) — ExecStart MUST be the WRAPPER, not python. PRD §4.9's placeholder reads
#   ExecStart=/home/dustin/projects/voice-typing/.venv/bin/python -m voice_typing.daemon
# but the item CONTRACT + the wrapper PRP (P1.M1.T2.S1 Integration Points) OVERRIDE it:
#   ExecStart=/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh
# Bypassing the wrapper => cuDNN/cuBLAS not on LD_LIBRARY_PATH at exec => the daemon crash-loops with
# "cannot load libcudnn_ops.so.9" (PRD §8 risk row #1). Use the WRAPPER path, verbatim.

# CRITICAL #2 (G2) — NO Environment=LD_LIBRARY_PATH (commented or live). The wrapper computes the lib
#   dirs from the LIVE nvidia wheels on every launch (survives `uv sync` + version bumps); a baked
#   Environment= value goes stale the moment a wheel is reinstalled. Replace PRD §4.9's
#   `# Environment=LD_LIBRARY_PATH=... ← install.sh fills this in` placeholder with a comment that
#   says the WRAPPER sets it (research §2; this is option-1 beating option-2).

# CRITICAL #3 (G3) — no listening-state flag. The unit starts the process; the process boots
#   NOT-LISTENING by its own default (daemon.py: threading.Event() cleared + set_listening(False) in
#   run()). There is no ExecStart arg or Environment= for listening. The acceptance check is
#   `voicectl status` -> listening: off AFTER start. Do NOT invent a flag.

# CRITICAL #4 (G4) — leave Type= at the default (simple). DO NOT add Type=. The wrapper ends in
#   `exec "$PY" ...`, so execve replaces bash with python in the SAME PID; systemd Type=simple (the
#   default) tracks python as the main PID and delivers SIGTERM (KillSignal= default) directly to it
#   -> the daemon's signal handlers (P1.M4.T2.S2) run -> clean shutdown. Adding Type=forking would
#   break PID tracking; Type=oneshot would treat a running daemon as "done". The default is correct.

# CRITICAL #5 (G5) — no Environment= for XDG_RUNTIME_DIR either. The systemd USER manager always
#   exports XDG_RUNTIME_DIR=/run/user/$UID to user units (verified: this session = /run/user/1000).
#   The daemon's socket ($XDG_RUNTIME_DIR/voice-typing/control.sock) + state file resolve fine. A
#   redundant Environment= would be noise (and wrong if the UID ever changes).

# CRITICAL #6 (G6) — After= targets are USER units (verified). pipewire.service + ydotool.service are
#   BOTH user-scope on this box (/usr/lib/systemd/user/pipewire.service; ydotool.service in the user
#   manager). A user unit's After= resolves within the same manager, so the ordering is valid. Use
#   EXACTLY `After=pipewire.service ydotool.service` (PRD §4.9 + contract). Do NOT add a `.service`
#   suffix mismatch or a scope prefix (e.g. NOT `pipewire.service@1000`).

# CRITICAL #7 (G7) — Restart=on-failure, NOT always/no/never. `on-failure` restarts only on nonzero
#   exit / signal kill / timeout. main() returns 1 on fatal init (restart = self-heal) and 0 on clean
#   quit/SIGTERM (no restart = respects `voicectl quit`). RestartSec=2 (the contract value) is a sane
#   back-off (systemd default is 100ms — too aggressive for a model-loading daemon).

# CRITICAL #8 (G8) — the unit file is pure INI; shellcheck is N/A (it lints shell, not .service).
#   The gate is `systemd-analyze verify systemd/voice-typing.service` (the systemd unit linter, present
#   on this box). Do NOT run shellcheck on the .service file (it will be noisy + meaningless).

# CRITICAL #9 (G9) — comment syntax is `#` at line start (or after whitespace). systemd unit files use
#   `#` comments (systemd.unit(5)). Inline trailing comments after a KEY=VALUE are NOT supported (the
#   `# ...` would be parsed as part of the value) — put each comment on its OWN line. The Mode-A
#   rationale goes as a comment block ABOVE the ExecStart line.

# CRITICAL #10 (G10) — WantedBy=default.target (user session target), NOT multi-user.target /
#   graphical.target (those are SYSTEM targets). The unit is a USER unit; `enable` symlinks into
#   ~/.config/systemd/user/default.target.wants/. default.target = the user's login session.

# CRITICAL #11 (G11) — the absolute ExecStart path is the SOURCE-TREE path, not a wheel/site-packages
#   path. /home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh (verified via realpath).
#   Even though pyproject packages voice_typing/ into the wheel, systemd/install.sh call the source
#   tree. Do NOT relativize the path or use $HOME (systemd needs the absolute path).

# CRITICAL #12 (G12) — no ExecStartPre/ExecStartPost. CUDA smoke + prefetch live in install.sh (run
#   once at setup), NOT in the unit (run on every start/restart). Putting them in the unit would
#   re-run them on every crash-restart + slow startup + could fail the start. Keep the unit minimal.
```

## Implementation Blueprint

### Data models and structure

None. A single INI file: three stanzas (`[Unit]`, `[Service]`, `[Install]`) + one `#` comment block.
No code, no types, no schemas.

### `systemd/voice-typing.service` reference content (research §12 — implement verbatim)

```ini
[Unit]
Description=Local voice typing daemon (RealtimeSTT)
After=pipewire.service ydotool.service

[Service]
# ExecStart points at the LD_LIBRARY_PATH wrapper (voice_typing/launch_daemon.sh), NOT python
# directly. faster-whisper / ctranslate2 load cuBLAS + cuDNN 9 shared objects from the nvidia-*-cu12
# wheels; cuDNN 9's split sub-libs (libcudnn_ops.so.9, libcudnn_cnn.so.9, ...) are resolved by the
# dynamic linker and the wheels ship no $ORIGIN RUNPATH for them, so they MUST be on LD_LIBRARY_PATH
# or the daemon dies at startup with "cannot load libcudnn_ops.so.9" (PRD §8 risk row #1).
#
# LD_LIBRARY_PATH is read by ld.so ONLY at process exec (execve) — mutating os.environ inside the
# already-running python has NO effect. The wrapper therefore exports it BEFORE exec'ing python.
#
# DO NOT add `Environment=LD_LIBRARY_PATH=...` here. The wrapper recomputes the lib dirs from the
# LIVE installed nvidia wheels on every launch, so this unit survives `uv sync` reinstalls and
# version bumps without edits. A baked value would go stale and break the service on the next sync.
# Debugging a cuDNN load failure: see the header comment in voice_typing/launch_daemon.sh
# (journalctl --user -u voice-typing -e; systemctl --user show voice-typing -p Environment;
#  LD_DEBUG=libs voice_typing/launch_daemon.sh 2>&1 | grep -i cudnn).
#
# The daemon boots NOT-LISTENING — it never hot-mics on boot / restart. `voicectl start` or
# `voicectl toggle` arms the mic over the control socket ($XDG_RUNTIME_DIR/voice-typing/control.sock).
# (PRD §4.9.) Verify with: voicectl status   ->   listening: off
ExecStart=/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — confirm the consumed wrapper exists (the ExecStart target) + the target file/dir
        does NOT exist yet (no mutation; informational).
  - RUN (from /home/dustin/projects/voice-typing):
      test -x voice_typing/launch_daemon.sh && echo "wrapper OK (ExecStart target present + executable)" \
        || echo "PREFLIGHT FAIL: voice_typing/launch_daemon.sh missing or not executable (P1.M1.T2.S1)"
      realpath voice_typing/launch_daemon.sh   # MUST print /home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh
      test ! -e systemd/voice-typing.service && echo "ok: systemd/voice-typing.service not yet created" \
        || echo "PREFLIGHT FAIL: systemd/voice-typing.service already exists"
      # Verify the After= targets are user-scope units on THIS machine (so the ordering resolves):
      systemctl --user list-unit-files 2>/dev/null | grep -E '^(pipewire|ydotool)\.service' \
        && echo "After= targets are user units (ordering valid)" \
        || echo "PREFLIGHT NOTE: an After= target is not a user unit on this box — re-check PRD §4.9"
      command -v systemd-analyze >/dev/null && echo "systemd-analyze OK (verify gate available)"
      echo "XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-(unset — install.sh preflights this)}"
  - EXPECTED: wrapper present + executable; realpath = the absolute path above; the .service absent;
    pipewire.service + ydotool.service both listed as user units; systemd-analyze present.
  - DO NOT: create/edit any file, run install.sh, systemctl start, or touch other modules.

Task 1: CREATE systemd/voice-typing.service — the reference content above VERBATIM.
  - FILE: systemd/voice-typing.service (NEW; create the systemd/ dir + the file). `mkdir -p systemd`
    is implicit via the write tool (it creates parent dirs).
  - KEEP: the three stanzas in order; ExecStart = the WRAPPER absolute path (G1); NO Environment=
    directive anywhere (G2/G5); Restart=on-failure + RestartSec=2 (G7); After=pipewire.service
    ydotool.service (G6); WantedBy=default.target (G10); the inline comment block ABOVE ExecStart with
    the wrapper rationale + the un-armed-start rationale (Mode A; G9 — each # comment on its own line).
  - DO NOT: add Type= (G4); add Environment=LD_LIBRARY_PATH (G2) or Environment=XDG_RUNTIME_DIR (G5);
    add ExecStartPre/ExecStartPost (G12); point ExecStart at .venv/bin/python (G1); add trailing
    inline comments after a KEY=VALUE (G9); edit launch_daemon.sh/daemon.py/install.sh/pyproject/
    config.toml/any module; create a README or hypr-binds.conf; touch PRD.md/tasks.json/prd_snapshot.md/.gitignore.

Task 2: VALIDATE — run the Validation Loop L1–L4. Iterate until all gates pass.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M6.T1.S2: systemd/voice-typing.service unit (ExecStart→wrapper, un-armed, Restart=on-failure)".
```

### Implementation Patterns & Key Details

```ini
# PATTERN 1 — ExecStart → wrapper (G1). The unit ExecStarts the wrapper (absolute source-tree path),
#   which sets LD_LIBRARY_PATH at exec and exec's python. systemd Type=simple (default) then tracks
#   python as the main PID. Do NOT point at .venv/bin/python — cuDNN would be unfound.
ExecStart=/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh

# PATTERN 2 — auto-restart on crash, respect clean stop (G7). main() returns 1 on fatal init (restart)
#   and 0 on clean quit/SIGTERM (no restart). RestartSec=2 is the contract's back-off.
Restart=on-failure
RestartSec=2

# PATTERN 3 — comment block above the directive it explains (G9). Each comment on its OWN line;
#   NEVER a trailing `# ...` after KEY=VALUE (systemd parses it as part of the value).
# ExecStart points at the wrapper ...
# DO NOT add Environment=LD_LIBRARY_PATH=... here ...
# The daemon boots NOT-LISTENING ...
ExecStart=/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh

# PATTERN 4 — user-scope ordering + install target (G6/G10). Both After= targets are user units on
#   this box (verified). default.target = the user session (start at login, not boot).
After=pipewire.service ydotool.service
[Install]
WantedBy=default.target
```

### Integration Points

```yaml
CONSUMED BY — install.sh (SIBLING S1, P1.M6.T1.S1):
  - src:   "$REPO/systemd/voice-typing.service"                    # THIS file (repo-relative path)
  - dest:  "$XDG_CONFIG_HOME/systemd/user/voice-typing.service"    # XDG unset -> ~/.config/systemd/user/
  - cmds:  systemctl --user daemon-reload; enable; restart         # S1 runs these; NOT this task
  - note:  S1 COPIES the unit; it does NOT author/edit its content (scope boundary). If this file is
           absent when S1 runs, S1 fails CLEARLY ("missing — run P1.M6.T1.S2 first").

EXECSTART TARGET — voice_typing/launch_daemon.sh (P1.M1.T2.S1):
  - path:  /home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh   # absolute (verified)
  - bit:   +x required (set by P1.M1.T2.S1 in the tree; re-asserted idempotently by install.sh)
  - role:  sets LD_LIBRARY_PATH (cuBLAS+cuDNN) at exec, then `exec "$PY" -m voice_typing.daemon "$@"`
           -> python is systemd's main PID -> SIGTERM -> daemon's clean-shutdown handlers (P1.M4.T2.S2)

DAEMON EXIT CODES — voice_typing/daemon.py main() (P1.M4.T3.S1):
  - exit 1: fatal lifecycle error (config/recorder/server init) -> Restart=on-failure fires (self-heal)
  - exit 0: clean shutdown (voicectl quit / SIGTERM) -> NO restart (respects the user's stop)
  - boot:   run() calls set_listening(False) -> daemon is NOT-listening at start (PRD §4.9)

ACCEPTANCE CRITERION 6 (PRD §7): the daemon runs as a systemd user service, Restart=on-failure, starts
  not-listening. THIS unit file is what makes that provable.

NO Environment= of any kind. NO Type= (default simple). NO ExecStartPre/Post. NO edit to any other file.
```

## Validation Loop

> Run from `/home/dustin/projects/voice-typing`. L1 (static lint) + L2 (structure) are always runnable
> and need nothing else. L3 (install + live start) requires the sibling `install.sh` (S1) + a populated
> `.venv` + prefetched models — if S1 has not landed yet, run L1/L2/L4 now and DEFER L3 to after S1
> (the orchestrator runs S1 alongside this task; the unit itself is provably correct via L1/L2).

### Level 1: Static lint (the canonical systemd unit-file gate)

```bash
cd /home/dustin/projects/voice-typing
systemd-analyze verify systemd/voice-typing.service && echo "L1 verify OK (no errors)" || echo "L1 FAIL: verify reported errors — read them + fix"
# (Optional, user-scope lint — equivalent if a user manager is up:)
systemd-analyze --user verify systemd/voice-typing.service 2>&1 | head
# Expected: no errors. systemd-analyze catches unknown keys, bad ExecStart (missing binary), malformed
# stanza, unresolvable WantedBy=/After=. (shellcheck is N/A for .service files — G8.)
```

### Level 2: Structural invariants (grep — fast, no side effects)

```bash
cd /home/dustin/projects/voice-typing
test -f systemd/voice-typing.service && echo "L2 file present" || echo "L2 FAIL: file missing"
grep -q '^\[Unit\]'     systemd/voice-typing.service && echo "L2 [Unit] OK"     || echo "L2 FAIL"
grep -q '^\[Service\]'  systemd/voice-typing.service && echo "L2 [Service] OK"  || echo "L2 FAIL"
grep -q '^\[Install\]'  systemd/voice-typing.service && echo "L2 [Install] OK"  || echo "L2 FAIL"
grep -qx 'After=pipewire.service ydotool.service' systemd/voice-typing.service && echo "L2 After= OK" || echo "L2 FAIL: After= mismatch"
grep -qx 'ExecStart=/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh' systemd/voice-typing.service \
  && echo "L2 ExecStart→wrapper OK" || echo "L2 FAIL: ExecStart must be the wrapper path (G1)"
grep -qx 'Restart=on-failure' systemd/voice-typing.service && echo "L2 Restart OK" || echo "L2 FAIL: Restart= mismatch"
grep -qx 'RestartSec=2'        systemd/voice-typing.service && echo "L2 RestartSec OK" || echo "L2 FAIL: RestartSec mismatch"
grep -qx 'WantedBy=default.target' systemd/voice-typing.service && echo "L2 WantedBy OK" || echo "L2 FAIL: WantedBy mismatch"
# CRITICAL negative checks (G2/G4):
! grep -qi '^Environment=' systemd/voice-typing.service && echo "L2 no Environment= OK (G2/G5)" || echo "L2 FAIL: do NOT set Environment= (wrapper/user-manager own it)"
! grep -qi '^Type='        systemd/voice-typing.service && echo "L2 no Type= OK (G4, default simple)" || echo "L2 FAIL: do NOT set Type= (default simple is correct)"
! grep -qi '^ExecStartPre\|^ExecStartPost' systemd/voice-typing.service && echo "L2 no ExecStart* OK (G12)" || echo "L2 FAIL: no ExecStartPre/Post (G12)"
# Mode-A doc comment present (G9):
grep -qi 'LD_LIBRARY_PATH' systemd/voice-typing.service && echo "L2 wrapper rationale commented OK" || echo "L2 FAIL: no LD_LIBRARY_PATH rationale in comment"
grep -qi 'not-listening\|NOT-LISTENING\|not listening' systemd/voice-typing.service && echo "L2 un-armed rationale commented OK" || echo "L2 FAIL: no un-armed-start rationale in comment"
grep -qi 'launch_daemon.sh' systemd/voice-typing.service && echo "L2 wrapper referenced OK" || echo "L2 FAIL"
# Expected: all OK; no Environment= / Type= / ExecStartPre|Post; both rationale comments present.
```

### Level 3: Integration (install.sh copies + live start) — DEFER if S1 not yet landed

```bash
cd /home/dustin/projects/voice-typing
# REQUIRES: install.sh (S1) present + .venv populated + models prefetched. If S1 is still in flight,
# DEFER this level (the unit is already proven correct by L1/L2); re-run after S1 lands.
test -x ./install.sh || { echo "L3 SKIP: install.sh (S1) not present yet — defer"; }
if [ -x ./install.sh ]; then
  ./install.sh                                          # copies the unit, daemon-reload, enable, restart
  # Post-conditions (acceptance criterion 6):
  systemctl --user is-active --quiet voice-typing.service && echo "L3 active OK" || echo "L3 FAIL: not active"
  systemctl --user is-enabled --quiet voice-typing.service && echo "L3 enabled OK" || echo "L3 FAIL: not enabled"
  systemctl --user cat voice-typing.service | grep -qx 'ExecStart=/home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh' \
    && echo "L3 installed ExecStart matches source OK" || echo "L3 FAIL: installed unit ExecStart drift"
  # The un-armed guarantee (G3): daemon running but NOT listening.
  .venv/bin/voicectl status | grep -qi 'listening: off' && echo "L3 un-armed (no hot-mic) OK" || echo "L3 FAIL: daemon is listening on boot (G3)"
  journalctl --user -u voice-typing -n 20 --no-pager    # sanity: no cuDNN crash-loop, no errors
fi
# Expected: active + enabled; installed ExecStart == source; voicectl status -> listening: off; logs clean.
```

### Level 4: Creative & Domain-Specific Validation

```bash
cd /home/dustin/projects/voice-typing
# (a) The After= targets are genuinely user-scope units on THIS box (G6 — the ordering must resolve):
systemctl --user list-unit-files 2>/dev/null | grep -E '^(pipewire|ydotool)\.service' \
  && echo "L4a After= targets are user units (ordering valid)" \
  || echo "L4a NOTE: a target isn't a user unit — re-check PRD §4.9 (but do NOT deviate from the contract value)"

# (b) ExecStart path is the absolute source-tree wrapper (G1/G11) + the wrapper exists + is executable:
test -x /home/dustin/projects/voice-typing/voice_typing/launch_daemon.sh \
  && echo "L4b ExecStart target exists + executable" || echo "L4b FAIL: wrapper missing/not executable"
grep -o 'ExecStart=[^ ]*' systemd/voice-typing.service | head -1

# (c) The wrapper's exec→PID story (why Type= is left default — G4): confirm the wrapper ends in exec:
tail -1 voice_typing/launch_daemon.sh | grep -q '^exec ' && echo "L4c wrapper ends in exec (Type=simple correct)" || echo "L4c NOTE: wrapper's last line isn't a bare exec"

# (d) Manual isolated copy+daemon-reload (proves systemd parses the unit WITHOUT needing models/start):
DEST="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$DEST"
cp systemd/voice-typing.service "$DEST/voice-typing.service"
systemctl --user daemon-reload
systemctl --user cat voice-typing.service >/dev/null && echo "L4d systemd parsed the unit (cat OK)" || echo "L4d FAIL: systemd could not cat/parse the unit"
# (Do NOT start it here — the daemon needs prefetched models; L3 is the live-start gate. Clean up the
#  manual copy only if you want; install.sh (S1) owns the real install.)
# Expected: both After= targets are user units; wrapper exists+executable+ends-in-exec; systemd cat OK.
```

## Final Validation Checklist

### Technical Validation

- [ ] `systemd-analyze verify systemd/voice-typing.service` → no errors (L1).
- [ ] L2 structural greps all pass; negative checks confirm NO `Environment=` / `Type=` / `ExecStartPre|Post`.
- [ ] (L3, if S1 landed) `systemctl --user is-active` → active; `is-enabled` → enabled; installed
      ExecStart == source; `voicectl status` → listening: off; logs show no cuDNN crash-loop.

### Feature Validation

- [ ] `[Unit]` Description + `After=pipewire.service ydotool.service` (both verified user units).
- [ ] `[Service]` ExecStart = the WRAPPER absolute path (G1); Restart=on-failure; RestartSec=2.
- [ ] NO `Environment=` anywhere (G2: no LD_LIBRARY_PATH; G5: no XDG_RUNTIME_DIR — wrapper/user-manager own them).
- [ ] `[Install]` WantedBy=default.target (user session).
- [ ] Inline comment explains the wrapper + no-Environment= rationale (PRD §8) AND un-armed-start (PRD §4.9).
- [ ] Post-install: daemon active, NOT listening (no hot-mic on boot/restart) (G3).

### Code Quality Validation

- [ ] File placement: `systemd/voice-typing.service` (new `systemd/` dir at repo root; PRD §4.1 layout).
- [ ] Comments are line-leading `#` (G9) — no trailing `#` after a KEY=VALUE.
- [ ] ExecStart is the absolute source-tree path (G11) — no `$HOME` / relativization.
- [ ] No `Type=` (G4: default simple is correct because the wrapper `exec`s python).
- [ ] No edit to launch_daemon.sh/daemon.py/install.sh/pyproject.toml/config.toml/any module; no README;
      no hypr-binds.conf; no PRD.md/tasks.json/prd_snapshot.md/.gitignore.

### Documentation & Deployment

- [ ] The inline comment is the operator-facing "why ExecStart→wrapper + why no Environment= + why
      not-listening" doc (Mode A). README (P2.M1.T2.S1) may reprint it.
- [ ] The comment points at PRD §8 risk row #1 (cuDNN cannot load libcudnn_ops) and PRD §4.9 (un-armed).
- [ ] No new env vars, no new dependencies, no pyproject/uv.lock change.

---

## Anti-Patterns to Avoid

- ❌ Don't point ExecStart at `.venv/bin/python -m voice_typing.daemon` (the PRD §4.9 placeholder) — use
  the WRAPPER (G1). Bypassing it crash-loops on cuDNN.
- ❌ Don't add `Environment=LD_LIBRARY_PATH=...` (commented or live) — the wrapper sets it dynamically
  from the live wheels; a baked value goes stale on `uv sync` (G2).
- ❌ Don't add `Environment=XDG_RUNTIME_DIR=...` — the user manager already exports it (G5).
- ❌ Don't add `Type=` — the default `simple` is correct because the wrapper `exec`s python into the
  main PID (G4). `forking`/`oneshot` would break PID tracking.
- ❌ Don't add `ExecStartPre`/`ExecStartPost` — CUDA smoke + prefetch live in install.sh, not the unit
  (G12); they'd re-run on every restart.
- ❌ Don't add a listening-state flag/arg — the daemon boots not-listening by its own default (G3).
- ❌ Don't use a trailing `# comment` after a `KEY=VALUE` — systemd parses it as part of the value (G9).
- ❌ Don't change `After=` to a scope-prefixed name or drop the `.service` suffix — use EXACTLY
  `After=pipewire.service ydotool.service` (both verified user units; G6).
- ❌ Don't use `WantedBy=multi-user.target` / `graphical.target` — those are SYSTEM targets; a user unit
  uses `default.target` (G10).
- ❌ Don't run `shellcheck` on the `.service` file — it lints shell, not INI (G8); the gate is
  `systemd-analyze verify`.
- ❌ Don't author `install.sh` content or duplicate its copy/daemon-reload/enable/restart here — S1 owns
  that; this task authors ONLY the unit file.
- ❌ Don't edit `launch_daemon.sh`/`daemon.py`/`install.sh`/`pyproject.toml`/`config.toml`/any module, or
  create a README / hypr-binds.conf — out of scope (owned by P1.M1.T2.S1 / P1.M4.T3.S1 / P1.M6.T1.S1 /
  P1.M2.T1.S1 / P2.M1.T2.S1 / P2.M1.T1.S1 respectively).

---

## Confidence Score

**9/10** for one-pass implementation success. The deliverable is a single ~20-line INI file whose entire
content is pinned verbatim, and **every directive is contract-mandated and machine-verified**:
`ExecStart` = the wrapper's absolute path (`realpath`-confirmed; G1); `After=` targets are both
user-scope units on this box (`systemctl --user list-unit-files`-confirmed; G6); `Restart=on-failure` +
`RestartSec=2` align with `daemon.py main()`'s 0/1 exit codes (read from the landed source; G7);
`WantedBy=default.target` is the user-session target (G10); NO `Environment=` (the wrapper owns
`LD_LIBRARY_PATH`, the user manager owns `XDG_RUNTIME_DIR`; G2/G5); NO `Type=` (the wrapper's
`exec`→main-PID makes the default `simple` correct; G4). The wrapper PRP (P1.M1.T2.S1) documents the
ExecStart→wrapper + remove-the-Environment-placeholder as a **binding downstream integration point**, so
this unit and the wrapper are contractually aligned. `systemd-analyze verify` (present on this box) is
the canonical static gate, runnable with zero dependencies. The −1 residual risk is **scheduling**, not
correctness: L3 (the live install+start via `install.sh`) requires the sibling S1 + a populated venv +
prefetched models; if S1 is still in flight when this task runs its own validation, L3 is deferred (the
PRP says so explicitly) and only L1/L2/L4 run now — but those three PROVE the unit is well-formed and
consumable (static lint clean, structure correct, systemd parses it via `systemctl --user cat`). No code
is written, so the only "implementation bug" surface is the INI text — which is specified
character-for-character and negative-checked (no Environment=/Type=/ExecStartPre).
