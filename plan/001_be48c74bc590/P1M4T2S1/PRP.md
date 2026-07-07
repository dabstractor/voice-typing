# PRP — P1.M4.T2.S1: Control socket server (toggle/start/stop/status/quit JSON protocol)

## Goal

**Feature Goal**: Add a **`ControlServer`** to `voice_typing/daemon.py` — a background
`threading.Thread` that accepts connections on an **AF_UNIX SOCK_STREAM** socket at
`$XDG_RUNTIME_DIR/voice-typing/control.sock`, speaks a **one-JSON-object-per-line** request/
response protocol, and dispatches `toggle`/`start`/`stop`/`status`/`quit` to the running
`VoiceTypingDaemon` (P1.M4.T1.S2). This is the `voicectl`↔daemon wire surface (PRD §4.2(3),
§4.8, §4 architecture). Robust to malformed JSON, stale socket files, and clean shutdown.

**Deliverable** (4 files — 2 MODIFY source, 2 ADD tests; **NO new module file**):
1. `voice_typing/daemon.py` — ADD `import json`/`os`/`select`/`socket`; ADD module-level
   `_default_control_socket_path()`; ADD `VoiceTypingDaemon.status_snapshot()` +
   `_resolved_device()` (two new methods, **no existing-method edit**); ADD the
   `ControlServer` class (`start`/`stop`/`_accept_loop`/`_handle`/`_dispatch`). **Do NOT
   touch** `__init__`/`run`/`on_final`/`_arm`/`_disarm`/`start`/`stop`/`toggle`/
   `request_shutdown`/`_build_callbacks`/`_construct`/`build_recorder` (P1.M4.T1.S1/S2/S3 own
   those; edits are 100% additive → zero merge conflict).
2. `voice_typing/feedback.py` — ADD `Feedback.snapshot() -> dict` (one public read of the live
   in-memory state; additive; existing tests unchanged).
3. `tests/test_control_socket.py` — **NEW** — dispatch logic + real-socket round-trip +
   lifecycle/hardening (stale `.sock`, dir 0700/file 0600, idempotent start, clean stop).
4. `tests/test_daemon.py` — **APPEND** `status_snapshot`/`_resolved_device` unit tests
   (reuse the S2 `_make_daemon()` helper; do NOT edit S1/S2/(future S3) test bodies).

**Success Definition**:
- (a) `voice_typing/daemon.py` + `voice_typing/feedback.py` + the two test files
  `py_compile`-clean; `import voice_typing.daemon` stays import-pure (NO
  `RealtimeSTT`/`torch`/`ctranslate2` imported at module top — only stdlib `json`/`os`/`select`/
  `socket` added); `ControlServer` and `VoiceTypingDaemon.status_snapshot` are module attributes.
- (b) `ControlServer(daemon, socket_path=...)` exposes `start()`/`stop()`. `start()`: creates
  the parent dir **0700**, unlinks a stale `.sock` (tolerates `FileNotFoundError`), binds, sets
  the socket file mode **0600**, `listen(8)`, then launches a daemon `threading.Thread`.
  `stop()`: sets a stop `Event`, closes the listening socket, `join(timeout=2.0)` — the accept
  thread exits within ~1 s (verified, see research §6).
- (c) Protocol (EXACT): `{"cmd":"toggle"}`/`start`/`stop`/`status` → `{"ok":true,
  **status_snapshot()}` (uniform payload; PRD §4.2 minimal shapes are a SUBSET); `{"cmd":"quit"}`
  → `{"ok":true,"shutting_down":true}` + `daemon.request_shutdown()`; malformed JSON →
  `{"ok":false,"error":"malformed JSON: ..."}`; non-dict JSON → `{"ok":false,"error":"request
  must be a JSON object"}`; unknown/missing cmd → `{"ok":false,"error":"unknown command: ..."}`.
- (d) `status_snapshot()` returns `{listening, partial, last_final, uptime_s, device,
  compute_type, final_model, realtime_model}` — `listening` from `is_listening()`, `partial`/
  `last_final` from `feedback.snapshot()` (live in-memory, NOT throttled disk), `uptime_s` from
  `uptime_s` (rounded 0.001), device/models from `_resolve_device_config(cfg)` **cached once**.
- (e) `Feedback.snapshot()` returns a shallow copy of `self._state`
  (`{listening,phase,partial,last_final,ts}`); existing `test_feedback.py` assertions unchanged.
- (f) `_default_control_socket_path()` = `$XDG_RUNTIME_DIR/voice-typing/control.sock`; raises
  `RuntimeError` if `XDG_RUNTIME_DIR` unset (mirrors `FeedbackConfig.resolved_state_file()`).
- (g) **Backward compat**: the existing 134 (S1+S2) tests pass UNCHANGED; ~25 new tests pass;
  `.venv/bin/python -m pytest tests/ -q` green (~159+ passed). Coexists with the in-flight
  P1.M4.T1.S3 latency-logging edits (S1 touches NO symbol S3 edits — research §1/§5).
- (h) **No out-of-scope code:** NO `main()`/`if __name__ == "__main__":` (P1.M4.T3.S1), NO
  `recorder.shutdown()` (P1.M4.T2.S2), NO `logging.basicConfig`/signal handlers, NO auto-wiring
  of `ControlServer` into `run()`/`__init__` (T3 constructs it in `main()`), NO `ctl.py`
  (P1.M5.T1.S1), NO edits to `config.py`/`config.toml`/`pyproject.toml`/`uv.lock`/`PRD.md`/
  `tasks.json`/`.gitignore`/`cuda_check.py`/`textproc.py`/`typing_backends.py`.

## User Persona

**Target User**: Internal — three future consumers read this surface:
1. **P1.M5.T1.S1 (`voicectl` / `ctl.py`)** — connects to the socket, sends one JSON line,
   prints a human-readable result (`listening: on`), exit 0/1; `status` pretty-prints partial +
   models. Exits 2 if the daemon isn't running (connection refused).
2. **P1.M4.T2.S2 (`quit`/clean-shutdown)** — enhances the quit path with `recorder.shutdown()`
   + full socket close. S1's `quit` only calls `daemon.request_shutdown()` + replies; S2 owns
   the recorder teardown.
3. **P1.M7.T3.S1 (`e2e_virtual_mic.sh`)** — drives the daemon via `voicectl toggle`/`status`/
   `stop` against a tmux pane and asserts typed content.

**Use Case**: The daemon is running (systemd user service, started NOT listening per PRD §4.9).
The user hits the SUPER+ALT+D Hyprland keybind → `voicectl toggle` → connects, sends
`{"cmd":"toggle"}\n`, reads `{"ok":true,"listening":true,...}\n`, prints `listening: on`, exits.
The daemon's `toggle()` armed the mic; partials flow to the state file; the user speaks; finals
are typed. `voicectl status` shows the live partial + loaded models. `voicectl quit` drains.

**Pain Points Addressed**: (1) PRD §4.2(3) mandates a control socket but the daemon (S1/S2) has
no socket yet — S1 ships it. (2) `voicectl`/E2E need a programmatic, robust, low-latency status
(live partial, not the throttled disk file). (3) Clean shutdown without a hard kill.

## Why

- **This is the daemon's only external control surface.** PRD §4 architecture + §4.8 put
  `voicectl` and the socket at the center of the UX (toggle arming, status, quit). Nothing else
  (keybind, tmux status, E2E) functions without it. T5 (voicectl) + T7.T3 (E2E) are BLOCKED on S1.
- **The accept loop has a non-obvious correctness trap.** The textbook "close the listening
  socket from `stop()` to unblock `accept()`" **does not work reliably** on Linux (close(2)
  NOTES: unspecified; fd-reuse race) — verified empirically (research §6 Run 1: the thread never
  exited). S1 uses `select.select([sock],[],[],timeout)` + a stop `Event` (research §3, verified
  Run 2: clean exit within 1 s). This is the single highest-risk implementation detail.
- **`makefile` + `settimeout` is a trap.** `socket.makefile()` raises `OSError` if the socket
  has a timeout set ("must be in blocking mode"). Using `select` (not `settimeout`) keeps
  accepted connections in blocking mode so `makefile("r")`/`("w")` work for the readline
  protocol. Picking the wrong tool here silently breaks the protocol.
