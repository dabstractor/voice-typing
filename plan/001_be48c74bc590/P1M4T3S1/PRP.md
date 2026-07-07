# PRP — P1.M4.T3.S1: `main()` entry point — `__main__` guard, signal handlers, logging setup

## Goal

**Feature Goal**: Add the **process entry point** to `voice_typing/daemon.py` — a `main()`
function + the `if __name__ == "__main__": sys.exit(main())` guard + the stderr **logging
handler** setup — that wires together every component built by the prior subtasks into the single
sanctioned daemon lifecycle, and that is the runnable target of `python -m voice_typing.daemon`
(systemd `ExecStart`, PRD §4.9) and the `voice-typing-daemon` console script (`pyproject.toml`
`[project.scripts]`, already declared in P1.M1.T1.S1). This is the LAST piece of `daemon.py` and
the one that makes `python -m voice_typing.daemon` actually run.

The two gaps this closes (both verified against the live source):
1. **No entry point.** `daemon.py` today defines `VoiceTypingDaemon.run()` (BLOCKS until shutdown)
   but has **no `main()`** and **no `if __name__ == "__main__":` guard** — so `python -m
   voice_typing.daemon` imports the module and exits having done nothing. The `voice-typing-daemon`
   console script (entry `voice_typing.daemon:main`) currently **fails at runtime** with
   `AttributeError: module 'voice_typing.daemon' has no attribute 'main'`.
2. **No logging handler.** `VoiceTypingDaemon.run()` already calls `self._configure_log_level()`,
   but that fn's own docstring states *"Namespace-scoped only — NOT basicConfig (handler/root config
   is P1.M4.T3.S1's job)"* — it sets ONLY the `voice_typing` namespace logger LEVEL, adding **no
   handler**. With no handler on the namespace logger and none on root, records pass the logger gate
   but have nowhere to emit → **silent daemon**. PRD §4.2 requires "logging to stderr (journald picks
   it up under systemd) at INFO; DEBUG via config" — T3.S1 installs that handler.

**Deliverable** (2 files — 1 MODIFY source, 1 MODIFY tests; **NO new module**, **NO pyproject change**):
1. `voice_typing/daemon.py` — ADD `import sys` (one stdlib line, module-top); ADD module-level
   `_resolve_log_level()` + `_setup_logging()` + `main()` + the `if __name__ == "__main__":`
   guard at MODULE END (after `install_shutdown_signal_handlers`, which P1.M4.T2.S2 adds).
   **Do NOT touch** any existing symbol (S1/S2/S3 of M4.T1 + S1-of-T2 of M4.T2 + T2.S2 of M4.T2 own
   them); all edits are **100% additive** → zero merge conflict.
2. `tests/test_daemon.py` — **APPEND** a `main()`/`_setup_logging`/`_resolve_log_level`/guard test
   section that reuses `_make_daemon()`/`_StubRecorder`/`_wait_for` (do NOT edit prior test bodies).

**Success Definition**:
- (a) `voice_typing/daemon.py` + `tests/test_daemon.py` `py_compile`-clean; `import voice_typing.daemon`
  stays import-pure (only stdlib `sys` added at module top; `RealtimeSTT`/`torch`/`ctranslate2` NOT in
  `sys.modules` after import); `main`, `_setup_logging`, `_resolve_log_level` are module attributes
  and `main` is callable; `daemon.py` contains an `if __name__ == "__main__":` module-level guard.
- (b) **`main()` orchestrates exactly this lifecycle** (the P1.M4.T2.S2 teardown contract):
  `cfg = VoiceTypingConfig.load()` → `_setup_logging(cfg.log.level)` → `Feedback(cfg.feedback)` →
  `VoiceTypingDaemon(cfg, fb)` → `ControlServer(d, on_quit=d.shutdown)` → `srv.start()` →
  `restore = install_shutdown_signal_handlers(d)` → `try: d.run() finally: restore(); d.shutdown();
  srv.stop()` → `return 0`. The guard is `if __name__ == "__main__": sys.exit(main())`.
- (c) **Logging gap closed:** `_setup_logging(level)` calls `logging.basicConfig(stream=sys.stderr,
  level=_resolve_log_level(level), format=...)` — installs a stderr handler at the resolved level
  (journald captures unit stderr; PRD §4.2). `_resolve_log_level("INFO"→20, "DEBUG"→10, "info"→20,
  invalid/"VERBOSE"→INFO, non-str→INFO)`. Idempotent (`basicConfig` no-op if root already has a
  handler, e.g. pytest caplog → tests use caplog, the desired non-intrusive behavior).
- (d) **`on_quit` wiring correct:** `ControlServer` is constructed with `on_quit=daemon.shutdown`
  (the SAME bound method) — so the voicectl `quit` path runs `recorder.shutdown()` AFTER
  `request_shutdown()` broke `text()` (the P1.M4.T2.S2 contract).
- (e) **Teardown ordering correct + robust:** in `finally`, `restore()` (signals) → `daemon.shutdown()`
  (idempotent `recorder.shutdown()`; no-op on the 2nd call) → `srv.stop()` (main thread only —
  joins the accept thread; NEVER from `on_quit` → self-join-deadlock). Each step guarded (`None`
  checks + try/except) so a partial build (e.g. socket bind failed) releases what was built without
  raising; `srv.stop()` runs ONLY here.
- (f) **Exit codes propagate:** clean shutdown → `main()` returns 0; fatal error (config load /
  recorder build / socket bind) → caught, logged, returns 1 → `sys.exit(main())` → systemd
  `Restart=on-failure` restarts the unit (PRD §4.9). `main()` never raises (all fatal paths caught).
- (g) **Start NOT-LISTENING on boot (PRD §4.9):** satisfied automatically — `main()` calls `d.run()`
  (which clears the listening gate + logs "ready (not listening)"); `main()` must NOT arm the mic
  (no `d.start()`/`d.toggle()`). No extra code needed; this criterion is "main() must call run()
  and must not arm".
- (h) **Backward compat:** the existing 173 tests pass UNCHANGED; ~8–10 new tests pass;
  `.venv/bin/python -m pytest tests/ -q` green (~182+ passed: 173 + ~9 from T2.S2 when it merges +
  ~8–10 new). The `voice-typing-daemon` console script now resolves (`main()` exists).
- (i) **No out-of-scope code:** NO `ctl.py` (P1.M5.T1.S1 — the OTHER `main()`), NO
  `systemd/voice-typing.service` (P1.M6.T1.S2), NO `install.sh` (P1.M6.T1.S1), NO `LD_LIBRARY_PATH`
  in-process (item contract forbids it — launch_daemon.sh owns it), NO `pyproject.toml` edit (the
  `voice-typing-daemon = "voice_typing.daemon:main"` entry is ALREADY declared), NO edit to
  `config.py`/`config.toml`/`uv.lock`/`PRD.md`/`tasks.json`/`.gitignore`/`feedback.py`/
  `cuda_check.py`/`textproc.py`/`typing_backends.py`, NO change to any existing daemon.py symbol.

## User Persona

**Target User**: Internal — three future consumers read this surface:
1. **systemd (`voice-typing.service`, P1.M6.T1.S2)** — `ExecStart=.venv/bin/python -m
   voice_typing.daemon` runs the module as `__main__` → the guard calls `main()`. `Restart=on-
   failure` sends SIGTERM to stop the old instance (→ the T2.S2 handler → clean shutdown) and
   relies on `main()`'s non-zero exit (→ restart) if startup fails.
2. **`launch_daemon.sh` (P1.M1.T2.S1)** — `exec .venv/bin/python -m voice_typing.daemon` after
   exporting `LD_LIBRARY_PATH`; `-m` sets `__name__ == "__main__"` so the guard fires.
3. **Operators / devs** — `voice-typing-daemon` console script (entry `voice_typing.daemon:main`)
   for manual runs; Ctrl-C / `systemctl --user stop` / `voicectl quit` all drain via the T2.S2
   signal/quit handlers this `main()` installs.

**Use Case**: The daemon boots as a systemd user service. `main()` loads config, sets up stderr
logging (journald captures it), builds the daemon (models load resident into VRAM), binds the
control socket, installs SIGTERM/SIGINT handlers, and enters `run()` (NOT listening — no hot-mic
on boot, PRD §4.9). The user arms it with `voicectl toggle`. On `voicectl quit` / SIGTERM / Ctrl-C,
the T2.S2 handlers break `run()`, and `main()`'s `finally` releases the GPU workers + closes the
socket. `journalctl --user -u voice-typing` shows the INFO logs (per-utterance latency line).

**Pain Points Addressed**: (1) `python -m voice_typing.daemon` does nothing today — T3.S1 makes it
run. (2) The daemon is silent today (no handler) — T3.S1 wires stderr. (3) Without the `__main__`
guard, RealtimeSTT's spawn-started multiprocessing workers would re-import `__main__` and re-run
heavy top-level code → recursive spawning; T3.S1 keeps ALL heavy work inside `main()`.

