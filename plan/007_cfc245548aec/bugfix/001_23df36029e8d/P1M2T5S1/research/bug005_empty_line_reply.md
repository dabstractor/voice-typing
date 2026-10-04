# P1.M2.T5.S1 research — BUG-005: control socket empty-line reply

Source: `voice_typing/daemon.py` (ControlServer) + `tests/test_control_socket.py`, read directly.

## Defect
`ControlServer._handle` (daemon.py:2477-2479): the per-connection readline loop strips each line
and `continue`s on empty/whitespace-only lines WITHOUT writing a response. Every other malformed
request gets exactly one JSON error line (`_dispatch`, daemon.py:2520-2522:
`{"ok": false, "error": f"malformed JSON: {exc}"}`). A client that sends a bare newline then
reads blocks forever — acute here because the control socket has NO read timeout (AGENTS.md
wedge hazard class; `ctl.py` uses `sock.makefile("r")`). Verified live in the bug report:
`printf '\n' | timeout 5 nc -U $XDG_RUNTIME_DIR/voice-typing/control.sock` → no reply.

## Fix shape (minimal, matches the bug report recommendation)
Replace the silent `continue` with the malformed-JSON error reply — simplest correct shape is to
fall through to `self._dispatch("")`, whose `json.loads("")` raises ValueError → returns
`{"ok": false, "error": "malformed JSON: Expecting value: line 1 column 1 (char 0)"}`. Either
call `_dispatch(line)` on the empty string or write an explicit
`{"ok": false, "error": "malformed JSON: empty request"}`; both satisfy the contract "one
response line per request line". Semantics decision: EVERY empty/whitespace-only request line is
now a request (gets an error reply) — a client sending a trailing bare newline after its real
request gets one extra error line it will ignore (voicectl sends exactly one line and reads one;
no current client sends blank lines, so no regression). `shutting_down` handling unaffected (the
error dict has no such key → loop continues normally).

## Test seams (all exist in tests/test_control_socket.py)
- `_disp(line)` helper: direct `_dispatch` calls (test_dispatch_malformed_json pattern, line ~178).
- `server` fixture + `_send(path, bytes)` / `_send_lines(path, *dicts)` wire helpers
  (test_round_trip_malformed_over_wire, ~line 203; test_round_trip_multi_line_one_connection ~210).
  `_send` writes raw bytes and reads one reply line — perfect for `b"\n"` and `b"   \n"`.
- Also relevant: ctl.py client exit-code behavior unchanged; no ctl change needed.

## Gotchas
- AGENTS.md discipline: voicectl/nc probes against a live daemon always under `timeout`.
- Keep the flush (`wfile.write(...); wfile.flush()`) — makefile("w") buffers.
- Do not change the `shutting_down` break or the OSError swallow paths.