- **Status must show the LIVE partial, not the throttled disk.** `state.json` is written at
  ≥10 Hz max (P1.M3.T2.S1); reading it for status would lag. `Feedback.snapshot()` reads the
  in-memory state (always current). And status must report the models the recorder ACTUALLY
  loaded — reuse `_resolve_device_config(cfg)` (the S1 helper `build_recorder` used), cached once.
- **Uniform payload beats four shapes.** Returning `{"ok":true,**status_snapshot()}` for ALL of
  toggle/start/stop/status makes the protocol uniform, voicectl selects keys, and the PRD §4.2
  minimal shapes are a SUBSET (additive keys are harmless to JSON clients).

## What

A standalone `ControlServer` class + minimal additive status helpers. The **exact code** is
pinned in "Implementation Tasks" (copy-pasteable; verified empirically). All edits are additive
to `daemon.py` (new imports + one module fn + two new methods + one new class) and `feedback.py`
(one new method) — no existing symbol is modified, so S1/S2/S3 stay green and there is zero
overlap with the in-flight S3 latency work.

### Success Criteria

- [ ] `ControlServer` has `start`/`stop`/`_accept_loop`/`_handle`/`_dispatch` (research §3/§4).
- [ ] `start()` is idempotent; creates dir 0700; unlinks stale `.sock`; binds; chmod 0600;
  `listen(8)`; launches a daemon accept thread.
- [ ] `stop()` exits the accept thread within ~1 s (select-poll + stop Event); closes the socket.
- [ ] Protocol responses EXACTLY as in Success Definition (c) — pin every shape in tests.
- [ ] `status_snapshot()` returns the 8 keys; `_resolved_device()` caches (resolve called once).
- [ ] `Feedback.snapshot()` returns `dict(self._state)`; existing feedback tests unchanged.
- [ ] Malformed/non-dict JSON + unknown cmd + stale `.sock` all handled without crashing.
- [ ] Import purity preserved (only `json`/`os`/`select`/`socket` added at module top).
- [ ] `.venv/bin/python -m pytest tests/ -q` green (~159+ passed); S1/S2 test bodies UNCHANGED.

## All Needed Context

### Context Completeness Check

_Pass._ The implementer needs no prior codebase knowledge: the exact `ControlServer` /
`status_snapshot` / `_resolved_device` / `Feedback.snapshot` code is pinned below (verified
empirically against `.venv/bin/python`); the consumed daemon surface (`is_listening`,
`uptime_s`, `toggle`/`start`/`stop`/`request_shutdown`, `_feedback`, `_cfg`) + feedback
(`_state`) + cuda_check (`_resolve_device_config`) are read at preflight against the LIVE source
below; the S3 parallel-context contract is documented (research §1); and the validation commands
are executable as written.

### Documentation & References

```yaml
# MUST READ — the work-item design + empirical verification (THIS is the spec).
- file: plan/001_be48c74bc590/P1M4T2S1/research/control_socket_design.md
  why: "§1 deliverable + the S3 parallel-context contract (what S1 may NOT touch). §2 the EXACT
        wire protocol (response shapes tests pin). §3 the accept loop — WHY select() not
        close-to-unblock (the #1 correctness trap) + why select not settimeout (the makefile
        trap). §4 status_snapshot + Feedback.snapshot + the lazy device cache. §6 the verbatim
        empirical output proving close-to-unblock FAILS and select+stop-Event WORKS. §7 URLs. §8
        the test strategy."
  critical: "The accept loop MUST use select.select([sock],[],[],timeout) + a threading.Event,
             NOT socket.settimeout (makefile breaks with a timeout) and NOT close-to-unblock
             (unreliable, fd-reuse race). stop() sets the event (select returns within the poll
             interval) AND closes the socket (belt-and-suspenders). Verified clean exit <1 s."

# MUST READ — the module being EXTENDED (live S1+S2 state; 134 tests green).
- file: voice_typing/daemon.py
  why: "The exact starting point. Consumed daemon surface: VoiceTypingDaemon.is_listening() ->
        bool, uptime_s property, toggle()/start()/stop()/request_shutdown() (all use self._lock),
        self._feedback (Feedback), self._cfg (VoiceTypingConfig). Module helpers: _resolve_device_
        config(cfg) (the cuda_check resolution build_recorder used — REUSE for status, do not
        re-probe ad hoc). module-top imports are inspect/logging/threading/time/typing + textproc/
        typing_backends/cuda_check/config; module-top `logger = logging.getLogger(__name__)`.
        S1 ADDS json/os/select/socket + _default_control_socket_path + 2 daemon methods +
        ControlServer. (After S3 merges: collections + LatencyLog also at module top + an optional
        latency param on _build_callbacks/_construct/build_recorder + self._latency in __init__ —
        NONE of which S1 touches.)"
  critical: "Do NOT modify __init__/run/on_final/_arm/_disarm/start/stop/toggle/request_shutdown/
             _build_callbacks/_construct/build_recorder/cfg_to_kwargs/_resolve_device_config/
             _filter_kwargs_to_signature/_FIXED_KWARGS/_PARTIAL_CALLBACK_ATTR. ALL S1 edits are
             ADDITIVE (new imports, new module fn, 2 new methods on the class, 1 new class). Reuse
             _resolve_device_config (do not re-probe cuda_check ad hoc). Place ControlServer AFTER
             class VoiceTypingDaemon (module end) — it consumes the daemon."

# MUST READ — feedback (EXTENDED with snapshot()).
- file: voice_typing/feedback.py
  why: "Feedback._state is {listening,phase,partial,last_final,ts} (single source of truth).
        snapshot() returns dict(self._state). The disk state.json is THROTTLED (>=10 Hz) so it
        LAGS — status must read the live in-memory snapshot, not the file. Add snapshot() in the
        public-API section (after set_listening, before `# --- internals ---`)."
  critical: "snapshot() must return dict(self._state) (a COPY) so a concurrent socket thread
             reading it never aliases the live dict. Additive only — do not change update_partial/
             set_phase/record_final/set_listening/_write/_notify. No Lock needed (CPython dict
             copy is atomic; Feedback is designed lock-free per its docstring)."

# MUST READ — the S1/S2 tests (regression baseline S1 of T2 must NOT break; + where status tests go).
- file: tests/test_daemon.py
  why: "S1 tests: cfg_to_kwargs/_build_callbacks/_construct/_filter. S2 tests: _DaemonFakeFeedback,
        _StubRecorder, _FakeBackend, _make_daemon(), test_on_final_*/start_*/stop_*/toggle_*/run_loop_*.
        S1 of T2 APPENDS status_snapshot/_resolved_device tests — reuse _make_daemon() (injects a
        _StubRecorder so no RealtimeSTT) + monkeypatch daemon._resolve_device_config (cuda path)
        for hermetic device values. Do NOT edit S1/S2 test bodies."
  critical: "_make_daemon() returns (daemon, fb, rec, be); the daemon's _feedback is a
             _DaemonFakeFeedback (has record_final/set_listening but NO snapshot unless you extend
             the stub OR test status_snapshot on a real daemon). For status_snapshot tests, build a
             real Feedback: from voice_typing.feedback import Feedback; daemon constructed with a
             real Feedback(FeedbackConfig(state_file=str(tmp_path/'s.json'))). See Task 4."

# MUST READ — the RealtimeSTT/cuda resolution helper reused for status device/models.
- file: voice_typing/cuda_check.py
  why: "resolve_device_and_models() returns CUDA_DEFAULTS (echo) or CPU_FALLBACK (hard override).
        _resolve_device_config(cfg) in daemon.py wraps it with cfg-derived defaults. status must
        match build_recorder's resolution -> REUSE _resolve_device_config (cache once via getattr)."
  critical: "The probe IMPORTS ctranslate2 (heavy) + calls get_cuda_device_count(). Cache it ONCE
             (never per-status-call). In production ctranslate2 is already imported by build_recorder
             (fast); in tests monkeypatch daemon._resolve_device_config for hermeticity. Wrap the
             probe in try/except (degrade to 'unknown' on ANY failure — a status call must never
             crash the daemon)."

