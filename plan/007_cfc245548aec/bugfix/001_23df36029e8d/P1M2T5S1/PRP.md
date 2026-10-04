name: "P1.M2.T5.S1 — BUG-005: control socket replies to empty request lines (malformed-JSON error)"
description: One-line protocol fix — every request line (including empty/whitespace-only) gets exactly one JSON response line, so no client can hang on the timeout-less control socket.

---

## Goal

**Feature Goal**: A client that sends an empty or whitespace-only request line to the control socket receives an immediate `{"ok": false, "error": "malformed JSON: ..."}` reply — identical treatment to any other malformed request — instead of silence.

**Deliverable**: Modified `ControlServer._handle` in `voice_typing/daemon.py` (~lines 2477-2479) plus regression tests in `tests/test_control_socket.py`.

**Success Definition**: `b"\n"` and `b"   \n"` over the wire each yield one JSON error line; every other behavior (valid dispatch, malformed JSON, multi-line connections, quit/shutting_down, OSError swallow) is unchanged; full fast unit suite green.

## User Persona (if applicable)

**Target User**: Script/automation authors talking to `$XDG_RUNTIME_DIR/voice-typing/control.sock` (and `voicectl` itself).

**Use Case**: A client writes a request line then blocks reading the response.

**Pain Points Addressed**: A bare newline currently gets NO response, and the socket has no read timeout — the client hangs forever (AGENTS.md wedge hazard class). Verified live: `printf '\n' | timeout 5 nc -U .../control.sock` times out.

## Why

- Protocol consistency: the codebase already promises every malformed request one error line (`_dispatch` returns `malformed JSON: ...` for `garbled\n`); empty lines are the only silent case.
- Safety: this repo's AGENTS.md specifically documents control-socket wedging as a session-hang vector; a no-reply path on a timeout-less socket is the cheapest possible hang.

## What

In `ControlServer._handle`'s readline loop, an empty (after `.strip()`) request line currently hits `continue  # empty line -> skip (no response)`. Change it to produce and write the standard malformed-JSON error response.

### Success Criteria

- [ ] `{"cmd":"status"}` etc. unchanged (existing round-trip tests still pass).
- [ ] Sending `b"\n"` over a real socket connection returns one line: JSON with `ok: false` and an `error` starting with `malformed JSON`.
- [ ] Whitespace-only line (`b"   \n"`) behaves identically.
- [ ] Multi-line single-connection flows still get exactly one response per request line (now including empty ones); `quit`'s `shutting_down` break unaffected.
- [ ] `timeout 120 .venv/bin/pytest tests/test_control_socket.py -q` green; full fast suite green.

## All Needed Context

### Context Completeness Check

The change is ~3 lines in one function plus tests; everything needed (exact current code, helpers, fixtures) is quoted/anchored below.

### Documentation & References

