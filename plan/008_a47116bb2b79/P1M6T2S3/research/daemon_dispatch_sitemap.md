# Daemon control-socket dispatch site map (READ-ONLY recon)

Purpose: everything needed to add a new `session` command to the `{"cmd": ...}` JSON-line
protocol without touching anything else. File: `voice_typing/daemon.py` (3342 lines).

## 1. Dispatch site — `ControlServer._dispatch` (daemon.py:3005–3051)

Class `ControlServer` at **daemon.py:2826**. The dispatch method:

```python
def _dispatch(self, line: str) -> dict:                                    # 3005
    """Parse one request line -> dispatch cmd -> response dict. Never raises (robustness)."""
    try:
        msg = json.loads(line)
    except ValueError as exc:  # json.JSONDecodeError is a ValueError subclass
        return {"ok": False, "error": f"malformed JSON: {exc}"}
    if not isinstance(msg, dict):
        return {"ok": False, "error": "request must be a JSON object"}
    cmd = msg.get("cmd")
```

Handled commands (exact branches):

| cmd | reply | lines |
|---|---|---|
| `toggle`, `toggle-lite` (deprecated alias) | `_arm_response()` when an arm was attempted, else `{"ok": True, **status_snapshot()}` | 3014–3027 |
| `start` | `self._daemon.start()` then `_arm_response()` | 3028–3032 |
| `stop` | `self._daemon.stop()` then `{"ok": True, **status_snapshot()}` | 3033–3035 |
| `cancel` | passthrough `self._daemon.cancel()` (daemon returns `{ok, listening, **status_snapshot}`) | 3036–3039 |
| `status` | `{"ok": True, **self._daemon.status_snapshot()}` | 3040–3041 |
| `quit` | `request_shutdown()` + optional `on_quit()` callback, then `{"ok": True, "shutting_down": True}` | 3042–3049 |

Unknown-command handling (line 3050):

```python
    return {"ok": False, "error": f"unknown command: {cmd!r}"}            # 3050
```

Reply shapes:
- success: `{"ok": True, ...}` — usually `**status_snapshot()` spread on top of `ok`.
- arm failure: `_arm_response()` (daemon.py:2988–3003) returns
  `{"ok": False, "error": f"model load failed: {load_error}"}` when `_load_error` is set and
  not listening; otherwise `{"ok": True, **status_snapshot()}`.
- errors: `{"ok": False, "error": "<text>"}` (malformed JSON / non-dict / unknown cmd).

**Extra unknown payload keys: fully ignored.** The payload is accessed only via
`msg.get("cmd")` (line 3013) — no other key is read, no schema validation, no rejection of
extra fields. A new `session` command may carry additional keys (e.g. `{"cmd":"session",
...}`) without any protocol change; `_dispatch` just won't see them unless the new branch
reads them.

## 2. `status_snapshot()` (daemon.py:2568–2624)

Docstring (2569–2593) documents 18 keys: listening, mode ("lite" constant), phase,
models_loaded, load_error, partial, last_final, uptime_s, device, compute_type, model,
mic_ok, mic_error, context_prompt, delivery_mode, delivery_state, delivery_reason,
last_confirmed_op.

P1.M3.T3.S2 delivery surface excerpt (lines 2618–2623):

```python
            # P1.M3.T3.S2: bulk-delivery status surface (PRD §4.2sexies R.5) — ADDITIVE keys,
            # .get defaults == the Feedback seeds so minimal snapshot() doubles keep working;
            # written only by the bulk wiring (P1.M6.T2.S1).
            "delivery_mode": snap.get("delivery_mode", "stream-edit"),   # 2620
            "delivery_state": snap.get("delivery_state", "inactive"),   # 2621
            "delivery_reason": snap.get("delivery_reason", ""),         # 2622
            "last_confirmed_op": snap.get("last_confirmed_op", ""),     # 2623
```

`snap = self._feedback.snapshot()` (line 2595) — the LIVE in-memory Feedback state, not the
throttled state.json. Safe to call from the socket thread; never raises.

The `status` command reply is line 3041: `return {"ok": True, **self._daemon.status_snapshot()}`
— i.e. the snapshot keys + `ok`.

## 3. `ctl.py format_result` delivery rendering (ctl.py:133–157)

```python
        delivery_mode = response.get("delivery_mode", "") or "unknown"    # 133
        delivery_state = response.get("delivery_state", "") or "unknown"  # 134
        delivery_reason = response.get("delivery_reason", "") or ""       # 135
        delivery_op = response.get("last_confirmed_op", "") or ""         # 136
        ...
            f"delivery: {delivery_mode} ({delivery_state})"               # 153
        if delivery_reason:                                               # 155
            text += f"\ndelivery reason: {delivery_reason}"               # 156
        if delivery_op:
            text += f"\ndelivery op: {delivery_op}"
```

Missing/empty keys read as "unknown" (context_prompt tolerance precedent, per comments at
131–132). `format_result(cmd, response) -> tuple[str, int]` defined at ctl.py:82;
`ok:false` → `("error: ...", 1)` at ctl.py:99.