# Background — the preceding subtask PRPs (house style + the daemon surface S1 consumes).
- file: plan/001_be48c74bc590/P1M4T1S2/PRP.md
  why: "The S2 VoiceTypingDaemon design: toggle/start/stop/_arm/_disarm/request_shutdown/
        is_listening/uptime_s/_lock/_feedback/_cfg — exactly what ControlServer dispatches to."
  critical: "start()/stop()/toggle() take self._lock and mutate the listening gate + recorder mic.
        request_shutdown() sets _shutdown + aborts (NO recorder.shutdown() — that's T2.S2). S1's
        quit cmd calls request_shutdown() exactly; do not duplicate the gate logic."

# MUST READ — the in-flight S3 PRP (parallel context; treat as a contract).
- file: plan/001_be48c74bc590/P1M4T1S3/PRP.md
  why: "S3 is being implemented in parallel and edits daemon.py (LatencyLog + optional latency
        param + on_final/run/__init__ edits) + config.py ([log]) + config.toml. S1 of T2 runs
        AFTER S3 merges, so the live source is post-S3. S1 touches NONE of S3's symbols."
  critical: "Do NOT add a latency param, do NOT edit on_final/run/__init__, do NOT touch _build_
             callbacks/_construct/build_recorder. S1's status_snapshot/_resolved_device are new
             methods; ControlServer is a new class; the imports json/os/select/socket are disjoint
             from S3's collections import. Zero overlap -> no merge conflict. (research §1/§5.)"

# Downstream — the consumers S1 feeds (do NOT build).
- file: plan/001_be48c74bc590/tasks.json
  why: "P1.M5.T1.S1 (voicectl): connects + sends one JSON line + prints human output + exit 0/1/2.
        P1.M4.T2.S2 (quit/clean-shutdown): recorder.shutdown() + socket close. P1.M7.T3.S1 (E2E):
        drives voicectl against a tmux pane. Confirms the contract S1 must expose."
  critical: "Do NOT build ctl.py / main() / recorder.shutdown() here. The protocol response shapes
             + the ControlServer.start()/stop() surface are the contract voicectl + E2E rely on —
             do not rename them."
```

### Current Codebase tree (state at P1.M4.T2.S1 start — S1+S2 merged, 134 passing; +S3 when it lands)

```bash
/home/dustin/projects/voice-typing/
├── .git/ .gitignore .venv/        # DO NOT touch .gitignore
├── PRD.md                         # READ-ONLY (§4.2(3) socket, §4.8 voicectl, §4 architecture)
├── config.toml pyproject.toml uv.lock   # DO NOT touch (no new deps; stdlib only)
├── voice_typing/
│   ├── __init__.py                # DO NOT touch
│   ├── cuda_check.py              # READ ONLY (resolve_device_and_models; reused via _resolve_device_config)
│   ├── config.py                  # READ ONLY (VoiceTypingConfig/FeedbackConfig; consumed, not edited)
│   ├── textproc.py typing_backends.py status.sh launch_daemon.sh prefetch.py  # unrelated
│   ├── feedback.py                # ← MODIFY (Task 1): ADD Feedback.snapshot() (additive).
│   └── daemon.py                  # ← MODIFY (Task 2): ADD json/os/select/socket imports +
│                                  #   _default_control_socket_path() + VoiceTypingDaemon.status_snapshot()/
│                                  #   _resolved_device() + ControlServer class. (NO existing-method edit.)
└── tests/
    ├── test_config.py test_config_repo_default.py   # DO NOT EDIT
    ├── test_textproc.py test_typing_backends.py test_feedback.py  # test_feedback.py: APPEND snapshot test
    └── test_daemon.py             # ← MODIFY (Task 4b): APPEND status_snapshot/_resolved_device tests.
    # + tests/test_control_socket.py   ← NEW (Task 4a): dispatch + round-trip + lifecycle.
```

### Desired Codebase tree with files to be added/modified

```bash
voice_typing/feedback.py           # +snapshot() (1 method, additive)
voice_typing/daemon.py             # +4 imports, +_default_control_socket_path(), +2 daemon methods, +ControlServer
tests/test_control_socket.py       # NEW — dispatch + real-socket round-trip + lifecycle/hardening
tests/test_daemon.py               # +status_snapshot/_resolved_device tests (appended)
tests/test_feedback.py             # +snapshot() test (appended)
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL #1 — close-to-unblock accept() is UNRELIABLE. A throwaway server closed its listening
#   socket from stop(); accept() in the worker did NOT raise and the thread never exited (research
#   §6 Run 1). Linux close(2) NOTES: closing an fd another thread is blocked on is unspecified +
#   the freed fd can be reused before the woken syscall re-reads it (fd-reuse race).
#   FIX: select.select([sock], [], [], 0.3) + a threading.Event. stop() sets the event (select
#   returns within the poll interval) AND closes the socket (belt-and-suspenders). Verified clean
#   exit <1 s (research §6 Run 2). Do NOT use socket.settimeout on the listening socket (see #2).

# CRITICAL #2 — socket.makefile() RAISES if the socket has a timeout set ("must be in blocking
#   mode", Python docs). If you settimeout on the LISTENING socket, accepted CONNECTION sockets
#   risk inheriting it and makefile("r")/("w") break. Using select (not settimeout) leaves every
#   accepted conn in blocking mode -> makefile works for the readline protocol. (research §3.)

# CRITICAL #3 — makefile("w") BUFFERS; you MUST flush() after every response line or the client
#   blocks forever waiting for data still buffered server-side. (Verified: round-trip needs flush.)
#   Use conn.makefile("r", encoding="utf-8", newline="\n") for readline + makefile("w", ...) for
#   write; newline="\n" so readline splits on \n and write emits \n line endings (no \r).

# CRITICAL #4 — stale .sock blocks bind (EADDRINUSE). FIX: try: os.unlink(path) except
#   FileNotFoundError: pass BEFORE bind. SO_REUSEADDR is MEANINGLESS for AF_UNIX path sockets
#   (unix(7)) — do NOT setsockopt; the file must be unlinked. (Verified Run 1.)

# CRITICAL #5 — _resolve_device_config() IMPORTS ctranslate2 + probes CUDA (expensive). Cache it
#   ONCE (getattr/setattr lazy cache) — NEVER per-status-call. Wrap in try/except (any probe
#   failure -> device="unknown" etc.; a status call must never crash the daemon). In tests,
#   monkeypatch daemon._resolve_device_config for hermetic device values (mirror S1's _cuda_resolve).
#   Reuse _resolve_device_config (the S1 module helper build_recorder used) so status matches the
#   models the recorder ACTUALLY loaded — do NOT re-probe cuda_check ad hoc.

# CRITICAL #6 — backward compat is non-negotiable. S1's daemon.py edits are 100% ADDITIVE: new
#   imports (json/os/select/socket, all stdlib-cheap), one new module fn, two NEW methods on
#   VoiceTypingDaemon, one new class. Do NOT touch __init__/run/on_final/start/stop/toggle/
#   request_shutdown/_build_callbacks/_construct/build_recorder. (research §5 — the proof.) The
#   in-flight S3 edits those; S1 does not -> no merge conflict.

# CRITICAL #7 — import purity. S1 adds only stdlib imports at module top. RealtimeSTT/torch/
#   ctranslate2 stay lazily imported inside build_recorder (unchanged). The import-purity grep
#   (`RealtimeSTT|torch|ctranslate2` must NOT appear in sys.modules after `import voice_typing
#   .daemon`) must still pass. ControlServer references only json/os/select/socket/threading/
#   logging — all stdlib.

# CRITICAL #8 — Feedback.snapshot() must return dict(self._state) (a COPY), not self._state.
#   A concurrent socket-status thread reading the snapshot must never alias the live dict the
#   RealtimeSTT callback threads mutate. CPython dict(self._state) is atomic; no Lock needed
#   (Feedback is designed lock-free). The DISK state.json is THROTTLED (>=10 Hz) and LAGS ->
#   status reads the live in-memory snapshot, never the file.

# CRITICAL #9 — the protocol is uniform: toggle/start/stop/status ALL return {"ok":true,
#   **status_snapshot()} (8 status keys). The PRD §4.2 minimal shapes are a SUBSET (additive keys
#   are harmless — JSON clients ignore unknown keys; voicectl selects what it formats). quit
#   returns {"ok":true,"shutting_down":true} (NO status keys — going down). Do NOT invent four
#   different response shapes.

# CRITICAL #10 — quit must reply THEN break the connection's read loop (so the client gets the
#   response before the socket tears down) and call daemon.request_shutdown() (sets _shutdown +
#   aborts the recorder; run()'s loop exits). Do NOT call recorder.shutdown() here — that's
#   P1.M4.T2.S2. Do NOT close the listening socket from the quit handler — stop() (called by T3's
#   main() after run() returns) owns socket teardown.