## Why

- **The entry point is the thing that makes the daemon a daemon.** Every prior subtask built a
  component; none wired them into a running process. `systemd`, `launch_daemon.sh`, the console
  script, and the test suite (P1.M7.*) all call `main()` / `python -m voice_typing.daemon`. T3.S1
  is the unblocker for the whole install/test phase (P1.M6/P1.M7).
- **The `__main__` guard is MANDATORY, not stylistic.** RealtimeSTT starts `transcript_process` +
  `reader_process` as `mp.Process` with `mp.set_start_method("spawn")` (verified in the T2.S2
  research, citing `.venv/.../RealtimeSTT/core/initialization.py:354-355,397,433`). With spawn, the
  child **re-imports the parent's `__main__` module** (Python docs, "Safe importing of main
  module"). Without the guard, the child re-runs config load + recorder construction → recursive
  process storms. The guard ensures heavy work runs only in the real parent (`__name__ ==
  "__main__"`). This is exactly why the item contract + RealtimeSTT README mandate it.
- **`_configure_log_level()` left a handler gap on purpose.** Its docstring explicitly defers
  handler/root config to T3.S1. Without T3.S1, the daemon logs nothing to the journal — operators
  cannot see the per-utterance latency line (PRD §6 T1) or diagnose a bad start. The fix is one
  `basicConfig` call to stderr (journald's native capture surface).
- **Teardown ordering is subtle and was already proven by T2.S2.** `srv.stop()` must run on the
  MAIN thread (it joins the accept thread; `on_quit` runs on a worker OF that thread → self-join
  if called from there). `daemon.shutdown()` is idempotent so the quit path (`on_quit`) and the
  finally path can both fire. T3.S1 implements the exact `finally` order T2.S2 specified.

## What

Three small, additive pieces (the exact code is pinned in "Implementation Blueprint" —
copy-pasteable; verified against the live `daemon.py` and the consumed component signatures):

1. `_resolve_log_level(level_name) -> int` — defensive `cfg.log.level` → int (INFO fallback for
   invalid/non-str; `getLevelName` returns a string for unknown names, not an exception).
2. `_setup_logging(level_name) -> None` — `logging.basicConfig(stream=sys.stderr, level=…,
   format=…)`; idempotent (no-op under pytest caplog).
3. `main() -> int` — config load → logging → Feedback → Daemon → ControlServer(`on_quit=shutdown`)
   → `srv.start()` → `install_shutdown_signal_handlers(d)` → `try: d.run() finally: restore();
   d.shutdown(); srv.stop()` → `return 0`; fatal errors caught → `return 1`. Plus the
   `if __name__ == "__main__": sys.exit(main())` guard.

### Success Criteria

- [ ] `main`, `_setup_logging`, `_resolve_log_level` exist and are callable; `main()` returns an int.
- [ ] `daemon.py` has an `if __name__ == "__main__":` module-level guard whose body calls `main`.
- [ ] `main()` builds `VoiceTypingDaemon(cfg, Feedback(cfg.feedback))`; `ControlServer(d,
      on_quit=d.shutdown)`; calls `install_shutdown_signal_handlers(d)`; `srv.start()`; `d.run()`;
      in `finally`: `restore()` → `d.shutdown()` → `srv.stop()`.
- [ ] `_setup_logging("DEBUG")` → `basicConfig(stream=sys.stderr, level=10, format=…asctime…)`;
      `_resolve_log_level` maps INFO/DEBUG/invalid as specified.
- [ ] Fatal error (load / construct / run) → `main()` returns 1; clean shutdown → returns 0.
- [ ] Import purity preserved (only stdlib `sys` added); existing 173 tests unchanged; ~182+ pass.
- [ ] `voice-typing-daemon` console script resolves (no `AttributeError`).

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior codebase knowledge: the exact `main()` + `_setup_logging` +
`_resolve_log_level` + guard source is pinned below (verified against the live `daemon.py` and the
exact consumed signatures — `VoiceTypingConfig.load()` (config.py), `Feedback(cfg: FeedbackConfig)`
(feedback.py), `VoiceTypingDaemon(cfg, feedback, *, …)` (daemon.py), `ControlServer(daemon, *,
on_quit=…)` (daemon.py), `install_shutdown_signal_handlers(daemon) -> restore()` (T2.S2)). The
consumed daemon surface + the logging-gap analysis (the single highest-risk detail) are fully
documented (research §2). The T2.S2 dependency + merge timing is a hard preflight gate (research
§11/R1). The validation commands are executable as written.

### Documentation & References

```yaml
# MUST READ — the work-item design + verified facts (THIS is the spec).
- file: plan/001_be48c74bc590/P1M4T3S1/research/daemon_entrypoint_design.md
  why: "§0 scope + the consumed-symbol table. §1 the AUTHORITATIVE main() lifecycle (the P1.M4.T2.S2
        teardown contract — copy this). §2 THE logging gap: run()'s _configure_log_level sets only the
        namespace LEVEL, no handler -> silent daemon; T3.S1 = basicConfig(stream=sys.stderr). §3 WHY the
        __main__ guard is mandatory (RealtimeSTT spawn re-imports __main__). §4 the pyproject entry is
        ALREADY declared (item 'voice_typing.ctl:main' is a typo -> real target voice_typing.daemon:main;
        do NOT edit pyproject). §5 not-listening-on-boot is automatic via run(). §6 import-sys placement.
        §7 do NOT set LD_LIBRARY_PATH in-process. §8 Feedback(cfg.feedback) exact ctor. §9 test strategy.
        §10 validation commands. §11 risks."
  critical: "main() body + finally teardown order is PINNED in §1 — implement verbatim. The logging
             helper MUST use basicConfig (idempotent) NOT a manual addHandler (would double-handle /
             fight pytest caplog). The guard MUST be `if __name__ == '__main__': sys.exit(main())` so
             the exit code reaches systemd. main() MUST NOT arm the mic (run() starts not-listening)."

# MUST READ — the module being EXTENDED (live S1/S2/S3 + S1-of-T2 state; +T2.S2 when it merges).
- file: voice_typing/daemon.py
  why: "The exact starting point. Module-top imports (post S1-of-T2): collections, inspect, json,
        logging, os, select, socket, threading, time (+ signal after T2.S2 merges, placed between
        select and socket). `logger = logging.getLogger(__name__)` is module-level. `run()` already
        calls `_configure_log_level()` (sets ONLY the voice_typing namespace level; no handler -> the
        gap T3.S1 closes) + `_log_resolved_device()` + `self._feedback.set_listening(False)` (not-
        listening on boot). `class ControlServer` (S1-of-T2) + module fn `install_shutdown_signal_
        handlers` + `VoiceTypingDaemon.shutdown` (T2.S2) are the consumed teardown surface. T3.S1
        APPENDS `import sys` + 3 module fns + the guard at MODULE END — no existing symbol is edited."
  critical: "Do NOT modify __init__/run/on_final/_arm/_disarm/start/stop/toggle/request_shutdown/
             shutdown/_build_callbacks/_construct/build_recorder/cfg_to_kwargs/_resolve_device_config/
             _filter_kwargs_to_signature/_configure_log_level/_log_resolved_device/uptime_s/status_
             snapshot/_resolved_device/LatencyLog/_default_control_socket_path/ControlServer/install_
             shutdown_signal_handlers. ALL T3.S1 edits are ADDITIVE (1 new stdlib import + 3 new module
             fns + the guard). Keep ALL heavy work INSIDE main() — nothing heavy at module top (spawn
             guard invariant; research §3)."

# MUST READ — the P1.M4.T2.S2 teardown contract (in-flight parallel; treat as a hard dependency).
- file: plan/001_be48c74bc590/P1M4T2S2/PRP.md
  why: "Pins `VoiceTypingDaemon.shutdown()` (idempotent: getattr-guarded _shutdown_done flag + defensive
        try/except around recorder.shutdown()) and `install_shutdown_signal_handlers(daemon, *, signals=
        None) -> restore()` (SIGTERM/SIGINT -> spawn daemon thread -> daemon.request_shutdown()). Its
        'Integration Points' section is the AUTHORITATIVE main() body T3.S1 implements (quoted verbatim
        in research §1)."
  critical: "main() depends on BOTH shutdown() AND install_shutdown_signal_handlers() existing. The
             PRP preflight (Task 0) asserts they are present; if T2.S2 hasn't merged, STOP — T3.S1
             cannot run without them. srv.stop() runs ONLY in main()'s finally (main thread); it joins
             the accept thread on which on_quit runs -> calling srv.stop() from on_quit self-join-
             deadlocks (T2.S2 Critical #5)."

# MUST READ — the config loader + LogConfig (consumed).
- file: voice_typing/config.py
  why: "VoiceTypingConfig.load(path=None) (PRD §4.5 search order; returns dataclass defaults if no file).
        LogConfig.level: str = 'INFO' (PRD §4.2 'at INFO; DEBUG via config'). The SAME field run()'s
        _configure_log_level reads -> root handler + namespace logger agree when main() also reads it."
  critical: "main() calls VoiceTypingConfig.load() with NO args (the search order; systemd unit sets
             no --config). A load failure (corrupt TOML) -> main() returns 1 after a fallback INFO
             basicConfig so the traceback is visible (logging may not yet be configured)."

# MUST READ — Feedback constructor (consumed).
- file: voice_typing/feedback.py
  why: "Feedback(cfg: FeedbackConfig) — takes cfg.feedback (NOT cfg, NOT the resolved state file).
        resolved_state_file() is called lazily inside _write() (raises only at write time if
        XDG_RUNTIME_DIR unset + state_file empty). Pure stdlib -> importing it lazily in main() keeps
        import purity."
  critical: "main() does Feedback(cfg.feedback) (research §8 verified). Import Feedback LAZILY inside
             main() (`from voice_typing.feedback import Feedback`) so the module-top change is just
             `import sys` AND so tests can monkeypatch voice_typing.feedback.Feedback (the in-main
             `from X import Y` resolves the live attribute at call time)."

# MUST READ — the established house main()/guard pattern (match its form).
- file: voice_typing/cuda_check.py
  why: "The reference for a console-script entry point + guard in this repo: a `_main() -> int` that
        returns an exit code, guarded by `if __name__ == '__main__': sys.exit(_main())`. T3.S1 follows
        the SAME guard form (sys.exit(main())) so the exit code propagates to systemd. cuda_check also
        documents the 'do NOT set LD_LIBRARY_PATH in-process' rule (ld.so reads it only at exec) — the
        same rule the T3.S1 item contract states."
  critical: "Use `sys.exit(main())` in the guard, NOT a bare `main()` — systemd Restart=on-failure
             needs the non-zero exit code. (The item's literal '...: main()' is shorthand for 'the
             guard calls main'; the exit-code-propagation reading is the correct one, research §3.)"

# MUST READ — the S1/S2/S3/(S1-of-T2)/(T2.S2) tests (regression baseline + helpers to reuse).
- file: tests/test_daemon.py
  why: "_StubRecorder (has shutdown/abort/set_microphone/text), _make_daemon(*, recorder=, backend=,
        cfg=) -> (daemon, fb, rec, be), _wait_for(predicate, timeout=2.0). The new T3.S1 section
        APPENDS — it does NOT edit S1/S2/S3/T2 bodies. For the orchestration test, monkeypatch the
        module-level names (daemon.VoiceTypingConfig / daemon.VoiceTypingDaemon / daemon.ControlServer
        / daemon.install_shutdown_signal_handlers) + voice_typing.feedback.Feedback."
  critical: "DO NOT call the real main() unmodified in unit tests (it builds a real recorder -> CUDA).
             Monkeypatch every component to a fake that records calls; the fake daemon's run() sets a
             flag and returns immediately. For _setup_logging, monkeypatch logging.basicConfig to
             capture kwargs (hermetic — avoids pytest's root-handler entanglement)."

# External — the __main__ guard + spawn + logging mandates (authoritative).
- url: https://docs.python.org/3/library/multiprocessing.html#the-spawn-and-forkserver-start-methods
  why: "'Spawn' start method: the child re-imports the parent __main__ module — the reason ALL heavy
        work must live inside main() under the if __name__ == '__main__' guard."
- url: https://docs.python.org/3/library/multiprocessing.html#safe-importing-of-main-module
  why: "'Safe importing of main module' — explicitly warns that un-guarded __main__ causes recursive
        imports/AttributeError with spawn. Confirms the guard is a correctness requirement."
- url: https://docs.python.org/3/library/logging.html#logging.basicConfig
  why: "basicConfig(): 'does nothing if the root logger already has handlers configured' (idempotent —
        the property that makes _setup_logging a no-op under pytest caplog) + stream= for the handler +
        level= for the root level + format= for the formatter. The exact API _setup_logging uses. NOTE:
        basicConfig already DEFAULTS its handler to sys.stderr, so stream=sys.stderr is explicit-but-
        harmless (the readable, intent-obvious form — research external_citations.md §2)."
- url: https://www.freedesktop.org/software/systemd/man/systemd.exec.html
  why: "StandardError= default is 'inherit' -> for a user service, the daemon's stderr (fd 2) is connected
        to systemd-journald, so ALL logging output appears in 'journalctl --user -u voice-typing'. This is
        the authoritative reason logging.basicConfig(stream=sys.stderr) satisfies PRD §4.2 'logging to
        stderr (journald picks it up under systemd)' with ZERO extra unit config (research §3)."
- url: https://docs.python.org/3/library/__main__.html
  why: "Confirms `python -m pkg.mod` runs the module as __main__ (sets __name__=='__main__') — the path
        systemd ExecStart + launch_daemon.sh use, and the path the guard protects."
- url: https://github.com/KoljaB/RealtimeSTT
  why: "RealtimeSTT README: documents that the application must use `if __name__ == '__main__':` because
        the library spawns multiprocessing workers (the item contract's citation)."

# Background — the preceding subtask PRPs (house style + the consumed surfaces).
- file: plan/001_be48c74bc590/P1M4T1S2/PRP.md
  why: "VoiceTypingDaemon design (run() blocks, request_shutdown sets _shutdown + aborts, _listening
        cleared at boot). Confirms run() is the blocking entry and starts not-listening."
- file: plan/001_be48c74bc590/P1M4T2S1/PRP.md
  why: "ControlServer(daemon, *, socket_path=, on_quit=) + start()/stop() contract main() consumes."

# Downstream — the consumers T3.S1 feeds (do NOT build).
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M5.T1.S1 (voicectl/ctl.py — the OTHER main(), separate binary), P1.M6.T1.S1 (install.sh),
        P1.M6.T1.S2 (systemd unit ExecStart=python -m voice_typing.daemon), P1.M7.* (tests drive the
        running daemon via voicectl). Confirms main() is the contract they all call."
  critical: "Do NOT build ctl.py / systemd unit / install.sh here. main() is the contract — do not
             rename it or change its return type (int)."
```

### Current Codebase tree (state at P1.M4.T3.S1 start — S1/S2/S3 + S1-of-T2 merged, 173 passing; +T2.S2 when it lands)

```bash
/home/dustin/projects/voice-typing/
├── .git/ .gitignore .venv/        # DO NOT touch .gitignore
├── PRD.md                         # READ-ONLY (§4.2 logging/quit, §4.9 systemd/not-listening)
├── config.toml pyproject.toml uv.lock   # DO NOT touch (entry already declared; no new deps; stdlib sys)
├── voice_typing/
│   ├── __init__.py cuda_check.py config.py textproc.py typing_backends.py status.sh launch_daemon.sh prefetch.py
│   ├── feedback.py                # READ ONLY (Feedback(cfg) ctor consumed)
│   └── daemon.py                  # ← MODIFY (Task 1): ADD `import sys` + _resolve_log_level() +
│                                  #   _setup_logging() + main() + `if __name__ == "__main__":` guard.
│                                  #   (NO existing-symbol edit; module-END additions only.)
└── tests/
    ├── test_config.py test_config_repo_default.py test_textproc.py test_typing_backends.py test_feedback.py
    ├── test_control_socket.py     # (S1-of-T2) — DO NOT touch
    └── test_daemon.py             # ← MODIFY (Task 2): APPEND main()/logging/guard tests.
```

### Desired Codebase tree with files to be added/modified

```bash
voice_typing/daemon.py             # +import sys, +_resolve_log_level(), +_setup_logging(), +main(), +guard (module END)
tests/test_daemon.py               # +main()/logging/guard test section (appended)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — _configure_log_level() adds NO handler (the gap T3.S1 closes). Verified in live
#   daemon.py: run() calls self._configure_log_level() whose docstring says "Namespace-scoped only —
#   NOT basicConfig (handler/root config is P1.M4.T3.S1's job)". It does logging.getLogger("voice_typing
#   ").setLevel(level) ONLY. With no handler on voice_typing AND none on root, logger.info(...) records
#   pass the logger gate but have nowhere to emit -> SILENT. T3.S1 = logging.basicConfig(stream=sys.
#   stderr, level=..., format=...). (research §2.)

# CRITICAL #2 — for DEBUG-via-config to actually SHOW debug records, the HANDLER/ROOT level must come
#   from cfg.log.level too. Python logging: a record is emitted only if it passes BOTH the logger's
#   effective level AND at least one handler's level. If root handler is INFO but voice_typing logger
#   is DEBUG (set by _configure_log_level), DEBUG records pass the namespace gate, propagate to root's
#   handler, but the INFO handler DROPS them. So _setup_logging MUST pass level=_resolve_log_level(cfg.
#   log.level) to basicConfig (root level), not hardcode INFO. (research §2.)

# CRITICAL #3 — basicConfig is IDEMPOTENT (a no-op if root already has handlers). This is the DESIRED
#   behavior under pytest caplog (root has caplog's handler -> basicConfig no-op -> tests use caplog,
#   non-intrusive). In a fresh process (systemd/console-script/-m) root has no handlers -> it installs
#   the stderr handler. Do NOT use a manual root.addHandler(StreamHandler(sys.stderr)) instead — that
#   would double-handle under pytest and is not idempotent. (research §2.)

# CRITICAL #4 — logging.getLevelName(name) returns an INT for a valid level ("INFO"->20) but returns
#   the STRING "Level <name>" for an UNKNOWN name (it does NOT raise). So _resolve_log_level MUST guard
#   with isinstance(level, int) (else a typo'd cfg.log.level="VERBOSE" would set root level to the
#   string "Level VERBOSE" -> logging breaks). Mirrors _configure_log_level's defensive posture. (§2.)

# CRITICAL #5 — the __main__ guard is MANDATORY (RealtimeSTT spawn). transcript_process + reader_process
#   are mp.Process with set_start_method("spawn") (verified T2.S2 research). spawn children RE-IMPORT
#   the parent's __main__ module. If __main__ has top-level heavy code (config load, recorder build),
#   the child re-runs it -> recursive spawning. The guard ensures heavy work runs ONLY in the real
#   parent. THEREFORE all heavy work (cfg load, Feedback, VoiceTypingDaemon, signal install, run) MUST
#   live INSIDE main(). daemon.py has ZERO top-level side effects today (imports + constants + pure
#   defs only) — KEEP IT THAT WAY. T3.S1 adds only: `import sys`, 3 module fns, the guard (the guard's
#   body calls main(); main() is not invoked at import). (research §3.)

# CRITICAL #6 — use `if __name__ == "__main__": sys.exit(main())`, NOT a bare `main()`. sys.exit
#   propagates main()'s return code: clean=0, fatal=1 -> systemd Restart=on-failure restarts on fatal
#   (PRD §4.9). Matches the house pattern in voice_typing/cuda_check.py (`sys.exit(_main())`). The item's
#   literal `...: main()` is shorthand for "the guard calls main"; exit-code propagation is correct. (§3.)

# CRITICAL #7 — BOTH invocation paths work and BOTH call main(): (a) `python -m voice_typing.daemon`
#   (systemd/launch_daemon.sh) runs the module AS __main__ -> guard calls main(). Python 3 sets __spec__
#   on -m runs so spawn children re-import via the qualified name (not as __main__) -> guard protects
#   them. (b) `voice-typing-daemon` console script (entry voice_typing.daemon:main) -> hatchling wrapper
#   imports voice_typing.daemon (__name__=="voice_typing.daemon") + calls main() directly (guard
#   irrelevant here, but main() being the single heavy entry still keeps spawn children clean). (§3.)

# CRITICAL #8 — the [project.scripts] entry is ALREADY DECLARED. Verified pyproject.toml:
#     voice-typing-daemon = "voice_typing.daemon:main"   # already there (P1.M1.T1.S1)
#   The item description's "voice_typing.ctl:main" is a TYPO (ctl.py is voicectl, P1.M5.T1.S1, a
#   different binary). T3.S1 does NOT edit pyproject.toml — it only IMPLEMENTS main() so the existing
#   entry resolves. (research §4.)

# CRITICAL #9 — NOT-LISTENING on boot is AUTOMATIC. run() sets _feedback.set_listening(False) + logs
#   "ready (not listening)"; __init__ clears the _listening Event. main() just calls d.run() and must
#   NOT arm the mic (no d.start()/d.toggle()). No extra code for PRD §4.9. (research §5.)

# CRITICAL #10 — the ONLY new module-top import is `import sys` (for sys.stderr + sys.exit). Place it
#   alphabetically BETWEEN `socket` and `threading` (s-o-c < s-y-s < t-h-r). This anchor is STABLE
#   whether or not T2.S2's `import signal` has merged: signal sits BETWEEN select and socket (BEFORE
#   socket), so the socket->threading adjacency is unchanged. Pure addition; import purity preserved
#   (sys is stdlib-cheap). (research §6.)

# CRITICAL #11 — do NOT set LD_LIBRARY_PATH in-process (item contract). The dynamic linker reads it
#   ONLY at process exec (ld.so(8)); mutating os.environ inside the running process has NO effect on
#   ctranslate2's dlopen. launch_daemon.sh (P1.M1.T2.S1) is the single sanctioned place (it exports
#   the cuBLAS+cuDNN dirs then exec python -m voice_typing.daemon). systemd wiring is P1.M6.T1.S2.
#   (research §7.)

# CRITICAL #12 — Feedback is imported LAZILY inside main() (`from voice_typing.feedback import
#   Feedback`), NOT at module top. Two reasons: (a) keeps the module-top change to JUST `import sys`
#   (no churn to the TYPE_CHECKING block S1/S2/S3/T2.S2 reference); (b) it stays monkeypatchable —
#   tests do monkeypatch.setattr("voice_typing.feedback.Feedback", Fake) and the in-main `from X import
#   Y` resolves the live attribute at call time. Feedback is pure stdlib so this is also import-pure.
#   (research §8.)

# CRITICAL #13 — teardown order in finally is FIXED (the P1.M4.T2.S2 contract): restore() (stop
#   diverting signals) -> daemon.shutdown() (idempotent recorder.shutdown() — first call wins; 2nd is
#   a no-op) -> srv.stop() (LAST + MAIN THREAD ONLY — it joins the accept thread; on_quit runs ON a
#   worker of that thread -> srv.stop() from on_quit self-join-deadlocks). main() is the main thread.
#   (research §1; T2.S2 Critical #5.)

# CRITICAL #14 — finally must be NULL-SAFE + exception-safe. If construction fails partway (e.g. socket
#   bind raises), daemon/server/restore may be None. Initialize all three to None before the try; in
#   finally guard each with `is not None` + its own try/except (log-not-raise) so teardown of what WAS
#   built never masks the original error. Do NOT `return` from finally (a finally return overrides the
#   except's return value). (research §1.)

# CRITICAL #15 — main() MUST NOT raise (all fatal paths caught + logged + return 1). A propagating
#   exception from main() would bypass the clean return-code contract; the console wrapper's
#   sys.exit(main()) would never run (Python prints a traceback + exits 1 anyway, but logging the
#   error at ERROR level first is the clean, journal-friendly path). KeyboardInterrupt during run() is
#   handled by the installed SIGINT handler (request_shutdown -> run() exits cleanly); during
#   construction (before install) it propagates (rare; systemd restarts). (research §1.)

# CRITICAL #16 — FULL PATHS for tooling (zsh aliases python/pytest). ALWAYS
#   `.venv/bin/python -m pytest` / `.venv/bin/python -m py_compile` (never bare python/pytest).
#   mypy is NOT installed — do NOT list it. ruff is optional (/home/dustin/.local/bin/ruff);
#   py_compile + pytest are the authoritative gates.
```

## Implementation Blueprint

### Data models and structure

No new data model. Three module-level callables + the guard:

```python
_resolve_log_level(level_name: object) -> int        # cfg.log.level name -> int (INFO fallback)
_setup_logging(level_name: object) -> None           # basicConfig(stream=sys.stderr, level=…, format=…)
main() -> int                                        # the lifecycle orchestrator (returns exit code)
# + the module-level guard: if __name__ == "__main__": sys.exit(main())
```

`main()` holds only transient orchestration state (`daemon`/`server`/`restore`, initialized `None`).

### `_resolve_log_level()` + `_setup_logging()` reference implementation (research §2 — implement verbatim)

```python
# ADD at module END (after install_shutdown_signal_handlers; after ControlServer). Uses logging + sys
# (both stdlib; `sys` is the one new module-top import T3.S1 adds).


def _resolve_log_level(level_name: object) -> int:
    """Resolve a config log-level name to a logging int (INFO default; PRD §4.2 'DEBUG via config').

    `logging.getLevelName(name)` returns an int for a valid level name ("INFO"->20, "DEBUG"->10) but
    returns the STRING 'Level <name>' for an unknown one (it does NOT raise) -> the isinstance guard
    turns any typo/garbage into INFO. Mirrors VoiceTypingDaemon._configure_log_level's defensive
    posture (an invalid level is ignored, not crashed on). A non-str input (None, int) -> INFO.
    """
    if not isinstance(level_name, str):
        return logging.INFO
    level = logging.getLevelName(level_name.strip().upper())
    return level if isinstance(level, int) else logging.INFO


def _setup_logging(level_name: object) -> None:
    """Configure stderr logging at the resolved level (PRD §4.2; P1.M4.T3.S1).

    Closes the gap VoiceTypingDaemon._configure_log_level deliberately left open: that fn sets ONLY
    the 'voice_typing' namespace logger LEVEL (no handler) -> without this, records pass the logger
    gate but have nowhere to emit (silent daemon). logging.basicConfig is IDEMPOTENT: a no-op if the
    root logger already has a handler (e.g. under pytest caplog -> tests keep using caplog, the
    desired non-intrusive behavior); in a fresh process (systemd, console script, `python -m`) it
    installs a single StreamHandler on stderr (journald captures unit stderr) at the resolved level.
    The SAME cfg.log.level is read by run()'s _configure_log_level -> root handler + namespace logger
    agree, so 'DEBUG' actually shows debug records (not just passes the namespace gate).
    """
    logging.basicConfig(
        stream=sys.stderr,
        level=_resolve_log_level(level_name),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
```

### `main()` + the guard reference implementation (research §1/§3 — implement verbatim)

```python
# ADD at module END (after _setup_logging). The single sanctioned lifecycle. ALL heavy work lives
# HERE (not at module top) so RealtimeSTT's spawn-started multiprocessing children, which re-import
# __main__, do not re-run it (the if __name__ == "__main__" guard invariant; research §3).


def main() -> int:
    """Daemon process entry point: logging + config + daemon/server + signals + run + teardown.

    (PRD §4.2/§4.9; P1.M4.T3.S1.) Wires together the components built by every prior subtask into the
    single sanctioned lifecycle. Guarded by `if __name__ == "__main__": sys.exit(main())` (RealtimeSTT
    uses spawn-started multiprocessing workers that re-import __main__ -> ALL heavy work must live in
    main(), never at module top; the guard + this invariant keep spawn children clean).

    Lifecycle (the teardown order is the P1.M4.T2.S2 contract):
      cfg = VoiceTypingConfig.load(); _setup_logging(cfg.log.level)
      Feedback(cfg.feedback) -> VoiceTypingDaemon(cfg, fb) -> ControlServer(d, on_quit=d.shutdown)
      srv.start(); restore = install_shutdown_signal_handlers(d);   (both main-thread)
      try: d.run()                                            # BLOCKS until quit/signal
      finally: restore(); d.shutdown(); srv.stop()            # idempotent shutdown; srv.stop main-thread only
      return 0
    Returns 0 on clean shutdown, 1 on a fatal error (config/recorder/server init) so systemd
    Restart=on-failure restarts the unit. NEVER raises (all fatal paths caught + logged).
    """
    # 1. Config first (needed for the logging level). A load failure is fatal + unrecoverable; set up
    #    a fallback stderr INFO handler so the traceback is visible (logging may not be configured yet).
    try:
        cfg = VoiceTypingConfig.load()
    except Exception:
        _setup_logging("INFO")
        logger.exception("failed to load config; exiting")
        return 1
    # 2. Logging to stderr (journald) at cfg.log.level (PRD §4.2). Closes the _configure_log_level gap.
    _setup_logging(cfg.log.level)
    logger.info("voice-typing daemon starting (pid=%s)", os.getpid())

    daemon = None        # type: VoiceTypingDaemon | None
    server = None        # type: ControlServer | None
    restore = None       # type: Callable[[], None] | None
    try:
        from voice_typing.feedback import Feedback   # lazy: keeps module-top change to just `import sys`;
        #                                  also stays monkeypatchable (tests patch voice_typing.feedback.Feedback)
        daemon = VoiceTypingDaemon(cfg, Feedback(cfg.feedback))
        # quit path: ControlServer._dispatch("quit") -> request_shutdown() (blocks until text() returns)
        #   -> on_quit=daemon.shutdown() -> recorder.shutdown() (release VRAM). research §1/§d.
        server = ControlServer(daemon, on_quit=daemon.shutdown)
        # SIGTERM/SIGINT -> a spawned daemon thread calls daemon.request_shutdown() (NOT abort() from the
        #   handler — that deadlocks; T2.S2). Returns restore() reinstating the prior handlers.
        restore = install_shutdown_signal_handlers(daemon)
        server.start()
        daemon.run()        # BLOCKS until quit/signal; starts NOT-LISTENING (PRD §4.9; no hot-mic on boot)
    except Exception:
        logger.exception("fatal error during daemon lifecycle; exiting")
        return 1
    finally:
        # Teardown order (P1.M4.T2.S2 contract): stop diverting signals -> release GPU workers -> close
        # the control socket. Each step is NULL-SAFE + best-effort (a failure here must not mask the
        # original reason). server.stop() runs ONLY here (main thread): it joins the accept thread, and
        # on_quit runs on a worker OF that thread -> calling server.stop() from on_quit would self-join.
        if restore is not None:
            try:
                restore()
            except Exception:
                logger.exception("signal handler restore failed (ignored)")
        if daemon is not None:
            try:
                daemon.shutdown()      # idempotent: no-op if on_quit (quit path) already shut the recorder
            except Exception:
                logger.exception("daemon.shutdown() failed during teardown (ignored)")
        if server is not None:
            try:
                server.stop()         # close socket + unlink + join accept thread (main thread)
            except Exception:
                logger.exception("ControlServer.stop() failed during teardown (ignored)")
    return 0


if __name__ == "__main__":
    # The guard RealtimeSTT's spawn-based multiprocessing requires (re-import of __main__ in children
    # skips this body). sys.exit propagates main()'s exit code to systemd (Restart=on-failure).
    sys.exit(main())
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — confirm the live state + consumed surface + the T2.S2 dependency + the baseline.
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/daemon.py && echo ok
      .venv/bin/python -m pytest tests/ -q 2>&1 | tail -1      # expect "173 passed" (+~9 if T2.S2 merged -> ~182)
      .venv/bin/python -c "
import sys, voice_typing.daemon as d
# HARD DEPENDENCY on P1.M4.T2.S2 (parallel, in flight). Assert BOTH shipped before proceeding.
assert hasattr(d.VoiceTypingDaemon, 'shutdown'), 'P1.M4.T2.S2 not merged: VoiceTypingDaemon.shutdown missing — STOP'
assert hasattr(d, 'install_shutdown_signal_handlers'), 'P1.M4.T2.S2 not merged: install_shutdown_signal_handlers missing — STOP'
# Consumed surface (must all exist).
assert hasattr(d, 'VoiceTypingDaemon') and hasattr(d, 'ControlServer')
assert hasattr(d.VoiceTypingConfig, 'load')
from voice_typing.feedback import Feedback
import inspect
assert list(inspect.signature(Feedback.__init__).parameters) == ['self', 'cfg']   # Feedback(cfg)
# T3.S1 targets not yet present.
assert not hasattr(d, 'main'), 'main() already present (unexpected)'
assert not callable(getattr(d, '_setup_logging', None)), '_setup_logging already present (unexpected)'
# Import purity pre-task.
assert not [m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules], 'import purity broken pre-task'
print('consumed surface + T2.S2 dependency + import purity OK; baseline green')
"
      grep -n '^import \|^from ' voice_typing/daemon.py | head     # confirm the import block (anchor for Task 1a)
  - EXPECTED: 173 passed (or ~182 if T2.S2 merged); shutdown() + install_shutdown_signal_handlers() present
    (HARD GATE — if missing, T2.S2 hasn't merged; STOP and wait for it); VoiceTypingDaemon/ControlServer/
    VoiceTypingConfig.load/Feedback(cfg) present; main()/_setup_logging NOT yet present; import purity holds.
    NOTE the exact import-block lines for the Task 1a anchor (signal may already be present if T2.S2 merged).
  - DO NOT create/edit any file, run uv sync/add, or touch other modules.

Task 1: MODIFY voice_typing/daemon.py — ADD `import sys` + _resolve_log_level() + _setup_logging() +
        main() + the `if __name__ == "__main__":` guard.
  - FILE: voice_typing/daemon.py.
  - (1a) ADD `import sys` to the module-top stdlib import block, alphabetically BETWEEN `import socket`
         and `import threading` (s-o-c < s-y-s < t-h-r). See "Task 1a edit". This anchor is stable whether
         or not T2.S2's `import signal` has merged (signal sits between select and socket, BEFORE socket,
         so the socket->threading adjacency is unchanged). Do NOT reorder existing imports.
  - (1b) ADD `_resolve_log_level()` + `_setup_logging()` + `main()` + the guard verbatim (above) at
         MODULE END — AFTER `install_shutdown_signal_handlers` (T2.S2) and AFTER `class ControlServer`
         (S1-of-T2), i.e. the very end of the file. Pure addition.
  - DO NOT: modify any existing symbol (see CRITICAL list); add any module-top code that has side
    effects (the spawn-guard invariant — ALL heavy work stays inside main()); set LD_LIBRARY_PATH;
    edit pyproject.toml/config.py/config.toml/uv.lock/feedback.py/cuda_check.py; add a 2nd main() or
    touch ctl.py; arm the mic in main() (no d.start()/d.toggle()); add a manual root.addHandler
    (use basicConfig — idempotent).

Task 2: MODIFY tests/test_daemon.py — APPEND the main()/logging/guard test section.
  - FILE: tests/test_daemon.py. APPEND only; do NOT edit S1/S2/S3/(T2) bodies. See "Task 2 SOURCE".
  - PATTERNS: monkeypatch the module-level names (daemon.VoiceTypingConfig / daemon.VoiceTypingDaemon /
    daemon.ControlServer / daemon.install_shutdown_signal_handlers) + voice_typing.feedback.Feedback to
    fakes that RECORD calls; the fake daemon's run() sets a flag + returns immediately (NO block, NO
    recorder). For _setup_logging, monkeypatch logging.basicConfig to capture kwargs (hermetic — avoids
    pytest's root-handler entanglement). For _resolve_log_level, call directly (pure fn). For the guard,
    an AST parse of daemon.py (hermetic — no subprocess, no CUDA). Reuse _wait_for if needed.
  - COVERAGE: (Layer A — _resolve_log_level) INFO/DEBUG/lowercase/invalid/non-str mappings. (Layer B —
    _setup_logging) basicConfig called with stream=sys.stderr + level=_resolve_log_level(name) + a format
    with asctime/levelname/name/message; idempotency (basicConfig is the real call's contract — the test
    asserts the kwargs, not root mutation). (Layer C — main orchestration) the lifecycle order (load ->
    Feedback(cfg.feedback) -> VoiceTypingDaemon(cfg, fb) -> ControlServer(d, on_quit=d.shutdown) ->
    install_shutdown_signal_handlers(d) -> srv.start() -> d.run() -> finally restore/d.shutdown/srv.stop)
    + main() returns 0. (Layer D — on_quit wiring) ControlServer received on_quit IS daemon.shutdown
    (same bound method). (Layer E — fatal path) fake VoiceTypingDaemon raises in __init__ -> main()
    returns 1 + finally does NOT touch None refs (no AttributeError); config-load failure -> returns 1.
    (Layer F — guard) AST: an `if __name__ == "__main__":` module-level If exists whose body calls main;
    callable(daemon.main).
  - DO NOT: import RealtimeSTT/torch; call the real main() unmodified (builds a recorder -> CUDA);
    depend on XDG_RUNTIME_DIR; send real signals; sleep gratuitously.

Task 3: VALIDATE — run the Validation Loop L1–L4. Iterate until all gates pass.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M4.T3.S1: daemon main() entry point (__main__ guard, signal/log wiring, lifecycle teardown)".
```

#### Task 1a edit — `voice_typing/daemon.py` import block (stable whether or not T2.S2's `signal` merged)

```
oldText:
import socket
import threading
newText:
import socket
import sys
import threading
```
(If the live block differs and `import socket`/`import threading` are not adjacent, insert
`import sys` in alphabetical position among the existing `import X` lines, after `socket` and
before `threading`. T2.S2's `import signal` sits between `select` and `socket` — it does NOT break
the `socket`/`threading` adjacency. Never reorder existing imports.)

#### Task 2 SOURCE — `tests/test_daemon.py` APPEND section (skeleton; expand to ~8–10 tests)

```python
# ===========================================================================
# P1.M4.T3.S1 — daemon main() entry point: _resolve_log_level / _setup_logging /
# main() lifecycle + the if __name__ == "__main__" guard.
# (ADDITIVE — everything above is S1/S2/S3/(S1-of-T2)/(T2.S2); do not change it.)
# ===========================================================================
import ast
import logging
import sys
from pathlib import Path

from voice_typing import daemon
from voice_typing.config import VoiceTypingConfig


# --- Layer A: _resolve_log_level ---------------------------------------------------------

def test_resolve_log_level_valid_names():
    assert daemon._resolve_log_level("INFO") == logging.INFO
    assert daemon._resolve_log_level("DEBUG") == logging.DEBUG
    assert daemon._resolve_log_level("warning") == logging.WARNING      # case-insensitive
    assert daemon._resolve_log_level("  debug  ") == logging.DEBUG      # stripped

def test_resolve_log_level_invalid_falls_back_to_info():
    assert daemon._resolve_log_level("VERBOSE") == logging.INFO         # getLevelName -> "Level VERBOSE"
    assert daemon._resolve_log_level("") == logging.INFO
    assert daemon._resolve_log_level(None) == logging.INFO              # non-str
    assert daemon._resolve_log_level(20) == logging.INFO                # non-str


# --- Layer B: _setup_logging (monkeypatch basicConfig — hermetic) -------------------------

def test_setup_logging_configures_stderr_at_level(monkeypatch):
    captured = {}
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: captured.update(kw))
    daemon._setup_logging("DEBUG")
    assert captured["stream"] is sys.stderr
    assert captured["level"] == logging.DEBUG
    assert "asctime" in captured["format"] and "message" in captured["format"]

def test_setup_logging_passes_resolved_level(monkeypatch):
    captured = {}
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: captured.update(kw))
    daemon._setup_logging("not-a-level")        # invalid -> INFO
    assert captured["level"] == logging.INFO


