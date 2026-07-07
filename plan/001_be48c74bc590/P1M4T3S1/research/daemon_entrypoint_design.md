# P1.M4.T3.S1 — `main()` entry point design (verified against LIVE source)

This note records every fact the PRP relies on, each verified by reading the actual files in
`/home/dustin/projects/voice-typing` at planning time (2026-07-06). It is the authoritative spec
for the PRP.

## 0. Scope + boundary (what T3.S1 is, and is NOT)

T3.S1 is the **process entry point** — the `main()` function + the `if __name__ == "__main__":`
guard + the logging handler setup. It is the LAST piece of `voice_typing/daemon.py`; it wires
together the components built by every prior subtask:

| Built by            | Symbol T3.S1 consumes                                          |
|---------------------|----------------------------------------------------------------|
| P1.M2.T1.S1         | `voice_typing.config.VoiceTypingConfig.load(path=None)` + `cfg.log.level` (`LogConfig.level`, default `"INFO"`) |
| P1.M3.T2.S1         | `voice_typing.feedback.Feedback(cfg: FeedbackConfig)` constructor |
| P1.M4.T1.S2         | `VoiceTypingDaemon(cfg, feedback, *, recorder=None, backend=None, latency=None)` + `.run()` (BLOCKS until shutdown) |
| P1.M4.T2.S1 (merged)| `ControlServer(daemon, *, socket_path=None, on_quit=None, accept_timeout=0.3)` + `.start()`/`.stop()` |
| P1.M4.T2.S2 (in flight, treat as contract) | `VoiceTypingDaemon.shutdown()` (idempotent, defensive `recorder.shutdown()`) + module fn `install_shutdown_signal_handlers(daemon, *, signals=None) -> restore()` |

T3.S1 does NOT: build `ctl.py` (P1.M5.T1.S1), build `systemd/voice-typing.service` (P1.M6.T1.S2),
build `install.sh` (P1.M6.T1.S1), touch `config.py`/`config.toml`/`pyproject.toml`/`uv.lock`,
or set `LD_LIBRARY_PATH` in-process (the item contract forbids it — see §7).

## 1. The authoritative `main()` body (from P1.M4.T2.S2 PRP "Integration Points")

The T2.S2 PRP (in flight) pins the EXACT teardown contract T3.S1 must implement in its
"Integration Points" section. This is the authoritative sequence — T3.S1 prepends config-load +
logging-setup and wraps it in error handling, but the core orchestration is fixed:

```python
cfg = VoiceTypingConfig.load()
_setup_logging(cfg.log.level)
fb = Feedback(cfg.feedback)
d = VoiceTypingDaemon(cfg, fb)
srv = ControlServer(d, on_quit=d.shutdown)      # quit -> request_shutdown() then recorder.shutdown()
srv.start()
restore = install_shutdown_signal_handlers(d)   # SIGTERM/SIGINT -> spawn-thread -> request_shutdown
try:
    d.run()                                     # blocks until shutdown requested (quit or signal)
finally:
    restore()                                   # reinstall prior signal handlers
    d.shutdown()                                # idempotent: no-op if on_quit already did it (signal path)
    srv.stop()                                  # close socket + unlink — MUST be main thread (joins accept thread)
return 0
```

**Teardown ordering (why this exact order):**
- `restore()` FIRST — stop diverting signals so a late signal during teardown uses Python defaults
  (we are exiting anyway).
- `d.shutdown()` — `recorder.shutdown()` joins+terminates the spawn-started `transcript_process`/
  `reader_process` (releases GPU VRAM + the mic). Idempotent (T2.S2 `_shutdown_done` + RealtimeSTT
  `is_shut_down`), so the on_quit path and the finally path can BOTH fire — first wins.