# CRITICAL #11 — malformed/non-dict JSON + unknown/missing cmd MUST reply {"ok":false,"error":...}
#   (the contract). Empty lines are SKIPPED (continue, no response) so a one-shot client that sends
#   a trailing newline doesn't hang. A bare string/number/array is "non-dict" (error), NOT a valid
#   cmd. json.loads raises json.JSONDecodeError (a ValueError subclass) — catch ValueError to be safe.

# CRITICAL #12 — FULL PATHS for tooling (zsh aliases python/pytest). ALWAYS
#   `.venv/bin/python -m pytest` / `.venv/bin/python -m py_compile` (never bare python/pytest).
#   mypy is NOT installed — do NOT list it. ruff is optional (/home/dustin/.local/bin/ruff);
#   py_compile + pytest are the authoritative gates.

# GOTCHA #13 — _default_control_socket_path() mirrors FeedbackConfig.resolved_state_file(): raise
#   RuntimeError if XDG_RUNTIME_DIR is unset (no safe default — fail clearly, like the state file).
#   Tests pass an explicit socket_path (tmp_path) so they NEVER depend on XDG_RUNTIME_DIR. The
#   resolution test monkeypatches XDG_RUNTIME_DIR to a tmp dir.
```

## Implementation Blueprint

### Data models and structure

No persistent data model. `ControlServer` holds only transient runtime state:

```python
self._daemon: VoiceTypingDaemon          # the daemon cmds dispatch to
self._socket_path: str                    # resolved or injected
self._sock: socket.socket | None          # the listening AF_UNIX socket (None when stopped)
self._thread: threading.Thread | None     # the accept thread (daemon=True)
self._stop: threading.Event               # set by stop(); polled in _accept_loop via select
self._on_quit: Callable[[], None] | None  # optional hook (S2/T3 may wire recorder.shutdown here)
self._accept_timeout: float = 0.3         # select poll interval (stop latency <= this + epsilon)
self._lock: threading.Lock                # serializes start()/stop() against each other
```

`VoiceTypingDaemon` gains NO new attribute at construction — `_resolved_device()` lazily caches
via `getattr(self, "_resolved_device_cache", None)` (avoids editing `__init__`, which S3 owns).
`Feedback` gains NO new attribute (snapshot() just returns a copy).

### `ControlServer` reference implementation (research §3/§4 — implement this verbatim)

```python
# Place at module END (after class VoiceTypingDaemon). Consumes the daemon; uses only stdlib.

_CONTROL_SOCKET_SUBPATH = ("voice-typing", "control.sock")  # under $XDG_RUNTIME_DIR


def _default_control_socket_path() -> str:
    """Resolve $XDG_RUNTIME_DIR/voice-typing/control.sock (PRD §4.2(3)).

    Mirrors FeedbackConfig.resolved_state_file(): raises RuntimeError if XDG_RUNTIME_DIR is
    unset/empty (no safe default — fail clearly rather than bind a socket to a wrong path).
    Production runs under a systemd user session (XDG_RUNTIME_DIR=/run/user/$UID, 0700). Tests
    pass an explicit socket_path so they never hit this.
    """
    xdg = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if not xdg:
        raise RuntimeError(
            "XDG_RUNTIME_DIR is not set; cannot resolve the control socket path. "
            "Pass socket_path= explicitly, or run under a session that exports "
            "XDG_RUNTIME_DIR (systemd user sessions set it)."
        )
    return os.path.join(xdg, *_CONTROL_SOCKET_SUBPATH)