# --- Layer C: main() lifecycle orchestration (all components monkeypatched) ----------------

class _FakeFeedback:
    def __init__(self, cfg): self.cfg = cfg

class _FakeDaemon:
    def __init__(self, cfg, fb, **kw):
        self.cfg, self.fb = cfg, fb
        self.run_called = False
        self.shutdown_calls = 0
    def run(self): self.run_called = True          # return immediately (NO block, NO recorder)
    def shutdown(self): self.shutdown_calls += 1
    # on_quit is wired to this bound method; ControlServer must receive it AS-IS

class _FakeServer:
    def __init__(self, d, *, on_quit=None, **kw):
        self.daemon = d; self.on_quit = on_quit
        self.start_calls = self.stop_calls = 0
    def start(self): self.start_calls += 1
    def stop(self): self.stop_calls += 1

def _patch_lifecycle(monkeypatch, *, daemon_cls=_FakeDaemon, server_cls=_FakeServer,
                     feedback_cls=_FakeFeedback, install_returns_restore=True):
    refs = {}
    monkeypatch.setattr(daemon, "VoiceTypingConfig",
                        type("C", (), {"load": classmethod(lambda cls: VoiceTypingConfig())}))
    monkeypatch.setattr(daemon, "VoiceTypingDaemon", daemon_cls)
    monkeypatch.setattr(daemon, "ControlServer", server_cls)
    monkeypatch.setattr("voice_typing.feedback.Feedback", feedback_cls)
    restored = {"called": False}
    def _install(d, *, signals=None):
        refs["install_arg"] = d
        def _restore(): restored["called"] = True
        return _restore if install_returns_restore else (lambda: None)
    monkeypatch.setattr(daemon, "install_shutdown_signal_handlers", _install)
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: None)   # don't touch real root
    return refs, restored

