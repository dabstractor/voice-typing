# Research: empty-line control-socket reply (P1.M2.T5.S1 / BUG-005)

## 1. The bug (verified in code)

`ControlServer._handle` (daemon.py:2465) strips each line and runs `if not line: continue  # empty
line -> skip (no response)` — so a bare `b"\n"` or whitespace-only line gets NO reply. Every other
malformed request IS answered (`_dispatch` :2518 `{"ok": False, "error": f"malformed JSON: {exc}"}`),
but the empty line never even reaches `_dispatch` (the `continue` is upstream). On this no-read-timeout
socket (ctl.py `send_command` + the AGENTS.md wedged-socket hazard class) any client that writes an
empty line then reads **hangs forever**. Verified live in the bug report: `printf '\n' | timeout 5 nc
-U …/control.sock` → silence for 5s, while `not json at all` returns an error object.

## 2. The fix (verbatim site — daemon.py:2472-2476)

Current:
```python
                for line in rfile:  # one JSON object per line (PRD §4.2(3))
                    line = line.strip()
                    if not line:
                        continue  # empty line -> skip (no response)
                    response = self._dispatch(line)
                    wfile.write(json.dumps(response) + "\n")
                    wfile.flush()  # CRITICAL: makefile("w") buffers; flush every reply
```
Replace the `continue` branch with an inline reply in the SAME error shape, and KEEP SERVING the
connection (no close/break; a later valid line on the same connection still answers). The reply has
no `shutting_down` key, so the quit-break is unaffected. See the PRP Task 2 for the exact newText.

## 3. Why the test is ROUND-TRIP level (not `_dispatch`)

`test_dispatch_malformed_json` (test_control_socket.py:178) drives `_dispatch` directly and passes —
an empty line never reaches `_dispatch`. The `continue` lives in `_handle`, so only a real
socket round-trip exercises it. The file already has the right machinery: the `server` fixture
(in-process ControlServer on a tmp_path socket), `socket`/`json` imports, and multi-line
one-connection helpers (`_send_lines` :80 sends several lines on one connection). The new test opens
its own connection (mirroring `_send_lines`), sends `b"\n   \n" + status-line`, and reads exactly 3
reply lines (each reply is flushed per line — `wfile.flush()` — so per-line reads are deterministic).

## 4. Docs (Mode A)

- **ControlServer class docstring behavior table** (~daemon.py:2355-2365) — add a row after the
  `malformed JSON` row: `empty/whitespace-only line -> {"ok":false,"error":"malformed JSON: empty
  request line"}`.
- **README :339** ("Logs, status, stopping") — verified: it does NOT document request framing
  (journald + stop instructions only) → **no README change**.
- Class docstring intro line :2347 says "Robust to malformed JSON…" — still true.

## 5. Scope + parallel

- Files: `voice_typing/daemon.py` (_handle branch + one docstring row) + `tests/test_control_socket.py`
  (1 round-trip test). Nothing else.
- P1.M1.T4.S1 (parallel, Implementing): `_on_partial` listening gate — daemon.py ~:1390 +
  test_daemon.py. Disjoint from `_handle` (:2465) / the docstring (:2355) / test_control_socket.py.
- pytest>=9.1.1; NO ruff/mypy. Full paths + functional `timeout` (AGENTS.md).