class ControlServer:
    """AF_UNIX SOCK_STREAM control socket speaking one-JSON-object-per-line (PRD §4.2(3), §4.8).

    A background daemon thread accepts connections (one daemon worker per connection); each worker
    reads newline-delimited JSON requests, dispatches cmd to the daemon, and writes one JSON line
    per request. Robust to malformed JSON, stale socket files, and clean shutdown.

    Lifecycle: construct with the daemon (and optional socket_path + on_quit hook); start() binds
    + listens + launches the accept thread; stop() sets a stop Event (the accept loop uses
    select() polling, NOT close-to-unblock, which is unreliable on Linux) and joins the thread.
    The daemon does NOT own a ControlServer — the entry point (P1.M4.T3.S1 main()) constructs +
    starts one and calls stop() after run() returns.

    Protocol (PRD §4.2(3); research §2 — uniform status payload):
      {"cmd":"toggle"|"start"|"stop"|"status"} -> {"ok":true, **daemon.status_snapshot()}
      {"cmd":"quit"}                           -> {"ok":true,"shutting_down":true}  (+ request_shutdown)
      malformed JSON                           -> {"ok":false,"error":"malformed JSON: ..."}
      non-dict JSON                            -> {"ok":false,"error":"request must be a JSON object"}
      unknown/missing cmd                      -> {"ok":false,"error":"unknown command: ..."}
    """

    def __init__(
        self,
        daemon: "VoiceTypingDaemon",
        *,
        socket_path: str | None = None,
        on_quit: "Callable[[], None] | None" = None,
        accept_timeout: float = 0.3,
    ) -> None:
        self._daemon = daemon
        self._socket_path = (
            socket_path if socket_path is not None else _default_control_socket_path()
        )
        self._on_quit = on_quit
        self._accept_timeout = accept_timeout
        self._sock: Any = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    def start(self) -> None:
        """Bind + listen + launch the accept thread. Idempotent (no-op if already running).

        Creates the parent dir 0700; unlinks a stale .sock (EADDRINUSE prevention, PRD §4.2(3));
        binds; chmod 0600; listen(8). Raises RuntimeError if bind still fails (a live daemon
        holds the path — a real misconfiguration the operator must see).
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return  # already running
            directory = os.path.dirname(self._socket_path) or "."
            os.makedirs(directory, exist_ok=True, mode=0o700)
            # stale socket: unlink before bind (SO_REUSEADDR is meaningless for AF_UNIX path sockets)
            try:
                os.unlink(self._socket_path)
            except FileNotFoundError:
                pass
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.bind(self._socket_path)
            except OSError as exc:
                sock.close()
                raise RuntimeError(
                    f"cannot bind control socket {self._socket_path!r}: {exc}"
                ) from exc
            os.chmod(self._socket_path, 0o600)   # owner-only (belt-and-suspenders on the 0700 dir)
            sock.listen(8)
            self._sock = sock
            self._stop = threading.Event()
            self._thread = threading.Thread(
                target=self._accept_loop,
                name="voice-typing-control",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        """Signal the accept loop to exit + close the listening socket + join the thread.

        Uses the stop Event (the accept loop polls via select(), so it notices within
        accept_timeout) and ALSO closes the socket (belt-and-suspenders: any blocked select/
        accept raises immediately). Joins up to 2 s. Unlinks the socket file (next start() also
        unlinks, but a clean quit leaves no stale .sock).
        """
        with self._lock:
            self._stop.set()
            sock = self._sock
            self._sock = None
            thread = self._thread
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if thread is not None:
            thread.join(timeout=2.0)
        try:
            os.unlink(self._socket_path)
        except (FileNotFoundError, OSError):
            pass

    def _accept_loop(self) -> None:
        """Accept connections until stop(). Uses select() polling (NOT close-to-unblock)."""
        sock = self._sock
        if sock is None:
            return
        while not self._stop.is_set():
            try:
                ready, _, _ = select.select([sock], [], [], self._accept_timeout)
            except (OSError, ValueError):
                break  # listening socket closed (stop()) -> select raises
            if not ready:
                continue  # poll timeout -> re-check the stop Event
            try:
                conn, _addr = sock.accept()
            except OSError:
                break  # socket closed between select and accept
            # one daemon worker per connection (voicectl is one-shot; a persistent client also works)
            threading.Thread(
                target=self._handle, args=(conn,), daemon=True
            ).start()

    def _handle(self, conn: Any) -> None:
        """Per-connection readline loop: parse JSON, dispatch, write one JSON line per request."""
        rfile = wfile = None
        try:
            rfile = conn.makefile("r", encoding="utf-8", newline="\n")
            wfile = conn.makefile("w", encoding="utf-8", newline="\n")
            try:
                for line in rfile:                 # one JSON object per line (PRD §4.2(3))
                    line = line.strip()
                    if not line:
                        continue                   # empty line -> skip (no response)
                    response = self._dispatch(line)
                    wfile.write(json.dumps(response) + "\n")
                    wfile.flush()                  # CRITICAL: makefile("w") buffers; flush every reply
                    if response.get("shutting_down"):
                        break                      # quit -> reply sent, then close this connection
            finally:
                for f in (rfile, wfile):
                    if f is not None:
                        try:
                            f.close()
                        except OSError:
                            pass
        except OSError:
            pass  # client gone mid-line; worker exits cleanly
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _dispatch(self, line: str) -> dict:
        """Parse one request line -> dispatch cmd -> response dict. Never raises (robustness)."""
        try:
            msg = json.loads(line)
        except ValueError as exc:  # json.JSONDecodeError is a ValueError subclass
            return {"ok": False, "error": f"malformed JSON: {exc}"}
        if not isinstance(msg, dict):
            return {"ok": False, "error": "request must be a JSON object"}
        cmd = msg.get("cmd")
        if cmd == "toggle":
            self._daemon.toggle()
            return {"ok": True, **self._daemon.status_snapshot()}
        if cmd == "start":
            self._daemon.start()
            return {"ok": True, **self._daemon.status_snapshot()}
        if cmd == "stop":
            self._daemon.stop()
            return {"ok": True, **self._daemon.status_snapshot()}
        if cmd == "status":
            return {"ok": True, **self._daemon.status_snapshot()}
        if cmd == "quit":
            self._daemon.request_shutdown()
            if self._on_quit is not None:
                try:
                    self._on_quit()
                except Exception:
                    logger.exception("on_quit callback failed")
            return {"ok": True, "shutting_down": True}
        return {"ok": False, "error": f"unknown command: {cmd!r}"}
```

### `VoiceTypingDaemon` additions (research §4 — two NEW methods; NO existing-method edit)

```python
    # ADD these two methods to class VoiceTypingDaemon (e.g. right after the uptime_s property).
    # They are pure additions — do not modify __init__/run/on_final/anything else.

    def status_snapshot(self) -> dict:
        """The status payload for the control socket `status`/`toggle`/`start`/`stop` cmds.

        Returns {listening, partial, last_final, uptime_s, device, compute_type, final_model,
        realtime_model}. partial/last_final come from the LIVE in-memory Feedback state (NOT the
        throttled state.json, which lags >=10 Hz); device/models come from _resolve_device_config
        (the SAME resolution build_recorder used -> status matches the actually-loaded models),
        cached on first call. Safe to call from the socket thread; never raises (device probe
        failures degrade to 'unknown').
        """
        snap = self._feedback.snapshot()
        dev = self._resolved_device()
        return {
            "listening": self.is_listening(),
            "partial": snap.get("partial", ""),
            "last_final": snap.get("last_final", ""),
            "uptime_s": round(self.uptime_s, 3),
            "device": dev.get("device", "unknown"),
            "compute_type": dev.get("compute_type", "unknown"),
            "final_model": dev.get("final_model", "unknown"),
            "realtime_model": dev.get("realtime_model", "unknown"),
        }

    def _resolved_device(self) -> dict[str, str]:
        """Resolved {device,compute_type,final_model,realtime_model}, cached on first call.

        Lazily cached via getattr (no __init__ edit) so S1/S3's __init__ is untouched. The
        cuda_check probe (inside _resolve_device_config) imports ctranslate2 + calls
        get_cuda_device_count() — run AT MOST ONCE. Any failure degrades to 'unknown' (a status
        call must never crash the daemon). In tests, monkeypatch daemon._resolve_device_config.
        """
        resolved = getattr(self, "_resolved_device_cache", None)
        if resolved is None:
            try:
                resolved = _resolve_device_config(self._cfg)
            except Exception as exc:
                logger.warning("status: device resolution failed (%s); reporting 'unknown'", exc)
                resolved = {
                    "device": "unknown",
                    "compute_type": "unknown",
                    "final_model": "unknown",
                    "realtime_model": "unknown",
                }
            self._resolved_device_cache = resolved
        return resolved
```

### `Feedback.snapshot()` addition (research §4 — one NEW method; additive)

```python
    # ADD to class Feedback, in the public-API section (after set_listening, before `# --- internals ---`).

    def snapshot(self) -> dict:
        """A shallow copy of the live in-memory state {listening,phase,partial,last_final,ts}.

        For low-latency status reads (the control socket `status` cmd) WITHOUT hitting the
        throttled state.json on disk (which lags >=10 Hz). Returns a COPY (dict(self._state)) so
        a concurrent reader never aliases the live dict the callback threads mutate. CPython dict
        copy is atomic; no Lock needed (Feedback is designed lock-free).
        """
        return dict(self._state)
```

### Implementation Tasks (ordered by dependencies)

```yaml
Task 0: PREFLIGHT — confirm the live S1+S2 state + consumed surface + the baseline.
  - RUN (from /home/dustin/projects/voice-typing):
      test -f voice_typing/daemon.py && test -f voice_typing/feedback.py && echo ok
      .venv/bin/python -m pytest tests/ -q 2>&1 | tail -1      # expect "134 passed" (or ~144 if S3 landed)
      .venv/bin/python -c "
import sys, voice_typing.daemon as d
from voice_typing.feedback import Feedback
assert hasattr(d,'VoiceTypingDaemon') and hasattr(d,'_resolve_device_config')
assert all(hasattr(d.VoiceTypingDaemon, m) for m in
           ('is_listening','uptime_s','toggle','start','stop','request_shutdown','run'))
assert not hasattr(d.VoiceTypingDaemon,'status_snapshot')          # not added yet
assert not hasattr(d,'ControlServer')                               # not added yet
assert not hasattr(Feedback,'snapshot')                             # not added yet
assert not [m for m in('RealtimeSTT','torch','ctranslate2') if m in sys.modules], 'import purity broken pre-task'
print('daemon + feedback + import purity OK; baseline green')
"
  - EXPECTED: 134 passed (S1+S2; +~10 if S3 already merged); VoiceTypingDaemon has the consumed
    surface; status_snapshot/ControlServer/Feedback.snapshot are NOT yet present; import purity holds.
  - NOTE: if S3 has merged, _build_callbacks/_construct/build_recorder have an extra optional
    `latency` param and __init__ has self._latency — that's EXPECTED and does NOT affect S1 of T2
    (S1 adds new symbols only). Do NOT create/edit any file, run uv sync/add, or touch other modules.

Task 1: MODIFY voice_typing/feedback.py — ADD Feedback.snapshot() (research §4).
  - FILE: voice_typing/feedback.py. ADD the snapshot() method verbatim (above) in the public-API
    section, AFTER set_listening and BEFORE the `# --- internals ---` divider.
  - DO NOT: change update_partial/set_phase/record_final/set_listening/_write/_notify; add a Lock;
    read the disk file (snapshot is in-memory); touch __init__.

Task 2: MODIFY voice_typing/daemon.py — ADD imports + _default_control_socket_path() +
        VoiceTypingDaemon.status_snapshot()/_resolved_device() + ControlServer.
  - FILE: voice_typing/daemon.py.
  - (2a) ADD `import json`, `import os`, `import select`, `import socket` to the module-top
         import block (alphabetical, with inspect/logging/threading/time). See "Task 2a edit".
  - (2b) ADD the `_CONTROL_SOCKET_SUBPATH` constant + `_default_control_socket_path()` module fn
         verbatim (above). Place AFTER the existing module helpers (e.g. after build_recorder),
         BEFORE `class VoiceTypingDaemon`.
  - (2c) ADD `status_snapshot()` + `_resolved_device()` to class VoiceTypingDaemon (verbatim,
         above). Place right AFTER the `uptime_s` property (module end of the class).
  - (2d) ADD the `ControlServer` class (verbatim, above) at module END (after VoiceTypingDaemon).
  - DO NOT: modify __init__/run/on_final/_arm/_disarm/start/stop/toggle/request_shutdown/
    _build_callbacks/_construct/build_recorder/cfg_to_kwargs/_resolve_device_config/
    _filter_kwargs_to_signature; add main()/__main__/signal/basicConfig; wire ControlServer into
    run()/__init__; call recorder.shutdown(); edit config.py/config.toml/pyproject.toml.

Task 3: CREATE tests/test_control_socket.py — dispatch logic + real-socket round-trip +
        lifecycle/hardening (research §8).
  - FILE: tests/test_control_socket.py (NEW). See "Task 3 SOURCE" below for the stubs + tests.
  - PATTERNS: a _StubDaemon (records toggle/start/stop/quit + canned status_snapshot) for dispatch
    tests; an explicit socket_path under pytest tmp_path (NO XDG_RUNTIME_DIR dependency); a
    _send(path, msg) client helper; _wait_for(predicate, timeout=2.0) for thread-join assertions.
  - COVERAGE: toggle/start/stop/status/quit response shapes; unknown/missing cmd; malformed +
    non-dict JSON; empty-line skip; multi-line-in-one-connection -> N responses; real round-trip;
    idempotent start; dir 0700 + socket 0600; stale-.sock recovery; stop joins thread <1 s +
    unlinks file; _default_control_socket_path honors XDG_RUNTIME_DIR + raises when unset.
  - DO NOT: import RealtimeSTT/torch; depend on XDG_RUNTIME_DIR; use a real VoiceTypingDaemon
    in dispatch tests (use _StubDaemon); sleep() gratuitously (use _wait_for).

Task 4: MODIFY tests — (4a) tests/test_feedback.py APPEND a snapshot() test; (4b) tests/test_daemon.py
        APPEND status_snapshot/_resolved_device tests.
  - FILES: tests/test_feedback.py, tests/test_daemon.py. APPEND only; do NOT edit existing bodies.
  - (4a) test_feedback.py: assert snapshot() returns a copy with the 5 keys + that mutating it
    does not affect the live _state (copy semantics) + that it reflects a recorded final.
  - (4b) test_daemon.py: build a real daemon with a real Feedback (state_file under tmp_path) via
    _make_daemon()-style construction (inject _StubRecorder); monkeypatch daemon._resolve_device_config
    for the cuda path; assert status_snapshot keys + values (listening mirrors is_listening; partial/
    last_final from feedback; uptime_s rounded; device=cuda/float16/distil-large-v3/small.en; cpu path
    -> CPU_FALLBACK models); assert _resolved_device() caches (resolve called once across 2 snapshots);
    assert a resolve failure -> device="unknown" (monkeypatch to raise). See "Task 4b notes".
  - DO NOT edit S1/S2/(S3) test bodies. Reuse _make_daemon/_StubRecorder/_wait_for where helpful.

Task 5: VALIDATE — run the Validation Loop L1–L4. Iterate until all gates pass.
  - No git commit unless the orchestrator directs it. If asked: message
    "P1.M4.T2.S1: control socket server (ControlServer JSON-lines protocol + status_snapshot)".
```

#### Task 2a edit — `voice_typing/daemon.py` import block

oldText:
```
import inspect
import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Callable
```
newText:
```
import inspect
import json
import logging
import os
import select
import socket
import threading
import time
from typing import TYPE_CHECKING, Any, Callable
```
(If S3 has merged and `import collections` is present, keep it — add the four new imports in
alphabetical position alongside the existing ones. The anchor above is the S1+S2 baseline; if
the live block differs (S3 merged), merge the four new stdlib imports into it preserving order.)

#### Task 3 SOURCE — `tests/test_control_socket.py` (skeleton; expand to ~20 tests)

```python
"""Unit + integration tests for voice_typing.daemon.ControlServer (P1.M4.T2.S1).