def test_main_runs_full_lifecycle_and_returns_zero(monkeypatch):
    refs, restored = _patch_lifecycle(monkeypatch)
    code = daemon.main()
    assert code == 0
    # run() was called (the blocking entry); server started + stopped; restore called.
    # (the fakes are module-level singletons via the patched classes; re-grab via the patched names)
    assert daemon.VoiceTypingDaemon.__name__ == "_FakeDaemon"     # sanity: patch active

def test_main_calls_run_start_stop_and_restore(monkeypatch):
    # Use instance-tracking fakes to assert call counts.
    bag = {}
    class D(_FakeDaemon):
        def __init__(self, *a, **k): super().__init__(*a, **k); bag["d"] = self
    class S(_FakeServer):
        def __init__(self, *a, **k): super().__init__(*a, **k); bag["s"] = self
    refs, restored = _patch_lifecycle(monkeypatch, daemon_cls=D, server_cls=S)
    assert daemon.main() == 0
    assert bag["d"].run_called is True
    assert bag["s"].start_calls == 1 and bag["s"].stop_calls == 1
    assert bag["d"].shutdown_calls == 1                 # finally called shutdown() (no quit here)
    assert restored["called"] is True                   # restore() ran in finally

def test_main_wires_on_quit_to_daemon_shutdown(monkeypatch):
    bag = {}
    class D(_FakeDaemon):
        def __init__(self, *a, **k): super().__init__(*a, **k); bag["d"] = self
    class S(_FakeServer):
        def __init__(self, *a, **k): super().__init__(*a, **k); bag["s"] = self
    _patch_lifecycle(monkeypatch, daemon_cls=D, server_cls=S)
    daemon.main()
    # ControlServer MUST have been built with on_quit == the daemon's shutdown bound method.
    assert bag["s"].on_quit == bag["d"].shutdown