```yaml
- file: voice_typing/daemon.py
  why: ControlServer._handle, the readline loop to change (around lines 2477-2479)
  pattern: current code:
      for line in rfile:  # one JSON object per line (PRD §4.2(3))
          line = line.strip()
          if not line:
              continue  # empty line -> skip (no response)
          response = self._dispatch(line)
          wfile.write(json.dumps(response) + "\n")
          wfile.flush()  # CRITICAL: makefile("w") buffers; flush every reply
          if response.get("shutting_down"):
              break
  fix: replace the `continue` branch so an empty line ALSO goes through _dispatch — the
       simplest correct form is to DELETE the empty-line special case entirely and always
       `response = self._dispatch(line)`: json.loads("") raises ValueError, and _dispatch
       (line ~2520-2522) already maps that to {"ok": false, "error": "malformed JSON: <exc>"}.
       (Equivalent alternative: keep the branch and write an explicit
       {"ok": false, "error": "malformed JSON: empty request"} + flush.) Either shape is
       accepted; deleting the branch is the least-code option and reuses the tested error path.
  gotcha: PRESERVE the per-reply `wfile.flush()` and the `shutting_down` break; do NOT touch the
       OSError swallow / finally close paths.

- file: voice_typing/daemon.py
  why: ControlServer._dispatch (lines ~2518-2522) — the existing malformed-JSON error mapping the fix reuses:
      try: msg = json.loads(line)
      except ValueError as exc: return {"ok": False, "error": f"malformed JSON: {exc}"}

- file: tests/test_control_socket.py
  why: test patterns to extend — `_disp(line)` direct-dispatch helper (test_dispatch_malformed_json, ~line 178) and the `server` fixture + `_send(path, bytes)` / `_send_lines(path, *dicts)` wire helpers (test_round_trip_malformed_over_wire ~line 203, test_round_trip_multi_line_one_connection ~line 210)
  pattern: add (a) `test_dispatch_empty_line` via `_disp("")` asserting ok False + error startswith "malformed JSON:", and (b) `test_round_trip_empty_line_gets_error_reply(server)` using `_send(path, b"\n")` plus a whitespace-only `b"   \n"` case; optionally a multi-line case (valid, empty, valid → 3 replies) proving the loop survives an error reply mid-connection
  gotcha: `_send` writes raw bytes and reads ONE reply line — that is exactly the hang the fix removes; before the fix these tests block/timeout, after it they pass

- file: AGENTS.md (repo root)
  why: timeout discipline — any live-socket probe (nc/voicectl) must run under `timeout 30`; pytest under `timeout 600` with a higher bash-tool timeout
```

### Current Codebase tree (relevant slice)

```bash
voice_typing/daemon.py            # ControlServer._handle (the fix), _dispatch (error path reused)
tests/test_control_socket.py      # _disp helper, server fixture, _send/_send_lines wire helpers
```

### Desired Codebase tree with files to be added

```bash
voice_typing/daemon.py            # MODIFIED — _handle empty-line branch removed/replaced
tests/test_control_socket.py      # MODIFIED — 2-3 new regression tests
# no new files
```

### Known Gotchas of our codebase & Library Quirks

```python
# CRITICAL (AGENTS.md): the control socket has NO read timeout — this bug is precisely a
#   client-hang vector; test it with the in-process `server` fixture, not a live daemon.
# CRITICAL: every reply needs wfile.flush() (makefile("w") buffers).
# GOTCHA: line.strip() runs first, so "   \n" must take the same path as "\n".
# GOTCHA: keep "one response line per request line" invariant — including the new error
#   replies — so multi-line clients stay in lockstep.
# GOTCHA: ctl.py (voicectl) sends exactly one well-formed line; no client change needed.
```

## Implementation Blueprint

### Data models and structure

No new data models. Response contract unchanged: one JSON object per line out.

### Implementation Tasks (ordered by dependencies)

```yaml
Task 1: MODIFY voice_typing/daemon.py — ControlServer._handle
  - IMPLEMENT: remove the `if not line: continue` special case (or replace with an explicit
    {"ok": false, "error": "malformed JSON: empty request"} write+flush), so EVERY request line
    produces exactly one response line
  - ALSO: update the docstring/protocol comment near daemon.py:2363 ("malformed JSON -> ...")
    to mention empty lines, and drop the stale "# empty line -> skip (no response)" comment
  - PRESERVE: flush-per-reply, shutting_down break, OSError swallow, finally-close
  - NAMING/PLACEMENT: no new symbols

Task 2: MODIFY tests/test_control_socket.py — regression tests
  - IMPLEMENT (follow existing patterns in that file):
    - test_dispatch_empty_line: _disp("") -> ok False, error.startswith("malformed JSON:")
    - test_round_trip_empty_line_gets_error_reply(server): _send(path, b"\n") returns a JSON
      line with ok False; same for b"   \n"
    - (optional but cheap) test_round_trip_empty_line_mid_connection(server): _send_lines-style
      mixed valid/empty/valid over ONE connection -> 3 replies, first and third ok
  - PLACEMENT: next to the existing malformed-JSON tests (~line 178 dispatch section; ~line 203
    round-trip section)

Task 3: VALIDATE
  - Level 1 + 2 commands below; also grep the repo for other readers of the protocol
    (README.md §control socket, tests/ACCEPTANCE.md) and update prose ONLY where it explicitly
    claims empty lines get no response (none known — verify)
```