Three layers (research §8):
  A. _dispatch() logic — no socket; a _StubDaemon records calls + returns canned status.
  B. Real AF_UNIX round-trip — ControlServer on a tmp_path socket_path; a client connects,
     sends one JSON line, reads one response line, json.loads, asserts.
  C. Lifecycle/hardening — idempotent start, dir 0700 / socket 0600, stale-.sock recovery,
     clean stop (select-poll) joins the thread <1 s + unlinks the file.

NO RealtimeSTT / NO CUDA / NO XDG_RUNTIME_DIR (explicit socket_path under tmp_path).
Run:
    cd /home/dustin/projects/voice-typing
    .venv/bin/python -m pytest tests/test_control_socket.py -v
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time as _time

import pytest

from voice_typing import daemon


class _StubDaemon:
    """Duck-type VoiceTypingDaemon for dispatch tests (no recorder, no CUDA)."""
    def __init__(self, *, listening=False, snapshot=None):
        self.calls: list[str] = []
        self._listening = listening
        self._snapshot = snapshot or {
            "listening": listening, "partial": "", "last_final": "",
            "uptime_s": 0.0, "device": "cuda", "compute_type": "float16",
            "final_model": "distil-large-v3", "realtime_model": "small.en",
        }
    def toggle(self): self.calls.append("toggle"); self._listening = not self._listening
    def start(self): self.calls.append("start"); self._listening = True
    def stop(self): self.calls.append("stop"); self._listening = False
    def request_shutdown(self): self.calls.append("quit")
    def is_listening(self): return self._listening
    def status_snapshot(self):
        s = dict(self._snapshot); s["listening"] = self._listening; return s


def _wait_for(predicate, timeout=2.0, interval=0.01):
    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if predicate(): return True
        _time.sleep(interval)
    return predicate()


def _send(path, msg_obj_or_bytes):
    """One client round-trip: connect, send one line, read one response line, close."""
    raw = msg_obj_or_bytes if isinstance(msg_obj_or_bytes, bytes) else (
        json.dumps(msg_obj_or_bytes) + "\n"
    ).encode()
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(path)
    c.sendall(raw)
    data = b""
    while not data.endswith(b"\n"):
        chunk = c.recv(4096)
        if not chunk: break
        data += chunk
    c.close()
    return data.decode().strip()


def _send_lines(path, *objs):
    """Send multiple JSON lines in one connection; return the list of response lines."""
    payload = b"".join((json.dumps(o) + "\n").encode() for o in objs)
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.connect(path); c.sendall(payload)
    data = b""
    while data.count(b"\n") < len(objs):
        chunk = c.recv(4096)
        if not chunk: break
        data += chunk
    c.close()
    return [ln for ln in data.decode().splitlines() if ln]


@pytest.fixture
def server(tmp_path):
    """A ControlServer on a tmp_path socket backed by a _StubDaemon."""
    path = str(tmp_path / "control.sock")
    srv = daemon.ControlServer(_StubDaemon(), socket_path=path)
    srv.start()
    yield srv, path
    srv.stop()


# --- A. dispatch logic (no socket) --------------------------------------------------------

def _disp(msg_obj_or_str):
    return daemon.ControlServer(_StubDaemon())._dispatch(
        msg_obj_or_str if isinstance(msg_obj_or_str, str) else json.dumps(msg_obj_or_str)
    )

def test_dispatch_toggle():
    r = _disp({"cmd": "toggle"})
    assert r["ok"] is True and r["listening"] is True and "device" in r   # uniform payload
def test_dispatch_status_has_all_keys():
    r = _disp({"cmd": "status"})
    assert set(r) == {"ok","listening","partial","last_final","uptime_s","device",
                      "compute_type","final_model","realtime_model"}
def test_dispatch_start_stop_set_listening():
    assert _disp({"cmd": "start"})["listening"] is True
    assert _disp({"cmd": "stop"})["listening"] is False
def test_dispatch_quit_calls_request_shutdown():
    d = _StubDaemon()
    daemon.ControlServer(d)._dispatch(json.dumps({"cmd": "quit"}))
    assert d.calls == ["quit"]
    r = daemon.ControlServer(_StubDaemon())._dispatch(json.dumps({"cmd":"quit"}))
    assert r == {"ok": True, "shutting_down": True}
def test_dispatch_unknown_command():
    assert _disp({"cmd": "frobnicate"}) == {"ok": False, "error": "unknown command: 'frobnicate'"}
def test_dispatch_missing_cmd():
    assert _disp({})["ok"] is False and "unknown command" in _disp({})["error"]
def test_dispatch_malformed_json():
    r = _disp("not json{")
    assert r["ok"] is False and r["error"].startswith("malformed JSON:")
def test_dispatch_non_dict_json():
    for bad in ('"a string"', "42", "[1,2]"):
        assert _disp(bad) == {"ok": False, "error": "request must be a JSON object"}

# --- B. real-socket round-trip ------------------------------------------------------------

def test_round_trip_status(server):
    srv, path = server
    r = json.loads(_send(path, {"cmd": "status"}))
    assert r["ok"] is True and r["device"] == "cuda"