def test_main_passes_config_feedback_to_daemon(monkeypatch):
    bag = {}
    class D(_FakeDaemon):
        def __init__(self, cfg, fb, **k): super().__init__(cfg, fb, **k); bag["cfg"], bag["fb"] = cfg, fb
    _patch_lifecycle(monkeypatch, daemon_cls=D)
    daemon.main()
    assert isinstance(bag["cfg"], VoiceTypingConfig)
    assert isinstance(bag["fb"], _FakeFeedback) and bag["fb"].cfg is bag["cfg"].feedback


# --- Layer E: fatal path -> return 1, no None-deref ---------------------------------------

def test_main_returns_one_on_daemon_construction_failure(monkeypatch):
    class BoomDaemon:
        def __init__(self, *a, **k): raise RuntimeError("recorder init failed")
        def run(self): pass
        def shutdown(self): pass
    _patch_lifecycle(monkeypatch, daemon_cls=BoomDaemon)
    assert daemon.main() == 1                 # caught, logged, returns 1 (systemd Restart)

def test_main_returns_one_on_config_load_failure(monkeypatch):
    monkeypatch.setattr(daemon, "VoiceTypingConfig",
                        type("C", (), {"load": classmethod(lambda cls: (_ for _ in ()).throw(RuntimeError("bad toml")))}))
    monkeypatch.setattr(logging, "basicConfig", lambda **kw: None)
    assert daemon.main() == 1