## 4. Text-field precedent in replies

Yes — `status_snapshot()` already carries free-text fields consumed by ctl.py: `partial`
(daemon.py:2606: `snap.get("partial", "")`), `last_final` (2607), `load_error` (2605),
`mic_error` (2614), `delivery_reason` (2622). ctl.py renders `partial`/`last_final` at lines
~112–113 and 146–147. A `session` reply carrying text fields has direct precedent.

## 5. tests/test_control_socket.py structure

Three layers (module docstring): A) `_dispatch()` logic with `_StubDaemon`, no socket; B) real
AF_UNIX round-trip on `tmp_path` socket via `_send()`; C) lifecycle/hardening. No CUDA, no
daemon process. Key fixtures/helpers:

- `_StubDaemon` (line ~33): duck-typed daemon recording `calls`, canned `status_snapshot()`.
- `server` fixture (line ~104): constructs `daemon.ControlServer(_StubDaemon(), socket_path=str(tmp_path/"control.sock"))`, `start()`, yields `(srv, path)`, `srv.stop()` on teardown.
- `_disp(msg)` helper: `daemon.ControlServer(_StubDaemon())._dispatch(json.dumps(msg))`.
- `_send(path, obj)` / `_send_lines(...)`: one/multi-line client round-trips; `_wait_for` poll helper.
- Exit-code context (ctl.py header, lines 8/55): 1 = daemon `{"ok": false, ...}`, 64 = usage error, 2 = daemon not running.

Representative verbatim tests:

```python
def test_dispatch_toggle():
    r = _disp({"cmd": "toggle"})
    assert r["ok"] is True and r["listening"] is True and "device" in r   # uniform payload


def test_dispatch_unknown_command():
    assert _disp({"cmd": "frobnicate"}) == {"ok": False, "error": "unknown command: 'frobnicate'"}
```

Also relevant: `test_dispatch_status_has_all_keys` asserts the EXACT key set of the status
reply (ok + snapshot keys) — a new `session` command returning `**status_snapshot()` plus
extra keys must not extend the `status` reply itself unless this test is updated.
`test_dispatch_lite_commands_are_unknown_except_toggle_lite_alias` pins the unknown-command
reply format; `test_dispatch_missing_cmd` and `test_dispatch_malformed_json` pin error paths.

## 6. ControlServer construction / threading / socket / timeouts

- Class docstring + protocol block: daemon.py:2826–2845.
- `__init__` (2850–2865): args `daemon, *, socket_path=None, on_quit=None, accept_timeout=0.3`.
  Default path via `_default_control_socket_path()` (468–483):
  `$XDG_RUNTIME_DIR/voice-typing/control.sock` (constant `_CONTROL_SOCKET_SUBPATH` at 465);
  raises RuntimeError if XDG_RUNTIME_DIR unset.
- `start()` (2869–2905): makedirs 0700, unlink stale .sock, bind AF_UNIX SOCK_STREAM, chmod
  0600, listen(8), launch daemon `threading.Thread(target=self._accept_loop,
  name="voice-typing-control")`.
- `_accept_loop()` (2932–2949): `select()` polling with `accept_timeout` (NOT
  close-to-unblock, NOT settimeout — makefile() incompatible); one daemon worker thread per
  connection: `threading.Thread(target=self._handle, args=(conn,), daemon=True).start()`.
- `_handle()` (2951–2986): per-connection `conn.makefile("r"/"w", encoding="utf-8",
  newline="\n")` readline loop; every request line (even empty — BUG-005) gets exactly one
  `json.dumps(response) + "\n"` reply, flushed; breaks after a `shutting_down` reply.
- `stop()` (2907–2930): set stop Event, close socket, join ≤2 s, unlink path.
- **Read timeout: NONE.** The socket is timeout-less by design — documented in the docstring;
  this is why voicectl calls must always be wrapped in `timeout 30` per AGENTS.md.
- Constructed in `main()` (~daemon.py:3289): `server = ControlServer(daemon, on_quit=daemon.shutdown)`; started after signal handlers; `server.stop()` in the final teardown (main thread only).

## Where a `session` command plugs in

Add one branch in `_dispatch` before the unknown-command fallthrough (before line 3050), e.g.
after the `cancel`/`status` branches, reading any extra keys via `msg.get(...)` (ignored-key
behavior is already the norm). Returning `{"ok": True, **self._daemon.status_snapshot(),
...extra}` matches the uniform-payload precedent; a dedicated shape like `cancel`'s passthrough
also has precedent. Tests: add `_disp`-layer tests in tests/test_control_socket.py mirroring
`test_dispatch_toggle` / `test_dispatch_unknown_command`; extend `_StubDaemon` with the daemon
method. ctl.py-side: add to `_COMMANDS` (validated in `main()` at ctl.py:267, exit 64
otherwise) and a `format_result` branch following the delivery rendering pattern.