def test_round_trip_toggle_then_status(server):
    srv, path = server
    json.loads(_send(path, {"cmd": "toggle"}))      # arms
    r = json.loads(_send(path, {"cmd": "status"}))
    assert r["listening"] is True
def test_round_trip_malformed_over_wire(server):
    srv, path = server
    r = json.loads(_send(path, b"garbled\n"))
    assert r["ok"] is False
def test_round_trip_multi_line_one_connection(server):
    srv, path = server
    lines = _send_lines(path, {"cmd": "start"}, {"cmd": "stop"}, {"cmd": "status"})
    assert len(lines) == 3
    assert json.loads(lines[0])["listening"] is True
    assert json.loads(lines[1])["listening"] is False
def test_round_trip_quit(server):
    srv, path = server
    r = json.loads(_send(path, {"cmd": "quit"}))
    assert r == {"ok": True, "shutting_down": True}

# --- C. lifecycle / hardening -------------------------------------------------------------

def test_start_creates_dir_0700_and_socket_0600(tmp_path):
    path = str(tmp_path / "sub" / "control.sock")
    srv = daemon.ControlServer(_StubDaemon(), socket_path=path); srv.start()
    try:
        assert oct(os.stat(tmp_path / "sub").st_mode & 0o777) == "0o700"
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    finally:
        srv.stop()
def test_start_recovers_stale_socket_file(tmp_path):
    path = str(tmp_path / "control.sock")
    open(path, "w").close()                # pre-existing stale file -> would block bind
    srv = daemon.ControlServer(_StubDaemon(), socket_path=path); srv.start()
    try:
        assert os.path.exists(path) and stat_is_socket(path)
    finally:
        srv.stop()
def test_start_is_idempotent(tmp_path):
    path = str(tmp_path / "control.sock")
    srv = daemon.ControlServer(_StubDaemon(), socket_path=path)
    srv.start(); t1 = srv._thread
    srv.start(); t2 = srv._thread          # second start is a no-op
    assert t1 is t2
    srv.stop()
def test_stop_joins_thread_and_unlinks(tmp_path):
    path = str(tmp_path / "control.sock")
    srv = daemon.ControlServer(_StubDaemon(), socket_path=path); srv.start()
    srv.stop()
    assert srv._thread is not None and not srv._thread.is_alive()
    assert not os.path.exists(path)
def test_default_socket_path_honors_xdg(monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/tmp/fake-xdg-123")
    assert daemon._default_control_socket_path() == "/tmp/fake-xdg-123/voice-typing/control.sock"
def test_default_socket_path_raises_when_xdg_unset(monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    with pytest.raises(RuntimeError):
        daemon._default_control_socket_path()

def stat_is_socket(p):
    import stat
    return stat.S_ISSOCK(os.stat(p).st_mode)
```

#### Task 4b notes — `tests/test_daemon.py` status_snapshot tests (APPEND)

```python
# ===========================================================================
# P1.M4.T2.S1 — VoiceTypingDaemon.status_snapshot() + _resolved_device() (ADDITIVE)
# ===========================================================================
from voice_typing.feedback import Feedback
from voice_typing.config import FeedbackConfig

def _cuda_resolve(monkeypatch, mapping):
    is_fb = mapping is daemon.cuda_check.CPU_FALLBACK
    def _resolve(defaults=None):
        return dict(mapping) if is_fb else dict(defaults)
    monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", _resolve)

def _make_daemon_with_feedback(tmp_path, monkeypatch, *, cuda=True):
    _cuda_resolve(monkeypatch, daemon.cuda_check.CUDA_DEFAULTS if cuda else daemon.cuda_check.CPU_FALLBACK)
    cfg = VoiceTypingConfig(feedback=FeedbackConfig(state_file=str(tmp_path / "state.json")))
    fb = Feedback(cfg.feedback)
    rec = _StubRecorder(); be = _FakeBackend()
    return daemon.VoiceTypingDaemon(cfg, fb, recorder=rec, backend=be), fb

def test_status_snapshot_keys_and_cuda_values(tmp_path, monkeypatch):
    d, fb = _make_daemon_with_feedback(tmp_path, monkeypatch, cuda=True)
    fb.update_partial("hello"); fb.record_final("world")
    s = d.status_snapshot()
    assert set(s) == {"listening","partial","last_final","uptime_s",
                      "device","compute_type","final_model","realtime_model"}
    assert s["listening"] is False and s["partial"] == "hello" and s["last_final"] == "world"
    assert s["device"] == "cuda" and s["compute_type"] == "float16"
    assert s["final_model"] == "distil-large-v3" and s["realtime_model"] == "small.en"

def test_status_snapshot_reflects_listening_toggle(tmp_path, monkeypatch):
    d, _fb = _make_daemon_with_feedback(tmp_path, monkeypatch)
    assert d.status_snapshot()["listening"] is False
    d.start()
    assert d.status_snapshot()["listening"] is True

def test_status_snapshot_cpu_fallback_models(tmp_path, monkeypatch):
    d, _fb = _make_daemon_with_feedback(tmp_path, monkeypatch, cuda=False)
    s = d.status_snapshot()
    assert s["device"] == "cpu" and s["final_model"] == "small.en" and s["realtime_model"] == "tiny.en"

def test_resolved_device_caches_resolve_called_once(tmp_path, monkeypatch):
    calls = {"n": 0}
    def _resolve(defaults=None):
        calls["n"] += 1; return dict(daemon.cuda_check.CUDA_DEFAULTS)
    monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", _resolve)
    d, _fb = _make_daemon_with_feedback(tmp_path, monkeypatch)
    d.status_snapshot(); d.status_snapshot()
    assert calls["n"] == 1                      # cached after the first call

def test_resolved_device_failure_degrades_to_unknown(tmp_path, monkeypatch):
    def boom(defaults=None): raise RuntimeError("cuda exploded")
    monkeypatch.setattr(daemon.cuda_check, "resolve_device_and_models", boom)
    d, _fb = _make_daemon_with_feedback(tmp_path, monkeypatch)
    s = d.status_snapshot()
    assert s["device"] == "unknown"             # never raises; degrades gracefully
```

### Integration Points

```yaml
SOCKET:
  - path: "$XDG_RUNTIME_DIR/voice-typing/control.sock" (AF_UNIX SOCK_STREAM; dir 0700, file 0600)
  - resolution: _default_control_socket_path() (raises if XDG_RUNTIME_DIR unset; tests inject socket_path)
  - stale handling: unlink-before-bind (SO_REUSEADDR is a no-op for AF_UNIX path sockets)

CONFIG:
  - none. No new config field (the socket path is fixed at $XDG_RUNTIME_DIR/voice-typing/control.sock,
    mirroring the state-file path; not user-tunable per PRD §4.2(3)). Do NOT edit config.py/config.toml.

ENTRY POINT (P1.M4.T3.S1 — NOT this task):
  - main() will: cfg=load(); fb=Feedback(cfg.feedback); d=VoiceTypingDaemon(cfg,fb);
    srv=ControlServer(d); srv.start(); d.run(); srv.stop(). S1 PROVIDES ControlServer; does not wire it.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
# Per-file syntax check after each creation/modification:
.venv/bin/python -m py_compile voice_typing/daemon.py voice_typing/feedback.py
.venv/bin/python -m py_compile tests/test_control_socket.py tests/test_daemon.py tests/test_feedback.py

# Import purity (the hard gate): importing daemon must NOT pull RealtimeSTT/torch/ctranslate2.
.venv/bin/python -c "
import sys; import voice_typing.daemon
bad=[m for m in('RealtimeSTT','torch','ctranslate2') if m in sys.modules]
assert not bad, f'import purity broken: {bad}'
from voice_typing.daemon import ControlServer, VoiceTypingDaemon, _default_control_socket_path
from voice_typing.feedback import Feedback
assert hasattr(VoiceTypingDaemon,'status_snapshot') and hasattr(VoiceTypingDaemon,'_resolved_device')
assert hasattr(Feedback,'snapshot')
print('imports + symbols + purity OK')
"

# Optional lint/format (ruff is optional at /home/dustin/.local/bin/ruff; mypy is NOT installed):
/home/dustin/.local/bin/ruff check voice_typing/daemon.py voice_typing/feedback.py tests/test_control_socket.py 2>/dev/null || true
# Expected: zero errors. Fix anything reported before proceeding.
```

### Level 2: Unit Tests (Component Validation)

```bash
cd /home/dustin/projects/voice-typing
# The new control-socket suite:
.venv/bin/python -m pytest tests/test_control_socket.py -v
# Expected: all green (dispatch ~8 + round-trip ~5 + lifecycle ~7 ≈ 20 tests).

# The status_snapshot additions + the feedback snapshot test:
.venv/bin/python -m pytest tests/test_daemon.py -v -k "status_snapshot or resolved_device"
.venv/bin/python -m pytest tests/test_feedback.py -v -k "snapshot"

# Full suite (regression — S1/S2 unchanged):
.venv/bin/python -m pytest tests/ -q
# Expected: ~159+ passed (134 S1+S2 + ~10 S3 if landed + ~25 new), 0 failed.
```

### Level 3: Integration Testing (Real socket round-trip)

```bash
cd /home/dustin/projects/voice-typing
# End-to-end socket smoke: start a ControlServer on a tmp socket, talk to it as voicectl would.
.venv/bin/python - <<'PY'
import json, os, socket, tempfile, threading
from voice_typing import daemon
class Stub:
    def __init__(self): self.l=False
    def toggle(self): self.l=not self.l
    def start(self): self.l=True
    def stop(self): self.l=False
    def request_shutdown(self): pass
    def is_listening(self): return self.l
    def status_snapshot(self): return {"listening":self.l,"partial":"hi","last_final":"yo",
        "uptime_s":1.2,"device":"cuda","compute_type":"float16","final_model":"distil-large-v3","realtime_model":"small.en"}
d=tempfile.mkdtemp(); path=os.path.join(d,"control.sock")
srv=daemon.ControlServer(Stub(), socket_path=path); srv.start()
def send(o):
    c=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); c.connect(path)
    c.sendall((json.dumps(o)+"\n").encode()); data=b""
    while not data.endswith(b"\n"):
        ch=c.recv(4096); 
        if not ch: break
        data+=ch
    c.close(); return json.loads(data)
print("toggle:", send({"cmd":"toggle"})["listening"])
print("status:", send({"cmd":"status"})["device"], send({"cmd":"status"})["partial"])
print("bogus:", send({"cmd":"nope"})["ok"])
print("malformed:", send_str if False else "tested in suite")
srv.stop()
print("socket gone:", not os.path.exists(path))
print("dir 0700:", oct(os.stat(d).st_mode & 0o777))
PY
# Expected: toggle: True; status: cuda hi; bogus: False; socket gone: True; dir 0700: 0o700.
```

### Level 4: Creative & Domain-Specific Validation

```bash
# Concurrency: hammer the status endpoint from N threads (the daemon lock must not deadlock,
# the accept loop must keep serving, no malformed responses).
cd /home/dustin/projects/voice-typing
.venv/bin/python - <<'PY'
import json, os, socket, tempfile, threading
from voice_typing import daemon
class Stub:
    l=False
    def toggle(self): self.l=not self.l
    def start(self): self.l=True
    def stop(self): self.l=False
    def request_shutdown(self): pass
    def is_listening(self): return self.l
    def status_snapshot(self): return {"listening":self.l,"partial":"","last_final":"","uptime_s":0.0,"device":"cuda","compute_type":"float16","final_model":"m","realtime_model":"r"}
d=tempfile.mkdtemp(); path=os.path.join(d,"c.sock")
srv=daemon.ControlServer(Stub(), socket_path=path); srv.start()
errs=[]
def worker():
    try:
        for _ in range(50):
            c=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); c.connect(path)
            c.sendall(b'{"cmd":"status"}\n'); data=b""
            while not data.endswith(b"\n"):
                ch=c.recv(4096)
                if not ch: break
                data+=ch
            c.close()
            assert json.loads(data)["ok"] is True
    except Exception as e: errs.append(e)
