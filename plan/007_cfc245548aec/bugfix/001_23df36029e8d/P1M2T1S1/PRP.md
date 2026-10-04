# PRP — P1.M2.T5.S1 (BUG-005): Daemon: empty-line request gets a malformed-JSON error reply

## Goal

**Feature Goal**: Fix **BUG-005** (Minor): `ControlServer._handle` (daemon.py:2465) silently skips empty/whitespace-only request lines (`if not line: continue`, :2474-2475) — on this no-read-timeout control socket (ctl.py `send_command`; the AGENTS.md wedged-socket hazard class) any client that writes an empty line then reads **hangs forever**, while every other malformed request gets a JSON error line. Replace the silent `continue` with a reply in the **same error shape** — `{"ok": false, "error": "malformed JSON: empty request line"}` — and keep serving subsequent lines on the same connection.

**Deliverable** (2 files, TDD):
1. `tests/test_control_socket.py` — ONE new **round-trip** test (written FIRST, RED): one connection sends `b"\n"` + `b"   \n"` + a valid `status` request; each empty line must yield exactly one JSON error reply line and the status must still answer. Verbatim below.
2. `voice_typing/daemon.py` — the `_handle` empty-line branch replies instead of `continue` (verbatim oldText→newText below); one row added to the ControlServer class-docstring behavior table (~:2359). README **unchanged** (verified: "Logs, status, stopping" :339 does not document request framing).

**Success Definition**:
- (a) The new test is RED before the daemon.py edit (no reply lines for the empty inputs → readline blocks/fails) and GREEN after (2 error lines + 1 ok status).
- (b) Each empty/whitespace-only line yields exactly one `{"ok": false, "error": "malformed JSON: empty request line"}` reply; the connection keeps serving (the later `status` line still answers `{"ok": true, ...}`).
- (c) `timeout 60 .venv/bin/python -m pytest tests/test_control_socket.py -q` → all pass (existing + 1 new); the full fast sweep stays green.
- (d) Only `voice_typing/daemon.py` + `tests/test_control_socket.py` changed; `_dispatch`, the quit-break, and the accept loop are untouched.

## User Persona

Not applicable (wire-protocol robustness; no user-facing surface — DOCS: Mode A = the class-docstring row).

## Why

- **Silence is the worst reply on a socket with no read timeout.** The PRD validation proved it live: `printf '\n' | timeout 5 nc -U …/control.sock` → nothing for 5s, while `not json at all` returns an error object. Any script/client that emits a stray newline before its JSON (or probes with an empty line) wedges. The AGENTS.md hazard table documents this exact class (untimed control-socket reads hang forever).
- **Consistency with the documented contract**: the class docstring says "Robust to malformed JSON" and every other malformed request is answered — the empty line is the lone silent case. One reply makes the "one request line → one response line" invariant hold universally, which is what line-oriented clients (voicectl, nc, tests) rely on.

## What

`_handle`'s empty-line branch becomes an inline error reply (same shape as `_dispatch`'s malformed-JSON reply) instead of `continue`; the loop continues to the next line. No change to `_dispatch`, the `shutting_down` break, buffering/flushing discipline, or the accept loop.

### Success Criteria

- [ ] `b"\n"` and `b"   \n"` each get exactly one `{"ok": false, "error": "malformed JSON: empty request line"}` reply.
- [ ] A later valid line on the SAME connection still answers (no close/break).
- [ ] New round-trip test RED→GREEN; existing control-socket tests green; full fast sweep green.
- [ ] Docstring table row added; README untouched; only the 2 files changed.

## All Needed Context

### Context Completeness Check

_Pass._ The verbatim `_handle` loop (daemon.py:2465-2486), the verbatim fix, the `_dispatch` error shape (:2518), the docstring-table row site (~:2359), the round-trip test machinery (`server` fixture, `socket`/`json` imports, per-line flush determinism), and the README no-change verification are all below + in the research note.

### Documentation & References