- `srv.stop()` LAST and on the MAIN thread — it `join(timeout=2.0)`s the accept thread. `on_quit`
  runs ON a worker of that thread → calling `srv.stop()` from `on_quit` would self-join-deadlock
  (T2.S2 Critical #5). So `srv.stop()` runs only in `main()`'s finally.

## 2. The logging-setup gap T3.S1 closes (the central technical detail)

**Verified fact:** `VoiceTypingDaemon.run()` already calls `self._configure_log_level()` (live
`voice_typing/daemon.py`), whose docstring states:

> Namespace-scoped only — NOT basicConfig (handler/root config is P1.M4.T3.S1's job).

`_configure_log_level()` does ONLY:
```python
logging.getLogger("voice_typing").setLevel(level_name.upper())   # invalid -> caught, default left
```
It sets the **namespace logger level** but adds **NO handler**. Therefore, with no handler on the
`voice_typing` logger and none on root, `logger.info(...)` records pass the logger gate but have
nowhere to emit → **silent**. T3.S1 MUST install the stderr handler (the gap).

**Python logging semantics that govern the design:**
- A record is emitted only if it passes BOTH (a) the originating logger's effective level AND
  (b) at least one handler's level on the logger or an ancestor it propagates to.
- `_configure_log_level()` sets the `voice_typing` logger level (a). For (b), a handler must exist.
- If main() sets the ROOT logger level to INFO but the `voice_typing` logger is DEBUG, DEBUG records
  pass the namespace gate, propagate to root's handler, but the root handler (INFO) drops them. So
  **the handler/root level must ALSO come from `cfg.log.level`** for "DEBUG via config" to actually
  show debug records (PRD §4.2).

**Chosen approach — `logging.basicConfig`:**
```python
logging.basicConfig(
    stream=sys.stderr,            # journald captures stderr under systemd (PRD §4.2)
    level=_resolve_log_level(cfg.log.level),   # INFO default; DEBUG via config
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
```
- `basicConfig` is **idempotent**: it is a no-op if the root logger already has handlers. In a fresh
  process (systemd, console script, `python -m`) root has no handlers → it configures stderr. Under
  **pytest caplog**, root already has caplog's handler → basicConfig no-op → tests keep using caplog
  (the desired, non-intrusive behavior).
- `stream=sys.stderr` matches PRD §4.2 "logging to stderr (journald picks it up under systemd)".
- The level is derived from `cfg.log.level` (the SAME field `_configure_log_level` reads), so root
  handler + namespace logger agree.

**`_resolve_log_level` helper (defensive, mirrors `_configure_log_level`):**
```python
def _resolve_log_level(level_name) -> int:
    if not isinstance(level_name, str):
        return logging.INFO
    level = logging.getLevelName(level_name.strip().upper())   # "INFO"->20; "VERBOSE"->"Level VERBOSE"
    return level if isinstance(level, int) else logging.INFO
```
`logging.getLevelName(name)` returns an int for valid names but returns the **string** `"Level X"`
for unknown names (it does NOT raise) — so the `isinstance(level, int)` guard is required.

## 3. The `if __name__ == "__main__":` guard — WHY it is mandatory (RealtimeSTT multiprocessing)

**Item contract + PRD:** "README mandates `if __name__ == "__main__":` because RealtimeSTT uses
multiprocessing for model work." Verified against the installed RealtimeSTT 1.0.2 source (cited in
the T2.S2 research `shutdown_signals_design.md`): `transcript_process` + `reader_process` are
`mp.Process` started with `mp.set_start_method("spawn")` (`.venv/lib/python3.12/site-packages/
RealtimeSTT/core/initialization.py`).

**The mechanism (Python multiprocessing spawn):**
- With the `spawn` start method, the child is a fresh Python interpreter that **re-imports the
  parent's `__main__` module** to rebuild state before running the target.
- If the `__main__` module has **top-level** side effects (constructing the daemon/recorder,
  starting threads/processes), the child re-runs them → recursive process spawning / import storms.
- The `if __name__ == "__main__":` guard ensures the heavy work runs ONLY in the real parent (where
  `__name__ == "__main__"`), never in the spawn child (where the module is imported under its
  qualified name, so `__name__ != "__main__"`).
- **THEREFORE every heavy step (config load, Feedback build, VoiceTypingDaemon build, recorder
  construction, signal install, run) MUST live INSIDE `main()`, NOT at module top level.** daemon.py
  today has zero top-level side effects (verified: module top is only imports + constants + pure
  function/class defs) — T3.S1 must keep it that way.

**Both invocation paths work and both invoke `main()`:**
1. `.venv/bin/python -m voice_typing.daemon` (systemd ExecStart, launch_daemon.sh) → the module runs
   as `__main__` → the guard calls `main()`. Python 3 sets `__spec__` on `-m` runs so spawn children
   re-import via the qualified name `voice_typing.daemon` (not as `__main__`) → guard protects them.
2. `voice-typing-daemon` console script (entry `voice_typing.daemon:main`) → the hatchling-generated
   wrapper imports `voice_typing.daemon` (so `__name__ == "voice_typing.daemon"`) and calls
   `main()` directly. The guard is irrelevant for THIS path (main is called explicitly), but main()
   being the single heavy-work entry still keeps spawn children clean.

**Guard form:** use `if __name__ == "__main__": sys.exit(main())` (NOT a bare `main()`).
- `sys.exit(main())` propagates main()'s return code → systemd `Restart=on-failure` sees non-zero
  on a fatal error and restarts the unit (PRD §4.9). A bare `main()` would discard the code.
- This matches the established house pattern: `voice_typing/cuda_check.py` ends with
  `if __name__ == "__main__": sys.exit(_main())`.
- The item's literal wording (`...: main()`) is shorthand for "the guard calls main"; the exit-code
  propagation is the correct, systemd-compatible reading.

## 4. The console-script entry — ALREADY declared (item has a typo)

**Verified (live `pyproject.toml`):**
```toml
[project.scripts]
voicectl = "voice_typing.ctl:main"
voice-typing-daemon = "voice_typing.daemon:main"
```
The `voice-typing-daemon` entry is ALREADY declared as `voice_typing.daemon:main` (by P1.M1.T1.S1).
The item description's `voice_typing.ctl:main` is a **typo** — the real target is
`voice_typing.daemon:main` (ctl.py is voicectl, P1.M5.T1.S1, a different binary).

**Implication:** T3.S1 does NOT modify `pyproject.toml`. It only IMPLEMENTS `main()` so the existing
entry resolves at runtime. (The hatchling wrapper is generated at install time as a string reference;
once `main()` exists the already-installed `voice-typing-daemon` script works. A `uv sync` is the
safe re-validation but is not strictly required.)

## 5. The "start NOT-LISTENING" requirement — already satisfied by `run()`

PRD §4.9: "The daemon starts in not-listening state — it must never hot-mic on boot." Verified in
live `voice_typing/daemon.py`: `VoiceTypingDaemon.__init__` sets `self._listening =
threading.Event()` (cleared by default), and `run()` calls `self._feedback.set_listening(False)` +
logs "voice-typing daemon ready (not listening)". So as long as T3.S1 calls `d.run()` (it does,
§1), the not-listening-on-boot guarantee holds automatically. T3.S1 does NOT need to add anything
for this — it must merely NOT arm the mic in main() (don't call `d.start()`/`d.toggle()`).

## 6. Import-block placement — `import sys` is the only new module-top import

**Live `voice_typing/daemon.py` module-top block (post S1-of-T2 merge; T2.S2 will add `signal`):**
```python
import collections
import inspect
import json
import logging
import os
import select
import socket          # <- after T2.S2 merges, `import signal` sits between `select` and `socket`
import threading
import time
from typing import TYPE_CHECKING, Any, Callable
```
T3.S1 needs `sys` (for `sys.stderr` in `_setup_logging` + `sys.exit` in the guard). Alphabetically
`sys` belongs **between `socket` and `threading`** (s-o-c < s-y-s < t-h-r). So:
```python
import socket
import sys
import threading
```
- Pure addition; preserves import purity (`sys` is stdlib-cheap; RealtimeSTT/torch/ctranslate2 stay
  lazily imported inside `build_recorder`).
- If `signal` (T2.S2) has merged, the block already contains it; place `sys` by alphabetical
  position among the live `import X` lines. Do NOT reorder existing imports.

## 7. `LD_LIBRARY_PATH` — T3.S1 MUST NOT touch it (item contract)

**Item:** "the LD_LIBRARY_PATH must already be set by launch_daemon.sh (P1.M1.T2.S1) before this
process starts — do NOT try to set it in-process."

**Verified why** (live `voice_typing/launch_daemon.sh` + `voice_typing/cuda_check.py` docstring):
the dynamic linker reads `LD_LIBRARY_PATH` **only at process exec** (ld.so(8)); mutating
`os.environ["LD_LIBRARY_PATH"]` inside the running Python process has NO effect on libraries
already loaded / about to be loaded by ctranslate2. `launch_daemon.sh` is the single sanctioned
place (it computes the cuBLAS+cuDNN lib dirs from the live wheels and exports them, then
`exec python -m voice_typing.daemon`). T3.S1 must NOT set it. (systemd wiring of
LD_LIBRARY_PATH/launch_daemon.sh as ExecStart is P1.M6.T1.S2's concern, not T3.S1's.)

## 8. Feedback constructor — exact signature (verified)

**Live `voice_typing/feedback.py`:**
```python
class Feedback:
    def __init__(self, cfg: FeedbackConfig) -> None: ...
```
So main() does `Feedback(cfg.feedback)` (NOT `Feedback(cfg)`, NOT the resolved state file —
`Feedback._write()` calls `cfg.resolved_state_file()` lazily at write time). This matches the
T2.S2 PRP Level-3 integration example `fb = Feedback(cfg.feedback)`.

**Import strategy for testability:** main() does the Feedback import LAZILY inside main():
`from voice_typing.feedback import Feedback`. This (a) keeps the module-top import block change to
just `import sys` (no churn to the TYPE_CHECKING block S1/S2/S3/T2.S2 reference), and (b) is still
monkeypatchable: tests do `monkeypatch.setattr("voice_typing.feedback.Feedback", FakeFeedback)` and
the in-main `from voice_typing.feedback import Feedback` resolves the fake at call time.

## 9. Test strategy (all gates executable WITHOUT CUDA/torch/mic)

main() builds a real recorder (heavy) → unit tests must NOT call main() unmodified. The components
are all module-level names → **monkeypatch** them to fakes, then call `main()`, asserting the
orchestration order + teardown. Concretely (tests APPENDED to `tests/test_daemon.py`, reusing its
`_make_daemon`/`_StubRecorder`/`_wait_for` helpers where useful):

- **Logging helper `_resolve_log_level` / `_setup_logging`:** "INFO"→20, "DEBUG"→10,
  "info" (lowercase)→20, invalid/"VERBOSE"→INFO fallback, non-str→INFO; `_setup_logging("DEBUG")`
  leaves root with a stderr handler at level DEBUG (assert handler.stream is sys.stderr + level);
  idempotent (basicConfig no-op → calling twice does not add a 2nd handler).
- **Orchestration (monkeypatch):** replace `daemon.VoiceTypingConfig.load` (returns a real
  `VoiceTypingConfig()`), `voice_typing.feedback.Feedback`, `daemon.VoiceTypingDaemon`,
  `daemon.ControlServer`, `daemon.install_shutdown_signal_handlers` with fakes that RECORD calls;
  the fake daemon's `run()` sets a flag and returns immediately (no block); assert: load→Feedback
  built with cfg.feedback→Daemon built with (cfg, feedback)→ControlServer built with
  (daemon, on_quit=daemon.shutdown)→install_shutdown_signal_handlers(daemon)→srv.start()→d.run();
  in the finally: restore() called, d.shutdown() called, srv.stop() called; main() returns 0.
- **on_quit wiring:** assert the ControlServer received `on_quit is daemon.shutdown` (the SAME
  bound method) — this is the quit→recorder.shutdown() link from T2.S2.
- **Fatal path:** make the fake VoiceTypingDaemon raise in __init__ → main() returns 1; the finally
  does NOT call srv.stop()/d.shutdown() (they're None — assert no AttributeError); config-load
  failure → main() returns 1 (logging falls back to a stderr handler at INFO so the traceback logs).
- **Guard presence (AST, hermetic):** parse `voice_typing/daemon.py` with `ast` and assert an
  `if __name__ == "__main__":` module-level guard exists whose body calls `main` (no subprocess,
  no CUDA). Plus `assert callable(daemon.main)`.

**DO NOT** in tests: import RealtimeSTT/torch; call the real `main()` unmodified; depend on
`XDG_RUNTIME_DIR`; send real SIGTERM/SIGINT; sleep gratuitously (use `_wait_for`).

## 10. Validation commands (verified tooling)

- `.venv/bin/python -m py_compile voice_typing/daemon.py tests/test_daemon.py`
- Import purity: `import voice_typing.daemon` must NOT pull RealtimeSTT/torch/ctranslate2.
- `.venv/bin/python -m pytest tests/ -q` → expect **~182+ passed** (173 baseline + ~9 from T2.S2
  when it merges + ~8-10 new T3.S1 tests). NEVER bare `python`/`pytest` (zsh aliases).
- Console-script smoke (optional, needs the env): `voice-typing-daemon` should attempt to start and
  exit cleanly on SIGTERM (full E2E is P1.M7.T3.S1, not T3.S1's gate).

## 11. Risks + mitigations

- **R1 — T2.S2 not yet merged when T3.S1 runs.** Mitigation: preflight asserts
  `hasattr(daemon.VoiceTypingDaemon,'shutdown')` and `hasattr(daemon,'install_shutdown_signal_
  handlers')`; if missing, T2.S2 hasn't merged — STOP (T3.S1 depends on them). The PRP marks this
  as a hard preflight gate.
- **R2 — basicConfig no-op under pytest caplog.** Mitigation: this is the DESIRED behavior (tests
  use caplog); the `_setup_logging` unit test checks the root handler/level in a FRESH process
  context (or asserts basicConfig was called with the right args via monkeypatching
  `logging.basicConfig`).
- **R3 — forgetting `sys.exit` so systemd can't see the exit code.** Mitigation: pin
  `if __name__ == "__main__": sys.exit(main())` verbatim; the AST test asserts the guard calls
  main.
- **R4 — construction failure after build_recorder orphans a recorder.** Mitigation: extremely
  unlikely (post-build_recorder, __init__ only does `make_backend`, cheap); noted as a known
  limitation, not a gate. main() guards the finally against None references.