ts=[threading.Thread(target=worker) for _ in range(8)]
[t.start() for t in ts]; [t.join() for t in ts]
srv.stop()
print("concurrent 400 reqs, errors:", len(errs))
PY
# Expected: concurrent 400 reqs, errors: 0
```

## Final Validation Checklist

### Technical Validation

- [ ] All 4 validation levels completed successfully.
- [ ] `.venv/bin/python -m pytest tests/ -q` green (~159+ passed; S1/S2 test bodies UNCHANGED).
- [ ] `.venv/bin/python -m py_compile voice_typing/daemon.py voice_typing/feedback.py` clean.
- [ ] Import purity: `RealtimeSTT`/`torch`/`ctranslate2` NOT in `sys.modules` after `import
      voice_typing.daemon`.
- [ ] `ruff check` (optional) reports zero errors on the changed files.

### Feature Validation

- [ ] All success criteria from "What" met (a–h).
- [ ] Real socket round-trip (Level 3) returns the documented shapes.
- [ ] Concurrent load (Level 4) produces zero errors.
- [ ] Stale `.sock` recovered; clean `stop()` joins the thread <1 s + unlinks the file.
- [ ] Malformed/non-dict JSON + unknown/missing cmd all reply `{"ok":false,"error":...}`.
- [ ] `status` reflects the LIVE partial (not the throttled disk) + the resolved device/models.

### Code Quality Validation

- [ ] Follows existing codebase patterns (stubs, tmp_path, monkeypatch, `_wait_for`, additive-only
      edits, module-level helpers, `logger = logging.getLogger(__name__)`).
- [ ] File placement matches the desired tree (no new module; ControlServer in daemon.py).
- [ ] Anti-patterns avoided (no close-to-unblock; no settimeout+makefile; no re-probe per call;
      no existing-method edit; no scope creep into main/ctl/recorder.shutdown).
- [ ] No new dependencies (stdlib only); pyproject.toml/uv.lock untouched.

### Documentation & Deployment

- [ ] Code is self-documenting (clear docstrings on ControlServer/status_snapshot/_resolved_device/
      Feedback.snapshot explaining the WHY: select-not-close, in-memory-not-disk, cache-once).
- [ ] No new env vars (socket path is fixed; XDG_RUNTIME_DIR is pre-existing).
- [ ] Logs are informative (device-resolution failure WARNING; on_quit callback exception logged).

---

## Anti-Patterns to Avoid

- ❌ Don't use `socket.settimeout` on the listening socket — `makefile` raises with a timeout; use
  `select` polling instead.
- ❌ Don't rely on closing the listening socket to unblock `accept()` — unreliable on Linux
  (close(2) unspecified; fd-reuse race); use `select` + a stop `Event`.
- ❌ Don't forget to `wfile.flush()` after every response — `makefile("w")` buffers; the client
  hangs forever otherwise.
- ❌ Don't skip the stale-`.sock` unlink — bind raises `EADDRINUSE`; `SO_REUSEADDR` won't help
  (no-op for AF_UNIX path sockets).
- ❌ Don't call `_resolve_device_config` per-status-call — it imports ctranslate2 + probes CUDA;
  cache it once.
- ❌ Don't read the throttled `state.json` for status — it lags ≥10 Hz; read `Feedback.snapshot()`.
- ❌ Don't edit `__init__`/`run`/`on_final`/`_build_callbacks`/`_construct`/`build_recorder` (S1/S2/S3
  own them; additive-only edits keep the merge conflict-free and the regression suite green).
- ❌ Don't build `main()`/`ctl.py`/`recorder.shutdown()`/signal handlers — those are T3/T5/T2.S2.
- ❌ Don't catch bare `Exception` in `_dispatch` without replying `{"ok":false,...}` — the contract
  requires a JSON error response for malformed input (the parse path catches `ValueError`; the
  dispatch path returns `unknown command`).
- ❌ Don't invent four response shapes — uniform `{"ok":true,**status_snapshot()}` for
  toggle/start/stop/status; `{"ok":true,"shutting_down":true}` for quit.

---

## Confidence Score

**9/10** — one-pass implementation success is highly likely. The complete, verified
`ControlServer` / `status_snapshot` / `_resolved_device` / `Feedback.snapshot` source is pinned
above (empirically validated against `.venv/bin/python`, including the non-obvious select-vs-close
and makefile-vs-settimeout traps). The single residual risk is the exact `__init__`/module-top
text after S3 merges — mitigated by (a) S1 touching NONE of S3's symbols (additive-only) and (b)
the Task 2a anchor note covering the S3-merged import block. The validation gates (py_compile,
import-purity grep, pytest, real + concurrent socket round-trips) are executable as written and
catch regressions immediately.
