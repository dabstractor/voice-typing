# Research — P1.M4.T1.S2: IM subprocess lifecycle (spawn/monitor/teardown + unavailable handling)

All facts verified against the live repo + the S1 transport PRP (the contract) on this machine.

## 1. The two consumed contracts

### 1a. S1 transport (`voice_typing/ime/`, P1.M4.T1.S1 — in parallel; treat as landed)
- `voice_typing/ime/protocol.py` — PURE (json only; imports without WAYLAND_DISPLAY):
  `REQUEST_CMDS = ("acquire","show","verify","leave","ping")` (`cancel` reserved), `SHOW_RESULTS`,
  `encode(obj)->bytes` (JSON + `\n`), `decode(line)->dict` (raises `ProtocolError` on bad JSON),
  `make_reply(id, cmd, **fields)`, `make_error(id, message)`, `make_event(name, **fields)` (id-less
  `{"ev":..., "t_ms":...}`), `validate_request(obj)->(cmd|None, error|None)`, `EventLogWriter`
  (64 KiB cap), `ProtocolError(ValueError)`.
- `voice_typing/ime/ime_host.py` — `main(argv)`: log path from `argv[1]` (default
  `$XDG_RUNTIME_DIR/voice-typing/ime-events.jsonl` best-effort); `ImeHost.serve()` reads
  **stdin** line-by-line, writes replies/events to **stdout** (flush); every request `id` gets
  exactly ONE reply echoing it; unknown request → error reply, keeps serving; async events are
  id-less `{"ev":...}` lines that interleave arbitrarily; **`unavailable` event → clean `exit(0)`**
  (one-IM-per-seat; "S2 marks the route unavailable" — verbatim S1 fence note).