# --- Layer F: the __main__ guard (AST — hermetic, no subprocess) --------------------------

def test_main_guard_present_and_calls_main():
    tree = ast.parse(Path("voice_typing/daemon.py").read_text())
    guard = None
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            t = node.test
            if (isinstance(t.left, ast.Name) and t.left.id == "__name__"
                    and any(isinstance(o, ast.Eq) for o in t.ops)
                    and any(isinstance(c, ast.Constant) and c.value == "__main__" for c in t.comparators)):
                guard = node
                break
    assert guard is not None, "no `if __name__ == '__main__':` guard at module level"
    # body references main (either `main()` or `sys.exit(main())`).
    names = set()
    for stmt in guard.body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            if isinstance(call.func, ast.Name):           names.add(call.func.id)            # main()
            elif isinstance(call.func, ast.Attribute):    names.add(call.func.attr)          # sys.exit(...)
            for arg in call.args:
                if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name):
                    names.add(arg.func.id)                                               # exit(main())
    assert "main" in names, "guard body does not call main()"

def test_main_is_callable():
    assert callable(daemon.main)
```

### Integration Points

```yaml
ENTRY POINT (this task):
  - main() is the lifecycle orchestrator (pinned verbatim above). `python -m voice_typing.daemon`
    (systemd ExecStart / launch_daemon.sh) runs it via the guard; `voice-typing-daemon` console
    script (pyproject entry voice_typing.daemon:main) calls it directly. Both reach main().