```yaml
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M2T1S1/research/empty_line_reply.md
  why: "§1 the bug (live-verified hang). §2 the verbatim fix site. §3 why the test must be round-trip
        (the continue is in _handle, upstream of _dispatch — test_dispatch_malformed_json can't see it).
        §4 docs. §5 scope/parallel."
- file: voice_typing/daemon.py
  why: "_handle @2465: the loop at :2472-2476 (strip → if not line: continue → _dispatch → write+flush).
        _dispatch @2510: the malformed-JSON reply shape f'malformed JSON: {exc}'. Class docstring table
        ~:2355-2365 (rows: valid cmds / malformed JSON / non-dict / unknown cmd) — add the empty-line row
        after 'malformed JSON'."
  critical: "Reply from _handle (the empty line never reaches _dispatch). Keep serving — no break/close.
             The error dict has no 'shutting_down' key, so the quit-break is unaffected."
- file: tests/test_control_socket.py
  why: "The `server` fixture (in-process ControlServer on tmp_path) used by test_round_trip_*; `socket` +
        `json` already imported; _send_lines :80 shows the one-connection multi-line pattern. The new test
        opens its own connection and reads exactly 3 reply lines (each reply is flushed per line)."
  gotcha: "test_dispatch_malformed_json (:178) drives _dispatch directly — useless for this bug. The test
           MUST be round-trip."
- file: plan/007_cfc245548aec/bugfix/001_23df36029e8d/prd_snapshot.md  # h2.3/h3.4 Issue 1 (BUG-005) — the live repro
- docfile: plan/007_cfc245548aec/bugfix/001_23df36029e8d/P1M1T4S1/PRP.md  # parallel: _on_partial gate (daemon.py ~1390, test_daemon.py) — NO overlap
```

### Known Gotchas

```python
# CRITICAL #1 — FIX _handle, NOT _dispatch. The empty line is stripped-and-continued upstream (:2474);
#   _dispatch never sees it. Test at round-trip level for the same reason.
# CRITICAL #2 — KEEP SERVING: no break/close after the reply — the contract requires a later valid line
#   on the same connection to still answer.
# CRITICAL #3 — Same error shape/wording as _dispatch's ('malformed JSON: …') so clients/tests can treat
#   all malformed input uniformly. The reply dict has no 'shutting_down' — the quit-break is unaffected.
# GOTCHA #4 — Do NOT touch _dispatch, the accept loop, buffering, or the quit path. README :339 does NOT
#   document request framing (verified) — no README edit.
# GOTCHA #5 — Full paths + functional `timeout` on every command (AGENTS.md); pytest>=9.1.1, NO ruff/mypy.
```

## Implementation Blueprint

### Implementation Tasks