### Implementation Patterns & Key Details

```python
# After the fix, the loop body is simply:
for line in rfile:                      # one JSON object per line (PRD §4.2(3))
    line = line.strip()
    response = self._dispatch(line)     # "" -> ValueError -> malformed-JSON error reply
    wfile.write(json.dumps(response) + "\n")
    wfile.flush()
    if response.get("shutting_down"):
        break
# PATTERN: reuse the tested _dispatch error mapping; do not invent a second error path.
```

### Integration Points

```yaml
PROTOCOL:
  - daemon.py ControlServer docstring (~2351-2363): note that empty lines now get an error reply
DOCS:
  - README.md control-socket section: only if it documents the empty-line behavior (verify; likely silent)
NO config / IPC schema / state-file changes.
```

## Validation Loop

### Level 1: Syntax & Style (Immediate Feedback)

```bash
cd /home/dustin/projects/voice-typing
.venv/bin/ruff check voice_typing/daemon.py tests/test_control_socket.py --fix
.venv/bin/ruff format voice_typing/daemon.py tests/test_control_socket.py
# Expected: zero errors
```

### Level 2: Unit Tests (Component Validation)

```bash
timeout 120 .venv/bin/pytest tests/test_control_socket.py -q          # bash-tool timeout 200
timeout 300 .venv/bin/pytest tests/test_control_socket.py tests/test_voicectl.py -q
# Expected: all pass, including the new empty-line tests.
```

### Level 3: Integration (live socket, bounded — optional)

```bash
# Only if a daemon is already running under systemd; every probe under timeout:
printf '\n' | timeout 5 nc -U "$XDG_RUNTIME_DIR/voice-typing/control.sock"   # now replies with one JSON error line
printf '   \n' | timeout 5 nc -U "$XDG_RUNTIME_DIR/voice-typing/control.sock"
timeout 30 .venv/bin/voicectl status   # normal client unaffected
```

### Level 4: Domain-Specific Validation

```bash
timeout 120 .venv/bin/pytest tests/test_control_socket.py -k "empty" -v
```

## Final Validation Checklist

### Technical Validation
- [ ] Level 1 clean; `tests/test_control_socket.py` green; adjacent `test_voicectl.py` green
- [ ] Full fast suite unchanged: `timeout 600 .venv/bin/pytest tests/ -q --ignore=tests/test_feed_audio.py --ignore=tests/test_daemon.py --ignore=tests/test_recorder_host.py` (or the repo's usual fast-suite invocation)

### Feature Validation
- [ ] Empty and whitespace-only request lines each yield one `ok:false` malformed-JSON reply
- [ ] Valid requests, multi-line connections, and quit behavior unchanged
- [ ] Live `nc` probe (optional) confirms the hang is gone

### Code Quality Validation
- [ ] Reuses `_dispatch`'s existing error path; no duplicate error formatting
- [ ] Stale comment removed; protocol docstring updated

## Anti-Patterns to Avoid

- ❌ Don't write a reply without `wfile.flush()` — the client still hangs.
- ❌ Don't special-case empty lines into a NEW error shape distinct from malformed JSON (two shapes = two test matrices, no benefit).
- ❌ Don't touch `shutting_down`/OSError/finally paths.
- ❌ Don't probe the live socket without `timeout` (AGENTS.md).

---

**Confidence Score: 10/10** — the fix reuses an already-tested error path; the only work is deleting a special case plus tests that directly reproduce the reported hang with the repo's own `server` fixture and `_send` wire helper.