CONSUMED (built by prior subtasks — do NOT rebuild):
  - VoiceTypingConfig.load()                       (P1.M2.T1.S1)
  - Feedback(cfg.feedback)                         (P1.M3.T2.S1)  [lazy import in main()]
  - VoiceTypingDaemon(cfg, feedback) + .run()      (P1.M4.T1.S2)
  - ControlServer(d, on_quit=) + .start()/.stop()  (P1.M4.T2.S1)
  - VoiceTypingDaemon.shutdown()                   (P1.M4.T2.S2)  [on_quit + finally]
  - install_shutdown_signal_handlers(d) -> restore (P1.M4.T2.S2)

SYSTEMD (P1.M6.T1.S2 — NOT this task):
  - ExecStart=.venv/bin/python -m voice_typing.daemon (sets __name__=="__main__" -> guard -> main()).
    Restart=on-failure relies on main()'s non-zero exit (fatal) + the SIGTERM handler (clean stop).
    LD_LIBRARY_PATH is set by launch_daemon.sh OR Environment= in the unit — NOT in main().

CONFIG:
  - none new. main() reads cfg.log.level (existing LogConfig.level). Do NOT edit config.py/toml.

CONSOLE SCRIPT:
  - voice-typing-daemon = "voice_typing.daemon:main" is ALREADY in pyproject.toml (P1.M1.T1.S1).
    T3.S1 does NOT edit pyproject. Once main() exists, the entry resolves (a `uv sync` re-validates).
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
# Per-file syntax check after the edit:
.venv/bin/python -m py_compile voice_typing/daemon.py tests/test_daemon.py

# Import purity (the hard gate): importing daemon must NOT pull RealtimeSTT/torch/ctranslate2,
# AND main/_setup_logging/_resolve_log_level must exist + main be callable.
.venv/bin/python -c "
import sys; import voice_typing.daemon
bad=[m for m in('RealtimeSTT','torch','ctranslate2') if m in sys.modules]
assert not bad, f'import purity broken: {bad}'
from voice_typing.daemon import main, _setup_logging, _resolve_log_level
assert callable(main) and callable(_setup_logging) and callable(_resolve_log_level)
import logging
assert _resolve_log_level('INFO')==logging.INFO and _resolve_log_level('DEBUG')==logging.DEBUG
assert _resolve_log_level('garbage')==logging.INFO
print('imports + symbols + purity + level-resolve OK')
"

# Optional lint (ruff optional at /home/dustin/.local/bin/ruff; mypy NOT installed):
/home/dustin/.local/bin/ruff check voice_typing/daemon.py tests/test_daemon.py 2>/dev/null || true
# Expected: zero errors. Fix anything reported before proceeding.
```

### Level 2: Unit Tests (Component Validation)

```bash
cd /home/dustin/projects/voice-typing
# The new main/logging/guard section:
.venv/bin/python -m pytest tests/test_daemon.py -v -k "resolve_log_level or setup_logging or main_ or guard"
# Expected: all green (~10 tests: level-resolve x2 + setup_logging x2 + main lifecycle x4 + fatal x2 + guard x2).

# Full suite (regression — S1/S2/S3/S1-of-T2/T2.S2 unchanged):
.venv/bin/python -m pytest tests/ -q
# Expected: ~182+ passed (173 + ~9 T2.S2 + ~10 new), 0 failed.
```

### Level 3: Integration Testing (the lifecycle, with fakes — no CUDA)

```bash
cd /home/dustin/projects/voice-typing
# Simulate the full main() lifecycle with fakes: quit-path (on_quit) + finally both reach
# shutdown() exactly once; srv.start/stop + restore each called once; returns 0.
.venv/bin/python - <<'PY'
import logging
from voice_typing import daemon
from voice_typing.config import VoiceTypingConfig

class FakeFB:
    def __init__(self, cfg): self.cfg = cfg
class FakeDaemon:
    def __init__(self, cfg, fb, **k):
        self.cfg, self.fb = cfg, fb; self.run_called=False; self.shuts=0
    def run(self): self.run_called=True
    def shutdown(self): self.shuts+=1
class FakeServer:
    def __init__(self, d, *, on_quit=None, **k):
        self.d=d; self.on_quit=on_quit; self.starts=self.stops=0
    def start(self): self.starts+=1
    def stop(self): self.stops+=1

orig = (daemon.VoiceTypingConfig, daemon.VoiceTypingDaemon, daemon.ControlServer,
        daemon.install_shutdown_signal_handlers)
import voice_typing.feedback as fbmod; origfb = fbmod.Feedback
bag={}
class D(FakeDaemon):
    def __init__(self,*a,**k): super().__init__(*a,**k); bag['d']=self
class S(FakeServer):
    def __init__(self,*a,**k): super().__init__(*a,**k); bag['s']=self
daemon.VoiceTypingConfig = type('C',(),{'load':classmethod(lambda cls: VoiceTypingConfig())})
daemon.VoiceTypingDaemon = D
daemon.ControlServer = S
restored={'c':0}
def _inst(d,*,signals=None):
    def _r(): restored['c']+=1
    return _r
daemon.install_shutdown_signal_handlers = _inst
fbmod.Feedback = FakeFB
logging.basicConfig = lambda **kw: None

try:
    code = daemon.main()
    assert code==0, code
    assert bag['d'].run_called and bag['s'].starts==1 and bag['s'].stops==1
    assert bag['d'].shuts==1, bag['d'].shuts              # finally called shutdown once
    assert bag['s'].on_quit == bag['d'].shutdown          # on_quit wiring
    assert restored['c']==1                                # restore called
    # quit-path simulation: on_quit fires (voicectl quit) THEN finally -> idempotent (1 real, 2nd no-op
    # in the real shutdown(); here the fake counts both, so emulate the idempotent contract: call on_quit
    # then check the real daemon.shutdown() would no-op — covered by the T2.S2 shutdown() tests.)
    print("OK: lifecycle + on_quit wiring + teardown order; main()=0")