```yaml
Task 1: ADD the failing round-trip test to tests/test_control_socket.py (RED — FIRST)
  - APPEND at end of file (verbatim):
        def test_round_trip_empty_line_gets_error_reply_and_keeps_serving(server):
            """BUG-005: a bare/whitespace-only line previously got NO reply (silent continue in _handle),
            hanging any client that reads on this no-read-timeout socket. It must get one malformed-JSON
            error line (same shape as other malformed requests) and the connection must keep serving."""
            _srv, path = server
            c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            c.connect(path)
            try:
                c.sendall(b"\n   \n" + json.dumps({"cmd": "status"}).encode() + b"\n")
                r = c.makefile("r")
                e1 = json.loads(r.readline())
                e2 = json.loads(r.readline())
                ok = json.loads(r.readline())
            finally:
                c.close()
            assert e1["ok"] is False and "empty request line" in e1["error"]
            assert e2["ok"] is False and "empty request line" in e2["error"]
            assert ok["ok"] is True and ok["device"] == "cuda"  # connection kept serving
  - RUN (RED check): `timeout 60 .venv/bin/python -m pytest tests/test_control_socket.py -q -k empty_line`
    → EXPECTED: it FAILS (no reply for the empty lines — the first readline sees the status reply
    instead, or blocks; either way the assertions fail). This proves the test catches the bug.
  - DO NOT: test _dispatch directly (it can't see the bug); use a live daemon/voicectl.

Task 2: EDIT voice_typing/daemon.py — the _handle empty-line branch replies (GREEN)
  - EDIT (oldText → newText):
      OLD:
                    for line in rfile:  # one JSON object per line (PRD §4.2(3))
                        line = line.strip()
                        if not line:
                            continue  # empty line -> skip (no response)
                        response = self._dispatch(line)
                        wfile.write(json.dumps(response) + "\n")
                        wfile.flush()  # CRITICAL: makefile("w") buffers; flush every reply
      NEW:
                    for line in rfile:  # one JSON object per line (PRD §4.2(3))
                        line = line.strip()
                        if not line:
                            # BUG-005 (bugfix validation): a bare/whitespace-only line previously got NO
                            # reply (continue) — on this no-read-timeout socket any client that writes an
                            # empty line then reads hangs forever (verified live: b'\n' -> silence for 5s).
                            # Reply in the SAME error shape as other malformed requests and KEEP SERVING
                            # this connection (no break/close — a later valid line still answers).
                            response = {"ok": False, "error": "malformed JSON: empty request line"}
                        else:
                            response = self._dispatch(line)
                        wfile.write(json.dumps(response) + "\n")
                        wfile.flush()  # CRITICAL: makefile("w") buffers; flush every reply
  - EDIT the ControlServer class docstring table (~:2359): after the
    `malformed JSON -> {"ok":false,"error":"malformed JSON: ..."}` row, add:
        empty/whitespace-only line -> {"ok":false,"error":"malformed JSON: empty request line"}
  - DO NOT: touch _dispatch/the accept loop/the quit-break/flush discipline; close the connection
    after the error; edit README (:339 doesn't document framing — verified).

Task 3: VALIDATE.
  - `timeout 60 .venv/bin/python -m pytest tests/test_control_socket.py -q` → all pass (+1).
  - `timeout 150 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q` → 0 failed.
  - `git status --short` → ONLY the 2 files. Message if committed:
    "P1.M2.T5.S1/BUG-005: reply to empty control-socket request lines (malformed-JSON shape) + round-trip test".
```

### Integration Points

```yaml
DOWNSTREAM — wire contract: every request line (incl. empty) now yields exactly one response line;
  voicectl (one-shot line per connection) and the round-trip tests are unaffected (they never send
  empty lines); the fix only ADDS replies where there was silence.
UNCHANGED: _dispatch (all its replies), the accept loop (one worker per connection), the quit path
  (the error reply has no shutting_down key), ctl.py, README.
PARALLEL — P1.M1.T4.S1: _on_partial listening gate (daemon.py ~1390 + test_daemon.py) — disjoint.
```

## Validation Loop

```bash
cd /home/dustin/projects/voice-typing
timeout 60 .venv/bin/python -m pytest tests/test_control_socket.py -q -k empty_line   # GREEN (was RED)
timeout 60 .venv/bin/python -m pytest tests/test_control_socket.py -q                # all pass
timeout 150 .venv/bin/python -m pytest tests/ --ignore=tests/test_feed_audio.py -q   # 0 failed
git status --short    # ONLY voice_typing/daemon.py + tests/test_control_socket.py
```

## Final Validation Checklist

- [ ] Empty + whitespace-only lines each get exactly one `malformed JSON: empty request line` reply; the same connection still serves `status`.
- [ ] New test RED→GREEN; `_dispatch`/quit-break/accept-loop untouched; docstring row added; README untouched.
- [ ] control-socket suite + full fast sweep green; only 2 files changed.

## Anti-Patterns to Avoid

- ❌ Don't fix `_dispatch` or test it directly — the `continue` is in `_handle`, upstream of `_dispatch`.
- ❌ Don't close/break the connection after the error reply (must keep serving).
- ❌ Don't invent a new error shape — mirror `_dispatch`'s `malformed JSON: …` wording.
- ❌ Don't edit README (its :339 section doesn't document request framing — verified).
- ❌ No pytest without `timeout`; no bare python/pytest (zsh aliases); no ruff/mypy.

---

## Confidence Score

**10/10** — the verbatim oldText/newText for the exact buggy loop, the verbatim RED→GREEN round-trip test (with the why-round-trip rationale), the docstring row, the verified README no-change, and the disjoint parallel boundary are all pinned; behavior is purely additive (replies where there was silence).