- S1 PRP Integration seam, verbatim: **"P1.M4.T1.S2: spawns `python -m voice_typing.ime.ime_host
  <log>`; monitors via ping; owns teardown."**
- Fences S1 set for THIS task: no acquire/show semantics (T2/T3), no takeover policy (T4), no
  daemon/feedback edits, tools/im-lab untouched, stdlib only (no pyproject change).

### 1b. Status surface (P1.M3.T3.S2 — LANDED, verified in `voice_typing/feedback.py`)
- `feedback.set_delivery_state(state, reason="")` — taxonomy `_DELIVERY_STATES =
  ("inactive","active","unsupported","fault")`; `reason` ALWAYS overwritten, sanitized
  (whitespace-collapsed, ≤160 chars, counts/times — never recognition text). Docstring maps:
  acquire failure → `unsupported` + the reason; fault-ish stop reasons → `fault`; clean stop →
  `inactive`; successful acquire → `active`.
- **`set_delivery_state` is "Written ONLY by the bulk-delivery wiring (P1.M6.T2.S1)"** — so the
  manager MUST NOT import Feedback; it emits transitions through an injected
  `on_delivery_state(state, reason)` callback that M6.T2.S1 binds to `feedback.set_delivery_state`
  (duck-typed seam, mirroring how recorder_host takes callbacks instead of Feedback).

## 2. The canonical subprocess pattern (`voice_typing/recorder_host.py` — mirror it)

Verified facts (file:line):
- Child is its own process-group leader so teardown can `killpg`: recorder_host's child calls
  `os.setsid()` (:535). **With `subprocess.Popen` the equivalent is `start_new_session=True`** —
  simpler and does the setsid in the parent at fork time.
- Bounded teardown: `_STOP_JOIN_TIMEOUT_S = 5.0` (:102); `stop(timeout=...)` is **single-flight
  under `_stop_lock`** (:140/:169, bugfix Issue 1): graceful signal → join(5) → `_terminate_group()`
  = `os.killpg(os.getpgid(pid), SIGKILL)` (:470-483), with the comment that a wedged child is
  force-killed regardless of its own shutdown behavior.
- `spawn(timeout) -> bool`: waits a bounded readiness (`_SPAWN_READY_TIMEOUT_S`); on child-reported
  error → `_terminate_group()`, `_dead=True`, return False. No half-constructed state.
- Liveness: `is_alive` property (`_dead` flag + proc state); the DAEMON's run() loop polls
  `host.is_alive()` and calls `_handle_dead_host()` on death (Issue-3 recovery pattern in
  daemon.py) — **my manager similarly surfaces death via a transition, it does not restart.**
- RecorderHost uses multiprocessing queues; the IM host instead speaks **JSONL over stdin/stdout
  pipes** (S1 contract) → the manager is a `subprocess.Popen`-based correlating duplex driver.

## 3. The seat-IM exclusivity facts (why `unsupported` is a state, not an error)

- PRD R.2 / d2 map §5 open item: "one-IM-per-seat collision (`unavailable` event) must degrade
  gracefully (delivery_state `unsupported`/`fault` per §4 recipe)"; d2 §9 risk 3 repeats it with
  "a user IME (fcitx5) would conflict".
- Item contract: a user IME holding the seat sends `unavailable` → report
  `delivery_state=unsupported` with ONE reason, **never displace/disable the user's IME, no
  auto-retry fighting it (stay unsupported until the next arm)**. I.e. the manager must NOT loop
  respawn attempts against fcitx5 — that would be a spawn/restart fight over the seat.
- Distinguish from crash: the `unavailable` EVENT is the unsupported signal (S1 host exits 0 after
  it); unexpected EOF with rc≠0 (or rc==0 without `unavailable`) = **fault** ("IM process crash =
  delivery fault, not daemon death"). A DELIBERATE stop() must emit NOTHING (no spurious fault) —
  the caller/wiring owns the stop→inactive transition.

## 4. Design pinned — `voice_typing/ime/manager.py` (`ImeProcess`)

State machine (terminal-until-next-spawn for the failure states):
`IDLE` → spawn() → `STARTING` (await ping reply) → `RUNNING` → { `UNSUPPORTED` (unavailable) |
`FAULT` (crash/spawn-timeout) | stop() → `IDLE` }.

- `__init__(self, on_delivery_state=None, on_event=None, python_exe=None, log_path=None,
  spawn_timeout=10.0, stop_timeout=5.0)`. `on_delivery_state(state, reason)` is the feedback seam
  (unsupported/fault ONLY — active/inactive belong to T2/M6). `on_event(ev_dict)` is the T4
  takeover feed (id-less `{"ev":...}` lines forwarded as parsed dicts). All injectable → pure tests.
- `spawn(timeout=None) -> bool`: Popen `[python_exe or sys.executable, "-m",
  "voice_typing.ime.ime_host"]` (+ log_path arg when given) with `stdin=PIPE, stdout=PIPE,
  stderr=None` (child stderr → journald), **`start_new_session=True`**; start the reader thread;
  send one `ping` (id=1) and require its id-echo reply within `spawn_timeout` → RUNNING/True;
  timeout or child death during STARTING → bounded teardown, `FAULT` + reason
  `"ime subprocess not ready in {t}s"` (or the child's rc), False. **Idempotent guard: if already
  RUNNING → True; if UNSUPPORTED/FAULT → allowed (that IS the next-arm respawn) after implicit
  stop().**
- Reader thread (sole stdout consumer): `for line in proc.stdout` → `protocol.decode`;
  reply-with-`id` → resolve the pending request (Event + store); `{"ev":...}` → forward to
  `on_event`; **`ev == "unavailable"` → latch `_unavailable=True`, emit
  `on_delivery_state("unsupported", "seat input-method unavailable: another input method holds the
  seat")`; NO respawn.** EOF: if deliberate-stop latched → silent; elif `_unavailable` → silent
  (already emitted); else → `FAULT` + `"ime subprocess exited (rc=N)"`. EOF also fails all pending
  requests.
- `request(cmd, timeout=1.0, **fields) -> dict | None`: next id under `_send_lock`;
  `protocol.encode` → stdin write+flush; wait the per-id Event ≤ timeout; None on timeout or dead
  child (**no resend, ever** — R.5's never-retry law). This is the core T2/T3 call.
- `healthy() -> bool`: RUNNING and one short ping round-trip (the S1 "monitors via ping" seam;
  also used by arm-time re-check in M6).
- `stop(timeout=None) -> None`: **single-flight under `_stop_lock`** (bugfix Issue-1 lesson):
  latch deliberate-stop; SIGTERM (proc.terminate) → `proc.wait(stop_timeout)` → still alive →
  `os.killpg(os.getpgid(pid), SIGKILL)` guarded by `except OSError: proc.kill()` (fake pids in
  tests raise ProcessLookupError → fallback). No-op when IDLE. Emits NO delivery_state.
- Constants: `_DEFAULT_SPAWN_TIMEOUT_S = 10.0`, `_DEFAULT_STOP_TIMEOUT_S = 5.0`,
  `_REQUEST_TIMEOUT_S = 1.0`.
- Purity: imports only stdlib + `voice_typing.ime.protocol`. NEVER imports Feedback/daemon.
  `import voice_typing.ime.manager` must work with no WAYLAND_DISPLAY and no child spawned.

## 5. Test strategy (`tests/test_ime_manager.py`) — no compositor, no real subprocess

`_FakeProc` double with REAL `os.pipe()` streams (blocking reader is genuinely exercised):
`stdin` = the parent write end wrapped to also record writes; `stdout` = read end; `pid` (large
fake int → `os.getpgid` raises → killpg fallback path), `terminate/wait/poll/kill` recorders;
`returncode`; a `kill_and_close()` helper that closes the write end (→ reader EOF). A test-side
writer thread pushes scripted reply/event lines. Cases:
1. import purity (no WAYLAND_DISPLAY; no child).
2. spawn readiness: scripted ping reply → True, RUNNING; request ids start at 1.
3. spawn timeout → False + FAULT + `on_delivery_state("fault", …)` + teardown called.
4. request: id echo correlation; a late/other-id reply is ignored; timeout → None; NO bytes
   re-sent (count writes).
5. event forwarding: `{"ev":"surrounding_text",…}` line → `on_event` got the parsed dict.
6. **unavailable: event → `unsupported` with ONE reason; then EOF(rc=0) stays silent (no fault);
   no respawn (poll/kill call counts unchanged).**
7. crash: EOF rc=1 with no unavailable → `FAULT` + reason contains rc.
8. deliberate stop: `stop()` then EOF → NO transition emitted (only the pre-stop none).
9. stop single-flight + bounded: two concurrent stops → one terminate/killpg sequence; killpg
   fallback (`_FakeProc.kill` recorded when `os.getpgid(fake_pid)` fails); stop when IDLE → no-op.
10. request after death → None immediately (pending failed by EOF).

## 6. Validation gates (project-specific, verified executable)

- `timeout 120 .venv/bin/python -m pytest tests/test_ime_manager.py -q` (+ the S1 ime suites if
  landed: `tests/test_ime_protocol.py` must stay green — manager consumes protocol).
- Import purity: `env -u WAYLAND_DISPLAY .venv/bin/python -c "import voice_typing.ime.manager"`.
- Scope guard: `git status --porcelain` shows ONLY `voice_typing/ime/manager.py` +
  `tests/test_ime_manager.py`; `git diff --stat tools/im-lab | wc -l` → 0; daemon.py/feedback.py/
  bulk_*/config/pyproject untouched.
- AGENTS.md discipline: every command under GNU `timeout` + `.venv/bin/python`; no daemon
  foreground; no compositor in tests.