finally:
    (daemon.VoiceTypingConfig, daemon.VoiceTypingDaemon, daemon.ControlServer,
     daemon.install_shutdown_signal_handlers) = orig
    fbmod.Feedback = origfb
PY
# Expected: OK: lifecycle + on_quit wiring + teardown order; main()=0
```

### Level 4: Creative & Domain-Specific Validation (the guard + console script)

```bash
cd /home/dustin/projects/voice-typing
# (a) The module, imported as a normal module, must NOT run main() (no top-level side effects —
#     the spawn-guard invariant). Assert importing does nothing heavy:
.venv/bin/python -c "
import sys
before = set(sys.modules)
import voice_typing.daemon       # must NOT call main() / build a recorder
assert not [m for m in ('RealtimeSTT','torch','ctranslate2') if m in sys.modules], 'heavy import at module top!'
print('module import has no side effects (spawn-safe)')
"

# (b) The console-script entry resolves to main (no AttributeError):
.venv/bin/python -c "
from voice_typing.daemon import main
assert callable(main)
print('voice-typing-daemon entry (voice_typing.daemon:main) resolves; callable')
"

# (c) OPTIONAL end-to-end smoke (needs the launch_daemon.sh env / a mic or feed_audio; full E2E is
#     P1.M7.T3.S1, NOT a T3.S1 gate). If run, the daemon should START, log to stderr, and exit cleanly
#     on SIGTERM. Skipped here unless the operator wants a manual smoke:
#   voice_typing/launch_daemon.sh &  PID=$!; sleep 5; kill -TERM $PID; wait $PID; echo "exit=$?"
# Expected: module import is side-effect-free; the console entry resolves. (No CUDA needed for L4 a/b.)
```

## Final Validation Checklist

### Technical Validation

- [ ] All 4 validation levels completed successfully.
- [ ] `.venv/bin/python -m pytest tests/ -q` green (~182+ passed; S1/S2/S3/S1-of-T2/T2.S2 bodies UNCHANGED).
- [ ] `.venv/bin/python -m py_compile voice_typing/daemon.py tests/test_daemon.py` clean.
- [ ] Import purity: `RealtimeSTT`/`torch`/`ctranslate2` NOT in `sys.modules` after `import
      voice_typing.daemon`; module import has NO side effects (spawn-safe).
- [ ] `main`/`_setup_logging`/`_resolve_log_level` are module attributes; `main` callable; the
      `if __name__ == "__main__":` guard present (AST).
- [ ] `ruff check` (optional) reports zero errors on the changed files.

### Feature Validation

- [ ] All success criteria from "What" met (a–i).
- [ ] `main()` runs the full lifecycle (load → logging → Feedback → Daemon → ControlServer(on_quit=
      shutdown) → install_signals → start → run → finally restore/shutdown/stop) and returns 0.
- [ ] `_setup_logging` calls `basicConfig(stream=sys.stderr, level=_resolve_log_level(cfg.log.level),
      format=…)` (idempotent); `_resolve_log_level` maps INFO/DEBUG/invalid as specified.
- [ ] Fatal path (load / construct / run) → `main()` returns 1 (systemd Restart); clean → 0.
- [ ] Level 3 (lifecycle + on_quit wiring + teardown order) and Level 4 (side-effect-free import +
      console entry resolves) pass.
- [ ] The T2.S2 dependency was present at preflight (shutdown + install_shutdown_signal_handlers).

### Code Quality Validation

- [ ] Follows existing codebase patterns (module-level fns at module end; `logger =
      logging.getLogger(__name__)`; defensive try/except log-not-raise; additive-only edits; AST +
      monkeypatch tests; `sys.exit(main())` guard matching cuda_check.py's house form).
- [ ] File placement matches the desired tree (no new module; main + helpers + guard at module END
      of daemon.py; tests appended to test_daemon.py).
- [ ] Anti-patterns avoided (no heavy top-level code; no LD_LIBRARY_PATH in-process; no pyproject
      edit; no arming the mic in main(); no manual addHandler; no srv.stop() from on_quit; no return
      from finally; no scope creep into ctl.py/systemd/install.sh).
- [ ] No new dependencies (stdlib `sys` only); pyproject.toml/uv.lock/config.* untouched.

### Documentation & Deployment

- [ ] Code is self-documenting (docstrings on main/_setup_logging/_resolve_log_level explaining the
      WHY: the logging-gap closure, the spawn-guard invariant, the teardown order + idempotency, the
      exit-code→systemd contract).
- [ ] No new env vars or config.
- [ ] Logs are informative (startup INFO with pid; fatal errors at EXCEPTION level; teardown-step
      failures logged but swallowed).

---

## Anti-Patterns to Avoid

- ❌ Don't put ANY heavy work (config load, Feedback build, recorder construction, signal install,
  run) at module top level — RealtimeSTT's spawn-started multiprocessing children re-import `__main__`
  and would re-run it (recursive spawning). Everything heavy lives INSIDE `main()`. The only module-top
  addition is `import sys`.
- ❌ Don't use a bare `if __name__ == "__main__": main()` — use `sys.exit(main())` so the exit code
  reaches systemd `Restart=on-failure` (matches cuda_check.py's house pattern).
- ❌ Don't add a manual `root.addHandler(StreamHandler(sys.stderr))` — use `logging.basicConfig`
  (idempotent; a no-op under pytest caplog → non-intrusive). A manual addHandler would double-handle.
- ❌ Don't hardcode `level=logging.INFO` in `_setup_logging` — derive it from `cfg.log.level` (via
  `_resolve_log_level`) so "DEBUG via config" (PRD §4.2) actually shows debug records.
- ❌ Don't trust `logging.getLevelName(name)` to raise on a bad name — it returns the string
  `"Level <name>"`; guard with `isinstance(level, int)`.
- ❌ Don't call `ControlServer.stop()` from `on_quit` — it joins the accept thread on which `on_quit`
  runs → self-join-deadlock. `srv.stop()` runs ONLY in `main()`'s `finally` (main thread).
- ❌ Don't `return` from `finally` (it would override the `except`'s return value); don't leave the
  finally un-guarded against `None` (a partial build leaves refs `None`).
- ❌ Don't set `LD_LIBRARY_PATH` in-process — the dynamic linker reads it only at exec (ld.so(8));
  launch_daemon.sh (P1.M1.T2.S1) owns it. (Item contract.)
- ❌ Don't edit `pyproject.toml` — the `voice-typing-daemon = "voice_typing.daemon:main"` entry is
  ALREADY declared (the item's `voice_typing.ctl:main` is a typo; ctl.py is the OTHER binary,
  P1.M5.T1.S1). Just implement `main()`.
- ❌ Don't arm the mic in `main()` (`d.start()`/`d.toggle()`) — the daemon must start NOT-LISTENING
  (PRD §4.9; `run()` clears the gate automatically).
- ❌ Don't build `ctl.py` / `systemd/voice-typing.service` / `install.sh` — those are P1.M5.T1.S1 /
  P1.M6.T1.S2 / P1.M6.T1.S1. Don't add a 2nd `main()` anywhere.
- ❌ Don't let `main()` raise — catch all fatal paths, log at EXCEPTION level, `return 1`.

---

## Confidence Score

**9/10** — one-pass implementation success is highly likely. The complete, verified `main()` +
`_setup_logging` + `_resolve_log_level` + guard source is pinned above (validated against the LIVE
`voice_typing/daemon.py` post-S1/S2/S3/S1-of-T2 state, the consumed signatures in `config.py`/
`feedback.py`, the established `cuda_check.py` guard pattern, and the exact P1.M4.T2.S2 teardown
contract quoted in its PRP "Integration Points"). The two highest-risk details are fully grounded:
(1) the **logging gap** — verified by reading `_configure_log_level()`'s own docstring ("NOT
basicConfig … P1.M4.T3.S1's job") + Python logging level/handler semantics (research §2); (2) the
**`__main__` guard** — verified by RealtimeSTT's spawn-based multiprocessing (T2.S2 research citing
`core/initialization.py`) + the Python docs "Safe importing of main module". The single hard
dependency is T2.S2 (`shutdown()` + `install_shutdown_signal_handlers()`) — made a preflight GATE
(Task 0 asserts both present; STOP if not). Residual risks: (a) T2.S2 merge timing — mitigated by
the gate + the stable `import sys` anchor (unaffected by T2.S2's `import signal`); (b) the
`basicConfig`-under-pytest no-op — mitigated by the hermetic monkeypatch-`basicConfig` test
approach (asserts kwargs, not root mutation). The validation gates (py_compile, import-purity +
side-effect-free import, the AST guard test, pytest, the Level 3 lifecycle script asserting
order/on_quit-wiring/teardown, the Level 4 console-entry resolution) are executable as written.
